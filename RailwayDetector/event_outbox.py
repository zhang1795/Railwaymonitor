"""Durable, bounded event handoff. MQTT PUBACK is not a business commit."""
import hashlib
import fcntl
import json
import os
import sqlite3
import threading
import time


class OutboxFull(RuntimeError):
    pass


class EventOutbox:
    def __init__(self, path, worker_id, max_events=10000, max_bytes=64*1024*1024,
                 clock=time.time):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.worker_id, self.clock = worker_id, clock
        self.owner_file = open(path+'.lock', 'a')
        os.chmod(path+'.lock', 0o600)
        try:
            fcntl.flock(self.owner_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.owner_file.close()
            raise RuntimeError('outbox is already owned by a running worker')
        self.max_events, self.max_bytes = max_events, max_bytes
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=5)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS identity(worker_id TEXT PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS pending(
            event_id TEXT PRIMARY KEY, body TEXT NOT NULL, hash TEXT NOT NULL,
            bytes INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt REAL NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS rejected(
            event_id TEXT PRIMARY KEY, body TEXT NOT NULL, reason TEXT NOT NULL,
            rejected_at REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS control(
            camera_id TEXT PRIMARY KEY, generation INTEGER NOT NULL,
            session_id TEXT NOT NULL, enabled INTEGER NOT NULL,
            started INTEGER NOT NULL DEFAULT 0);
        ''')
        if 'started' not in {row[1] for row in self.db.execute('PRAGMA table_info(control)')}:
            self.db.execute('ALTER TABLE control ADD COLUMN started INTEGER NOT NULL DEFAULT 0')
            self.db.execute('UPDATE control SET started=1')
        owner = self.db.execute('SELECT worker_id FROM identity').fetchone()
        if owner and owner[0] != worker_id:
            self.close()
            raise ValueError('outbox belongs to another worker identity')
        self.db.execute('INSERT OR IGNORE INTO identity VALUES(?)', (worker_id,))
        self.db.commit()

        for suffix in ('-wal', '-shm'):
            if os.path.exists(path+suffix):
                os.chmod(path+suffix, 0o600)

    def enqueue(self, body):
        event = json.loads(body)
        if event.get('workerId') != self.worker_id:
            raise ValueError('event worker does not match local outbox')
        size = len(body.encode('utf-8'))
        if size > 16384:
            raise ValueError('event exceeds 16 KiB')
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        with self.lock, self.db:
            existing = self.db.execute('SELECT hash FROM pending WHERE event_id=?',
                                       (event['eventId'],)).fetchone()
            if existing:
                if existing['hash'] != digest:
                    raise ValueError('event ID reused with different contents')
                return
            count, total = self.db.execute('SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM pending').fetchone()
            if count >= self.max_events or total+size > self.max_bytes:
                raise OutboxFull('unacknowledged event capacity reached; monitoring must stop')
            self.db.execute('INSERT INTO pending(event_id,body,hash,bytes) VALUES(?,?,?,?)',
                            (event['eventId'], body, digest, size))

    def due(self, limit=32):
        with self.lock:
            return [dict(row) for row in self.db.execute(
                'SELECT * FROM pending WHERE next_attempt<=? ORDER BY rowid LIMIT ?',
                (self.clock(), limit))]

    def attempted(self, event_id):
        with self.lock, self.db:
            row = self.db.execute('SELECT attempts FROM pending WHERE event_id=?', (event_id,)).fetchone()
            if row:
                delay = min(30, 2 ** min(row['attempts'], 5))
                self.db.execute('UPDATE pending SET attempts=attempts+1,next_attempt=? WHERE event_id=?',
                                (self.clock()+delay, event_id))

    def acknowledge(self, ack):
        if ack.get('workerId') != self.worker_id or ack.get('status') not in ('APPLIED', 'REJECTED'):
            return False
        with self.lock, self.db:
            row = self.db.execute('SELECT * FROM pending WHERE event_id=?',
                                  (ack.get('eventId'),)).fetchone()
            if not row or row['hash'] != ack.get('payloadHash'):
                return False
            if ack['status'] == 'REJECTED':
                # The receiver has durably quarantined it. Keep a bounded local
                # diagnostic copy too; rejected is never presented as applied.
                self.db.execute('INSERT OR REPLACE INTO rejected VALUES(?,?,?,?)',
                    (row['event_id'], row['body'], str(ack.get('reason', 'rejected'))[:500], self.clock()))
                self.db.execute('DELETE FROM rejected WHERE rowid NOT IN '
                                '(SELECT rowid FROM rejected ORDER BY rowid DESC LIMIT 1000)')
            self.db.execute('DELETE FROM pending WHERE event_id=?', (row['event_id'],))
            return True

    def fence(self, camera_id, generation, session_id, enabled):
        """Persist control generation before acting, preventing stale restarts."""
        with self.lock, self.db:
            row = self.db.execute('SELECT * FROM control WHERE camera_id=?', (camera_id,)).fetchone()
            if row and (generation < row['generation'] or
                        (generation == row['generation'] and
                         (session_id != row['session_id'] or enabled != bool(row['enabled'])))):
                return False
            if row and generation == row['generation']:
                return True
            started = int(row['started']) if row and row['session_id'] == session_id else 0
            self.db.execute('INSERT OR REPLACE INTO control(camera_id,generation,session_id,enabled,started) VALUES(?,?,?,?,?)',
                            (camera_id, generation, session_id, int(enabled), started))
            return True

    def claim_session(self, camera_id, session_id):
        """A server session may launch exactly once across process restarts."""
        with self.lock, self.db:
            return self.db.execute('UPDATE control SET started=1 WHERE camera_id=? AND session_id=? AND started=0',
                                   (camera_id, session_id)).rowcount == 1

    def count(self):
        with self.lock:
            return self.db.execute('SELECT COUNT(*) FROM pending').fetchone()[0]

    def close(self):
        with self.lock:
            self.db.close()
            self.owner_file.close()
