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
        db.execute('''
            CREATE TABLE IF NOT EXISTS station_starts (
                start_id INTEGER PRIMARY KEY,
                acceptance_id INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                UNIQUE (acceptance_id, piece_id),
                FOREIGN KEY (acceptance_id, piece_id) REFERENCES station_selection(acceptance_id, piece_id)
            )
        ''')
