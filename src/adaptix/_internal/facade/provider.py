from __future__ import annotations

import re
from enum import Enum, EnumMeta
from types import MappingProxyType
from typing import Any, Callable, Iterable, List, Mapping, Optional, Sequence, Tuple, TypeVar, Union

from ..common import Catchable, Dumper, Loader, TypeHint, VarTuple
from ..model_tools import Default, DescriptorAccessor, NoDefault, OutputField, get_callable_figure
from ..provider import (
    BoundingProvider,
    Chain,
    ChainingProvider,
    DumperRequest,
    EnumExactValueProvider,
    EnumNameProvider,
    EnumValueProvider,
    LoaderRequest,
    LoadError,
    ModelLoaderProvider,
    NameSanitizer,
    NameStyle,
    OrRequestChecker,
    PropertyAdder,
    Provider,
    ValidationError,
    ValueProvider,
    create_request_checker,
)
from ..provider.model.loader_provider import InlinedInputExtractionMaker, make_input_creation
from ..provider.name_layout.base import ExtraIn, ExtraOut
from ..provider.name_layout.component import (
    ExtraMoveAndPoliciesOverlay,
    NameMapStack,
    RawKey,
    RawPath,
    SievesOverlay,
    StructureOverlay,
)
from ..provider.overlay_schema import OverlayProvider
from ..provider.request_filtering import RequestPattern
from ..utils import Omittable, Omitted

T = TypeVar('T')


def bound(pred: Any, provider: Provider) -> Provider:
    if pred == Omitted():
        return provider
    return BoundingProvider(create_request_checker(pred), provider)


def make_chain(chain: Optional[Chain], provider: Provider) -> Provider:
    if chain is None:
        return provider

    return ChainingProvider(chain, provider)


def loader(pred: Any, func: Loader, chain: Optional[Chain] = None) -> Provider:
    """Basic provider to define custom loader.

    :param pred: Predicate specifying where loader should be used. See :ref:`predicate-system` for details.
    :param func: Function that acts as loader.
        It must take one positional argument of raw data and return the processed value.
    :param chain: Controls how the function will interact with the previous loader.

        When ``None`` is passed, the specified function will fully replace the previous loader.

        If a parameter is ``Chain.FIRST``,
        the specified function will take raw data and its result will be passed to previous loader.

        If the parameter is ``Chain.LAST``, the specified function gets result of the previous loader.

    :return: desired provider
    """
    return bound(
        pred,
        make_chain(
            chain,
            ValueProvider(LoaderRequest, func)
        )
    )


def dumper(pred: Any, func: Dumper, chain: Optional[Chain] = None) -> Provider:
    """Basic provider to define custom dumper.

    :param pred: Predicate specifying where dumper should be used. See :ref:`predicate-system` for details.
    :param func: Function that acts as dumper.
        It must take one positional argument of raw data and return the processed value.
    :param chain: Controls how the function will interact with the previous dumper.

        When ``None`` is passed, the specified function will fully replace the previous dumper.

        If a parameter is ``Chain.FIRST``,
        the specified function will take raw data and its result will be passed to previous dumper.

        If the parameter is ``Chain.LAST``, the specified function gets result of the previous dumper.

    :return: desired provider
    """
    return bound(
        pred,
        make_chain(
            chain,
            ValueProvider(DumperRequest, func),
        ),
    )


def as_is_loader(pred: Any) -> Provider:
    """Provider that creates loader which does nothing with input data.

    :param pred: Predicate specifying where loader should be used. See :ref:`predicate-system` for details.
    :return: desired provider
    """
    return loader(pred, lambda x: x)


def as_is_dumper(pred: Any) -> Provider:
    """Provider that creates dumper which does nothing with input data.

    :param pred: Predicate specifying where dumper should be used. See :ref:`predicate-system` for details.
    :return: desired provider
    """
    return dumper(pred, lambda x: x)


def constructor(pred: Any, func: Callable) -> Provider:
    input_figure = get_callable_figure(func).input
    return bound(
        pred,
        ModelLoaderProvider(
            NameSanitizer(),
            InlinedInputExtractionMaker(input_figure),
            make_input_creation,
        ),
    )


NameMap = Mapping[Union[str, re.Pattern], Union[RawKey, Iterable[RawKey]]]


def _convert_name_map_to_stack(name_map: NameMap) -> NameMapStack:
    result: List[Tuple[re.Pattern, RawPath]] = []
    for pattern, path in name_map.items():
        path_tuple: VarTuple[RawKey]
        if isinstance(path, (str, int)) or path is Ellipsis:
            path_tuple = (path, )
        else:
            path_tuple = tuple(path)
            if not path_tuple:
                raise ValueError(f"Path for field {pattern!r} can not be empty iterable")

        result.append(
            (
                pattern if isinstance(pattern, re.Pattern) else re.compile(pattern),
                path_tuple
            )
        )

    return tuple(result)


