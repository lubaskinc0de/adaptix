import contextlib
from copy import copy
from typing import Dict, Mapping, Optional, Set

from ...code_tools import CodeBuilder, ContextNamespace
from ...common import Parser
from ...model_tools import ExtraTargets, InputField, InputFigure
from ...provider.definitions import (
    ExtraFieldsError,
    ExtraItemsError,
    NoRequiredFieldsError,
    NoRequiredItemsError,
    ParseError,
    TypeParseError,
)
from ...struct_path import append_path, extend_path
from .crown_definitions import (
    CrownPath,
    CrownPathElem,
    ExtraCollect,
    ExtraForbid,
    ExtraSkip,
    InpCrown,
    InpDictCrown,
    InpFieldCrown,
    InpListCrown,
    InpNoneCrown,
    RootInpCrown,
)
from .definitions import CodeGenerator, VarBinder


class GenState:
    KNOWN_FIELDS = 'known_fields'

    def __init__(self, binder: VarBinder, ctx_namespace: ContextNamespace, name_to_field: Dict[str, InputField]):
        self.binder = binder
        self.ctx_namespace = ctx_namespace
        self._name_to_field = name_to_field

        self.field_name2path: Dict[str, CrownPath] = {}
        self.path2suffix: Dict[CrownPath, str] = {}
        self.path2known_fields: Dict[CrownPath, Set[str]] = {}

        self._last_path_idx = 0
        self._path: CrownPath = ()
        self._parent_path: Optional[CrownPath] = None

    def _get_path_idx(self, path: CrownPath) -> str:
        try:
            return self.path2suffix[path]
        except KeyError:
            self._last_path_idx += 1
            suffix = str(self._last_path_idx)
            self.path2suffix[path] = suffix
            return suffix

    def get_data_var_name(self) -> str:
        if not self._path:
            return self.binder.data
        return self.binder.data + '_' + self._get_path_idx(self._path)

    def get_known_fields_var_name(self) -> str:
        if not self._path:
            return self.KNOWN_FIELDS

        return self.KNOWN_FIELDS + '_' + self._get_path_idx(self._path)

    def get_extra_var_name(self) -> str:
        if not self._path:
            return self.binder.extra

        return self.binder.extra + '_' + self._get_path_idx(self._path)

    def field_parser(self, field_name: str) -> str:
        return f"parser_{field_name}"

    def raw_field(self, field: InputField) -> str:
        return f"r_{field.name}"

    @property
    def path(self):
        return self._path

    @contextlib.contextmanager
    def add_key(self, key: CrownPathElem):
        past = self._path
        past_parent = self._parent_path

        self._parent_path = self._path
        self._path += (key,)
        yield
        self._path = past
        self._parent_path = past_parent

    def get_field(self, crown: InpFieldCrown) -> InputField:
        self.field_name2path[crown.name] = self._path
        return self._name_to_field[crown.name]

    def with_parent_path(self) -> "GenState":
        # pylint: disable=protected-access
        if self._parent_path is None:
            raise ValueError

        cp = copy(self)
        cp._path = self._parent_path
        cp._parent_path = None
        return cp


