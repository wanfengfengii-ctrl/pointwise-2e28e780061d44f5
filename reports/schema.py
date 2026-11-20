from dataclasses import dataclass
from fractions import Fraction

from database import transaction
from risk.explain import PieceRisk


V1_PACKET_VERSION = 1


@dataclass(frozen=True)
class InitialReceipt:
    receipt_id: int
    report_id: int
    batch_id: str
    freeze_id: int
    revision_id: int


@dataclass(frozen=True)
class InitialReport:
    report_id: int
    batch_id: str
    freeze_id: int
    revision_id: int
    limit: int
    selected: tuple[str, ...]
    ranked: tuple[PieceRisk, ...]
    receipt: InitialReceipt


@dataclass(frozen=True)
class InitialPacket:
    version: int
    batch_id: str
    report_id: int
    freeze_id: int
    revision_id: int
    limit: int
    selected: tuple[str, ...]
    risks: tuple[tuple[str, Fraction], ...]
    receipt: InitialReceipt


def initialize_reports_schema(db):
    with transaction(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS initial_reports (
                report_id INTEGER PRIMARY KEY,
                batch_id TEXT NOT NULL,
                freeze_id INTEGER NOT NULL,
                revision_id INTEGER NOT NULL,
                review_limit INTEGER NOT NULL CHECK (review_limit > 0),
                FOREIGN KEY (batch_id, freeze_id, revision_id)
                    REFERENCES freezes(batch_id, freeze_id, revision_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS initial_risks (
                report_id INTEGER NOT NULL REFERENCES initial_reports(report_id),
                position INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                score_num TEXT NOT NULL,
                score_den TEXT NOT NULL,
                valid_count INTEGER NOT NULL CHECK (valid_count > 0),
                evidence TEXT NOT NULL,
                PRIMARY KEY (report_id, piece_id),
                UNIQUE (report_id, position)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS initial_selection (
                report_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                PRIMARY KEY (report_id, piece_id),
                UNIQUE (report_id, position),
                FOREIGN KEY (report_id, piece_id) REFERENCES initial_risks(report_id, piece_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS initial_receipts (
                receipt_id INTEGER PRIMARY KEY,
                report_id INTEGER NOT NULL UNIQUE REFERENCES initial_reports(report_id)
            )
        ''')
