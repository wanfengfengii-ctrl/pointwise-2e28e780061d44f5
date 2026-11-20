from dataclasses import dataclass
from fractions import Fraction

from lots.gauges import LENGTH_TO_MM, GaugeSpec, parse_length_value
from measure.schema import Reading


@dataclass(frozen=True)
class NormalizedPair:
    value: Fraction
    unit: str
    normalized_mm: Fraction
    baseline_mm: Fraction


def normalize_pair(reading: Reading, gauge: GaugeSpec):
    if reading.gauge_name != gauge.name:
        raise ValueError('reading and baseline refer to different gauges')
    value = parse_length_value(reading.value, reading.unit)
    baseline = parse_length_value(gauge.baseline, gauge.unit)
    return NormalizedPair(
        value, reading.unit, value * LENGTH_TO_MM[reading.unit], baseline * LENGTH_TO_MM[gauge.unit],
    )
