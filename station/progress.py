from database import transaction
from station.ledger import load_acceptance, load_starts
from station.revision_store import load_effective_selection, load_revision_roster
from station.schema import StationProgress


def station_progress(db, batch_id):
    with transaction(db, write=False):
        accepted = load_acceptance(db, batch_id)
        started = {record.piece_id for record in load_starts(db, accepted)}
        effective = load_effective_selection(db, accepted.acceptance_id)
        if effective:
            roster = load_revision_roster(db, accepted.acceptance_id)
            order = tuple(piece for piece in roster if piece in set(effective))
        else:
            order = accepted.packet.selected
        return StationProgress(
            batch_id, accepted.acceptance_id, accepted.packet.report_id,
            tuple(piece for piece in order if piece in started),
            tuple(piece for piece in order if piece not in started),
        )
