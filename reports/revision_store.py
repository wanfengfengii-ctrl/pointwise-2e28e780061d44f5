from database import is_record_id, transaction


def get_request(db, request_id):
    """Return the stored request row, or None if the request name is unknown."""
    if not isinstance(request_id, str):
        return None
    row = db.execute('''
        SELECT request_id, batch_id, initial_report_id, revision_id, state, report_id
        FROM revision_requests WHERE request_id = ?
    ''', (request_id,)).fetchone()
    return None if row is None else row


def find_batch_request(db, batch_id):
    row = db.execute('''
        SELECT request_id FROM revision_requests WHERE batch_id = ?
    ''', (batch_id,)).fetchone()
    return None if row is None else row[0]


def save_pending_request(db, request_id, batch_id, initial_report_id, revision_id):
    with transaction(db):
        db.execute('''
            INSERT INTO revision_requests
                (request_id, batch_id, initial_report_id, revision_id, state, report_id)
            VALUES (?, ?, ?, ?, 'pending', NULL)
            ON CONFLICT(request_id) DO NOTHING
        ''', (request_id, batch_id, initial_report_id, revision_id))


def save_revision_report(db, request_id, batch_id, initial_report_id, revision_id,
                         started_at_activation, selected):
    """Register the applied request and its fixed ruling in one transaction."""
    with transaction(db):
        db.execute('''
            INSERT INTO revision_requests
                (request_id, batch_id, initial_report_id, revision_id, state, report_id)
            VALUES (?, ?, ?, ?, 'pending', NULL)
            ON CONFLICT(request_id) DO NOTHING
        ''', (request_id, batch_id, initial_report_id, revision_id))
        report_id = db.execute('''
            INSERT INTO revision_reports
                (batch_id, initial_report_id, revision_id, request_id)
            VALUES (?, ?, ?, ?)
        ''', (batch_id, initial_report_id, revision_id, request_id)).lastrowid
        db.executemany('INSERT INTO revision_started VALUES (?, ?, ?, ?)', (
            (report_id, batch_id, position, piece)
            for position, piece in enumerate(started_at_activation)
        ))
        db.executemany('INSERT INTO revision_selection VALUES (?, ?, ?, ?)', (
            (report_id, batch_id, position, piece) for position, piece in enumerate(selected)
        ))
        db.execute('''
            UPDATE revision_requests SET state = 'applied', report_id = ? WHERE request_id = ?
        ''', (report_id, request_id))
        return report_id


def load_revision_report(db, report_id):
    if not is_record_id(report_id):
        raise KeyError(report_id)
    header = db.execute('''
        SELECT report_id, batch_id, initial_report_id, revision_id, request_id
        FROM revision_reports WHERE report_id = ?
    ''', (report_id,)).fetchone()
    if header is None:
        raise KeyError(report_id)
    started = tuple(piece for piece, in db.execute('''
        SELECT piece_id FROM revision_started WHERE report_id = ? ORDER BY position
    ''', (report_id,)))
    selected = tuple(piece for piece, in db.execute('''
        SELECT piece_id FROM revision_selection WHERE report_id = ? ORDER BY position
    ''', (report_id,)))
    return header, started, selected
