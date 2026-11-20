from contextlib import closing
from fractions import Fraction
from threading import Event

from measure.amend import amend_readings
from measure.freeze import freeze
from measure.revisions import load_revision
from reports.export import export_initial
from reports.issue import issue_initial, issue_revision
from reports.read import read_initial, read_revision
from reports.revision_store import get_request
from reports.store import open_analysis
from station.intake import accept_initial, handle_revision
from station.ledger import load_acceptance, load_starts, open_station
from station.progress import station_progress
from station.revision_store import set_handover
from station.start import start_review
from station.schema import PendingStart
from tests.fixtures import (
    GAUGES, ROSTER, READINGS, ReplyDiscarded, WorkflowCase, pause_before,
)
from tests.revision_link import make_exchange


class RevisionCase(WorkflowCase):
    def setUp(self):
        super().setUp()
        _, self.initial_freeze = self.seed()
        self.initial_receipt = issue_initial(self.analysis, 'B', self.initial_freeze)
        self.initial_id = self.initial_receipt.report_id
        self.packet = export_initial(self.analysis, self.initial_id)
        accept_initial(self.station, self.packet)
        first = self._first_revision()
        self.corrected = amend_readings(
            self.analysis, 'B', first.revision_id,
            [('X', 'center', '10', 'mm'), ('Z', 'center', '14', 'mm')],
        )
        self.revision_id = self.corrected.revision_id
        self.corrected_freeze = freeze(self.analysis, 'B', self.revision_id)

    def _first_revision(self):
        return load_revision(self.analysis, 1)

    def exchange(self):
        return lambda message: handle_revision(self.station, message)

    def issue(self, request_id='rev-1'):
        return issue_revision(
            self.analysis, self.exchange(), 'B', self.initial_id,
            self.revision_id, request_id,
        )


class TestRevisionOrdering(RevisionCase):
    def test_started_before_exchange_keeps_x(self):
        start_x = start_review(self.station, 'B', 'X')
        report_id = self.issue()
        report = read_revision(self.analysis, report_id)
        self.assertEqual(report['started_at_activation'], ('X',))
        self.assertEqual(report['selected'], ('X', 'Z'))
        self.assertEqual(
            (report['batch_id'], report['initial_report_id'], report['revision_id'], report['request_id']),
            ('B', self.initial_id, self.revision_id, 'rev-1'),
        )
        progress = station_progress(self.station, 'B')
        self.assertEqual(progress.acceptance_id, 1)
        self.assertEqual(progress.report_id, self.initial_id)
        self.assertEqual((progress.started, progress.pending), (('X',), ('Z',)))
        start_z = start_review(self.station, 'B', 'Z')
        self.assertEqual(start_z.piece_id, 'Z')
        self.assertEqual(start_z.report_id, self.initial_id)
        self.assertNotEqual(start_z.start_id, start_x.start_id)
        with self.assertRaises(ValueError):
            start_review(self.station, 'B', 'Y')
        self.assertEqual(station_progress(self.station, 'B').pending, ())

    def test_exchange_first_selects_y_z(self):
        report_id = self.issue()
        report = read_revision(self.analysis, report_id)
        self.assertEqual(report['started_at_activation'], ())
        self.assertEqual(report['selected'], ('Y', 'Z'))
        progress = station_progress(self.station, 'B')
        self.assertEqual((progress.started, progress.pending), ((), ('Y', 'Z')))
        with self.assertRaises(ValueError):
            start_review(self.station, 'B', 'X')
        start_review(self.station, 'B', 'Y')
        start_review(self.station, 'B', 'Z')
        self.assertEqual(station_progress(self.station, 'B').started, ('Y', 'Z'))

    def test_replay_same_params_returns_same_report(self):
        start_review(self.station, 'B', 'X')
        first_id = self.issue()
        second_id = issue_revision(
            self.analysis, self.exchange(), 'B', self.initial_id, self.revision_id, 'rev-1',
        )
        self.assertEqual(first_id, second_id)
        # Later starts and further amendments must not change stored values.
        start_review(self.station, 'B', 'Z')
        later = amend_readings(self.analysis, 'B', self.revision_id,
                               [('Y', 'center', '20', 'mm')])
        freeze(self.analysis, 'B', later.revision_id)
        replay = read_revision(self.analysis, second_id)
        self.assertEqual((replay['started_at_activation'], replay['selected']),
                         (('X',), ('X', 'Z')))
        self.assertEqual(replay['revision_id'], self.revision_id)
        self.assertEqual(read_initial(self.analysis, self.initial_id).selected, ('X', 'Y'))

    def test_progress_after_reopen(self):
        start_review(self.station, 'B', 'X')
        self.issue()
        self.reopen_analysis()
        self.reopen_station()
        progress = station_progress(self.station, 'B')
        self.assertEqual((progress.report_id, progress.started, progress.pending),
                         (self.initial_id, ('X',), ('Z',)))
        start_review(self.station, 'B', 'Z')
        self.reopen_station()
        self.assertEqual(station_progress(self.station, 'B').started, ('X', 'Z'))

    def test_start_while_analysis_closed(self):
        start_review(self.station, 'B', 'X')
        self.issue()
        self.close_analysis()
        record = start_review(self.station, 'B', 'Z')
        self.assertEqual(record.piece_id, 'Z')
        with self.assertRaises(ValueError):
            start_review(self.station, 'B', 'Y')


