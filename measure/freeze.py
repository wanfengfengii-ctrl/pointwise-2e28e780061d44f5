from database import is_record_id, transaction
from measure.revisions import load_revision
from measure.schema import FrozenRevision


def freeze(db, batch_id, revision_id):
    with transaction(db):
        revision = load_revision(db, revision_id)
        if revision.batch_id != batch_id:
            raise ValueError('revision belongs to another batch')
        stored = db.execute('''
            SELECT freeze_id FROM freezes WHERE batch_id = ? AND revision_id = ?
        ''', (batch_id, revision_id)).fetchone()
        if stored is not None:
            return stored[0]
        return db.execute('''
            INSERT INTO freezes (batch_id, revision_id) VALUES (?, ?)
        ''', (batch_id, revision_id)).lastrowid


def load_frozen_revision(db, freeze_id):
    if not is_record_id(freeze_id):
        raise KeyError(freeze_id)
    stored = db.execute('SELECT revision_id FROM freezes WHERE freeze_id = ?', (freeze_id,)).fetchone()
    if stored is None:
        raise KeyError(freeze_id)
    return FrozenRevision(freeze_id, load_revision(db, stored[0]))
