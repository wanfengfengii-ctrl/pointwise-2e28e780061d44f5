from database import require_name, transaction
from station.ledger import load_acceptance, load_start, save_start
from station.revision_store import is_handover_paused, load_effective_selection
from station.schema import PendingStart


def start_review(db, batch_id, piece_id):
    require_name(piece_id, 'piece_id')
    with transaction(db):
        accepted = load_acceptance(db, batch_id)
        prior = load_start(db, accepted, piece_id)
        if prior is not None:
            return prior
        effective = load_effective_selection(db, accepted.acceptance_id)
        if effective:
            if piece_id not in effective:
                raise ValueError('piece is not on the effective revision list')
        elif piece_id not in accepted.packet.selected:
            raise ValueError('piece is not on the accepted initial list')
        # During handover, new starts are deferred and leave no start record.
        if is_handover_paused(db, batch_id):
            return PendingStart(batch_id, piece_id)
        return save_start(db, accepted, piece_id)
