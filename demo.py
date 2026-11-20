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
from reports.issue import issue_initial, issue_revision
from reports.read import read_initial, read_revision
from reports.store import open_analysis
from risk.ranking import preview_risk
from station.intake import accept_initial, handle_revision
from station.ledger import open_station
from station.progress import station_progress
from station.start import start_review
from tests.fixtures import ReplyDiscarded
from tests.revision_link import make_exchange


def _prepare(sample, analysis_path, station_path):
    batch = sample['batch_id']
    analysis = open_analysis(analysis_path)
    register_lot(analysis, batch, sample['roster'],
                 [GaugeSpec(*row) for row in sample['gauges']], sample['limit'])
    base = record_readings(analysis, batch, sample['ticket'], sample['readings'])
    initial_freeze = freeze(analysis, batch, base.revision_id)
    receipt = issue_initial(analysis, batch, initial_freeze)
    original = read_initial(analysis, receipt.report_id)
    packet = export_initial(analysis, receipt.report_id)
    station = open_station(station_path)
    accepted = accept_initial(station, packet)
    corrected = amend_readings(analysis, batch, base.revision_id, sample['corrections'])
    corrected_freeze = freeze(analysis, batch, corrected.revision_id)
    latest = preview_risk(analysis, corrected_freeze)
    return {
        'batch': batch, 'analysis': analysis, 'station': station,
        'packet': packet, 'accepted': accepted, 'original': original,
        'initial_id': receipt.report_id, 'revision_id': corrected.revision_id,
        'latest': latest,
    }


def _print_scenario(payload):
    print('POINTWISE_SCENARIO ' + json.dumps(payload, ensure_ascii=False))


def demo_v1(sample, directory):
    """The original V1 day-shift demonstration, kept as the first workflow."""
    analysis_path = Path(directory) / 'v1-analysis.sqlite'
    station_path = Path(directory) / 'v1-station.sqlite'
    world = _prepare(sample, analysis_path, station_path)
    analysis, station = world['analysis'], world['station']
    batch, packet = world['batch'], world['packet']
    started = start_review(station, batch, 'X')
    assert start_review(station, batch, 'X') == started
    analysis.close()
    with closing(open_analysis(analysis_path)) as reopened:
        saved = read_initial(reopened, world['initial_id'])
        assert saved == world['original']
        assert export_initial(reopened, world['initial_id']) == packet
    progress = station_progress(station, batch)
    assert accept_initial(station, packet) == world['accepted']
    try:
        start_review(station, batch, 'Z')
    except ValueError:
        pass
    else:
        raise AssertionError('a preview changed station eligibility')
    assert station_progress(station, batch) == progress
    station.close()

    expected = {'original': [['X', '3/2'], ['Y', '3/2'], ['Z', '1']],
                'corrected': [['Z', '4'], ['Y', '3/2'], ['X', '0']]}
    actual = {
        'original': [[risk.piece_id, str(risk.score)] for risk in saved.ranked],
        'corrected': [[risk.piece_id, str(risk.score)] for risk in world['latest'].ranked],
    }
    downstream_expected = {'selected': ['X', 'Y'], 'started': ['X'], 'pending': ['Y'], 'same_report': True}
    downstream_actual = {'selected': list(saved.selected), 'started': list(progress.started),
                         'pending': list(progress.pending), 'same_report': saved.report_id == progress.report_id}
    assert actual == expected and downstream_actual == downstream_expected
    _print_scenario({
        'case_id': 'T8.saved_report_values', 'input': sample, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
        'code_paths': ['measure/amend.py', 'risk/ranking.py', 'reports/read.py', 'station/progress.py'],
        'oracle': '原残差为 X(3,0)、Y(1,2)、Z(1)，勘误只将 X 首点改为 0、Z 首点改为 4。工位只开检原榜的 X。',
    })
    print('B 批原榜 X、Y。工位已开检 X，Y 待检。勘误后风险顺序为 Z、Y、X。')


def demo_revision_after_start(sample, directory):
    """Ordering one: X is already under review when the revision exchange activates."""
    analysis_path = Path(directory) / 'after-analysis.sqlite'
    station_path = Path(directory) / 'after-station.sqlite'
    world = _prepare(sample, analysis_path, station_path)
    analysis, station = world['analysis'], world['station']
    batch = world['batch']
    start_review(station, batch, 'X')

    def exchange(message):
        return handle_revision(station, message)

    report_id = issue_revision(analysis, exchange, batch, world['initial_id'],
                               world['revision_id'], 'req-after-start')
    report = read_revision(analysis, report_id)
    assert (report['started_at_activation'], report['selected']) == (('X',), ('X', 'Z'))
    # The effective list governs new starts; the dropped Y is refused.
    start_z = start_review(station, batch, 'Z')
    assert start_z.report_id == world['initial_id']
    try:
        start_review(station, batch, 'Y')
    except ValueError:
        pass
    else:
        raise AssertionError('Y must leave the effective list')
    progress = station_progress(station, batch)
    assert (progress.report_id, progress.acceptance_id) == (world['initial_id'], world['accepted'])
    assert (progress.started, progress.pending) == (('X', 'Z'), ())
    analysis.close()
    station.close()
    _print_scenario({
        'case_id': 'R1.exchange_after_start',
        'risk_order': [risk.piece_id for risk in world['latest'].ranked],
        'started_at_activation': list(report['started_at_activation']),
        'effective_selection': list(report['selected']),
        'station_progress': {'started': list(progress.started), 'pending': list(progress.pending)},
        'report_id': report_id, 'request_id': report['request_id'],
        'oracle': 'X 已开检占用原限额，余位按新风险序 Z、Y、X 补足 Z；Y 退出名单。',
    })
    print('换榜在 X 开检后生效：固定已开检 X，生效名单 X、Z；随后开检 Z，Y 被拒。')


