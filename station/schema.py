from dataclasses import dataclass

from database import transaction
from reports.schema import InitialPacket


@dataclass(frozen=True)
class AcceptedInitial:
    acceptance_id: int
    packet: InitialPacket


@dataclass(frozen=True)
class StartRecord:
    start_id: int
    batch_id: str
    report_id: int
    piece_id: str


@dataclass(frozen=True)
class PendingStart:
    """A start attempted while the station is in handover; no start record exists."""
    batch_id: str
    piece_id: str


@dataclass(frozen=True)
class StationProgress:
    batch_id: str
    acceptance_id: int
    report_id: int
    started: tuple[str, ...]
    pending: tuple[str, ...]


def initialize_station_schema(db):
    with transaction(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_acceptances (
                acceptance_id INTEGER PRIMARY KEY,
                batch_id TEXT NOT NULL UNIQUE,
                packet_version INTEGER NOT NULL CHECK (packet_version = 1),
                report_id INTEGER NOT NULL,
                freeze_id INTEGER NOT NULL,
                revision_id INTEGER NOT NULL,
                review_limit INTEGER NOT NULL CHECK (review_limit > 0),
                receipt_id INTEGER NOT NULL
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_selection (
                acceptance_id INTEGER NOT NULL REFERENCES station_acceptances(acceptance_id),
                position INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                score_num TEXT NOT NULL,
                score_den TEXT NOT NULL,
                PRIMARY KEY (acceptance_id, piece_id),
                UNIQUE (acceptance_id, position)
            )
        ''')
        # V1 constrained starts to the initial selection. The revised effective list
        # may admit pieces that were never on that selection, so the piece foreign key
        # is dropped. Rows and start ids are preserved on reopen.
        fk_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='station_starts'").fetchone()
        if fk_sql is not None and 'REFERENCES station_selection' in fk_sql[0]:
            db.execute('ALTER TABLE station_starts RENAME TO station_starts_v1')
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_starts (
                start_id INTEGER PRIMARY KEY,
                acceptance_id INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                UNIQUE (acceptance_id, piece_id),
                FOREIGN KEY (acceptance_id) REFERENCES station_acceptances(acceptance_id)
            )
        ''')
        if fk_sql is not None and 'REFERENCES station_selection' in fk_sql[0]:
            db.execute('''
                INSERT INTO station_starts (start_id, acceptance_id, piece_id)
                SELECT start_id, acceptance_id, piece_id FROM station_starts_v1
            ''')
            db.execute('DROP TABLE station_starts_v1')
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_handover (
                batch_id TEXT PRIMARY KEY NOT NULL REFERENCES station_acceptances(batch_id),
                paused INTEGER NOT NULL CHECK (paused IN (0, 1))
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_revision_requests (
                acceptance_id INTEGER NOT NULL,
                request_id TEXT NOT NULL,
                revision_id INTEGER NOT NULL,
                initial_report_id INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('pending', 'applied')),
                PRIMARY KEY (acceptance_id, request_id),
                FOREIGN KEY (acceptance_id) REFERENCES station_acceptances(acceptance_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_revisions (
                acceptance_id INTEGER PRIMARY KEY NOT NULL,
                request_id TEXT NOT NULL,
                revision_id INTEGER NOT NULL,
                initial_report_id INTEGER NOT NULL,
                FOREIGN KEY (acceptance_id) REFERENCES station_acceptances(acceptance_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_revision_roster (
                acceptance_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                PRIMARY KEY (acceptance_id, piece_id),
                UNIQUE (acceptance_id, position),
                FOREIGN KEY (acceptance_id) REFERENCES station_acceptances(acceptance_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_revision_selection (
                acceptance_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                PRIMARY KEY (acceptance_id, piece_id),
                UNIQUE (acceptance_id, position),
                FOREIGN KEY (acceptance_id) REFERENCES station_acceptances(acceptance_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_revision_started (
                acceptance_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                PRIMARY KEY (acceptance_id, piece_id),
                UNIQUE (acceptance_id, position),
                FOREIGN KEY (acceptance_id) REFERENCES station_acceptances(acceptance_id)
            )
        ''')