class BuiltinInputExtractionGen(CodeGenerator):
    """BuiltinInputExtractionGen generates code that extracts raw values from input data,
    calls parsers and stores results at variables.
    """

    def __init__(
        self,
        figure: InputFigure,
        crown: RootInpCrown,
        debug_path: bool,
        field_parsers: Mapping[str, Parser],
    ):
        self._figure = figure
        self._root_crown = crown
        self._debug_path = debug_path
        self._name_to_field: Dict[str, InputField] = {
            field.name: field for field in self._figure.fields
        }
        self._field_parsers = field_parsers

    @property
    def _can_collect_extra(self) -> bool:
        return self._figure.extra is not None

    def _is_extra_target(self, field: InputField):
        return (
            isinstance(self._figure.extra, ExtraTargets)
            and
            field.name in self._figure.extra.fields
        )

    def _create_state(self, binder: VarBinder, ctx_namespace: ContextNamespace) -> GenState:
        return GenState(binder, ctx_namespace, self._name_to_field)

    def __call__(self, binder: VarBinder, ctx_namespace: ContextNamespace) -> CodeBuilder:
        for exception in [
            ExtraFieldsError, ExtraItemsError,
            NoRequiredFieldsError, NoRequiredItemsError,
            TypeParseError, ParseError,
        ]:
            ctx_namespace.add(exception.__name__, exception)

        ctx_namespace.add("append_path", append_path)
        ctx_namespace.add("extend_path", extend_path)

        crown_builder = CodeBuilder()
        state = self._create_state(binder, ctx_namespace)

        for field_name, parser in self._field_parsers.items():
            state.ctx_namespace.add(state.field_parser(field_name), parser)

        if not self._gen_root_crown_dispatch(crown_builder, state, self._root_crown):
            raise TypeError

        builder = CodeBuilder()
        self._gen_header(builder, state)

        has_opt_fields = any(
            fld.is_optional and not self._is_extra_target(fld)
            for fld in self._figure.fields
        )

        if has_opt_fields:
            builder += f"{binder.opt_fields} = {{}}"

        builder.extend(crown_builder)

        self._gen_extra_targets_assigment(builder, state)

        return builder

    def _gen_header(self, builder: CodeBuilder, state: GenState):
        if state.path2suffix:
            builder += "# suffix to path"
            for path, suffix in state.path2suffix.items():
                builder += f"# {suffix} -> {list(path)}"

            builder.empty_line()

        if state.field_name2path:
            builder += "# field to path"
            for f_name, path in state.field_name2path.items():
                builder += f"# {f_name} -> {list(path)}"

            builder.empty_line()

    def _gen_root_crown_dispatch(self, builder: CodeBuilder, state: GenState, crown: InpCrown):
        """Returns True if code is generated"""
        if isinstance(crown, InpDictCrown):
            self._gen_dict_crown(builder, state, crown)
        elif isinstance(crown, InpListCrown):
            self._gen_list_crown(builder, state, crown)
        else:
            return False
        return True

    def _gen_crown_dispatch(self, builder: CodeBuilder, state: GenState, sub_crown: InpCrown, key: CrownPathElem):
        with state.add_key(key):
            if self._gen_root_crown_dispatch(builder, state, sub_crown):
                return
            if isinstance(sub_crown, InpFieldCrown):
                self._gen_field_crown(builder, state, sub_crown)
                return
            if isinstance(sub_crown, InpNoneCrown):
                self._gen_none_crown(builder, state, sub_crown)
                return

            raise TypeError

    def _wrap_error(self, error_expr: str, path: CrownPath) -> str:
        if self._debug_path:
            if len(path) == 0:
                return error_expr
            if len(path) == 1:
                return f"append_path({error_expr}, {path[0]!r})"
            return f"extend_path({error_expr}, {path!r})"
        return error_expr

    def _gen_var_assigment_from_data(
        self,
        builder: CodeBuilder,
        state: GenState,
        *,
        assign_to: str,
        ignore_lookup_error=False
    ):
        last_path_el = state.path[-1]
        parent_state = state.with_parent_path()
        data = parent_state.get_data_var_name()

        if isinstance(last_path_el, str):
            if ignore_lookup_error:
                on_error = "pass"
            else:
                error_expr = f"NoRequiredFieldsError([{last_path_el!r}])"
                on_error = "raise " + self._wrap_error(error_expr, parent_state.path)

            builder(
                f"""
                try:
                    {assign_to} = {data}[{last_path_el!r}]
                except KeyError:
                    {on_error}
                """,
            )
        else:
            builder(f"{assign_to} = {data}[{last_path_el!r}]")

    def _add_self_extra_to_parent_extra(self, builder: CodeBuilder, state: GenState):
        if not state.path:
            return

        extra = state.get_extra_var_name()
        parent_extra = state.with_parent_path().get_extra_var_name()
        builder(f"{parent_extra}[{state.path[-1]!r}] = {extra}")

    def _gen_dict_crown(self, builder: CodeBuilder, state: GenState, crown: InpDictCrown):
        known_fields = state.get_known_fields_var_name()

        if crown.extra in (ExtraForbid(), ExtraCollect()):
            state.ctx_namespace.add(known_fields, set(crown.map.keys()))

        data = state.get_data_var_name()
        extra = state.get_extra_var_name()

        if state.path:
            self._gen_var_assigment_from_data(
                builder, state, assign_to=state.get_data_var_name(),
            )
            builder.empty_line()

        builder += f"""
            if not isinstance({data}, dict):
                raise {self._wrap_error("TypeParseError(dict)", state.path)}
        """

        builder.empty_line()

        if crown.extra == ExtraForbid():
            error_expr = self._wrap_error(f"ExtraFieldsError({extra}_set)", state.path)
            builder += f"""
                {extra}_set = set({data}) - {known_fields}
                if {extra}_set:
                    raise {error_expr}
            """
            builder.empty_line()

        elif crown.extra == ExtraCollect():
            builder += f"""
                {extra} = {{}}
                for key in set({data}) - {known_fields}:
                    {extra}[key] = {data}[key]
            """
            builder.empty_line()

        if self._can_collect_extra:
            if crown.extra in (ExtraSkip(), ExtraForbid()):
                builder(f"{extra} = {{}}")

            self._add_self_extra_to_parent_extra(builder, state)

        for key, value in crown.map.items():
            self._gen_crown_dispatch(builder, state, value, key)

    def _gen_list_crown(self, builder: CodeBuilder, state: GenState, crown: InpListCrown):
        data = state.get_data_var_name()
        list_len = len(crown.map)

        if state.path:
            self._gen_var_assigment_from_data(
                builder, state, assign_to=state.get_data_var_name(),
            )
            builder.empty_line()

        no_required_items_error = self._wrap_error(f"NoRequiredItemsError({list_len})", state.path)

        if crown.extra == ExtraForbid():
            on_extra_items = "raise " + self._wrap_error(f"ExtraItemsError({list_len})", state.path)
        else:
            on_extra_items = ""

        builder += f"""
            if not isinstance({data}, list):
                raise {self._wrap_error("TypeParseError(list)", state.path)}

            if len({data}) != {list_len}:
                if len({data}) < {list_len}:
                    raise {no_required_items_error}
                {on_extra_items}
        """

        if self._can_collect_extra:
            extra = state.get_extra_var_name()
            list_literal: list = [
                {} if isinstance(sub_crown, (InpFieldCrown, InpNoneCrown)) else None
                for sub_crown in crown.map
            ]
            builder(f"{extra} = {list_literal!r}")

        for key, value in enumerate(crown.map):
            self._gen_crown_dispatch(builder, state, value, key)

        if self._can_collect_extra:
            self._add_self_extra_to_parent_extra(builder, state)

    def _gen_field_crown(self, builder: CodeBuilder, state: GenState, crown: InpFieldCrown):
        field = state.get_field(crown)

        if field.is_required:
            field_left_value = state.binder.field(field)
        else:
            field_left_value = f"{state.binder.opt_fields}[{field.name!r}]"

        self._gen_var_assigment_from_data(
            builder,
            state,
            assign_to=state.raw_field(field),
            ignore_lookup_error=field.is_optional,
        )
        data_for_parser = state.raw_field(field)

        if field.is_required:
            builder.empty_line()
            self._gen_field_assigment(
                builder,
                field_left_value,
                field.name,
                data_for_parser,
                state,
            )
        else:
            with builder("else:"):
                self._gen_field_assigment(
                    builder,
                    field_left_value,
                    field.name,
                    data_for_parser,
                    state,
                )

        builder.empty_line()

    def _gen_field_assigment(
        self,
        builder: CodeBuilder,
        field_left_value: str,
        field_name: str,
        data_for_parser: str,
        state: GenState,
    ):
        field_parser = state.field_parser(field_name)

        if self._debug_path and state.path:
            builder(
                f"""
                try:
                    {field_left_value} = {field_parser}({data_for_parser})
                except Exception as e:
                    raise {self._wrap_error('e', state.path)}
                """
            )
        else:
            builder(
                f"{field_left_value} = {field_parser}({data_for_parser})"
            )

    def _gen_extra_targets_assigment(self, builder: CodeBuilder, state: GenState):
        # Saturate extra targets with data.
        # If extra data is not collected, parser of required field will get empty dict
        if not isinstance(self._figure.extra, ExtraTargets):
            return

        if self._root_crown.extra == ExtraCollect():
            for target in self._figure.extra.fields:
                field = self._name_to_field[target]

                self._gen_field_assigment(
                    builder,
                    field_left_value=state.binder.field(field),
                    field_name=target,
                    data_for_parser=state.get_extra_var_name(),
                    state=state,
                )
        else:
            for target in self._figure.extra.fields:
                field = self._name_to_field[target]

                if field.is_required:
                    self._gen_field_assigment(
                        builder,
                        field_left_value=state.binder.field(field),
                        field_name=target,
                        data_for_parser="{}",
                        state=state,
                    )

        builder.empty_line()

    def _gen_none_crown(self, builder: CodeBuilder, state: GenState, crown: InpNoneCrown):
        pass