def demo_revision_before_start(sample, directory):
    """Ordering two: the revision exchange activates before any start."""
    analysis_path = Path(directory) / 'before-analysis.sqlite'
    station_path = Path(directory) / 'before-station.sqlite'
    world = _prepare(sample, analysis_path, station_path)
    analysis, station = world['analysis'], world['station']
    batch = world['batch']

    def exchange(message):
        return handle_revision(station, message)

    report_id = issue_revision(analysis, exchange, batch, world['initial_id'],
                               world['revision_id'], 'req-before-start')
    report = read_revision(analysis, report_id)
    assert (report['started_at_activation'], report['selected']) == ((), ('Y', 'Z'))
    try:
        start_review(station, batch, 'X')
    except ValueError:
        pass
    else:
        raise AssertionError('X must be off the new effective list')
    start_review(station, batch, 'Y')
    start_review(station, batch, 'Z')
    progress = station_progress(station, batch)
    assert (progress.started, progress.pending) == (('Y', 'Z'), ())
    analysis.close()
    station.close()
    _print_scenario({
        'case_id': 'R2.exchange_before_start',
        'started_at_activation': list(report['started_at_activation']),
        'effective_selection': list(report['selected']),
        'station_progress': {'started': list(progress.started), 'pending': list(progress.pending)},
        'report_id': report_id,
        'oracle': '换榜先完成时无已开检片，直接按新风险序取 Y、Z；原榜首片 X 被拒。',
    })
    print('换榜先于开检生效：生效名单 Y、Z，X 被拒；工位按新名单开检 Y、Z。')


def demo_dropped_reply_continuation(sample, directory):
    """The applied reply is lost; reopening both sides and replaying yields one report."""
    analysis_path = Path(directory) / 'drop-analysis.sqlite'
    station_path = Path(directory) / 'drop-station.sqlite'
    world = _prepare(sample, analysis_path, station_path)
    analysis, station = world['analysis'], world['station']
    batch = world['batch']
    start_review(station, batch, 'X')
    station.close()

    link = make_exchange(lambda: open_station(station_path), handle_revision,
                         drop_after_applied=True)
    try:
        issue_revision(analysis, link, batch, world['initial_id'],
                       world['revision_id'], 'req-dropped')
    except ReplyDiscarded:
        print('首个 applied 回包丢失，工位裁决已生效而分析端尚未签报。')
    else:
        raise AssertionError('the applied reply should have been discarded')
    # The analysis host goes offline; the station keeps working from its effective list.
    analysis.close()
    with closing(open_station(station_path)) as offline_station:
        start_z = start_review(offline_station, batch, 'Z')
        assert start_z.piece_id == 'Z'
        try:
            start_review(offline_station, batch, 'Y')
        except ValueError:
            pass
        else:
            raise AssertionError('Y is outside the fixed effective list')
        station_progress_before = station_progress(offline_station, batch)
    # A later amendment must not change the ruling fixed for the originally named revision.
    with closing(open_analysis(analysis_path)) as reopened_analysis:
        later = amend_readings(reopened_analysis, batch, world['revision_id'],
                               [('Y', 'center', '20', 'mm')])
        freeze(reopened_analysis, batch, later.revision_id)
    # Reopen both databases and continue with the original request parameters.
    with closing(open_analysis(analysis_path)) as reopened_analysis:
        new_link = make_exchange(lambda: open_station(station_path), handle_revision)
        report_id = issue_revision(reopened_analysis, new_link, batch, world['initial_id'],
                                   world['revision_id'], 'req-dropped')
        report = read_revision(reopened_analysis, report_id)
        # Replaying the identical request returns the same unique report number.
        again = issue_revision(reopened_analysis, new_link, batch, world['initial_id'],
                               world['revision_id'], 'req-dropped')
        assert again == report_id
        assert read_revision(reopened_analysis, again) == report
    assert (report['started_at_activation'], report['selected']) == (('X',), ('X', 'Z'))
    assert report['revision_id'] == world['revision_id']
    _print_scenario({
        'case_id': 'R3.dropped_reply_continuation',
        'fixed_started_at_activation': list(report['started_at_activation']),
        'fixed_effective_selection': list(report['selected']),
        'report_id': report_id, 'same_report_on_replay': again == report_id,
        'station_progress_while_analysis_closed': {
            'started': list(station_progress_before.started),
            'pending': list(station_progress_before.pending),
        },
        'oracle': '丢回包后同请求续办同一裁决；换榜后新增开检 Z 与再次勘误均不改变存值。',
    })
    print('丢回包后续办：报告固定 X 与 X、Z，同参重投返回同一报告号', report_id, '。')


def main():
    path = Path(__file__).with_name('examples') / 'day_shift.json'
    sample = json.loads(path.read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='qingcen-day-') as directory:
        demo_v1(sample, directory)
        demo_revision_after_start(sample, directory)
        demo_revision_before_start(sample, directory)
        demo_dropped_reply_continuation(sample, directory)


if __name__ == '__main__':
    main()
