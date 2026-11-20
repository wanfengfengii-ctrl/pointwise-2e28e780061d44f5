import json
import sqlite3
from fractions import Fraction

from lots.gauges import GaugeSpec
from lots.register import register_lot
from measure.freeze import freeze
from measure.import_readings import record_readings
from reports.export import export_initial
from reports.issue import issue_initial
from reports.read import read_initial
from risk.ranking import preview_risk
from tests.fixtures import GAUGES, READINGS, REPORT_TABLES, WorkflowCase, counts


class TestReports(WorkflowCase):
    def test_exact_risk_tie_uses_roster(self):
        _, frozen = self.seed(limit=1)
        risk = preview_risk(self.analysis, frozen)
        expected = [['X', '3/2'], ['Y', '3/2'], ['Z', '1']]
        actual = [[entry.piece_id, str(entry.score)] for entry in risk.ranked]
        self.assertEqual(actual, expected)
        receipt = issue_initial(self.analysis, 'B', frozen)
        report = read_initial(self.analysis, receipt.report_id)
        self.assertEqual(report.selected, ('X',))
        self.assertEqual(report.ranked, risk.ranked)
        self.assertEqual(report.receipt, receipt)
        packet = export_initial(self.analysis, receipt.report_id)
        self.assertEqual(packet.selected, ('X',))
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'T3', 'input': {'roster': ['X', 'Y', 'Z'], 'limit': 1, 'rows': READINGS},
            'expected': expected, 'actual': actual,
            'downstream_expected': ['X'], 'downstream_actual': list(packet.selected),
            'code_paths': ['risk/units.py', 'risk/ranking.py', 'reports/issue.py', 'reports/export.py'],
            'oracle': '10 mm and 0 um baselines give residuals (3,0), (1,2), and (1). X wins the tie by roster order.',
        }))

    def test_mixed_units(self):
        db = self.analysis
        register_lot(db, 'B', ('X', 'Y', 'Z'), (GaugeSpec('center', 1, 'cm'), GAUGES[1]), 1)
        rows = list(READINGS)
        rows[0] = ('X', 'center', '13/1000', 'm')
        rows[3] = ('Y', 'edge', '-2000', 'um')
        revision = record_readings(db, 'B', 'mixed', rows)
        frozen = freeze(db, 'B', revision.revision_id)
        by_piece = {risk.piece_id: risk for risk in preview_risk(db, frozen).ranked}
        center = by_piece['X'].evidence[0]
        edge = by_piece['Y'].evidence[1]
        self.assertEqual((center.value, center.unit), (Fraction(13, 1000), 'm'))
        self.assertEqual((center.normalized_mm, center.baseline_mm, center.residual_mm), (13, 10, 3))
        self.assertEqual((edge.normalized_mm, edge.baseline_mm, edge.residual_mm), (-2, 0, 2))
        self.assertEqual(by_piece['X'].score, Fraction(3, 2))
        self.assertEqual(by_piece['Y'].score, Fraction(3, 2))
        self.assertEqual(export_initial(db, issue_initial(db, 'B', frozen).report_id).selected, ('X',))

    def test_nonlexical_tie(self):
        _, frozen = self.seed(roster=('Y', 'X', 'Z'), limit=1)
        report = read_initial(self.analysis, issue_initial(self.analysis, 'B', frozen).report_id)
        self.assertEqual([risk.piece_id for risk in report.ranked], ['Y', 'X', 'Z'])
        self.assertEqual(report.selected, ('Y',))

    def test_partial_missing(self):
        _, frozen = self.seed(rows=READINGS[1:])
        risks = {risk.piece_id: risk for risk in preview_risk(self.analysis, frozen).ranked}
        self.assertEqual((risks['X'].valid_count, risks['X'].score), (1, 0))
        self.assertEqual([point.state for point in risks['X'].evidence], ['unreported', 'valid'])
        self.assertEqual((risks['Z'].valid_count, risks['Z'].score), (1, 1))
        missing = risks['Z'].evidence[1]
        self.assertEqual((missing.state, missing.value, missing.residual_mm), ('missing', None, None))

    def test_export_fixed_packet(self):
        revision, frozen = self.seed()
        receipt = issue_initial(self.analysis, 'B', frozen)
        packet = export_initial(self.analysis, receipt.report_id)
        self.assertEqual((packet.version, packet.batch_id, packet.report_id), (1, 'B', receipt.report_id))
        self.assertEqual((packet.freeze_id, packet.revision_id, packet.limit), (frozen, revision.revision_id, 2))
        self.assertEqual(packet.selected, ('X', 'Y'))
        self.assertEqual(packet.risks, (('X', Fraction(3, 2)), ('Y', Fraction(3, 2))))
        self.assertEqual(packet.receipt, receipt)
        with self.assertRaises(KeyError):
            export_initial(self.analysis, 999)

    def test_all_missing_piece_blocks_issue(self):
        _, frozen = self.seed(rows=READINGS[:4] + (('Z', 'center', None, None), ('Z', 'edge', None, None)))
        with self.assertRaises(ValueError):
            issue_initial(self.analysis, 'B', frozen)
        self.assertEqual(counts(self.analysis, REPORT_TABLES), (0, 0, 0, 0))

    def test_preview_all_missing(self):
        _, frozen = self.seed(rows=READINGS[:4] + (('Z', 'edge', None, None),))
        with self.assertRaises(ValueError):
            preview_risk(self.analysis, frozen)
        self.assertEqual(counts(self.analysis, REPORT_TABLES), (0, 0, 0, 0))

    def test_invalid_issue_reference(self):
        _, frozen = self.seed()
        register_lot(self.analysis, 'C', ('Q',), GAUGES, 1)
        for batch, version in [('missing', frozen), ('B', 999)]:
            with self.assertRaises(KeyError):
                issue_initial(self.analysis, batch, version)
        with self.assertRaises(ValueError):
            issue_initial(self.analysis, 'C', frozen)
        self.assertEqual(counts(self.analysis, REPORT_TABLES), (0, 0, 0, 0))

    def test_failed_commit_can_retry(self):
        db = self.analysis
        _, frozen = self.seed()
        db.executescript('''
            CREATE TEMP TABLE test_receipt_parent (id INTEGER PRIMARY KEY);
            CREATE TEMP TABLE test_receipt_gate (
                id INTEGER REFERENCES test_receipt_parent(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TEMP TRIGGER test_defer_receipt AFTER INSERT ON main.initial_receipts
            BEGIN INSERT INTO test_receipt_gate VALUES (99); END;
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            issue_initial(db, 'B', frozen)
        self.assertFalse(db.in_transaction)
        self.assertEqual(counts(db, REPORT_TABLES), (0, 0, 0, 0))
        self.assertEqual(counts(db, ('test_receipt_gate',)), (0,))
        db.execute('DROP TRIGGER test_defer_receipt')
        receipt = issue_initial(db, 'B', frozen)
        self.assertEqual(counts(db, REPORT_TABLES), (1, 3, 2, 1))
        complete = read_initial(db, receipt.report_id)
        packet = export_initial(db, receipt.report_id)
        self.assertEqual(complete.receipt, receipt)
        self.assertEqual(complete.ranked, preview_risk(db, frozen).ranked)
        self.assertEqual((packet.selected, packet.receipt, packet.freeze_id), (('X', 'Y'), receipt, frozen))
