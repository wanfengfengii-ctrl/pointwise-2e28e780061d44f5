from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from fractions import Fraction
from threading import Event

from measure.amend import amend_readings
from measure.freeze import freeze
from measure.revisions import load_current_revision
from reports.export import export_initial
from reports.issue import issue_initial
from reports.read import read_initial
from station.intake import accept_initial
from station.ledger import open_station
from station.progress import station_progress
from station.start import start_review
from tests.fixtures import ReplyDiscarded, WorkflowCase, counts, discard_first_success, pause_before


class TestStation(WorkflowCase):
    def test_offline_intake_and_start(self):
        packet = self.packet()
        accepted = accept_initial(self.station, packet)
        self.assertEqual(accept_initial(self.station, packet), accepted)
        self.close_analysis()
        record = start_review(self.station, 'B', 'X')
        self.assertEqual(record, start_review(self.station, 'B', 'X'))
        progress = station_progress(self.station, 'B')
        self.assertEqual((progress.report_id, progress.acceptance_id), (packet.report_id, accepted))
        self.assertEqual((progress.started, progress.pending), (('X',), ('Y',)))
        self.assertEqual(counts(self.station, ('station_starts',)), (1,))

    def test_restart_offline_replay(self):
        packet = self.packet()
        self.close_analysis()
        accepted = accept_initial(self.station, packet)
        record = start_review(self.station, 'B', 'X')
        self.reopen_station()
        equivalent = replace(packet, selected=list(packet.selected), risks=list(reversed(packet.risks)))
        self.assertEqual(accept_initial(self.station, equivalent), accepted)
        self.assertEqual(start_review(self.station, 'B', 'X'), record)
        self.assertEqual(station_progress(self.station, 'B').pending, ('Y',))
        self.assertEqual(counts(self.station, ('station_acceptances', 'station_starts')), (1, 1))

    def test_last_eligible_started(self):
        packet = self.packet()
        accept_initial(self.station, packet)
        start_review(self.station, 'B', 'Y')
        last = start_review(self.station, 'B', 'X')
        progress = station_progress(self.station, 'B')
        self.assertEqual((progress.started, progress.pending), (('X', 'Y'), ()))
        self.assertEqual(start_review(self.station, 'B', 'X'), last)
        self.assertEqual(station_progress(self.station, 'B'), progress)
        self.assertEqual(counts(self.station, ('station_starts',)), (2,))

    def test_unknown_original_report(self):
        self.packet()
        with self.assertRaises(KeyError):
            read_initial(self.analysis, 999)

    def test_conflicting_list_and_off_list_start(self):
        packet = self.packet()
        accepted = accept_initial(self.station, packet)
        original = start_review(self.station, 'B', 'X')
        changed = replace(packet, selected=('X', 'Z'), risks=(('X', Fraction(3, 2)), ('Z', Fraction(1))))
        with self.assertRaises(ValueError):
            accept_initial(self.station, changed)
        with self.assertRaises(ValueError):
            start_review(self.station, 'B', 'Z')
        progress = station_progress(self.station, 'B')
        self.assertEqual((progress.acceptance_id, progress.report_id), (accepted, packet.report_id))
        self.assertEqual((progress.started, progress.pending), (('X',), ('Y',)))
        self.assertEqual(start_review(self.station, 'B', 'X'), original)
        self.assertEqual(counts(self.station, ('station_acceptances', 'station_starts')), (1, 1))

    def test_invalid_packet(self):
        packet = self.packet()
        for malformed in (
            replace(packet, receipt=replace(packet.receipt, report_id=packet.report_id + 1)),
            replace(packet, selected=('X', 'X')),
            replace(packet, risks=packet.risks[:1]),
            replace(packet, limit=1),
            replace(packet, version=True),
        ):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                accept_initial(self.station, malformed)
        self.assertEqual(counts(self.station, ('station_acceptances', 'station_selection')), (0, 0))
        self.assertIsInstance(accept_initial(self.station, packet), int)

    def test_same_batch_conflict(self):
        packet = self.packet()
        accepted = accept_initial(self.station, packet)
        opening = start_review(self.station, 'B', 'X')
        parent = load_current_revision(self.analysis, 'B')
        amended = amend_readings(self.analysis, 'B', parent.revision_id, [('Z', 'center', 14, 'mm')])
        frozen = freeze(self.analysis, 'B', amended.revision_id)
        replacement = export_initial(self.analysis, issue_initial(self.analysis, 'B', frozen).report_id)
        self.assertEqual(replacement.selected, ('Z', 'X'))
        self.close_analysis()
        with self.assertRaises(ValueError):
            accept_initial(self.station, replacement)
        state = station_progress(self.station, 'B')
        self.assertEqual((state.acceptance_id, state.report_id), (accepted, packet.report_id))
        self.assertEqual((state.started, state.pending), (('X',), ('Y',)))
        self.assertEqual(start_review(self.station, 'B', 'X'), opening)
        self.assertEqual(start_review(self.station, 'B', 'Y').report_id, packet.report_id)

    def test_unknown_station_batch(self):
        with self.assertRaises(KeyError):
            start_review(self.station, 'unknown', 'X')
        with self.assertRaises(KeyError):
            station_progress(self.station, 'unknown')
        self.assertEqual(counts(self.station, ('station_starts',)), (0,))

    def test_successful_intake_reply_can_be_discarded(self):
        packet = self.packet()
        self.close_analysis()
        entered, resume = Event(), Event()

        def deliver():
            with closing(open_station(self.station_path)) as station:
                return accept_initial(station, packet)

        invoke = pause_before(discard_first_success(deliver), entered, resume)
        with ThreadPoolExecutor(max_workers=1) as worker:
            future = worker.submit(invoke)
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaises(KeyError):
                    station_progress(self.station, 'B')
            finally:
                resume.set()
            with self.assertRaises(ReplyDiscarded):
                future.result(timeout=10)
        self.reopen_station()
        progress = station_progress(self.station, 'B')
        self.assertEqual(accept_initial(self.station, packet), progress.acceptance_id)
        self.assertEqual(progress.pending, ('X', 'Y'))
