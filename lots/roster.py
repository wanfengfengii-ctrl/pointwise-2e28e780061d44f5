from database import require_name


def normalize_roster(roster):
    if not isinstance(roster, (tuple, list)) or not roster:
        raise ValueError('roster must be a nonempty ordered list or tuple')
    pieces = tuple(require_name(piece, 'piece_id') for piece in roster)
    if len(set(pieces)) != len(pieces):
        raise ValueError('duplicate piece in roster')
    return pieces


def validate_limit(limit, roster):
    if type(limit) is not int or not 1 <= limit <= len(roster):
        raise ValueError('review limit must be an integer between 1 and the roster size')
    return limit


def roster_positions(roster):
    return {piece: position for position, piece in enumerate(roster)}
