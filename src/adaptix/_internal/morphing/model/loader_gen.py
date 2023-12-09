import collections.abc
import contextlib
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Set

from ...code_tools.code_builder import CodeBuilder
from ...code_tools.context_namespace import ContextNamespace
from ...code_tools.utils import get_literal_expr, get_literal_from_factory
from ...common import Loader
from ...compat import CompatExceptionGroup
from ...definitions import DebugTrail
from ...load_error import (
    AggregateLoadError,
    ExcludedTypeLoadError,
    ExtraFieldsError,
    ExtraItemsError,
    LoadError,
    NoRequiredFieldsError,
    NoRequiredItemsError,
    TypeLoadError,
)
from ...model_tools.definitions import DefaultFactory, DefaultValue, InputField, InputShape, Param, ParamKind
from ...struct_trail import append_trail, extend_trail, render_trail_as_note
from .crown_definitions import (
    BranchInpCrown,
    CrownPath,
    CrownPathElem,
    ExtraCollect,
    ExtraForbid,
    ExtraKwargs,
    ExtraSaturate,
    ExtraTargets,
    InpCrown,
    InpDictCrown,
    InpFieldCrown,
    InpListCrown,
    InpNoneCrown,
    InputNameLayout,
)
from .definitions import CodeGenerator
from .special_cases_optimization import as_is_stub


class Namer:
    def __init__(
        self,
        debug_trail: DebugTrail,
        path_to_suffix: Mapping[CrownPath, str],
        path: CrownPath,
    ):
        self.debug_trail = debug_trail
        self.path_to_suffix = path_to_suffix
        self._path = path

    def _with_path_suffix(self, basis: str) -> str:
        if not self._path:
            return basis
        return basis + '_' + self.path_to_suffix[self._path]

    @property
    def path(self) -> CrownPath:
        return self._path

    @property
    def v_data(self) -> str:
        return self._with_path_suffix('data')

    @property
    def v_known_keys(self) -> str:
        return self._with_path_suffix('known_keys')

    @property
    def v_required_keys(self) -> str:
        return self._with_path_suffix('required_keys')

    @property
    def v_extra(self) -> str:
        return self._with_path_suffix('extra')

    @property
    def v_has_not_found_error(self) -> str:
        return self._with_path_suffix('has_not_found_error')

    def with_trail(self, error_expr: str) -> str:
        if self.debug_trail in (DebugTrail.FIRST, DebugTrail.ALL):
            if len(self._path) == 0:
                return error_expr
            if len(self._path) == 1:
                return f"append_trail({error_expr}, {self._path[0]!r})"
            return f"extend_trail({error_expr}, {self._path!r})"
        return error_expr

    def emit_error(self, error_expr: str) -> str:
        if self.debug_trail == DebugTrail.ALL:
            return f"errors.append({self.with_trail(error_expr)})"
        return f"raise {self.with_trail(error_expr)}"


class GenState(Namer):
    path_to_suffix: Dict[CrownPath, str]

    def __init__(
        self,
        builder: CodeBuilder,
        ctx_namespace: ContextNamespace,
        name_to_field: Dict[str, InputField],
        debug_trail: DebugTrail,
        root_crown: InpCrown,
    ):
        self.builder = builder
        self.ctx_namespace = ctx_namespace
        self._name_to_field = name_to_field

        self.field_id_to_path: Dict[str, CrownPath] = {}

        self._last_path_idx = 0
        self._parent_path: Optional[CrownPath] = None
        self._crown_stack: List[InpCrown] = [root_crown]

        self.type_checked_type_paths: Set[CrownPath] = set()
        super().__init__(debug_trail=debug_trail, path_to_suffix={}, path=())

    @property
    def parent(self) -> Namer:
        return Namer(self.debug_trail, self.path_to_suffix, self.parent_path)

    def v_field_loader(self, field_id: str) -> str:
        return f"loader_{field_id}"

    def v_raw_field(self, field: InputField) -> str:
        return f"r_{field.id}"

    def v_field(self, field: InputField) -> str:
        return f"f_{field.id}"

    @property
    def parent_path(self) -> CrownPath:
        if self._parent_path is None:
            raise ValueError
        return self._parent_path

    @property
    def parent_crown(self) -> BranchInpCrown:
        return self._crown_stack[-2]  # type: ignore[return-value]

    @contextlib.contextmanager
    def add_key(self, crown: InpCrown, key: CrownPathElem):
        past = self._path
        past_parent = self._parent_path

        self._parent_path = self._path
        self._path += (key,)
        self._crown_stack.append(crown)
        self._last_path_idx += 1
        self.path_to_suffix[self._path] = str(self._last_path_idx)
        yield
        self._crown_stack.pop(-1)
        self._path = past
        self._parent_path = past_parent

    def get_field(self, crown: InpFieldCrown) -> InputField:
        self.field_id_to_path[crown.id] = self._path
        return self._name_to_field[crown.id]


