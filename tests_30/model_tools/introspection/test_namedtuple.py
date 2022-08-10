import typing
from collections import namedtuple
from types import MappingProxyType
from typing import Any, NamedTuple

from dataclass_factory_30.model_tools import (
    AttrAccessor,
    DefaultValue,
    InputField,
    InputFigure,
    NoDefault,
    OutputField,
    OutputFigure,
    ParamKind,
    get_named_tuple_input_figure,
    get_named_tuple_output_figure,
)
from tests_30.test_helpers import requires_annotated

FooAB = namedtuple('FooAB', 'a b')
FooBA = namedtuple('FooBA', 'b a')


def test_order_ab():
    assert (
        get_named_tuple_input_figure(FooAB)
        ==
        InputFigure(
            constructor=FooAB,
            extra=None,
            fields=(
                InputField(
                    type=Any,
                    name='a',
                    default=NoDefault(),
                    is_required=True,
                    param_kind=ParamKind.POS_OR_KW,
                    metadata=MappingProxyType({}),
                    param_name='a',
                ),
                InputField(
                    type=Any,
                    name='b',
                    default=NoDefault(),
                    is_required=True,
                    param_kind=ParamKind.POS_OR_KW,
                    metadata=MappingProxyType({}),
                    param_name='b',
                ),
            ),
        )
    )

    assert (
        get_named_tuple_output_figure(FooAB)
        ==
        OutputFigure(
            extra=None,
            fields=(
                OutputField(
                    type=Any,
                    name='a',
                    default=NoDefault(),
                    accessor=AttrAccessor('a', is_required=True),
                    metadata=MappingProxyType({}),
                ),
                OutputField(
                    type=Any,
                    name='b',
                    default=NoDefault(),
                    accessor=AttrAccessor('b', is_required=True),
                    metadata=MappingProxyType({}),
                ),
            ),
        )
    )


def test_order_ba():
    assert (
        get_named_tuple_input_figure(FooBA)
        ==
        InputFigure(
            constructor=FooBA,
            extra=None,
            fields=(
                InputField(
                    type=Any,
                    name='b',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='b',
                ),
                InputField(
                    type=Any,
                    name='a',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='a',
                ),
            ),
        )
    )

    assert (
        get_named_tuple_output_figure(FooBA)
        ==
        OutputFigure(
            extra=None,
            fields=(
                OutputField(
                    type=Any,
                    name='b',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('b', is_required=True),
                ),
                OutputField(
                    type=Any,
                    name='a',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('a', is_required=True),
                ),
            ),
        )
    )


def func():
    return 0


FooDefs = namedtuple('FooDefs', 'a b c', defaults=[0, func])


def test_defaults():
    assert (
        get_named_tuple_input_figure(FooDefs)
        ==
        InputFigure(
            constructor=FooDefs,
            extra=None,
            fields=(
                InputField(
                    type=Any,
                    name='a',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='a',
                ),
                InputField(
                    type=Any,
                    name='b',
                    default=DefaultValue(0),
                    is_required=False,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='b',
                ),
                InputField(
                    type=Any,
                    name='c',
                    default=DefaultValue(func),
                    is_required=False,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='c',
                ),
            ),
        )
    )

    assert (
        get_named_tuple_output_figure(FooDefs)
        ==
        OutputFigure(
            extra=None,
            fields=(
                OutputField(
                    type=Any,
                    name='a',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('a', is_required=True),
                ),
                OutputField(
                    type=Any,
                    name='b',
                    default=DefaultValue(0),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('b', is_required=True),
                ),
                OutputField(
                    type=Any,
                    name='c',
                    default=DefaultValue(func),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('c', is_required=True),
                ),
            ),
        )
    )


WithRename = namedtuple('WithRename', ['abc', 'def', 'ghi', 'abc'], defaults=[0], rename=True)


