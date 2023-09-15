import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from typing import Union

from adaptix import Retort
from adaptix._internal.feature_requirement import IS_PYPY
from adaptix._internal.provider.concrete_provider import DatetimeFormatProvider
from adaptix.load_error import DatetimeFormatMismatch, TypeLoadError, ValueLoadError
from tests_helpers import parametrize_bool, raises_exc


def check_any_dt(loader):
    raises_exc(
        TypeLoadError(str),
        lambda: loader(None)
    )
    raises_exc(
        TypeLoadError(str),
        lambda: loader(10)
    )
    raises_exc(
        TypeLoadError(str),
        lambda: loader(datetime(2011, 11, 4, 0, 0))
    )
    raises_exc(
        TypeLoadError(str),
        lambda: loader(date(2019, 12, 4))
    )
    raises_exc(
        TypeLoadError(str),
        lambda: loader(time(4, 23, 1))
    )


def test_iso_format_provider_datetime(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )

    loader = retort.get_loader(datetime)
    assert loader('2011-11-04') == datetime(2011, 11, 4, 0, 0)
    assert loader('2011-11-04T00:05:23') == datetime(2011, 11, 4, 0, 5, 23)
    assert loader('2011-11-04T00:05:23+04:00') == datetime(
        2011, 11, 4, 0, 5, 23,
        tzinfo=timezone(timedelta(seconds=14400))
    )

    check_any_dt(loader)

    raises_exc(
        ValueLoadError("Invalid isoformat string"),
        lambda: loader("some string")
    )

    dumper = retort.get_dumper(datetime)
    assert dumper(datetime(2011, 11, 4, 0, 0)) == '2011-11-04T00:00:00'


def test_iso_format_provider_date(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )

    loader = retort.get_loader(date)
    assert loader('2019-12-04') == date(2019, 12, 4)
    check_any_dt(loader)

    raises_exc(
        ValueLoadError("Invalid isoformat string"),
        lambda: loader("some string")
    )

    dumper = retort.get_dumper(date)
    assert dumper(date(2019, 12, 4)) == '2019-12-04'


def test_iso_format_provider_time(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )

    loader = retort.get_loader(time)
    assert loader('04:23:01') == time(4, 23, 1)
    assert loader('04:23:01+04:00') == time(
        4, 23, 1,
        tzinfo=timezone(timedelta(seconds=14400))
    )
    check_any_dt(loader)

    raises_exc(
        ValueLoadError("Invalid isoformat string"),
        lambda: loader("some string")
    )

    dumper = retort.get_dumper(time)
    assert dumper(time(4, 23, 1)) == '04:23:01'


def test_datetime_format_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
        recipe=[
            DatetimeFormatProvider("%Y-%m-%d"),
        ],
    )

    loader = retort.get_loader(datetime)
    assert loader("3045-02-13") == datetime(year=3045, month=2, day=13)

    check_any_dt(loader)

    raises_exc(
        DatetimeFormatMismatch("%Y-%m-%d"),
        lambda: loader("some string")
    )

    dumper = retort.get_dumper(datetime)
    assert dumper(datetime(year=3045, month=2, day=13)) == "3045-02-13"


def test_seconds_timedelta_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )

    loader = retort.get_loader(timedelta)
    assert loader(10) == timedelta(seconds=10)
    assert loader(600) == timedelta(minutes=10)
    assert loader(0.123) == timedelta(milliseconds=123)
    assert loader(Decimal('0.123')) == timedelta(milliseconds=123)

    dumper = retort.get_dumper(timedelta)
    assert dumper(timedelta(minutes=10)) == 600


def test_none_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )

    loader = retort.get_loader(None)

    assert loader(None) is None
    raises_exc(
        TypeLoadError(None),
        lambda: loader(10)
    )

    dumper = retort.get_dumper(None)
    assert dumper(None) is None


def test_bytes_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )

    loader = retort.get_loader(bytes)

    assert loader('YWJjZA==') == b'abcd'

    raises_exc(
        ValueLoadError('Bad base64 string'),
        lambda: loader('Hello, world'),
    )

    raises_exc(
        ValueLoadError(
            'Invalid base64-encoded string: number of data characters (5)'
            ' cannot be 1 more than a multiple of 4'
        ),
        lambda: loader('aaaaa='),
    )

    raises_exc(
        ValueLoadError('Incorrect padding'),
        lambda: loader('YWJjZA'),
    )

    raises_exc(
        TypeLoadError(str),
        lambda: loader(108),
    )

    dumper = retort.get_dumper(bytes)
    assert dumper(b'abcd') == 'YWJjZA=='