@dataclass
class ModelLoaderProps:
    use_default_for_omitted: bool = True


class ModelLoaderGen(CodeGenerator):
    """ModelLoaderGen generates code that extracts raw values from input data,
    calls loaders and stores results to variables.
    """

    def __init__(
        self,
        shape: InputShape,
        name_layout: InputNameLayout,
        debug_trail: DebugTrail,
        strict_coercion: bool,
        field_loaders: Mapping[str, Loader],
        model_identity: str,
        props: ModelLoaderProps,
    ):
        self._shape = shape
        self._name_layout = name_layout
        self._debug_trail = debug_trail
        self._strict_coercion = strict_coercion
        self._id_to_field: Dict[str, InputField] = {
            field.id: field for field in self._shape.fields
        }
        self._field_id_to_param: Dict[str, Param] = {
            param.field_id: param for param in self._shape.params
        }
        self._field_loaders = field_loaders
        self._model_identity = model_identity
        self._props = props

    @property
    def _can_collect_extra(self) -> bool:
        return self._name_layout.extra_move is not None

    def _is_extra_target(self, field: InputField) -> bool:
        return (
            isinstance(self._name_layout.extra_move, ExtraTargets)
            and
            field.id in self._name_layout.extra_move.fields
        )

    def _create_state(self, ctx_namespace: ContextNamespace) -> GenState:
        return GenState(
            builder=CodeBuilder(),
            ctx_namespace=ctx_namespace,
            name_to_field=self._id_to_field,
            debug_trail=self._debug_trail,
            root_crown=self._name_layout.crown,
        )

    @property
    def has_packed_fields(self):
        return any(self._is_packed_field(fld) for fld in self._shape.fields)

    def _is_packed_field(self, field: InputField) -> bool:
        if self._props.use_default_for_omitted and isinstance(field.default, (DefaultValue, DefaultFactory)):
            return False
        return field.is_optional and not self._is_extra_target(field)

    def produce_code(self, ctx_namespace: ContextNamespace) -> CodeBuilder:
        state = self._create_state(ctx_namespace)

        for field_id, loader in self._field_loaders.items():
            state.ctx_namespace.add(state.v_field_loader(field_id), loader)

        for named_value in (
            append_trail, extend_trail, render_trail_as_note,
            ExtraFieldsError, ExtraItemsError,
            NoRequiredFieldsError, NoRequiredItemsError,
            TypeLoadError, ExcludedTypeLoadError,
            LoadError, AggregateLoadError,
        ):
            state.ctx_namespace.add(named_value.__name__, named_value)  # type: ignore[attr-defined]

        state.ctx_namespace.add('CompatExceptionGroup', CompatExceptionGroup)
        state.ctx_namespace.add('CollectionsMapping', collections.abc.Mapping)
        state.ctx_namespace.add('CollectionsSequence', collections.abc.Sequence)
        state.ctx_namespace.add('sentinel', object())

        if self._debug_trail == DebugTrail.ALL:
            state.builder += "errors = []"
            state.builder += "has_unexpected_error = False"
            state.ctx_namespace.add('model_identity', self._model_identity)

        if self.has_packed_fields:
            state.builder += "packed_fields = {}"

        if not self._gen_root_crown_dispatch(state, self._name_layout.crown):
            raise TypeError

        self._gen_extra_targets_assigment(state)

        if self._debug_trail == DebugTrail.ALL:
            state.builder(
                """
                if errors:
                    if has_unexpected_error:
                        raise CompatExceptionGroup(
                            f'while loading model {model_identity}',
                            [render_trail_as_note(e) for e in errors],
                        )
                    raise AggregateLoadError(
                        f'while loading model {model_identity}',
                        [render_trail_as_note(e) for e in errors],
                    )
                """
            )
            state.builder.empty_line()

        self._gen_constructor_call(state)
        self._gen_header(state)
        return state.builder

    def _gen_header(self, state: GenState):
        header_builder = CodeBuilder()
        if state.path_to_suffix:
            header_builder += "# suffix to path"
            for path, suffix in state.path_to_suffix.items():
                header_builder += f"# {suffix} -> {list(path)}"

            header_builder.empty_line()

        if state.field_id_to_path:
            header_builder += "# field to path"
            for f_name, path in state.field_id_to_path.items():
                header_builder += f"# {f_name} -> {list(path)}"

            header_builder.empty_line()

        state.builder.extend_above(header_builder)

    def _gen_constructor_call(self, state: GenState) -> None:
        state.ctx_namespace.add('constructor', self._shape.constructor)

        constructor_builder = CodeBuilder()
        with constructor_builder("constructor("):
            for param in self._shape.params:
                field = self._shape.fields_dict[param.field_id]

                if not self._is_packed_field(field):
                    value = state.v_field(field)
                else:
                    continue

                if param.kind == ParamKind.KW_ONLY:
                    constructor_builder(f"{param.name}={value},")
                else:
                    constructor_builder(f"{value},")

            if self.has_packed_fields:
                constructor_builder("**packed_fields,")

            if self._name_layout.extra_move == ExtraKwargs():
                constructor_builder(f"**{state.v_extra},")

        constructor_builder += ")"

        if isinstance(self._name_layout.extra_move, ExtraSaturate):
            state.ctx_namespace.add('saturator', self._name_layout.extra_move.func)
            state.builder += "result = "
            state.builder.extend_including(constructor_builder)
            state.builder += f"saturator(result, {state.v_extra})"
            state.builder += "return result"
        else:
            state.builder += "return "
            state.builder.extend_including(constructor_builder)

    def _gen_root_crown_dispatch(self, state: GenState, crown: InpCrown) -> bool:
        """Returns True if code is generated"""
        if isinstance(crown, InpDictCrown):
            self._gen_dict_crown(state, crown)
        elif isinstance(crown, InpListCrown):
            self._gen_list_crown(state, crown)
        else:
            return False
        return True

    def _gen_crown_dispatch(self, state: GenState, sub_crown: InpCrown, key: CrownPathElem):
        with state.add_key(sub_crown, key):
            if self._gen_root_crown_dispatch(state, sub_crown):
                return
            if isinstance(sub_crown, InpFieldCrown):
                self._gen_field_crown(state, sub_crown)
                return
            if isinstance(sub_crown, InpNoneCrown):
                self._gen_none_crown(state, sub_crown)
                return

            raise TypeError

    def _gen_raise_bad_type_error(
        self,
        state: GenState,
        bad_type_load_error: str,
        namer: Optional[Namer] = None,
    ) -> None:
        if namer is None:
            namer = state

        if not namer.path and self._debug_trail == DebugTrail.ALL:
            state.builder(
                f"""
                raise AggregateLoadError(
                    f'while loading model {{model_identity}}',
                    [render_trail_as_note({namer.with_trail(bad_type_load_error)})],
                )
                """
            )
        else:
            state.builder(
                f'raise {namer.with_trail(bad_type_load_error)}'
            )

    def _gen_assigment_from_parent_data(
        self,
        state: GenState,
        *,
        assign_to: str,
        on_lookup_error: Optional[str] = None,
    ):
        last_path_el = state.path[-1]
        if isinstance(last_path_el, str):
            lookup_error = 'KeyError'
            bad_type_error = '(TypeError, IndexError)'
            bad_type_load_error = f'TypeLoadError(CollectionsMapping, {state.parent.v_data})'
            not_found_error = (
                "NoRequiredFieldsError("
                f"{state.parent.v_required_keys} - set({state.parent.v_data}), {state.parent.v_data}"
                ")"
            )
        else:
            lookup_error = 'IndexError'
            bad_type_error = '(TypeError, KeyError)'
            bad_type_load_error = f'TypeLoadError(CollectionsSequence, {state.parent.v_data})'
            not_found_error = f"NoRequiredItemsError({len(state.parent_crown.map)}, {state.parent.v_data})"

        with state.builder(
            f"""
                try:
                    {assign_to} = {state.parent.v_data}[{last_path_el!r}]
                except {lookup_error}:
            """,
        ):
            if on_lookup_error is not None:
                state.builder += on_lookup_error
            elif self._debug_trail != DebugTrail.ALL:
                state.builder += f"raise {state.parent.with_trail(not_found_error)}"
            else:
                if isinstance(state.path[-1], str):
                    state.builder += f"""
                        if not {state.parent.v_has_not_found_error}:
                            errors.append({state.parent.with_trail(not_found_error)})
                            {state.parent.v_has_not_found_error} = True
                    """
                else:
                    state.builder += 'pass'

        if state.parent_path not in state.type_checked_type_paths:
            with state.builder(f'except {bad_type_error}:'):
                self._gen_raise_bad_type_error(state, bad_type_load_error, namer=state.parent)
            state.type_checked_type_paths.add(state.parent_path)

        self._gen_unexpected_exc_catching(state)

    def _gen_unexpected_exc_catching(self, state: GenState):
        if self._debug_trail == DebugTrail.FIRST:
            state.builder(
                f"""
                except Exception as e:
                    {state.with_trail('e')}
                    raise
                """
            )
        elif self._debug_trail == DebugTrail.ALL:
            state.builder(
                f"""
                except Exception as e:
                    errors.append({state.with_trail('e')})
                    has_unexpected_error = True
                """
            )

    def _gen_add_self_extra_to_parent_extra(self, state: GenState):
        if not state.path:
            return

        state.builder(f"{state.parent.v_extra}[{state.path[-1]!r}] = {state.v_extra}")
        state.builder.empty_line()

    @contextlib.contextmanager
    def _maybe_wrap_with_type_load_error_catching(self, state: GenState):
        if self._debug_trail != DebugTrail.ALL or not state.path:
            yield
            return

        with state.builder('try:'):
            yield
        state.builder(
            """
            except TypeLoadError as e:
                errors.append(e)
            """
        )
        state.builder.empty_line()

    def _get_dict_crown_required_keys(self, crown: InpDictCrown) -> Set[str]:
        return {
            key for key, value in crown.map.items()
            if not (isinstance(value, InpFieldCrown) and self._id_to_field[value.id].is_optional)
        }

    def _gen_dict_crown(self, state: GenState, crown: InpDictCrown):
        state.ctx_namespace.add(state.v_known_keys, set(crown.map.keys()))
        state.ctx_namespace.add(state.v_required_keys, self._get_dict_crown_required_keys(crown))

        if state.path:
            self._gen_assigment_from_parent_data(state, assign_to=state.v_data)
            state.builder.empty_line()

        if self._can_collect_extra:
            state.builder += f"{state.v_extra} = {{}}"
        if self._debug_trail == DebugTrail.ALL:
            state.builder += f"{state.v_has_not_found_error} = False"

        with self._maybe_wrap_with_type_load_error_catching(state):
            for key, value in crown.map.items():
                self._gen_crown_dispatch(state, value, key)

            if state.path not in state.type_checked_type_paths:
                with state.builder(f'if not isinstance({state.v_data}, CollectionsMapping):'):
                    self._gen_raise_bad_type_error(state, f'TypeLoadError(CollectionsMapping, {state.v_data})')
                state.builder.empty_line()
                state.type_checked_type_paths.add(state.path)

            if crown.extra_policy == ExtraForbid():
                state.builder += f"""
                    {state.v_extra}_set = set({state.v_data}) - {state.v_known_keys}
                    if {state.v_extra}_set:
                        {state.emit_error(f"ExtraFieldsError({state.v_extra}_set, {state.v_data})")}
                """
                state.builder.empty_line()
            elif crown.extra_policy == ExtraCollect():
                state.builder += f"""
                    for key in set({state.v_data}) - {state.v_known_keys}:
                        {state.v_extra}[key] = {state.v_data}[key]
                """
                state.builder.empty_line()

        if self._can_collect_extra:
            self._gen_add_self_extra_to_parent_extra(state)

    def _gen_forbidden_sequence_check(self, state: GenState) -> None:
        with state.builder(f'if type({state.v_data}) is str:'):
            self._gen_raise_bad_type_error(state, f'ExcludedTypeLoadError(CollectionsSequence, str, {state.v_data})')

    def _gen_list_crown(self, state: GenState, crown: InpListCrown):
        if state.path:
            self._gen_assigment_from_parent_data(state, assign_to=state.v_data)
            state.builder.empty_line()

        if self._can_collect_extra:
            list_literal: list = [
                {} if isinstance(sub_crown, (InpFieldCrown, InpNoneCrown)) else None
                for sub_crown in crown.map
            ]
            state.builder(f"{state.v_extra} = {list_literal!r}")

        with self._maybe_wrap_with_type_load_error_catching(state):
            if self._strict_coercion:
                self._gen_forbidden_sequence_check(state)

            for key, value in enumerate(crown.map):
                self._gen_crown_dispatch(state, value, key)

            if state.path not in state.type_checked_type_paths:
                with state.builder(f'if not isinstance({state.v_data}, CollectionsSequence):'):
                    self._gen_raise_bad_type_error(state, f'TypeLoadError(CollectionsSequence, {state.v_data})')
                state.builder.empty_line()
                state.type_checked_type_paths.add(state.path)

            expected_len = len(crown.map)
            if crown.extra_policy == ExtraForbid():
                state.builder += f"""
                    if len({state.v_data}) != {expected_len}:
                        if len({state.v_data}) < {expected_len}:
                            {state.emit_error(f"NoRequiredItemsError({expected_len}, {state.v_data})")}
                        else:
                            {state.emit_error(f"ExtraItemsError({expected_len}, {state.v_data})")}
                """
            else:
                state.builder += f"""
                    if len({state.v_data}) < {expected_len}:
                        {state.emit_error(f"NoRequiredItemsError({expected_len}, {state.v_data})")}
                """

        if self._can_collect_extra:
            self._gen_add_self_extra_to_parent_extra(state)

    def _get_default_clause_expr(self, state: GenState, field: InputField) -> str:
        if isinstance(field.default, DefaultValue):
            literal_expr = get_literal_expr(field.default.value)
            if literal_expr is not None:
                return literal_expr
            state.ctx_namespace.add(f'dfl_{field.id}', field.default.value)
            return f'dfl_{field.id}'
        if isinstance(field.default, DefaultFactory):
            literal_expr = get_literal_from_factory(field.default.factory)
            if literal_expr is not None:
                return literal_expr
            state.ctx_namespace.add(f'dfl_{field.id}', field.default.factory)
            return f'dfl_{field.id}()'
        raise ValueError

    def _gen_field_crown(self, state: GenState, crown: InpFieldCrown):
        field = state.get_field(crown)
        if field.is_required:
            self._gen_assigment_from_parent_data(
                state=state,
                assign_to=state.v_raw_field(field),
            )
            with state.builder('else:'):
                self._gen_field_assigment(
                    assign_to=state.v_field(field),
                    field_id=field.id,
                    loader_arg=state.v_raw_field(field),
                    state=state,
                )
        else:
            if self._is_packed_field(field):
                param_name = self._field_id_to_param[field.id].name
                assign_to = f"packed_fields[{param_name!r}]"
                on_lookup_error = 'pass'
            else:
                assign_to = state.v_field(field)
                on_lookup_error = f'{state.v_field(field)} = {self._get_default_clause_expr(state, field)}'

            if isinstance(state.path[-1], int):
                self._gen_assigment_from_parent_data(
                    state=state,
                    assign_to=state.v_raw_field(field),
                    on_lookup_error=on_lookup_error,
                )
                with state.builder('else:'):
                    self._gen_field_assigment(
                        assign_to=assign_to,
                        field_id=field.id,
                        loader_arg=state.v_raw_field(field),
                        state=state,
                    )
            else:
                self._gen_optional_field_extraction_from_mapping(
                    state=state,
                    field=field,
                    assign_to=assign_to,
                    on_lookup_error=on_lookup_error,
                )

        state.builder.empty_line()

    def _gen_optional_field_extraction_from_mapping(
        self,
        state: GenState,
        *,
        field: InputField,
        assign_to: str,
        on_lookup_error: str,
    ):
        if state.parent_path in state.type_checked_type_paths:
            with state.builder(f"if {state.path[-1]!r} in {state.parent.v_data}:"):
                self._gen_field_assigment(
                    assign_to=assign_to,
                    field_id=field.id,
                    loader_arg=f'{state.parent.v_data}[{state.path[-1]!r}]',
                    state=state,
                )
            state.builder(
                f"""
                else:
                    {on_lookup_error}
                """
            )
            return

        with state.builder(
            f"""
            try:
                getter = {state.parent.v_data}.get
            except AttributeError:
            """
        ):
            self._gen_raise_bad_type_error(
                state,
                f'TypeLoadError(CollectionsMapping, {state.parent.v_data})',
                namer=state.parent,
            )
            state.type_checked_type_paths.add(state.parent_path)

        self._gen_unexpected_exc_catching(state)
        with state.builder("else:"):
            state.builder(
                f"""
                try:
                    value = getter({state.path[-1]!r}, sentinel)
                """
            )
            self._gen_unexpected_exc_catching(state)
            with state.builder("else:"):
                with state.builder(
                    f"""
                    if value is sentinel:
                        {on_lookup_error}
                    else:
                    """
                ):
                    self._gen_field_assigment(
                        assign_to=assign_to,
                        field_id=field.id,
                        loader_arg='value',
                        state=state,
                    )

    def _gen_field_assigment(
        self,
        assign_to: str,
        field_id: str,
        loader_arg: str,
        state: GenState,
    ):
        if self._field_loaders[field_id] == as_is_stub:
            processing_expr = loader_arg
        else:
            field_loader = state.v_field_loader(field_id)
            processing_expr = f'{field_loader}({loader_arg})'

        if self._debug_trail in (DebugTrail.ALL, DebugTrail.FIRST):
            state.builder(
                f"""
                try:
                    {assign_to} = {processing_expr}
                except Exception as e:
                    {state.emit_error('e')}
                """
            )
        else:
            state.builder(
                f"{assign_to} = {processing_expr}"
            )

    def _gen_extra_targets_assigment(self, state: GenState):
        # Saturate extra targets with data.
        # If extra data is not collected, loader of the required field will get empty dict
        extra_move = self._name_layout.extra_move

        if not isinstance(extra_move, ExtraTargets):
            return

        if self._name_layout.crown.extra_policy == ExtraCollect():
            for target in extra_move.fields:
                field = self._id_to_field[target]

                self._gen_field_assigment(
                    assign_to=state.v_field(field),
                    field_id=target,
                    loader_arg=state.v_extra,
                    state=state,
                )
        else:
            for target in extra_move.fields:
                field = self._id_to_field[target]
                if field.is_required:
                    self._gen_field_assigment(
                        assign_to=state.v_field(field),
                        field_id=target,
                        loader_arg="{}",
                        state=state,
                    )

        state.builder.empty_line()

    def _gen_none_crown(self, state: GenState, crown: InpNoneCrown):
        pass