from dataclasses import replace
from fractions import Fraction

from database import is_record_id, require_name
from lots.roster import normalize_roster, validate_limit
from reports.schema import InitialPacket, InitialReceipt, V1_PACKET_VERSION


def initial_packet_identity(packet):
    return packet.batch_id, packet.report_id


def check_initial_packet(packet):
    if (not isinstance(packet, InitialPacket) or type(packet.version) is not int
            or packet.version != V1_PACKET_VERSION):
        raise ValueError('expected a V1 initial packet')
    require_name(packet.batch_id, 'batch_id')
    receipt = packet.receipt
    if not isinstance(receipt, InitialReceipt):
        raise ValueError('missing initial receipt')
    if not all(map(is_record_id, (packet.report_id, packet.freeze_id, packet.revision_id,
                                  receipt.receipt_id, receipt.report_id, receipt.freeze_id,
                                  receipt.revision_id))):
        raise ValueError('invalid packet or receipt identifier')
    if (receipt.batch_id, receipt.report_id, receipt.freeze_id, receipt.revision_id) != (
            packet.batch_id, packet.report_id, packet.freeze_id, packet.revision_id):
        raise ValueError('receipt references different evidence')
    selected = normalize_roster(packet.selected)
    validate_limit(packet.limit, selected)
    if packet.limit != len(selected):
        raise ValueError('packet selection size differs from its limit')
    if not isinstance(packet.risks, (tuple, list)):
        raise ValueError('packet risks must be piece-score pairs')
    allowed = set(selected)
    scores = {}
    for item in packet.risks:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError('invalid packet risk item')
        piece, score = item
        require_name(piece, 'risk piece')
        if piece not in allowed or piece in scores or not isinstance(score, Fraction) or score < 0:
            raise ValueError('invalid or duplicated packet risk')
        scores[piece] = score
    if scores.keys() != allowed:
        raise ValueError('risk evidence does not cover the selection')
    ordered_risks = tuple((piece, scores[piece]) for piece in selected)
    if any(left[1] < right[1] for left, right in zip(ordered_risks, ordered_risks[1:])):
        raise ValueError('risk scores contradict selection order')
    return replace(packet, selected=selected, risks=ordered_risks)
