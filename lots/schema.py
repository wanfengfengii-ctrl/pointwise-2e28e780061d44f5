from dataclasses import dataclass

from database import transaction
from lots.gauges import GaugeSpec


@dataclass(frozen=True)
class Lot:
    batch_id: str
    roster: tuple[str, ...]
    gauges: tuple[GaugeSpec, ...]
    limit: int


def initialize_lot_schema(db):
    with transaction(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS lots (
                batch_id TEXT PRIMARY KEY NOT NULL,
                review_limit INTEGER NOT NULL CHECK (review_limit > 0)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS lot_pieces (
                batch_id TEXT NOT NULL REFERENCES lots(batch_id),
                position INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                PRIMARY KEY (batch_id, piece_id),
                UNIQUE (batch_id, position)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS lot_gauges (
                batch_id TEXT NOT NULL REFERENCES lots(batch_id),
                position INTEGER NOT NULL,
                gauge_name TEXT NOT NULL,
                baseline_num TEXT NOT NULL,
                baseline_den TEXT NOT NULL,
                unit TEXT NOT NULL,
                PRIMARY KEY (batch_id, gauge_name),
                UNIQUE (batch_id, position)
            )
        ''')
