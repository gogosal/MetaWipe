"""Optional local history; never stores images, full paths or metadata values."""
from __future__ import annotations
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import sys


def data_directory():
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    current = base / 'MetaWipe'
    legacy = base / 'PixelGuard'
    # Reuse an existing database without duplicating private history records.
    if not (current / 'history.sqlite3').exists() and (legacy / 'history.sqlite3').exists():
        return legacy
    return current


class HistoryStore:
    def __init__(self, path=None, enabled=False):
        self.path = Path(path) if path else data_directory() / 'history.sqlite3'
        self.enabled = enabled

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        connection.execute('PRAGMA secure_delete=ON')
        connection.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, '
                           'at TEXT NOT NULL, file TEXT NOT NULL, operation TEXT NOT NULL, '
                           'metadata_count INTEGER NOT NULL, removed_count INTEGER NOT NULL)')
        return connection

    def add(self, file, operation, metadata_count, removed_count=0):
        if not self.enabled:
            return
        with self._connect() as db:
            db.execute('INSERT INTO events (at,file,operation,metadata_count,removed_count) VALUES (?,?,?,?,?)',
                       (datetime.now().astimezone().isoformat(timespec='seconds'), Path(file).name,
                        operation, int(metadata_count), int(removed_count)))
            db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 5000)')

    def list(self):
        if not self.path.exists():
            return []
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 5000')]

    def clear(self):
        if not self.path.exists():
            return
        with self._connect() as db:
            db.execute('DELETE FROM events')
        with self._connect() as db:
            db.execute('VACUUM')
