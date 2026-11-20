from database import transaction
from lots.register import load_lot
from measure.revisions import append_revision, load_current_revision, load_revision, validate_reading_rows


def amend_readings(db, batch_id, parent_id, rows):
    with transaction(db):
        lot = load_lot(db, batch_id)
        parent = load_revision(db, parent_id)
        if parent.batch_id != batch_id:
            raise ValueError('parent revision belongs to another batch')
        current = load_current_revision(db, batch_id)
        if current is None or current.revision_id != parent_id:
            raise ValueError('parent revision is no longer current')
        changes = validate_reading_rows(lot, rows)
        merged = {(row.piece_id, row.gauge_name): row for row in parent.readings}
        merged.update(((row.piece_id, row.gauge_name), row) for row in changes)
        return append_revision(db, batch_id, parent_id, merged.values())
