from dataclasses import dataclass
from fractions import Fraction

from database import transaction


@dataclass(frozen=True)
class Reading:
    piece_id: str
    gauge_name: str
    value: Fraction | None
    unit: str | None

    @property
    def state(self):
        return 'missing' if self.value is None else 'valid'


@dataclass(frozen=True)
class ReadingRevision:
    revision_id: int
    batch_id: str
    parent_id: int | None
    readings: tuple[Reading, ...]


@dataclass(frozen=True)
class FrozenRevision:
    freeze_id: int
    revision: ReadingRevision

    @property
    def batch_id(self):
        return self.revision.batch_id

    @property
    def revision_id(self):
        return self.revision.revision_id

    @property
    def readings(self):
        return self.revision.readings


def initialize_measure_schema(db):
    with transaction(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS reading_revisions (
                revision_id INTEGER PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES lots(batch_id),
                parent_id INTEGER,
                UNIQUE (batch_id, revision_id),
                FOREIGN KEY (batch_id, parent_id) REFERENCES reading_revisions(batch_id, revision_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS revision_readings (
                revision_id INTEGER NOT NULL,
                batch_id TEXT NOT NULL,
                piece_id TEXT NOT NULL,
                gauge_name TEXT NOT NULL,
                value_num TEXT,
                value_den TEXT,
                unit TEXT,
                PRIMARY KEY (revision_id, piece_id, gauge_name),
                FOREIGN KEY (batch_id, revision_id) REFERENCES reading_revisions(batch_id, revision_id),
                FOREIGN KEY (batch_id, piece_id) REFERENCES lot_pieces(batch_id, piece_id),
                FOREIGN KEY (batch_id, gauge_name) REFERENCES lot_gauges(batch_id, gauge_name),
                CHECK ((value_num IS NULL AND value_den IS NULL AND unit IS NULL)
                    OR (value_num IS NOT NULL AND value_den IS NOT NULL AND unit IS NOT NULL))
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS reading_heads (
                batch_id TEXT PRIMARY KEY NOT NULL,
                revision_id INTEGER NOT NULL,
                FOREIGN KEY (batch_id, revision_id) REFERENCES reading_revisions(batch_id, revision_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS import_tickets (
                batch_id TEXT NOT NULL,
                ticket TEXT NOT NULL,
                revision_id INTEGER NOT NULL,
                PRIMARY KEY (batch_id, ticket),
                FOREIGN KEY (batch_id, revision_id) REFERENCES reading_revisions(batch_id, revision_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS freezes (
                freeze_id INTEGER PRIMARY KEY,
                batch_id TEXT NOT NULL,
                revision_id INTEGER NOT NULL,
                UNIQUE (batch_id, revision_id),
                UNIQUE (batch_id, freeze_id, revision_id),
                FOREIGN KEY (batch_id, revision_id) REFERENCES reading_revisions(batch_id, revision_id)
            )
        ''')
