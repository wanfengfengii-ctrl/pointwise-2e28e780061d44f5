from database import transaction
from handoff import build_applied_reply, build_pending_reply, validate_revision_message
from lots.roster import roster_positions
from station.ledger import load_acceptance, load_starts, save_acceptance
from station.packet import check_initial_packet, initial_packet_identity
from station.revision_store import (
    get_applied_revision, get_revision_request, is_handover_paused,
    load_activation_started, load_effective_selection,
    save_applied_revision, save_pending_request,
)


def accept_initial(db, packet):
    canonical = check_initial_packet(packet)
    with transaction(db):
        try:
            prior = load_acceptance(db, canonical.batch_id)
        except KeyError:
            return save_acceptance(db, canonical).acceptance_id
        if initial_packet_identity(prior.packet) != initial_packet_identity(canonical):
            raise ValueError('batch already has a different initial report')
        if prior.packet != canonical:
            raise ValueError('initial packet identity has conflicting contents')
        return prior.acceptance_id


def _effective_selection(message, started_pieces):
    """All already-started pieces keep their slots; the rest fill by revised risk order."""
    ranked = tuple(piece for piece, _ in message['ranked'])
    limit = message['limit']
    positions = roster_positions(message['roster'])
    kept = tuple(piece for piece in message['roster'] if piece in started_pieces)
    fill = [piece for piece in ranked if piece not in started_pieces][:limit - len(kept)]
    effective = set(kept).union(fill)
    return tuple(sorted(effective, key=positions.get)), kept


def _fixed_reply(db, acceptance_id, message):
    """Replay an applied ruling: the activation-time set is fixed, later starts don't change it."""
    effective = load_effective_selection(db, acceptance_id)
    fixed_started = load_activation_started(db, acceptance_id)
    return build_applied_reply(message, fixed_started, effective)


def handle_revision(db, message):
    """Station entry point for a revision exchange request."""
    canonical = validate_revision_message(message)
    with transaction(db):
        try:
            accepted = load_acceptance(db, canonical['batch_id'])
        except KeyError as error:
            raise KeyError(canonical['batch_id']) from error
        acceptance_id = accepted.acceptance_id
        if accepted.packet.report_id != canonical['initial_report_id']:
            raise ValueError('initial report does not match the station acceptance')
        roster = set(canonical['roster'])
        started_before = {record.piece_id for record in load_starts(db, accepted)}
        if not started_before.issubset(roster):
            raise ValueError('revision roster does not cover pieces already under review')
        stored = get_revision_request(db, acceptance_id, canonical['request_id'])
        if stored is not None:
            _, stored_revision, stored_initial, stored_state = stored
            if (stored_revision, stored_initial) != (
                    canonical['revision_id'], canonical['initial_report_id']):
                raise ValueError('request id is already registered with different parameters')
            if stored_state == 'applied':
                applied = get_applied_revision(db, acceptance_id)
                if (applied[1], applied[2]) != (
                        canonical['revision_id'], canonical['initial_report_id']):
                    raise ValueError('station ruling was fixed for different revision parameters')
                return _fixed_reply(db, acceptance_id, canonical)
            # A pending replay stays pending during handover, otherwise it activates.
            if is_handover_paused(db, canonical['batch_id']):
                return build_pending_reply(canonical)
            selected, kept = _effective_selection(canonical, started_before)
            save_applied_revision(db, acceptance_id, canonical, kept, selected)
            return _fixed_reply(db, acceptance_id, canonical)
        if get_applied_revision(db, acceptance_id) is not None:
            raise ValueError('batch already has an effective revision under another request id')
        if db.execute('''
            SELECT 1 FROM station_revision_requests
            WHERE acceptance_id = ? AND state = 'pending'
        ''', (acceptance_id,)).fetchone() is not None:
            raise ValueError('another revision request for the batch is already pending')
        if is_handover_paused(db, canonical['batch_id']):
            save_pending_request(db, acceptance_id, canonical)
            return build_pending_reply(canonical)
        selected, kept = _effective_selection(canonical, started_before)
        save_applied_revision(db, acceptance_id, canonical, kept, selected)
        return _fixed_reply(db, acceptance_id, canonical)
