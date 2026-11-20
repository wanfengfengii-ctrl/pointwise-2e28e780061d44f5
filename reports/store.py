import json

from database import fraction_parts, is_record_id, open_database, transaction
from lots.schema import initialize_lot_schema
from measure.schema import initialize_measure_schema
from reports.schema import InitialReceipt, initialize_reports_schema


def open_analysis(path):
    db = open_database(path)
    try:
        initialize_lot_schema(db)
        initialize_measure_schema(db)
        initialize_reports_schema(db)
    except BaseException:
        db.close()
        raise
    return db


def _optional_parts(value):
    return None if value is None else fraction_parts(value)


def _encode_evidence(evidence):
    return json.dumps([
        (point.gauge_name, point.state, _optional_parts(point.value), point.unit,
         _optional_parts(point.normalized_mm), fraction_parts(point.baseline_mm),
         _optional_parts(point.residual_mm))
        for point in evidence
    ], ensure_ascii=False, separators=(',', ':'))


def commit_initial(db, result, limit, selected):
    with transaction(db):
        report_id = db.execute('''
            INSERT INTO initial_reports (batch_id, freeze_id, revision_id, review_limit)
            VALUES (?, ?, ?, ?)
        ''', (result.batch_id, result.freeze_id, result.revision_id, limit)).lastrowid
        db.executemany('INSERT INTO initial_risks VALUES (?, ?, ?, ?, ?, ?, ?)', (
            (report_id, position, risk.piece_id, *fraction_parts(risk.score),
             risk.valid_count, _encode_evidence(risk.evidence))
            for position, risk in enumerate(result.ranked)
        ))
        db.executemany('INSERT INTO initial_selection VALUES (?, ?, ?)', (
            (report_id, position, piece) for position, piece in enumerate(selected)
        ))
        receipt_id = db.execute('INSERT INTO initial_receipts (report_id) VALUES (?)', (report_id,)).lastrowid
        return InitialReceipt(receipt_id, report_id, result.batch_id, result.freeze_id, result.revision_id)


def load_initial_records(db, report_id):
    if not is_record_id(report_id):
        raise KeyError(report_id)
    header = db.execute('''
        SELECT r.batch_id, r.freeze_id, r.revision_id, r.review_limit, c.receipt_id
        FROM initial_reports AS r JOIN initial_receipts AS c USING (report_id)
        WHERE r.report_id = ?
    ''', (report_id,)).fetchone()
    if header is None:
        raise KeyError(report_id)
    ranked = db.execute('''
        SELECT piece_id, score_num, score_den, valid_count, evidence
        FROM initial_risks WHERE report_id = ? ORDER BY position
    ''', (report_id,)).fetchall()
    selection = db.execute('''
        SELECT piece_id FROM initial_selection WHERE report_id = ? ORDER BY position
    ''', (report_id,))
    return header, ranked, tuple(piece for piece, in selection)
