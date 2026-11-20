from fractions import Fraction

from lots.register import load_lot
from measure.amend import amend_readings
from measure.freeze import freeze
from measure.revisions import load_current_revision
from reports.export import export_initial
from reports.issue import issue_initial
from reports.read import read_initial
from risk.ranking import preview_risk
from station.intake import accept_initial
from station.progress import station_progress
from station.start import start_review
from tests.fixtures import MEASURE_TABLES, REPORT_TABLES, WorkflowCase, counts


class TestHistory(WorkflowCase):
    def test_amendment_keeps_initial_basis(self):
        first, original_freeze = self.seed()
        receipt = issue_initial(self.analysis, 'B', original_freeze)
        original = read_initial(self.analysis, receipt.report_id)
        accept_initial(self.station, export_initial(self.analysis, receipt.report_id))
        start_review(self.station, 'B', 'X')
        second = amend_readings(self.analysis, 'B', first.revision_id, [('Y', 'center', 15, 'mm')])
        revised_freeze = freeze(self.analysis, 'B', second.revision_id)
        self.reopen_analysis()
        self.reopen_station()
        new = preview_risk(self.analysis, revised_freeze)
        self.assertEqual([risk.piece_id for risk in new.ranked], ['Y', 'X', 'Z'])
        self.assertEqual(new.ranked[0].score, Fraction(7, 2))
        self.assertEqual(read_initial(self.analysis, receipt.report_id), original)
        self.assertEqual((original.freeze_id, original.revision_id, original.selected),
                         (original_freeze, first.revision_id, ('X', 'Y')))
        state = station_progress(self.station, 'B')
        self.assertEqual((state.report_id, state.started, state.pending), (receipt.report_id, ('X',), ('Y',)))

    def test_stale_parent(self):
        first, old = self.seed()
        second = amend_readings(self.analysis, 'B', first.revision_id, [('Z', 'center', 14, 'mm')])
        before = counts(self.analysis, MEASURE_TABLES)
        with self.assertRaises(ValueError):
            amend_readings(self.analysis, 'B', first.revision_id, [('X', 'center', 20, 'mm')])
        self.assertEqual(load_current_revision(self.analysis, 'B'), second)
        self.assertEqual(counts(self.analysis, MEASURE_TABLES), before)
        result = preview_risk(self.analysis, freeze(self.analysis, 'B', second.revision_id))
        self.assertEqual((result.ranked[0].piece_id, result.ranked[0].score), ('Z', Fraction(4)))
        self.assertEqual(preview_risk(self.analysis, old).ranked[0].piece_id, 'X')

    def test_amend_reference_errors(self):
        first, _ = self.seed()
        other, _ = self.seed(batch='C')
        before = counts(self.analysis, MEASURE_TABLES)
        valid = [('X', 'center', 14, 'mm')]
        for batch, parent in [('B', 999), ('unknown', first.revision_id)]:
            with self.assertRaises(KeyError):
                amend_readings(self.analysis, batch, parent, valid)
        with self.assertRaises(ValueError):
            amend_readings(self.analysis, 'B', other.revision_id, valid)
        with self.assertRaises(ValueError):
            amend_readings(self.analysis, 'B', first.revision_id, valid + [('X', 'unknown', 1, 'mm')])
        self.assertEqual(counts(self.analysis, MEASURE_TABLES), before)
        self.assertEqual(load_current_revision(self.analysis, 'B'), first)
        self.assertEqual(load_current_revision(self.analysis, 'C'), other)

    def test_old_freeze(self):
        old, original_freeze = self.seed()
        new = amend_readings(self.analysis, 'B', old.revision_id,
                             [('X', 'center', 10, 'mm'), ('Z', 'center', 14, 'mm')])
        revised_freeze = freeze(self.analysis, 'B', new.revision_id)
        self.reopen_analysis()
        previous = preview_risk(self.analysis, original_freeze)
        current = preview_risk(self.analysis, revised_freeze)
        self.assertEqual((previous.revision_id, current.revision_id), (old.revision_id, new.revision_id))
        self.assertEqual([entry.piece_id for entry in previous.ranked], ['X', 'Y', 'Z'])
        self.assertEqual([entry.piece_id for entry in current.ranked], ['Z', 'Y', 'X'])
        self.assertEqual(previous.ranked[0].evidence[0].residual_mm, Fraction(3))
        self.assertEqual(current.ranked[-1].evidence[0].residual_mm, Fraction(0))
        self.assertEqual(current.ranked[0].evidence[0].residual_mm, Fraction(4))
        self.assertEqual(current.ranked[0].evidence[1].state, 'missing')

    def test_unknown_preview(self):
        self.seed()
        with self.assertRaises(KeyError):
            preview_risk(self.analysis, 999)

    def test_saved_report_values(self):
        old, original_freeze = self.seed()
        receipt = issue_initial(self.analysis, 'B', original_freeze)
        saved = read_initial(self.analysis, receipt.report_id)
        packet = export_initial(self.analysis, receipt.report_id)
        accept_initial(self.station, packet)
        start = start_review(self.station, 'B', 'X')
        amended = amend_readings(self.analysis, 'B', old.revision_id, [('Z', 'center', 14, 'mm')])
        revised_freeze = freeze(self.analysis, 'B', amended.revision_id)
        self.reopen_analysis()
        self.reopen_station()
        self.assertEqual(preview_risk(self.analysis, revised_freeze).ranked[0].piece_id, 'Z')
        self.assertEqual(read_initial(self.analysis, receipt.report_id), saved)
        self.assertEqual(export_initial(self.analysis, receipt.report_id), packet)
        state = station_progress(self.station, 'B')
        self.assertEqual((state.report_id, state.started, state.pending), (saved.report_id, ('X',), ('Y',)))
        self.assertEqual(start_review(self.station, 'B', 'X'), start)
        with self.assertRaises(ValueError):
            start_review(self.station, 'B', 'Z')

    def test_repeat_initialization(self):
        old, frozen = self.seed(roster=('Y', 'X', 'Z'))
        lot = load_lot(self.analysis, 'B')
        receipt = issue_initial(self.analysis, 'B', frozen)
        saved = read_initial(self.analysis, receipt.report_id)
        packet = export_initial(self.analysis, receipt.report_id)
        accepted = accept_initial(self.station, packet)
        started = start_review(self.station, 'B', 'Y')
        current = amend_readings(self.analysis, 'B', old.revision_id, [('Z', 'center', 15, 'mm')])
        amended_freeze = freeze(self.analysis, 'B', current.revision_id)
        for _ in range(2):
            self.reopen_analysis()
            self.reopen_station()
            self.assertEqual(load_lot(self.analysis, 'B'), lot)
            self.assertEqual(load_current_revision(self.analysis, 'B'), current)
            self.assertEqual(preview_risk(self.analysis, frozen).ranked[0].piece_id, 'Y')
            self.assertEqual(preview_risk(self.analysis, amended_freeze).ranked[0].score, Fraction(5))
            self.assertEqual(read_initial(self.analysis, receipt.report_id), saved)
            self.assertEqual(accept_initial(self.station, packet), accepted)
            self.assertEqual(start_review(self.station, 'B', 'Y'), started)
            progress = station_progress(self.station, 'B')
            self.assertEqual((progress.started, progress.pending), (('Y',), ('X',)))
        self.assertEqual(counts(self.analysis, REPORT_TABLES), (1, 3, 2, 1))
        self.assertEqual(counts(self.station, ('station_acceptances', 'station_starts')), (1, 1))
