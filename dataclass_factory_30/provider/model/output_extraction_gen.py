from collections import deque
from typing import Mapping, Dict, Callable

from . import VarBinder
from .definitions import OutputExtractionGen, OutputFigure, ExtraTargets, ExtraExtract
from ..definitions import SerializeError, AttrAccessor, ItemAccessor
from ..request_cls import OutputFieldRM
from ...code_tools import ContextNamespace, CodeBuilder, get_literal_repr
from ...common import Serializer


class BuiltinOutputExtractionGen(OutputExtractionGen):
    def __init__(self, figure: OutputFigure, debug_path: bool):
        self._figure = figure
        self._debug_path = debug_path
        self._extra_targets = (
            self._figure.extra.fields
            if isinstance(self._figure.extra, ExtraTargets)
            else ()
        )

    def generate_output_extraction(
        self,
        binder: VarBinder,
        ctx_namespace: ContextNamespace,
        field_serializers: Mapping[str, Serializer],
    ) -> CodeBuilder:
        builder = CodeBuilder()

        ctx_namespace.add("SerializeError", SerializeError)
        ctx_namespace.add("deque", deque)
        name_to_fields = {field.name: field for field in self._figure.fields}

        for field_name, serializer in field_serializers.items():
            ctx_namespace.add(self._serializer(name_to_fields[field_name]), serializer)

        for field in self._figure.fields:
            if not self._is_extra_target(field):
                self._gen_field_extraction(
                    builder, binder, ctx_namespace, field,
                    on_access_error="pass",
                    on_access_ok_req=lambda expr: f"{binder.field(field)} = {expr}",  # NOSONAR
                    on_access_ok_opt=lambda expr: f"{binder.opt_fields}[{field.name!r}] = {expr}",  # NOSONAR
                )

        self._gen_extra_extraction(
            builder, binder, ctx_namespace, name_to_fields,
        )

        return builder

    def _is_extra_target(self, field: OutputFieldRM) -> bool:
        return field.name in self._extra_targets

    def _serializer(self, field: OutputFieldRM) -> str:
        return f"serializer_{field.name}"

    def _raw_field(self, field: OutputFieldRM) -> str:
        return f"r_{field.name}"

    def _accessor_getter(self, field: OutputFieldRM) -> str:
        return f"accessor_getter_{field.name}"

    def _gen_access_expr(self, binder: VarBinder, ctx_namespace: ContextNamespace, field: OutputFieldRM) -> str:
        accessor = field.accessor
        if isinstance(accessor, AttrAccessor):
            return f"{binder.data}.{accessor.attr_name}"
        if isinstance(accessor, ItemAccessor):
            return f"{binder.data}[{accessor.item_name!r}]"

        accessor_getter = self._accessor_getter(field)
        ctx_namespace.add(accessor_getter, field.accessor.getter)
        return f"{accessor_getter}({binder.data})"

    def _get_path_element_var_name(self, field: OutputFieldRM) -> str:
        return f"path_element_{field.name}"

    def _gen_path_element_expr(self, ctx_namespace: ContextNamespace, field: OutputFieldRM) -> str:
        path_element = field.accessor.path_element
        literal_repr = get_literal_repr(path_element)
        if literal_repr is not None:
            return literal_repr

        pe_var_name = self._get_path_element_var_name(field)
        ctx_namespace.add(pe_var_name, path_element)
        return pe_var_name

    def _gen_required_field_extraction(
        self,
        builder: CodeBuilder,
        binder: VarBinder,
        ctx_namespace: ContextNamespace,
        field: OutputFieldRM,
        *,
        on_access_ok: Callable[[str], str],
    ):
        raw_access_expr = self._gen_access_expr(binder, ctx_namespace, field)
        path_element_expr = self._gen_path_element_expr(ctx_namespace, field)

        serializer = self._serializer(field)
        on_access_ok_stmt = on_access_ok(f"{serializer}({raw_access_expr})")

        if self._debug_path:
            builder += f"""
                try:
                    {on_access_ok_stmt}
                except SerializeError as e:
                    e.append_path({path_element_expr})
                    raise e
                except Exception as e:
                    raise SerializeError(deque([{path_element_expr}])) from e
            """
        else:
            builder += on_access_ok_stmt

        builder.empty_line()

    def _get_access_error_var_name(self, field: OutputFieldRM) -> str:
        return f"access_error_{field.name}"

    def _gen_optional_field_extraction(
        self,
        builder: CodeBuilder,
        binder: VarBinder,
        ctx_namespace: ContextNamespace,
        field: OutputFieldRM,
        *,
        on_access_error: str,
        on_access_ok: Callable[[str], str],
    ):
        raw_access_expr = self._gen_access_expr(binder, ctx_namespace, field)
        path_element_expr = self._gen_path_element_expr(ctx_namespace, field)

        serializer = self._serializer(field)
        raw_field = self._raw_field(field)

        on_access_ok_stmt = on_access_ok(f"{serializer}({raw_field})")

        access_error = field.accessor.access_error
        access_error_var = get_literal_repr(access_error)
        if access_error_var is None:
            access_error_var = self._get_access_error_var_name(field)
            ctx_namespace.add(access_error_var, access_error)

        if self._debug_path:
            builder += f"""
                try:
                    {raw_field} = {raw_access_expr}
                except {access_error_var}:
                    {on_access_error}
                else:
                    try:
                        {on_access_ok_stmt}
                    except SerializeError as e:
                        e.append_path({path_element_expr})
                        raise e
                    except Exception as e:
                        raise SerializeError(deque([{path_element_expr}])) from e
            """
        else:
            builder += f"""
                try:
                    {raw_field} = {raw_access_expr}
                except {field.accessor.access_error}:
                    {on_access_error}
                else:
                    {on_access_ok_stmt}
            """

        builder.empty_line()

    def _gen_field_extraction(
        self,
        builder: CodeBuilder,
        binder: VarBinder,
        ctx_namespace: ContextNamespace,
        field: OutputFieldRM,
        *,
        on_access_ok_req: Callable[[str], str],
        on_access_ok_opt: Callable[[str], str],
        on_access_error: str,
    ):
        if field.is_required:
            self._gen_required_field_extraction(
                builder, binder, ctx_namespace, field,
                on_access_ok=on_access_ok_req,
            )
        else:
            self._gen_optional_field_extraction(
                builder, binder, ctx_namespace, field,
                on_access_ok=on_access_ok_opt,
                on_access_error=on_access_error,
            )

    def _gen_extra_extraction(
        self,
        builder: CodeBuilder,
        binder: VarBinder,
        ctx_namespace: ContextNamespace,
        name_to_fields: Dict[str, OutputFieldRM],
    ):
        extra = self._figure.extra
        if isinstance(extra, ExtraTargets):
            self._gen_extra_target_extraction(builder, binder, ctx_namespace, name_to_fields)
        elif isinstance(extra, ExtraExtract):
            self._gen_extra_extract_extraction(builder, binder, ctx_namespace, extra)
        elif extra is not None:
            raise ValueError

    def _get_extra_stack_name(self):
        return "extra_stack"

    def _gen_extra_target_extraction(
        self,
        builder: CodeBuilder,
        binder: VarBinder,
        ctx_namespace: ContextNamespace,
        name_to_fields: Dict[str, OutputFieldRM],
    ):
        if len(self._extra_targets) == 1:
            field = name_to_fields[self._extra_targets[0]]

            self._gen_field_extraction(
                builder, binder, ctx_namespace, field,
                on_access_error=f"{binder.extra} = {{}}",
                on_access_ok_req=lambda expr: f"{binder.extra} = {expr}",
                on_access_ok_opt=lambda expr: f"{binder.extra} = {expr}",
            )

        elif all(field.is_required for field in name_to_fields.values()):
            for field_name in self._extra_targets:
                field = name_to_fields[field_name]

                self._gen_required_field_extraction(
                    builder, binder, ctx_namespace, field,
                    on_access_ok=lambda expr: f"{binder.field(field_name)} = {expr}",  # NOSONAR
                )

            builder += f'{binder.extra} = {{'
            builder <<= ", ".join("**" + binder.field(field_name) for field_name in self._extra_targets)
            builder <<= '}'
        else:
            extra_stack = self._get_extra_stack_name()

            builder += f"{extra_stack} = []"

            for field_name in self._extra_targets:
                field = name_to_fields[field_name]

                self._gen_field_extraction(
                    builder, binder, ctx_namespace, field,
                    on_access_ok_req=lambda expr: f"{extra_stack}.append({expr})",
                    on_access_ok_opt=lambda expr: f"{extra_stack}.append({expr})",
                    on_access_error="pass",
                )

            builder += f"""
                {binder.extra} = {{
                    key: value for extra_element in {extra_stack} for key, value in extra_element.items()
                }}
            """

    def _gen_extra_extract_extraction(
        self,
        builder: CodeBuilder,
        binder: VarBinder,
        ctx_namespace: ContextNamespace,
        extra: ExtraExtract,
    ):
        ctx_namespace.add('extractor', extra.func)

        builder += f"{binder.extra} = extractor({binder.data})"
        builder.empty_line()
