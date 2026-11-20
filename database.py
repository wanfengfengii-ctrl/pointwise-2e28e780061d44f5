import sqlite3
from contextlib import contextmanager
from fractions import Fraction


def open_database(path):
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.execute('PRAGMA foreign_keys = ON')
    except BaseException:
        db.close()
        raise
    return db


@contextmanager
def transaction(db, *, write=True):
    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def require_name(value, label):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f'{label} must be a nonblank string without NUL')
    value.encode('utf-8')
    return value


def is_record_id(value):
    return type(value) is int and 0 < value <= 2**63 - 1


def fraction_parts(value):
    return str(value.numerator), str(value.denominator)


def from_fraction_parts(numerator, denominator):
    return Fraction(int(numerator), int(denominator))