class TestHandover(RevisionCase):
    def test_pending_then_activate(self):
        set_handover(self.station, 'B', True)
        result = self.issue()
        self.assertEqual(result, 'pending')
        self.assertEqual(get_request(self.analysis, 'rev-1')[4], 'pending')
        # No activation row and no new starts while paused.
        self.assertEqual(station_progress(self.station, 'B').pending, ('X', 'Y'))
        pending_start = start_review(self.station, 'B', 'Y')
        self.assertIsInstance(pending_start, PendingStart)
        self.assertEqual(load_starts(self.station, load_acceptance(self.station, 'B')), ())
        # Replay still pending during the handover.
        self.assertEqual(self.issue(), 'pending')
        set_handover(self.station, 'B', False)
        report_id = self.issue()
        self.assertIsInstance(report_id, int)
        report = read_revision(self.analysis, report_id)
        self.assertEqual((report['started_at_activation'], report['selected']), ((), ('Y', 'Z')))
        # The paused start left no record; Y still needs a real start.
        start_review(self.station, 'B', 'Y')
        self.assertEqual(station_progress(self.station, 'B').started, ('Y',))
    def test_pending_with_existing_start(self):
        start_review(self.station, 'B', 'X')
        set_handover(self.station, 'B', True)
        self.assertEqual(self.issue(), 'pending')
        pending = start_review(self.station, 'B', 'Y')
        self.assertIsInstance(pending, PendingStart)
        set_handover(self.station, 'B', False)
        report_id = self.issue()
        report = read_revision(self.analysis, report_id)
        self.assertEqual((report['started_at_activation'], report['selected']),
                         (('X',), ('X', 'Z')))

    def test_exchange_waits_while_start_is_paused(self):
        entered, resume = Event(), Event()

        def deliver(message):
            with closing(open_station(self.station_path)) as station_db:
                return handle_revision(station_db, message)

        ordered = pause_before(deliver, entered, resume)
        with closing(open_station(self.station_path)) as control:
            set_handover(control, 'B', True)
        # Each connection stays in its own thread while the call is in flight.
        self.close_station()
        self.close_analysis()
        from concurrent.futures import ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=1) as worker:
                future = worker.submit(self._issue_from_fresh_connection, ordered)
                self.assertTrue(entered.wait(10))
                # During the pause, a new start is deferred without a record.
                with closing(open_station(self.station_path)) as side:
                    deferred = start_review(side, 'B', 'X')
                self.assertIsInstance(deferred, PendingStart)
                resume.set()
                self.assertEqual(future.result(timeout=10), 'pending')
        finally:
            self.reopen_analysis()
            self.reopen_station()
        with closing(open_station(self.station_path)) as control:
            set_handover(control, 'B', False)
        report_id = self.issue()
        self.assertEqual(read_revision(self.analysis, report_id)['selected'], ('Y', 'Z'))

    def _issue_from_fresh_connection(self, exchange):
        with closing(open_analysis(self.analysis_path)) as analysis:
            return issue_revision(analysis, exchange, 'B', self.initial_id,
                                  self.revision_id, 'rev-1')


