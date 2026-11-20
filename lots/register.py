from database import fraction_parts, from_fraction_parts, require_name, transaction
from lots.gauges import GaugeSpec, validate_gauges
from lots.roster import normalize_roster, validate_limit
from lots.schema import Lot


def register_lot(db, batch_id, roster, gauges, limit):
    require_name(batch_id, 'batch_id')
    pieces = normalize_roster(roster)
    definition = Lot(batch_id, pieces, validate_gauges(gauges), validate_limit(limit, pieces))
    with transaction(db):
        try:
            existing = load_lot(db, batch_id)
        except KeyError:
            db.execute('INSERT INTO lots VALUES (?, ?)', (batch_id, definition.limit))
            db.executemany(
                'INSERT INTO lot_pieces VALUES (?, ?, ?)',
                ((batch_id, position, piece) for position, piece in enumerate(pieces)),
            )
            db.executemany(
                'INSERT INTO lot_gauges VALUES (?, ?, ?, ?, ?, ?)',
                ((batch_id, position, gauge.name, *fraction_parts(gauge.baseline), gauge.unit)
                 for position, gauge in enumerate(definition.gauges)),
            )
            return definition
        if existing != definition:
            raise ValueError('batch already has a different fixed definition')
        return existing


def load_lot(db, batch_id):
    if not isinstance(batch_id, str):
        raise KeyError(batch_id)
    header = db.execute('SELECT review_limit FROM lots WHERE batch_id = ?', (batch_id,)).fetchone()
    if header is None:
        raise KeyError(batch_id)
    pieces = db.execute('''
        SELECT piece_id FROM lot_pieces WHERE batch_id = ? ORDER BY position
    ''', (batch_id,))
    gauges = db.execute('''
        SELECT gauge_name, baseline_num, baseline_den, unit
        FROM lot_gauges WHERE batch_id = ? ORDER BY position
    ''', (batch_id,))
    return Lot(
        batch_id,
        tuple(piece for piece, in pieces),
        tuple(GaugeSpec(name, from_fraction_parts(num, den), unit) for name, num, den, unit in gauges),
        header[0],
    )
