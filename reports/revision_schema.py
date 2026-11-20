from database import transaction


def initialize_revision_schema(db):
    with transaction(db):
        db.execute('''
            CREATE TABLE IF NOT EXISTS revision_requests (
                request_id TEXT PRIMARY KEY NOT NULL,
                batch_id TEXT NOT NULL,
                initial_report_id INTEGER NOT NULL,
                revision_id INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('pending', 'applied')),
                report_id INTEGER UNIQUE,
                FOREIGN KEY (batch_id) REFERENCES lots(batch_id),
                FOREIGN KEY (initial_report_id) REFERENCES initial_reports(report_id),
                FOREIGN KEY (revision_id) REFERENCES reading_revisions(revision_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS revision_reports (
                report_id INTEGER PRIMARY KEY,
                batch_id TEXT NOT NULL,
                initial_report_id INTEGER NOT NULL,
                revision_id INTEGER NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                FOREIGN KEY (request_id) REFERENCES revision_requests(request_id),
                FOREIGN KEY (batch_id) REFERENCES lots(batch_id),
                FOREIGN KEY (initial_report_id) REFERENCES initial_reports(report_id),
                FOREIGN KEY (revision_id) REFERENCES reading_revisions(revision_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS revision_started (
                report_id INTEGER NOT NULL,
                batch_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                PRIMARY KEY (report_id, piece_id),
                UNIQUE (report_id, position),
                FOREIGN KEY (report_id) REFERENCES revision_reports(report_id),
                FOREIGN KEY (batch_id, piece_id) REFERENCES lot_pieces(batch_id, piece_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS revision_selection (
                report_id INTEGER NOT NULL,
                batch_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                piece_id TEXT NOT NULL,
                PRIMARY KEY (report_id, piece_id),
                UNIQUE (report_id, position),
                FOREIGN KEY (report_id) REFERENCES revision_reports(report_id),
                FOREIGN KEY (batch_id, piece_id) REFERENCES lot_pieces(batch_id, piece_id)
            )
        ''')
