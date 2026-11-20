from database import require_name, transaction


def is_handover_paused(db, batch_id):
    row = db.execute('''
        SELECT paused FROM station_handover WHERE batch_id = ?
    ''', (batch_id,)).fetchone()
    return bool(row[0]) if row is not None else False


def set_handover(db, batch_id, paused):
    require_name(batch_id, 'batch_id')
    if not isinstance(paused, bool):
        raise ValueError('paused must be a boolean')
    with transaction(db):
        if db.execute('SELECT 1 FROM station_acceptances WHERE batch_id = ?', (batch_id,)).fetchone() is None:
            raise KeyError(batch_id)
        db.execute('''
            INSERT INTO station_handover (batch_id, paused) VALUES (?, ?)
            ON CONFLICT (batch_id) DO UPDATE SET paused = excluded.paused
        ''', (batch_id, 1 if paused else 0))


def get_revision_request(db, acceptance_id, request_id):
    if not isinstance(request_id, str):
        return None
    return db.execute('''
        SELECT request_id, revision_id, initial_report_id, state
        FROM station_revision_requests WHERE acceptance_id = ? AND request_id = ?
    ''', (acceptance_id, request_id)).fetchone()


def get_applied_revision(db, acceptance_id):
    return db.execute('''
        SELECT request_id, revision_id, initial_report_id
        FROM station_revisions WHERE acceptance_id = ?
    ''', (acceptance_id,)).fetchone()


def load_revision_roster(db, acceptance_id):
    rows = db.execute('''
        SELECT piece_id FROM station_revision_roster WHERE acceptance_id = ? ORDER BY position
    ''', (acceptance_id,))
    return tuple(piece for piece, in rows)


def load_effective_selection(db, acceptance_id):
    rows = db.execute('''
        SELECT piece_id FROM station_revision_selection WHERE acceptance_id = ? ORDER BY position
    ''', (acceptance_id,))
    return tuple(piece for piece, in rows)


def load_activation_started(db, acceptance_id):
    rows = db.execute('''
        SELECT piece_id FROM station_revision_started WHERE acceptance_id = ? ORDER BY position
    ''', (acceptance_id,))
    return tuple(piece for piece, in rows)


def save_pending_request(db, acceptance_id, message):
    db.execute('''
        INSERT INTO station_revision_requests
            (acceptance_id, request_id, revision_id, initial_report_id, state)
        VALUES (?, ?, ?, ?, 'pending')
    ''', (acceptance_id, message['request_id'], message['revision_id'],
          message['initial_report_id']))


def save_applied_revision(db, acceptance_id, message, started_at_activation, selected):
    db.execute('''
        INSERT INTO station_revision_requests
            (acceptance_id, request_id, revision_id, initial_report_id, state)
        VALUES (?, ?, ?, ?, 'applied')
        ON CONFLICT(acceptance_id, request_id) DO UPDATE SET state = 'applied'
    ''', (acceptance_id, message['request_id'], message['revision_id'],
          message['initial_report_id']))
    db.execute('''
        INSERT INTO station_revisions (acceptance_id, request_id, revision_id, initial_report_id)
        VALUES (?, ?, ?, ?)
    ''', (acceptance_id, message['request_id'], message['revision_id'],
          message['initial_report_id']))
    db.executemany('INSERT INTO station_revision_roster VALUES (?, ?, ?)', (
        (acceptance_id, position, piece) for position, piece in enumerate(message['roster'])
    ))
    db.executemany('INSERT INTO station_revision_started VALUES (?, ?, ?)', (
        (acceptance_id, position, piece) for position, piece in enumerate(started_at_activation)
    ))
    db.executemany('INSERT INTO station_revision_selection VALUES (?, ?, ?)', (
        (acceptance_id, position, piece) for position, piece in enumerate(selected)
    ))
