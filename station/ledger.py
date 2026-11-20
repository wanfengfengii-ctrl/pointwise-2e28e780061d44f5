from database import fraction_parts, from_fraction_parts, open_database
from reports.schema import InitialPacket, InitialReceipt
from station.schema import AcceptedInitial, StartRecord, initialize_station_schema


def open_station(path):
    db = open_database(path)
    try:
        initialize_station_schema(db)
    except BaseException:
        db.close()
        raise
    return db


def load_acceptance(db, batch_id):
    if not isinstance(batch_id, str):
        raise KeyError(batch_id)
    header = db.execute('''
        SELECT acceptance_id, packet_version, report_id, freeze_id, revision_id, review_limit, receipt_id
        FROM station_acceptances WHERE batch_id = ?
    ''', (batch_id,)).fetchone()
    if header is None:
        raise KeyError(batch_id)
    acceptance_id, version, report_id, freeze_id, revision_id, limit, receipt_id = header
    rows = db.execute('''
        SELECT piece_id, score_num, score_den FROM station_selection
        WHERE acceptance_id = ? ORDER BY position
    ''', (acceptance_id,))
    risks = tuple((piece, from_fraction_parts(num, den)) for piece, num, den in rows)
    receipt = InitialReceipt(receipt_id, report_id, batch_id, freeze_id, revision_id)
    packet = InitialPacket(
        version, batch_id, report_id, freeze_id, revision_id, limit,
        tuple(piece for piece, _ in risks), risks, receipt,
    )
    return AcceptedInitial(acceptance_id, packet)


def save_acceptance(db, packet):
    acceptance_id = db.execute('''
        INSERT INTO station_acceptances
            (batch_id, packet_version, report_id, freeze_id, revision_id, review_limit, receipt_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (packet.batch_id, packet.version, packet.report_id, packet.freeze_id,
          packet.revision_id, packet.limit, packet.receipt.receipt_id)).lastrowid
    db.executemany('INSERT INTO station_selection VALUES (?, ?, ?, ?, ?)', (
        (acceptance_id, position, piece, *fraction_parts(score))
        for position, (piece, score) in enumerate(packet.risks)
    ))
    return AcceptedInitial(acceptance_id, packet)


def load_start(db, accepted, piece_id):
    row = db.execute('''
        SELECT start_id FROM station_starts WHERE acceptance_id = ? AND piece_id = ?
    ''', (accepted.acceptance_id, piece_id)).fetchone()
    if row is None:
        return None
    return StartRecord(row[0], accepted.packet.batch_id, accepted.packet.report_id, piece_id)


def save_start(db, accepted, piece_id):
    start_id = db.execute('''
        INSERT INTO station_starts (acceptance_id, piece_id) VALUES (?, ?)
    ''', (accepted.acceptance_id, piece_id)).lastrowid
    return StartRecord(start_id, accepted.packet.batch_id, accepted.packet.report_id, piece_id)


def load_starts(db, accepted):
    rows = db.execute('''
        SELECT start_id, piece_id FROM station_starts WHERE acceptance_id = ? ORDER BY start_id
    ''', (accepted.acceptance_id,))
    return tuple(StartRecord(start_id, accepted.packet.batch_id, accepted.packet.report_id, piece)
                 for start_id, piece in rows)
