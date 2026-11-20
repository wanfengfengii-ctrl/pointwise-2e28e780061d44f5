from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType

from database import require_name


LENGTH_TO_MM = MappingProxyType({
    'mm': Fraction(1),
    'cm': Fraction(10),
    'm': Fraction(1000),
    'um': Fraction(1, 1000),
})


@dataclass(frozen=True)
class GaugeSpec:
    name: str
    baseline: Fraction | Decimal | int | float | str
    unit: str


def parse_length_value(value, unit):
    if not isinstance(unit, str) or unit not in LENGTH_TO_MM:
        raise ValueError('unknown length unit')
    if isinstance(value, bool) or not isinstance(value, (Fraction, Decimal, int, float, str)):
        raise ValueError('invalid length value')
    try:
        return Fraction(str(value) if isinstance(value, float) else value)
    except (ValueError, OverflowError, ZeroDivisionError) as error:
        raise ValueError('length must be a finite rational number') from error


def validate_gauges(gauges):
    if not isinstance(gauges, (tuple, list)) or not gauges:
        raise ValueError('gauges must be a nonempty ordered list or tuple')
    seen = set()
    normalized = []
    for gauge in gauges:
        if not isinstance(gauge, GaugeSpec):
            raise ValueError('expected a GaugeSpec')
        name = require_name(gauge.name, 'gauge name')
        if name in seen:
            raise ValueError('duplicate gauge name')
        seen.add(name)
        normalized.append(GaugeSpec(name, parse_length_value(gauge.baseline, gauge.unit), gauge.unit))
    return tuple(normalized)
