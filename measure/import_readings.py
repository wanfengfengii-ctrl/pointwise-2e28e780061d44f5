from database import require_name, transaction
from lots.register import load_lot
from measure.revisions import (
    append_revision, bind_import_ticket, find_import_ticket, load_current_revision,
    validate_reading_rows,
)


def record_readings(db, batch_id, ticket, rows):
    with transaction(db):
        lot = load_lot(db, batch_id)
        require_name(ticket, 'import ticket')
        readings = validate_reading_rows(lot, rows)
        original = find_import_ticket(db, batch_id, ticket)
        if original is not None:
            if original.readings != readings:
                raise ValueError('ticket already refers to different readings')
            return original
        current = load_current_revision(db, batch_id)
        parent_id = current.revision_id if current is not None else None
        revision = append_revision(db, batch_id, parent_id, readings)
        bind_import_ticket(db, batch_id, ticket, revision.revision_id)
        return revision
