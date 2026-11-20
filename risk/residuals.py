from fractions import Fraction

from lots.gauges import LENGTH_TO_MM
from risk.explain import ResidualEvidence
from risk.units import normalize_pair


def residuals_for_piece(lot, piece_id, readings):
    points = []
    for gauge in lot.gauges:
        reading = readings.get((piece_id, gauge.name))
        if reading is None or reading.value is None:
            state = 'unreported' if reading is None else 'missing'
            points.append(ResidualEvidence(
                gauge.name, state, None, None, None, gauge.baseline * LENGTH_TO_MM[gauge.unit], None,
            ))
        else:
            pair = normalize_pair(reading, gauge)
            points.append(ResidualEvidence(
                gauge.name, 'valid', pair.value, pair.unit, pair.normalized_mm,
                pair.baseline_mm, abs(pair.normalized_mm - pair.baseline_mm),
            ))
    return tuple(points)


def mean_absolute_residual(piece_id, evidence):
    valid = [point.residual_mm for point in evidence if point.residual_mm is not None]
    if not valid:
        raise ValueError(f'piece {piece_id!r} has no valid measurements')
    return sum(valid, Fraction(0)) / len(valid)
