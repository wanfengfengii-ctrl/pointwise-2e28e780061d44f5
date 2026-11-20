from reports.read import read_initial
from reports.schema import InitialPacket, V1_PACKET_VERSION


def export_initial(db, report_id):
    report = read_initial(db, report_id)
    scores = {risk.piece_id: risk.score for risk in report.ranked}
    return InitialPacket(
        V1_PACKET_VERSION, report.batch_id, report.report_id, report.freeze_id,
        report.revision_id, report.limit, report.selected,
        tuple((piece, scores[piece]) for piece in report.selected), report.receipt,
    )
