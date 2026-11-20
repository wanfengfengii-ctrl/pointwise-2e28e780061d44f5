"""Implementation-defined handoff messages between the analysis host and the station.

The revision exchange travels through the caller-supplied ``exchange`` callable, so
both sides share these plain-dict representations. Scores keep exact ``Fraction``
values; the station re-validates every message on receipt.
"""
from fractions import Fraction

from database import is_record_id, require_name
from lots.roster import roster_positions, validate_limit


REVISION_KIND = 'qingcen.revision/1'


def _name_tuple(value, label):
    # Empty tuples are legal: a revision that activates before any start has
    # no started pieces to fix.
    if not isinstance(value, (tuple, list)):
        raise ValueError(f'{label} must be a tuple of piece ids')
    pieces = tuple(require_name(piece, label) for piece in value)
    if len(set(pieces)) != len(pieces):
        raise ValueError(f'{label} contains a duplicated piece')
    return pieces


def build_revision_message(*, batch_id, initial_report_id, revision_id, request_id,
                           roster, limit, ranked):
    batch_id = require_name(batch_id, 'batch_id')
    request_id = require_name(request_id, 'request_id')
    if not is_record_id(initial_report_id) or not is_record_id(revision_id):
        raise ValueError('revision message references must be positive record ids')
    pieces = _name_tuple(roster, 'roster')
    validate_limit(limit, pieces)
    if not isinstance(ranked, (tuple, list)):
        raise ValueError('ranked must be piece-score pairs in risk order')
    scores = {}
    order = []
    for item in ranked:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError('a ranked item needs a piece id and a Fraction score')
        piece, score = item
        require_name(piece, 'ranked piece')
        if not isinstance(score, Fraction) or score < 0 or piece in scores:
            raise ValueError('invalid or duplicated ranked risk')
        scores[piece] = score
        order.append(piece)
    if set(order) != set(pieces):
        raise ValueError('ranked risks must cover the whole roster')
    if any(scores[left] < scores[right] for left, right in zip(order, order[1:])):
        raise ValueError('ranked scores must be non-increasing in risk order')
    return {
        'kind': REVISION_KIND,
        'batch_id': batch_id,
        'initial_report_id': initial_report_id,
        'revision_id': revision_id,
        'request_id': request_id,
        'roster': tuple(pieces),
        'limit': limit,
        'ranked': tuple((piece, scores[piece]) for piece in order),
    }


def validate_revision_message(message):
    if not isinstance(message, dict) or message.get('kind') != REVISION_KIND:
        raise ValueError('expected a revision handoff message')
    return build_revision_message(
        batch_id=message.get('batch_id'),
        initial_report_id=message.get('initial_report_id'),
        revision_id=message.get('revision_id'),
        request_id=message.get('request_id'),
        roster=message.get('roster'),
        limit=message.get('limit'),
        ranked=message.get('ranked'),
    )


def build_pending_reply(message):
    return {
        'state': 'pending',
        'batch_id': message['batch_id'],
        'request_id': message['request_id'],
    }


def build_applied_reply(message, started_at_activation, selected):
    started = _name_tuple(started_at_activation, 'started_at_activation')
    effective = _name_tuple(selected, 'selected')
    return {
        'state': 'applied',
        'batch_id': message['batch_id'],
        'request_id': message['request_id'],
        'started_at_activation': started,
        'selected': effective,
    }


def _reply_piece_tuple(reply, field, roster):
    value = reply.get(field)
    pieces = _name_tuple(value, field)
    if any(piece not in roster for piece in pieces):
        raise ValueError(f'{field} contains pieces outside the roster')
    return pieces


def validate_applied_reply(reply, message):
    """Validate the station ruling and re-derive it from the analysis-side view."""
    if not isinstance(reply, dict) or reply.get('state') != 'applied':
        raise ValueError('expected an applied station ruling')
    if reply.get('batch_id') != message['batch_id'] or reply.get('request_id') != message['request_id']:
        raise ValueError('station ruling refers to a different request')
    roster = message['roster']
    started = _reply_piece_tuple(reply, 'started_at_activation', roster)
    selected = _reply_piece_tuple(reply, 'selected', roster)
    limit = message['limit']
    if len(selected) != limit or len(set(selected)) != limit:
        raise ValueError('station ruling does not honor the original limit')
    if not set(started).issubset(set(selected)):
        raise ValueError('every started piece must stay on the effective list')
    ranked = tuple(piece for piece, _ in message['ranked'])
    fill = [piece for piece in ranked if piece not in started][:limit - len(started)]
    if set(selected) != set(started).union(fill):
        raise ValueError('station ruling does not follow the revised risk order')
    positions = roster_positions(roster)
    if selected != tuple(sorted(selected, key=positions.get)):
        raise ValueError('station ruling must present pieces in roster order')
    if started != tuple(sorted(started, key=positions.get)):
        raise ValueError('started pieces must be presented in roster order')
    return started, selected


def validate_pending_reply(reply, message):
    if not isinstance(reply, dict) or reply.get('state') != 'pending':
        raise ValueError('expected a pending station reply')
    if reply.get('batch_id') != message['batch_id'] or reply.get('request_id') != message['request_id']:
        raise ValueError('station reply refers to a different request')
