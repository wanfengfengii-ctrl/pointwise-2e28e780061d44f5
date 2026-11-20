from database import transaction
from station.ledger import load_acceptance, load_starts
from station.schema import StationProgress


def station_progress(db, batch_id):
    with transaction(db, write=False):
        accepted = load_acceptance(db, batch_id)
        started = {record.piece_id for record in load_starts(db, accepted)}
        selected = accepted.packet.selected
        return StationProgress(
            batch_id, accepted.acceptance_id, accepted.packet.report_id,
            tuple(piece for piece in selected if piece in started),
            tuple(piece for piece in selected if piece not in started),
        )
