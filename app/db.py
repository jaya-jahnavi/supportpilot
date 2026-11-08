import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager

DATA=Path(os.environ.get('SUPPORTPILOT_DATA','.local')).resolve()
DATA.mkdir(parents=True,exist_ok=True)

@contextmanager
def connect():
    db=sqlite3.connect(DATA/'support.db',timeout=30)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:db.close()

def init():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,email TEXT,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS login_limits(email TEXT PRIMARY KEY,failures INTEGER,expires REAL);
        CREATE TABLE IF NOT EXISTS articles(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL);
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(id UNINDEXED,title,body);
        CREATE TABLE IF NOT EXISTS tickets(
          id TEXT PRIMARY KEY,subject TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL,
          created REAL,updated REAL,version INTEGER DEFAULT 0,attempts INTEGER DEFAULT 0,
          worker TEXT,lease_until REAL,idempotency_key TEXT UNIQUE,payload_sha TEXT,
          draft TEXT,trace TEXT,error TEXT,review_note TEXT);
        CREATE INDEX IF NOT EXISTS ticket_queue ON tickets(status,created);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,created REAL,action TEXT,ticket_id TEXT);
        CREATE TABLE IF NOT EXISTS workers(id TEXT PRIMARY KEY,seen REAL);
        """)

def event(db,action,ticket_id=None):
    db.execute('INSERT INTO events VALUES(?,?,?,?)',(str(uuid.uuid4()),time.time(),action,ticket_id))

def public(row):
    r=dict(row)
    for k in ('worker','lease_until','idempotency_key','payload_sha'):r.pop(k,None)
    for k in ('draft','trace'):
        r[k]=json.loads(r[k]) if r[k] else None
    return r