def test_rename():
    assert (
        get_named_tuple_input_figure(WithRename)
        ==
        InputFigure(
            constructor=WithRename,
            extra=None,
            fields=(
                InputField(
                    type=Any,
                    name='abc',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='abc',
                ),
                InputField(
                    type=Any,
                    name='_1',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='_1',
                ),
                InputField(
                    type=Any,
                    name='ghi',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='ghi',
                ),
                InputField(
                    type=Any,
                    name='_3',
                    default=DefaultValue(0),
                    is_required=False,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='_3',
                ),
            ),
        )
    )

    assert (
        get_named_tuple_output_figure(WithRename)
        ==
        OutputFigure(
            extra=None,
            fields=(
                OutputField(
                    type=Any,
                    name='abc',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('abc', is_required=True),
                ),
                OutputField(
                    type=Any,
                    name='_1',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('_1', is_required=True),
                ),
                OutputField(
                    type=Any,
                    name='ghi',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('ghi', is_required=True),
                ),
                OutputField(
                    type=Any,
                    name='_3',
                    default=DefaultValue(0),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('_3', is_required=True),
                ),
            ),
        )
    )


BarA = NamedTuple('BarA', a=int, b=str)  # type: ignore[misc]


def test_class_hinted_namedtuple():
    assert (
        get_named_tuple_input_figure(BarA)
        ==
        InputFigure(
            constructor=BarA,
            extra=None,
            fields=(
                InputField(
                    type=int,
                    name='a',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='a',
                ),
                InputField(
                    type=str,
                    name='b',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='b',
                ),
            ),
        )
    )

    assert (
        get_named_tuple_output_figure(BarA)
        ==
        OutputFigure(
            extra=None,
            fields=(
                OutputField(
                    type=int,
                    name='a',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('a', is_required=True),
                ),
                OutputField(
                    type=str,
                    name='b',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('b', is_required=True),
                ),
            ),
        )
    )


# ClassVar is not supported in NamedTuple

class BarB(NamedTuple):
    a: int
    b: str = 'abc'
    c: 'bool' = False


def test_hinted_namedtuple():
    assert (
        get_named_tuple_input_figure(BarB)
        ==
        InputFigure(
            constructor=BarB,
            extra=None,
            fields=(
                InputField(
                    type=int,
                    name='a',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='a',
                ),
                InputField(
                    type=str,
                    name='b',
                    default=DefaultValue('abc'),
                    is_required=False,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='b',
                ),
                InputField(
                    type=bool,
                    name='c',
                    default=DefaultValue(False),
                    is_required=False,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='c',
                ),
            ),
        )
    )

    assert (
        get_named_tuple_output_figure(BarB)
        ==
        OutputFigure(
            extra=None,
            fields=(
                OutputField(
                    type=int,
                    name='a',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('a', is_required=True),
                ),
                OutputField(
                    type=str,
                    name='b',
                    default=DefaultValue('abc'),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('b', is_required=True),
                ),
                OutputField(
                    type=bool,
                    name='c',
                    default=DefaultValue(False),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('c', is_required=True),
                ),
            ),
        )
    )


class Parent(NamedTuple):
    a: int


class Child(Parent):
    b: str


def test_inheritance():
    assert (
        get_named_tuple_input_figure(Child)
        ==
        InputFigure(
            constructor=Child,
            extra=None,
            fields=(
                InputField(
                    type=int,
                    name='a',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='a',
                ),
            ),
        )
    )

    assert (
        get_named_tuple_output_figure(Child)
        ==
        OutputFigure(
            extra=None,
            fields=(
                OutputField(
                    type=int,
                    name='a',
                    default=NoDefault(),
                    metadata=MappingProxyType({}),
                    accessor=AttrAccessor('a', is_required=True),
                ),
            ),
        )
    )


@requires_annotated
def test_annotated():
    class WithAnnotated(NamedTuple):
        annotated_field: typing.Annotated[int, 'metadata']

    assert (
        get_named_tuple_input_figure(WithAnnotated)
        ==
        InputFigure(
            constructor=WithAnnotated,
            extra=None,
            fields=(
                InputField(
                    type=typing.Annotated[int, 'metadata'],
                    name='annotated_field',
                    default=NoDefault(),
                    is_required=True,
                    metadata=MappingProxyType({}),
                    param_kind=ParamKind.POS_OR_KW,
                    param_name='annotated_field',
                ),
            ),
        )
    )

    assert (
        get_named_tuple_output_figure(WithAnnotated)
        ==
        OutputFigure(
            extra=None,
            fields=(
                OutputField(
                    type=typing.Annotated[int, 'metadata'],
                    name='annotated_field',
                    default=NoDefault(),
                    accessor=AttrAccessor('annotated_field', is_required=True),
                    metadata=MappingProxyType({}),
                ),
            ),
        )
    )