from lots.register import load_lot
from measure.freeze import load_frozen_revision
from reports.store import commit_initial
from risk.ranking import rank_frozen_revision


def issue_initial(db, batch_id, freeze_id):
    lot = load_lot(db, batch_id)
    frozen = load_frozen_revision(db, freeze_id)
    result = rank_frozen_revision(lot, frozen)
    selected = tuple(risk.piece_id for risk in result.ranked[:lot.limit])
    return commit_initial(db, result, lot.limit, selected)
