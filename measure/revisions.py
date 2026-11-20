from database import fraction_parts, from_fraction_parts, is_record_id, require_name
from lots.gauges import parse_length_value
from measure.schema import Reading, ReadingRevision


def validate_reading_rows(lot, rows):
    if not isinstance(rows, (tuple, list)):
        raise ValueError('reading rows must be a list or tuple')
    pieces = set(lot.roster)
    gauges = {spec.name for spec in lot.gauges}
    normalized = {}
    for item in rows:
        if isinstance(item, Reading):
            piece, gauge, value, unit = item.piece_id, item.gauge_name, item.value, item.unit
        elif isinstance(item, (tuple, list)) and len(item) == 4:
            piece, gauge, value, unit = item
        else:
            raise ValueError('a reading row needs piece, gauge, value and unit')
        require_name(piece, 'piece_id')
        require_name(gauge, 'gauge name')
        if piece not in pieces or gauge not in gauges:
            raise ValueError(f'unregistered reading location {piece!r}, {gauge!r}')
        key = (piece, gauge)
        if key in normalized:
            raise ValueError(f'repeated reading location {key!r}')
        if value is None:
            if unit is not None:
                raise ValueError('an explicit missing reading has no unit')
            normalized[key] = Reading(piece, gauge, None, None)
        else:
            normalized[key] = Reading(piece, gauge, parse_length_value(value, unit), unit)
    return tuple(normalized[key] for key in sorted(normalized))


def load_revision(db, revision_id):
    if not is_record_id(revision_id):
        raise KeyError(revision_id)
    header = db.execute('''
        SELECT batch_id, parent_id FROM reading_revisions WHERE revision_id = ?
    ''', (revision_id,)).fetchone()
    if header is None:
        raise KeyError(revision_id)
    rows = db.execute('''
        SELECT piece_id, gauge_name, value_num, value_den, unit
        FROM revision_readings WHERE revision_id = ? ORDER BY piece_id, gauge_name
    ''', (revision_id,))
    readings = tuple(
        Reading(piece, name, None if num is None else from_fraction_parts(num, den), unit)
        for piece, name, num, den, unit in rows
    )
    return ReadingRevision(revision_id, header[0], header[1], readings)


def load_current_revision(db, batch_id):
    row = db.execute('SELECT revision_id FROM reading_heads WHERE batch_id = ?', (batch_id,)).fetchone()
    return None if row is None else load_revision(db, row[0])


def append_revision(db, batch_id, parent_id, readings):
    """Append a validated snapshot inside the caller's write transaction."""
    revision_id = db.execute('''
        INSERT INTO reading_revisions (batch_id, parent_id) VALUES (?, ?)
    ''', (batch_id, parent_id)).lastrowid
    stored_rows = []
    for reading in readings:
        parts = (None, None) if reading.value is None else fraction_parts(reading.value)
        stored_rows.append((revision_id, batch_id, reading.piece_id, reading.gauge_name, *parts, reading.unit))
    db.executemany('INSERT INTO revision_readings VALUES (?, ?, ?, ?, ?, ?, ?)', stored_rows)
    db.execute('''
        INSERT INTO reading_heads (batch_id, revision_id) VALUES (?, ?)
        ON CONFLICT (batch_id) DO UPDATE SET revision_id = excluded.revision_id
    ''', (batch_id, revision_id))
    return load_revision(db, revision_id)


def find_import_ticket(db, batch_id, ticket):
    row = db.execute('''
        SELECT revision_id FROM import_tickets WHERE batch_id = ? AND ticket = ?
    ''', (batch_id, ticket)).fetchone()
    return None if row is None else load_revision(db, row[0])


def bind_import_ticket(db, batch_id, ticket, revision_id):
    db.execute('INSERT INTO import_tickets VALUES (?, ?, ?)', (batch_id, ticket, revision_id))