class TestDroppedReply(RevisionCase):
    def _link(self, *, drop):
        return make_exchange(
            lambda: open_station(self.station_path),
            handle_revision, drop_after_applied=drop,
        )

    def test_dropped_applied_reply_continues_with_same_ruling(self):
        start_review(self.station, 'B', 'X')
        exchange = self._link(drop=True)
        with self.assertRaises(ReplyDiscarded):
            issue_revision(self.analysis, exchange, 'B', self.initial_id,
                           self.revision_id, 'rev-1')
        # The station ruling is already in force; the analysis side never signed.
        self.reopen_station()
        self.assertEqual(station_progress(self.station, 'B').pending, ('Z',))
        # A fresh callable reconnects to the same station database.
        new_exchange = self._link(drop=False)
        # Station keeps working while the analysis host is offline.
        self.close_analysis()
        start_z = start_review(self.station, 'B', 'Z')
        self.assertEqual(start_z.piece_id, 'Z')
        with self.assertRaises(ValueError):
            start_review(self.station, 'B', 'Y')
        self.reopen_analysis()
        # Another amendment after the lost reply must not alter the fixed ruling.
        later = amend_readings(self.analysis, 'B', self.revision_id,
                               [('Y', 'center', '20', 'mm')])
        freeze(self.analysis, 'B', later.revision_id)
        self.reopen_analysis()
        self.reopen_station()
        report_id = issue_revision(self.analysis, new_exchange, 'B', self.initial_id,
                                   self.revision_id, 'rev-1')
        report = read_revision(self.analysis, report_id)
        self.assertEqual((report['started_at_activation'], report['selected']),
                         (('X',), ('X', 'Z')))
        self.assertEqual(report['revision_id'], self.revision_id)
        # Repeating the identical request returns the same report number.
        again = issue_revision(self.analysis, self._link(drop=False), 'B',
                               self.initial_id, self.revision_id, 'rev-1')
        self.assertEqual(again, report_id)
        self.assertEqual(read_revision(self.analysis, again), report)

    def test_connection_error_leaves_pending_state(self):
        set_handover(self.station, 'B', True)

        def broken(message):
            raise ConnectionError('station unreachable')

        with self.assertRaises(ConnectionError):
            issue_revision(self.analysis, broken, 'B', self.initial_id,
                           self.revision_id, 'rev-1')
        self.assertIsNone(get_request(self.analysis, 'rev-1'))
        # After recovery the same request proceeds normally.
        outcome = self.issue()
        self.assertEqual(outcome, 'pending')
        set_handover(self.station, 'B', False)
        report_id = self.issue()
        self.assertEqual(read_revision(self.analysis, report_id)['selected'], ('Y', 'Z'))


