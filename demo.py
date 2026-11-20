import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from lots.gauges import GaugeSpec
from lots.register import register_lot
from measure.amend import amend_readings
from measure.freeze import freeze
from measure.import_readings import record_readings
from reports.export import export_initial
from reports.issue import issue_initial
from reports.read import read_initial
from reports.store import open_analysis
from risk.ranking import preview_risk
from station.intake import accept_initial
from station.ledger import open_station
from station.progress import station_progress
from station.start import start_review


def main():
    path = Path(__file__).with_name('examples') / 'day_shift.json'
    sample = json.loads(path.read_text(encoding='utf-8'))
    batch = sample['batch_id']
    with TemporaryDirectory(prefix='qingcen-day-') as directory:
        analysis_path = Path(directory) / 'analysis.sqlite'
        station_path = Path(directory) / 'station.sqlite'
        with closing(open_analysis(analysis_path)) as analysis:
            register_lot(analysis, batch, sample['roster'],
                         [GaugeSpec(*row) for row in sample['gauges']], sample['limit'])
            base = record_readings(analysis, batch, sample['ticket'], sample['readings'])
            initial_freeze = freeze(analysis, batch, base.revision_id)
            receipt = issue_initial(analysis, batch, initial_freeze)
            original = read_initial(analysis, receipt.report_id)
            packet = export_initial(analysis, receipt.report_id)
        with closing(open_station(station_path)) as station:
            accepted = accept_initial(station, packet)
            started = start_review(station, batch, 'X')
            assert start_review(station, batch, 'X') == started
        with closing(open_analysis(analysis_path)) as analysis:
            corrected = amend_readings(analysis, batch, base.revision_id, sample['corrections'])
            corrected_freeze = freeze(analysis, batch, corrected.revision_id)
        with closing(open_analysis(analysis_path)) as analysis:
            saved = read_initial(analysis, receipt.report_id)
            latest = preview_risk(analysis, corrected_freeze)
            assert saved == original
            assert export_initial(analysis, receipt.report_id) == packet
            assert saved.revision_id == base.revision_id and latest.revision_id == corrected.revision_id
        with closing(open_station(station_path)) as station:
            progress = station_progress(station, batch)
            assert accept_initial(station, packet) == accepted
            assert start_review(station, batch, 'X') == started
            try:
                start_review(station, batch, 'Z')
            except ValueError:
                pass
            else:
                raise AssertionError('a preview changed station eligibility')
            assert station_progress(station, batch) == progress

    expected = {'original': [['X', '3/2'], ['Y', '3/2'], ['Z', '1']],
                'corrected': [['Z', '4'], ['Y', '3/2'], ['X', '0']]}
    actual = {
        'original': [[risk.piece_id, str(risk.score)] for risk in saved.ranked],
        'corrected': [[risk.piece_id, str(risk.score)] for risk in latest.ranked],
    }
    downstream_expected = {'selected': ['X', 'Y'], 'started': ['X'], 'pending': ['Y'], 'same_report': True}
    downstream_actual = {'selected': list(saved.selected), 'started': list(progress.started),
                         'pending': list(progress.pending), 'same_report': saved.report_id == progress.report_id}
    assert actual == expected
    assert downstream_actual == downstream_expected
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'T8.saved_report_values', 'input': sample, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
        'code_paths': ['measure/amend.py', 'risk/ranking.py', 'reports/read.py', 'station/progress.py'],
        'oracle': '原残差为 X(3,0)、Y(1,2)、Z(1)，勘误只将 X 首点改为 0、Z 首点改为 4。工位只开检原榜的 X。',
    }, ensure_ascii=False))
    print('B 批原榜 X、Y。工位已开检 X，Y 待检。勘误后风险顺序为 Z、Y、X。')


if __name__ == '__main__':
    main()