def name_mapping(
    pred: Omittable[Any] = Omitted(),
    *,
    # filtering which fields are presented
    skip: Omittable[Iterable[str]] = Omitted(),
    only: Omittable[Optional[Iterable[str]]] = Omitted(),
    only_mapped: Omittable[bool] = Omitted(),
    # mutating names of presented fields
    map: Omittable[NameMap] = Omitted(),  # noqa: A002
    trim_trailing_underscore: Omittable[bool] = Omitted(),
    name_style: Omittable[Optional[NameStyle]] = Omitted(),
    # filtering of dumped data
    omit_default: Omittable[bool] = Omitted(),
    # policy for data that does not map to fields
    extra_in: Omittable[ExtraIn] = Omitted(),
    extra_out: Omittable[ExtraOut] = Omitted(),
    # chaining with next matching provider
    chain: Optional[Chain] = Chain.FIRST,
) -> Provider:
    """A name mapping decides which fields will be presented
    to the outside world and how they will look.

    The mapping process consists of two stages:
    1. Determining which fields are presented
    2. Mutating names of presented fields

    `skip` parameter has higher priority than `only` and `only_mapped`.

    Mutating parameters works in that way:
    Mapper tries to use the value from the map.
    If the field is not presented in the map,
    trim trailing underscore and convert name style.

    The field must follow snake_case to could be converted.
    """
    return bound(
        pred,
        OverlayProvider(
            overlays=[
                StructureOverlay(
                    skip=skip,
                    only=only,
                    only_mapped=only_mapped,
                    map=Omitted() if isinstance(map, Omitted) else _convert_name_map_to_stack(map),
                    trim_trailing_underscore=trim_trailing_underscore,
                    name_style=name_style,
                ),
                SievesOverlay(
                    omit_default=omit_default,
                ),
                ExtraMoveAndPoliciesOverlay(
                    extra_in=extra_in,
                    extra_out=extra_out,
                ),
            ],
            chain=chain,
        )
    )


NameOrProp = Union[str, property]


def add_property(
    pred: Any,
    prop: NameOrProp,
    tp: Omittable[TypeHint] = Omitted(),
    /, *,
    default: Default = NoDefault(),
    access_error: Optional[Catchable] = None,
    metadata: Mapping[Any, Any] = MappingProxyType({}),
) -> Provider:
    attr_name = _ensure_attr_name(prop)

    field = OutputField(
        name=attr_name,
        type=tp,
        accessor=DescriptorAccessor(attr_name, access_error),
        default=default,
        metadata=metadata,
    )

    return bound(
        pred,
        PropertyAdder(
            output_fields=[field],
            infer_types_for=[field.name] if tp == Omitted() else [],
        )
    )


def _ensure_attr_name(prop: NameOrProp) -> str:
    if isinstance(prop, str):
        return prop

    fget = prop.fget
    if fget is None:
        raise ValueError(f"Property {prop} has no fget")

    return fget.__name__


EnumPred = Union[TypeHint, str, EnumMeta, RequestPattern]


def _wrap_enum_provider(preds: Sequence[EnumPred], provider: Provider) -> Provider:
    if len(preds) == 0:
        return provider

    if Enum in preds:
        raise ValueError(f"Can not apply enum provider to {Enum}")

    return BoundingProvider(
        OrRequestChecker([create_request_checker(pred) for pred in preds]),
        provider,
    )


def enum_by_name(*preds: EnumPred) -> Provider:
    """Provider that represents enum members to the outside world by their name.

    :param preds: Predicates specifying where the provider should be used.
        The provider will be applied if any predicates meet the conditions,
        if no predicates are passed, the provider will be used for all Enums.
        See :ref:`predicate-system` for details.
    :return: desired provider
    """
    return _wrap_enum_provider(preds, EnumNameProvider())


def enum_by_exact_value(*preds: EnumPred) -> Provider:
    """Provider that represents enum members to the outside world by their value without any processing.

    :param preds: Predicates specifying where the provider should be used.
        The provider will be applied if any predicates meet the conditions,
        if no predicates are passed, the provider will be used for all Enums.
        See :ref:`predicate-system` for details.
    :return: desired provider
    """
    return _wrap_enum_provider(preds, EnumExactValueProvider())


def enum_by_value(first_pred: EnumPred, /, *preds: EnumPred, tp: TypeHint) -> Provider:
    """Provider that represents enum members to the outside world by their value by loader and dumper of specified type.
    The loader will call the loader of the :paramref:`tp` and pass it to the enum constructor.
    The dumper will get value from eum member and pass it to the dumper of the :paramref:`tp`.

    :param first_pred: Predicate specifying where the provider should be used.
        See :ref:`predicate-system` for details.
    :param preds: Additional predicates. The provider will be applied if any predicates meet the conditions.
    :param tp: Type of enum members.
        This type must cover all enum members for the correct operation of loader and dumper
    :return: desired provider
    """
    return _wrap_enum_provider([first_pred, *preds], EnumValueProvider(tp))


def validator(
    pred: Any,
    func: Callable[[Any], bool],
    error: Union[str, Callable[[Any], LoadError], None] = None,
    chain: Chain = Chain.LAST,
) -> Provider:
    # pylint: disable=C3001
    exception_factory = (
        (lambda x: ValidationError(error))
        if error is None or isinstance(error, str) else
        error
    )

    def validating_loader(data):
        if func(data):
            return data
        raise exception_factory(data)

    return loader(pred, validating_loader, chain)