from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class ResidualEvidence:
    gauge_name: str
    state: str
    value: Fraction | None
    unit: str | None
    normalized_mm: Fraction | None
    baseline_mm: Fraction
    residual_mm: Fraction | None


@dataclass(frozen=True)
class PieceRisk:
    piece_id: str
    score: Fraction
    valid_count: int
    evidence: tuple[ResidualEvidence, ...]


@dataclass(frozen=True)
class RiskResult:
    batch_id: str
    freeze_id: int
    revision_id: int
    ranked: tuple[PieceRisk, ...]


def explain_piece(piece_id, score, evidence):
    points = tuple(evidence)
    return PieceRisk(piece_id, score, sum(point.residual_mm is not None for point in points), points)