class TestRevisionErrors(RevisionCase):
    def test_unknown_references_raise_key_error(self):
        exchange = self.exchange()
        with self.assertRaises(KeyError):
            issue_revision(self.analysis, exchange, 'missing', self.initial_id,
                           self.revision_id, 'rev-x')
        with self.assertRaises(KeyError):
            issue_revision(self.analysis, exchange, 'B', 999, self.revision_id, 'rev-x')
        with self.assertRaises(KeyError):
            issue_revision(self.analysis, exchange, 'B', self.initial_id, 999, 'rev-x')
        with self.assertRaises(KeyError):
            read_revision(self.analysis, 999)
        # Station without an acceptance.
        register_other = self._fresh_station()
        with self.assertRaises(KeyError):
            handle_revision(register_other, {
                'kind': 'qingcen.revision/1', 'batch_id': 'B',
                'initial_report_id': self.initial_id, 'revision_id': self.revision_id,
                'request_id': 'rev-x', 'roster': ROSTER, 'limit': 2,
                'ranked': (('Z', Fraction(4)), ('Y', Fraction(3, 2)), ('X', Fraction(0))),
            })
        register_other.close()

    def _fresh_station(self):
        from pathlib import Path
        path = Path(self.station_path).with_name('station-other.sqlite')
        return open_station(path)

    def test_invalid_arguments_raise_value_error(self):
        exchange = self.exchange()
        for kwargs in (
            {'request_id': ' '}, {'request_id': True}, {'request_id': 3},
            {'revision_id': True}, {'revision_id': 0},
            {'initial_report_id': 1.5},
        ):
            params = dict(batch_id='B', initial_report_id=self.initial_id,
                          revision_id=self.revision_id, request_id='rev-bad')
            params.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                issue_revision(self.analysis, exchange, **params)
        with self.assertRaises(ValueError):
            issue_revision(self.analysis, 'not callable', 'B', self.initial_id,
                           self.revision_id, 'rev-bad')

    def test_revision_batch_mismatch(self):
        from lots.register import register_lot
        from measure.import_readings import record_readings
        register_lot(self.analysis, 'C', ROSTER, GAUGES, 2)
        other = record_readings(self.analysis, 'C', 'c-1', READINGS)
        with self.assertRaises(ValueError):
            issue_revision(self.analysis, self.exchange(), 'B', self.initial_id,
                           other.revision_id, 'rev-c')

    def test_initial_report_mismatch_with_acceptance(self):
        second_receipt = issue_initial(self.analysis, 'B', self.corrected_freeze)
        with self.assertRaises(ValueError):
            issue_revision(self.analysis, self.exchange(), 'B', second_receipt.report_id,
                           self.revision_id, 'rev-mismatch')
        self.assertIsNone(get_request(self.analysis, 'rev-mismatch'))

    def test_same_request_id_different_parameters(self):
        self.issue('rev-1')
        with self.assertRaises(ValueError):
            issue_revision(self.analysis, self.exchange(), 'B', self.initial_id,
                           1, 'rev-1')

    def test_second_request_id_for_same_batch(self):
        self.issue('rev-1')
        with self.assertRaises(ValueError):
            self.issue('rev-2')
        # The first ruling still reads back unchanged.
        report = read_revision(self.analysis, 1)
        self.assertEqual(report['request_id'], 'rev-1')

    def test_station_rejects_second_request(self):
        self.issue('rev-1')
        message = {
            'kind': 'qingcen.revision/1', 'batch_id': 'B',
            'initial_report_id': self.initial_id, 'revision_id': self.revision_id,
            'request_id': 'rev-2', 'roster': ROSTER, 'limit': 2,
            'ranked': (('Z', Fraction(4)), ('Y', Fraction(3, 2)), ('X', Fraction(0))),
        }
        with self.assertRaises(ValueError):
            handle_revision(self.station, message)

    def test_unknown_station_acceptance_raises_key_error(self):
        from pathlib import Path
        empty_station = open_station(Path(self.station_path).with_name('station-empty.sqlite'))
        try:
            with self.assertRaises(KeyError):
                issue_revision(
                    self.analysis, lambda message: handle_revision(empty_station, message),
                    'B', self.initial_id, self.revision_id, 'rev-no-acceptance',
                )
        finally:
            empty_station.close()
        self.assertIsNone(get_request(self.analysis, 'rev-no-acceptance'))

    def test_unknown_revision_report_read_raises_key_error(self):
        with self.assertRaises(KeyError):
            read_revision(self.analysis, 4242)

    def test_malformed_station_message(self):
        for bad in ({}, {'kind': 'other'}, {'kind': 'qingcen.revision/1'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                handle_revision(self.station, bad)

    def test_business_rejection_enables_nothing(self):
        from lots.register import register_lot
        from measure.import_readings import record_readings
        register_lot(self.analysis, 'C', ROSTER, GAUGES, 2)
        other = record_readings(self.analysis, 'C', 'c-1', READINGS)
        with self.assertRaises(ValueError):
            issue_revision(self.analysis, self.exchange(), 'B', self.initial_id,
                           other.revision_id, 'rev-dup')
        self.assertIsNone(get_request(self.analysis, 'rev-dup'))
        # Initial workflow and progress remain untouched.
        self.assertEqual(read_initial(self.analysis, self.initial_id).selected, ('X', 'Y'))
        self.assertEqual(station_progress(self.station, 'B').pending, ('X', 'Y'))


class TestRevisionSample(RevisionCase):
    def test_day_shift_sample_tuples(self):
        # The exact REVISION.md example: limit 2, revised order Z, Y, X.
        start_review(self.station, 'B', 'X')
        after = read_revision(self.analysis, self.issue('req-after'))
        self.assertEqual(after['started_at_activation'], ('X',))
        self.assertEqual(after['selected'], ('X', 'Z'))

    def test_day_shift_sample_exchange_first_tuples(self):
        before = read_revision(self.analysis, self.issue('req-before'))
        self.assertEqual(before['started_at_activation'], ())
        self.assertEqual(before['selected'], ('Y', 'Z'))


class TestV1ReplayAfterRevision(RevisionCase):
    def test_v1_packet_replay_still_accepted(self):
        start_review(self.station, 'B', 'X')
        self.issue()
        start_review(self.station, 'B', 'Z')
        # Re-delivering the original V1 packet returns the original acceptance id.
        self.assertEqual(accept_initial(self.station, self.packet), 1)
        record_x = start_review(self.station, 'B', 'X')
        self.assertEqual(record_x.report_id, self.initial_id)
        progress = station_progress(self.station, 'B')
        self.assertEqual((progress.report_id, progress.started, progress.pending),
                         (self.initial_id, ('X', 'Z'), ()))


class TestRevisionCommitRecovery(RevisionCase):
    def test_failed_analysis_commit_can_retry_with_same_request(self):
        import sqlite3
        start_review(self.station, 'B', 'X')
        db = self.analysis
        db.executescript('''
            CREATE TEMP TABLE test_revision_parent (id INTEGER PRIMARY KEY);
            CREATE TEMP TABLE test_revision_gate (
                id INTEGER REFERENCES test_revision_parent(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TEMP TRIGGER test_defer_revision AFTER INSERT ON main.revision_reports
            BEGIN INSERT INTO test_revision_gate VALUES (99); END;
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            self.issue('rev-retry')
        self.assertFalse(db.in_transaction)
        # The station ruling is already effective; no analysis report was signed.
        self.assertEqual(get_request(db, 'rev-retry'), None)
        self.assertEqual(station_progress(self.station, 'B').pending, ('Z',))
        db.execute('DROP TRIGGER test_defer_revision')
        report_id = self.issue('rev-retry')
        report = read_revision(db, report_id)
        self.assertEqual((report['started_at_activation'], report['selected']),
                         (('X',), ('X', 'Z')))
        # A replay still returns the same report and fixed values.
        self.assertEqual(self.issue('rev-retry'), report_id)
        self.assertEqual(read_revision(db, report_id), report)
