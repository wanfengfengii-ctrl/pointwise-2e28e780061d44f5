from fractions import Fraction

from lots.gauges import GaugeSpec
from lots.register import load_lot, register_lot
from measure.freeze import freeze, load_frozen_revision
from measure.import_readings import record_readings
from measure.revisions import load_current_revision
from measure.schema import Reading
from tests.fixtures import GAUGES, MEASURE_TABLES, READINGS, WorkflowCase, counts


class TestReadings(WorkflowCase):
    def test_freeze_distinguishes_zero_and_missing(self):
        rows = [('X', 'center', 0, 'mm'), ('X', 'edge', None, None)]
        revision, frozen = self.seed(rows=rows)
        loaded = load_frozen_revision(self.analysis, frozen)
        self.assertEqual(loaded.revision_id, revision.revision_id)
        self.assertEqual(loaded.readings, (
            Reading('X', 'center', Fraction(0), 'mm'), Reading('X', 'edge', None, None),
        ))
        self.assertEqual(tuple(row.state for row in loaded.readings), ('valid', 'missing'))
        self.assertEqual(freeze(self.analysis, 'B', revision.revision_id), frozen)

    def test_fixed_lot_definition(self):
        db = self.analysis
        original = register_lot(db, 'B', ['Y', 'X'], GAUGES, 1)
        self.assertEqual(register_lot(db, 'B', ('Y', 'X'), GAUGES, 1), original)
        for roster, gauges, limit in (
            (['X', 'Y'], GAUGES, 1), (['Y', 'X'], GAUGES, 2),
            (['Y', 'Y'], GAUGES, 1), (['Y', 'X'], GAUGES, True),
            (['Y', 'X'], [GaugeSpec('center', 'NaN', 'mm')], 1),
            (['Y', 'X'], [GAUGES[0], GAUGES[0]], 1),
        ):
            with self.subTest(roster=roster, gauges=gauges, limit=limit), self.assertRaises(ValueError):
                register_lot(db, 'B', roster, gauges, limit)
        revision = record_readings(db, 'B', 'usable', READINGS[:4])
        self.assertEqual(load_lot(db, 'B').roster, ('Y', 'X'))
        self.assertEqual(load_lot(db, 'B').limit, 1)
        self.assertEqual(load_frozen_revision(db, freeze(db, 'B', revision.revision_id)).revision, revision)

    def test_ticket_replay(self):
        db = self.analysis
        first, _ = self.seed()
        second = record_readings(db, 'B', 'day-2', [('Y', 'center', 12, 'mm')])
        normalized = list(reversed(READINGS))
        normalized[-1] = ('X', 'center', '13.000', 'mm')
        self.assertEqual(record_readings(db, 'B', 'day-1', normalized), first)
        with self.assertRaises(ValueError):
            record_readings(db, 'B', 'day-1', [('X', 'center', 14, 'mm')])
        self.assertEqual(load_current_revision(db, 'B'), second)
        self.assertEqual(second.parent_id, first.revision_id)
        self.assertEqual(len(second.readings), 1)
        self.assertEqual(counts(db, MEASURE_TABLES), (2, 7, 1, 2))

    def test_bad_last_row_rejects_batch(self):
        db = self.analysis
        register_lot(db, 'B', ('X', 'Y'), GAUGES, 1)
        with self.assertRaises(ValueError):
            record_readings(db, 'B', 'late-error', [('X', 'center', 11, 'mm'), ('Y', 'unknown', 6, 'mm')])
        self.assertIsNone(load_current_revision(db, 'B'))
        self.assertEqual(counts(db, MEASURE_TABLES), (0, 0, 0, 0))

    def test_bad_tail_keeps_head(self):
        db = self.analysis
        first, frozen = self.seed()
        before = counts(db, MEASURE_TABLES)
        valid = [('X', 'edge', 0, 'um'), ('Z', 'edge', None, None)]
        with self.assertRaises(ValueError):
            record_readings(db, 'B', 'day-2', valid + [('X', 'unknown', 1, 'mm')])
        self.assertEqual(counts(db, MEASURE_TABLES), before)
        self.assertEqual(load_current_revision(db, 'B'), first)
        self.assertEqual(load_frozen_revision(db, frozen).revision, first)
        repaired = record_readings(db, 'B', 'day-2', valid + [('Y', 'center', 12, 'mm')])
        self.assertEqual(load_current_revision(db, 'B'), repaired)
        self.assertEqual(repaired.parent_id, first.revision_id)
        self.assertEqual(len(repaired.readings), 3)
        self.assertEqual(counts(db, MEASURE_TABLES), (2, 9, 1, 2))

    def test_historical_freeze(self):
        db = self.analysis
        register_lot(db, 'B', ('X',), GAUGES, 1)
        first = record_readings(db, 'B', 'a', [('X', 'center', 0, 'mm')])
        second = record_readings(db, 'B', 'b', [('X', 'edge', None, None)])
        old_freeze = freeze(db, 'B', first.revision_id)
        self.assertEqual(load_frozen_revision(db, old_freeze).readings, (Reading('X', 'center', Fraction(0), 'mm'),))
        self.assertEqual(load_current_revision(db, 'B'), second)
        self.assertNotEqual(freeze(db, 'B', second.revision_id), old_freeze)

    def test_freeze_reference_errors(self):
        revision, _ = self.seed()
        register_lot(self.analysis, 'C', ('X',), GAUGES, 1)
        with self.assertRaises(KeyError):
            freeze(self.analysis, 'B', 999)
        with self.assertRaises(ValueError):
            freeze(self.analysis, 'C', revision.revision_id)
        self.assertEqual(counts(self.analysis, ('freezes',)), (1,))

    def test_invalid_reading_rows_leave_ticket_unused(self):
        db = self.analysis
        first, _ = self.seed()
        for rows in (
            [('absent', 'center', 8, 'mm')], [('X', 'edge', None, 'um')],
            [('X', 'center', float('inf'), 'mm')], [('X', 'center', 3, 'km')],
            [('X', 'center', True, 'mm')], [READINGS[0], READINGS[0]],
        ):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                record_readings(db, 'B', 'repaired', rows)
        with self.assertRaises(KeyError):
            record_readings(db, 'missing', 'repaired', READINGS)
        self.assertEqual(load_current_revision(db, 'B'), first)
        self.assertEqual(counts(db, MEASURE_TABLES), (1, 6, 1, 1))
        self.assertEqual(record_readings(db, 'B', 'repaired', [READINGS[0]]).parent_id, first.revision_id)
