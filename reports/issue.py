from database import is_record_id, require_name
from handoff import (
    build_revision_message, validate_applied_reply, validate_pending_reply,
)
from lots.register import load_lot
from measure.freeze import load_frozen_revision
from measure.revisions import load_revision
from reports.revision_store import (
    find_batch_request, get_request, save_pending_request, save_revision_report,
)
from reports.store import commit_initial
from risk.ranking import rank_frozen_revision, rank_reading_revision


def issue_initial(db, batch_id, freeze_id):
    lot = load_lot(db, batch_id)
    frozen = load_frozen_revision(db, freeze_id)
    result = rank_frozen_revision(lot, frozen)
    selected = tuple(risk.piece_id for risk in result.ranked[:lot.limit])
    return commit_initial(db, result, lot.limit, selected)


def _validate_revision_inputs(db, batch_id, initial_report_id, revision_id, request_id):
    require_name(batch_id, 'batch_id')
    require_name(request_id, 'request_id')
    if not is_record_id(initial_report_id) or not is_record_id(revision_id):
        raise ValueError('initial_report_id and revision_id must be positive record ids')
    lot = load_lot(db, batch_id)
    header = db.execute('''
        SELECT report_id FROM initial_reports WHERE batch_id = ? AND report_id = ?
    ''', (batch_id, initial_report_id)).fetchone()
    if header is None:
        raise KeyError(initial_report_id)
    revision = load_revision(db, revision_id)
    if revision.batch_id != batch_id:
        raise ValueError('revision belongs to another batch')
    return lot, revision


def issue_revision(db, exchange, batch_id, initial_report_id, revision_id, request_id):
    """Submit or continue a revision exchange; returns a report id or 'pending'."""
    lot, revision = _validate_revision_inputs(
        db, batch_id, initial_report_id, revision_id, request_id,
    )
    params = (batch_id, initial_report_id, revision_id)
    existing = get_request(db, request_id)
    if existing is not None:
        _, ex_batch, ex_initial, ex_revision, state, report_id = existing
        if (ex_batch, ex_initial, ex_revision) != params:
            raise ValueError('request id is already registered with different parameters')
        if state == 'applied':
            return report_id
    else:
        other_request = find_batch_request(db, batch_id)
        if other_request is not None:
            raise ValueError('batch already has a revision under another request id')
    if not callable(exchange):
        raise ValueError('exchange must be a callable station delivery function')

    result = rank_reading_revision(lot, revision)
    message = build_revision_message(
        batch_id=batch_id,
        initial_report_id=initial_report_id,
        revision_id=revision_id,
        request_id=request_id,
        roster=lot.roster,
        limit=lot.limit,
        ranked=tuple((risk.piece_id, risk.score) for risk in result.ranked),
    )
    reply = exchange(message)
    if not isinstance(reply, dict):
        raise ValueError('station returned an invalid revision reply')
    if reply.get('state') == 'pending':
        validate_pending_reply(reply, message)
        save_pending_request(db, request_id, *params)
        return 'pending'
    started, selected = validate_applied_reply(reply, message)
    report_id = save_revision_report(db, request_id, *params, started, selected)
    return report_id