def test_bytearray_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )

    loader = retort.get_loader(bytearray)

    assert loader('YWJjZA==') == bytearray(b'abcd')

    raises_exc(
        ValueLoadError('Bad base64 string'),
        lambda: loader('Hello, world'),
    )

    raises_exc(
        ValueLoadError(
            'Invalid base64-encoded string: number of data characters (5)'
            ' cannot be 1 more than a multiple of 4'
        ),
        lambda: loader('aaaaa='),
    )

    raises_exc(
        ValueLoadError('Incorrect padding'),
        lambda: loader('YWJjZA'),
    )

    raises_exc(
        TypeLoadError(str),
        lambda: loader(108),
    )

    dumper = retort.get_dumper(bytearray)
    assert dumper(bytearray(b'abcd')) == 'YWJjZA=='


def test_regex_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )

    loader = retort.get_loader(re.Pattern)

    assert loader(r'\w') == re.compile(r'\w')

    raises_exc(
        TypeLoadError(str),
        lambda: loader(10)
    )
    raises_exc(
        ValueLoadError("bad escape (end of pattern) at position 0"),
        lambda: loader('\\')
    )

    dumper = retort.get_dumper(re.Pattern)
    assert dumper(re.compile(r'\w')) == r'\w'


def test_int_loader_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )
    loader = retort.get_loader(int)

    assert loader(100) == 100

    if strict_coercion:
        raises_exc(TypeLoadError(int), lambda: loader(None))
        raises_exc(TypeLoadError(int), lambda: loader('foo'))
        raises_exc(TypeLoadError(int), lambda: loader('100'))
    else:
        raises_exc(TypeLoadError(Union[int, float, str]), lambda: loader(None))
        raises_exc(ValueLoadError("Bad string format"), lambda: loader('foo'))
        assert loader('100') == 100


def test_float_loader_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )
    loader = retort.get_loader(float)

    assert loader(100.0) == 100.0
    assert isinstance(loader(100), float)

    if strict_coercion:
        raises_exc(TypeLoadError(Union[int, float]), lambda: loader(None))
        raises_exc(TypeLoadError(Union[int, float]), lambda: loader('foo'))
        raises_exc(TypeLoadError(Union[int, float]), lambda: loader('100'))
    else:
        raises_exc(TypeLoadError(Union[int, float, str]), lambda: loader(None))
        raises_exc(ValueLoadError("Bad string format"), lambda: loader('foo'))
        assert loader('100') == 100


def test_str_loader_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )
    loader = retort.get_loader(str)

    assert loader('foo') == 'foo'

    if strict_coercion:
        raises_exc(TypeLoadError(str), lambda: loader(None))
    else:
        assert loader(None) == 'None'


def test_bool_loader_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )
    loader = retort.get_loader(bool)

    assert loader(True) == True

    if strict_coercion:
        raises_exc(TypeLoadError(bool), lambda: loader(None))
    else:
        assert loader(None) == False


def test_decimal_loader_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )
    loader = retort.get_loader(Decimal)

    assert loader('100') == Decimal('100')
    assert loader(Decimal('100')) == Decimal('100')
    raises_exc(TypeLoadError(Union[str, Decimal]), lambda: loader(None))
    raises_exc(ValueLoadError("Bad string format"), lambda: loader('foo'))
    raises_exc(TypeLoadError(Union[str, Decimal]), lambda: loader(None))

    if strict_coercion:
        raises_exc(TypeLoadError(Union[str, Decimal]), lambda: loader([]))
    else:
        if IS_PYPY:
            description = (
                'Invalid tuple size in creation of Decimal from list or tuple.'
                '  The list or tuple should have exactly three elements.'
            )
        else:
            description = 'argument must be a sequence of length 3'

        raises_exc(ValueLoadError(description), lambda: loader([]))


def test_fraction_loader_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )
    loader = retort.get_loader(Fraction)

    assert loader('100') == Fraction('100')
    assert loader(Fraction('100')) == Fraction('100')
    raises_exc(TypeLoadError(Union[str, Fraction]), lambda: loader(None))
    raises_exc(ValueLoadError("Bad string format"), lambda: loader('foo'))
    raises_exc(TypeLoadError(Union[str, Fraction]), lambda: loader(None))
    raises_exc(TypeLoadError(Union[str, Fraction]), lambda: loader([]))


def test_complex_loader_provider(strict_coercion, debug_trail):
    retort = Retort(
        strict_coercion=strict_coercion,
        debug_trail=debug_trail,
    )
    loader = retort.get_loader(complex)

    assert loader('100') == complex('100')
    assert loader(complex('100')) == complex('100')
    raises_exc(TypeLoadError(Union[str, complex]), lambda: loader(None))
    raises_exc(ValueLoadError("Bad string format"), lambda: loader('foo'))
    raises_exc(TypeLoadError(Union[str, complex]), lambda: loader(None))
    raises_exc(TypeLoadError(Union[str, complex]), lambda: loader([]))
