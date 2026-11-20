from lots.register import load_lot
from lots.roster import roster_positions
from measure.freeze import load_frozen_revision
from risk.explain import RiskResult, explain_piece
from risk.residuals import mean_absolute_residual, residuals_for_piece


def rank_frozen_revision(lot, frozen):
    if lot.batch_id != frozen.batch_id:
        raise ValueError('freeze belongs to another batch')
    positions = roster_positions(lot.roster)
    readings = {(row.piece_id, row.gauge_name): row for row in frozen.readings}
    risks = []
    for piece_id in lot.roster:
        evidence = residuals_for_piece(lot, piece_id, readings)
        score = mean_absolute_residual(piece_id, evidence)
        risks.append(explain_piece(piece_id, score, evidence))
    risks.sort(key=lambda risk: (-risk.score, positions[risk.piece_id]))
    return RiskResult(lot.batch_id, frozen.freeze_id, frozen.revision_id, tuple(risks))


def preview_risk(db, freeze_id):
    frozen = load_frozen_revision(db, freeze_id)
    return rank_frozen_revision(load_lot(db, frozen.batch_id), frozen)
