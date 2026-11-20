import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from lots.gauges import GaugeSpec
from lots.register import register_lot
from measure.freeze import freeze
from measure.import_readings import record_readings
from reports.export import export_initial
from reports.issue import issue_initial
from reports.store import open_analysis
from station.ledger import open_station


GAUGES = (GaugeSpec('center', '10', 'mm'), GaugeSpec('edge', 0, 'um'))
ROSTER = ('X', 'Y', 'Z')
READINGS = (
    ('X', 'center', '13', 'mm'), ('X', 'edge', '0', 'um'),
    ('Y', 'center', '11', 'mm'), ('Y', 'edge', '2000', 'um'),
    ('Z', 'center', '11', 'mm'), ('Z', 'edge', None, None),
)
REPORT_TABLES = ('initial_reports', 'initial_risks', 'initial_selection', 'initial_receipts')
MEASURE_TABLES = ('reading_revisions', 'revision_readings', 'reading_heads', 'import_tickets')


def counts(db, tables):
    return tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables)


class ReplyDiscarded(ConnectionError):
    """The invocation succeeded but its return value was discarded."""


def discard_first_success(call):
    lock = Lock()
    discarded = False

    def invoke(*args, **kwargs):
        nonlocal discarded
        value = call(*args, **kwargs)
        with lock:
            if not discarded:
                discarded = True
                raise ReplyDiscarded('successful response discarded')
        return value

    return invoke


def pause_before(call, entered, resume, *, timeout=10):
    def invoke(*args, **kwargs):
        entered.set()
        if not resume.wait(timeout):
            raise TimeoutError('test did not release the call')
        return call(*args, **kwargs)

    return invoke


class WorkflowCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='qingcen-test-')
        self.addCleanup(directory.cleanup)
        self.analysis_path = Path(directory.name) / 'analysis.sqlite'
        self.station_path = Path(directory.name) / 'station.sqlite'
        self.analysis = None
        self.station = None
        self.addCleanup(self.close_analysis)
        self.addCleanup(self.close_station)
        self.reopen_analysis()
        self.reopen_station()

    def close_analysis(self):
        if self.analysis is not None:
            self.analysis.close()
            self.analysis = None

    def close_station(self):
        if self.station is not None:
            self.station.close()
            self.station = None

    def reopen_analysis(self):
        self.close_analysis()
        self.analysis = open_analysis(self.analysis_path)

    def reopen_station(self):
        self.close_station()
        self.station = open_station(self.station_path)

    def seed(self, *, batch='B', roster=ROSTER, limit=2, rows=READINGS):
        register_lot(self.analysis, batch, roster, GAUGES, limit)
        revision = record_readings(self.analysis, batch, 'day-1', rows)
        return revision, freeze(self.analysis, batch, revision.revision_id)

    def packet(self):
        _, frozen = self.seed()
        receipt = issue_initial(self.analysis, 'B', frozen)
        return export_initial(self.analysis, receipt.report_id)
