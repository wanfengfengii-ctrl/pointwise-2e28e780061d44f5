from database import transaction
from station.ledger import load_acceptance, load_start, save_start


def start_review(db, batch_id, piece_id):
    with transaction(db):
        accepted = load_acceptance(db, batch_id)
        if not isinstance(piece_id, str) or piece_id not in accepted.packet.selected:
            raise ValueError('piece is not on the accepted initial list')
        prior = load_start(db, accepted, piece_id)
        if prior is not None:
            return prior
        return save_start(db, accepted, piece_id)
