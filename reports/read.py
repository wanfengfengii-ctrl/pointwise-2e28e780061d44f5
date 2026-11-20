import json

from database import from_fraction_parts
from reports.schema import InitialReceipt, InitialReport
from reports.store import load_initial_records
from risk.explain import PieceRisk, ResidualEvidence


def _optional_fraction(parts):
    return None if parts is None else from_fraction_parts(*parts)


def _read_evidence(payload):
    return tuple(
        ResidualEvidence(
            name, state, _optional_fraction(value), unit, _optional_fraction(normalized),
            from_fraction_parts(*baseline), _optional_fraction(residual),
        )
        for name, state, value, unit, normalized, baseline, residual in json.loads(payload)
    )


def read_initial(db, report_id):
    header, risk_rows, selected = load_initial_records(db, report_id)
    batch_id, freeze_id, revision_id, limit, receipt_id = header
    receipt = InitialReceipt(receipt_id, report_id, batch_id, freeze_id, revision_id)
    ranked = tuple(
        PieceRisk(piece, from_fraction_parts(num, den), count, _read_evidence(payload))
        for piece, num, den, count, payload in risk_rows
    )
    return InitialReport(report_id, batch_id, freeze_id, revision_id, limit, selected, ranked, receipt)
