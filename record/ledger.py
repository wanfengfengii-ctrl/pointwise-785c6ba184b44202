from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class PlaybackInterval:
    segment_id: str
    start_tick: int
    end_tick: int | None
    start_position: int | None = None
    end_position: int | None = None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info({table})')}


def initialize_ledger(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS playback_intervals (
            show_id INTEGER NOT NULL REFERENCES show_sessions(show_id),
            segment_id TEXT NOT NULL,
            start_tick INTEGER NOT NULL CHECK (start_tick >= 0),
            end_tick INTEGER CHECK (end_tick > start_tick),
            start_position INTEGER,
            end_position INTEGER,
            PRIMARY KEY (show_id, segment_id)
        )
    ''')
    columns = _columns(connection, 'playback_intervals')
    if 'start_position' not in columns:
        connection.execute('ALTER TABLE playback_intervals ADD COLUMN start_position INTEGER')
    if 'end_position' not in columns:
        connection.execute('ALTER TABLE playback_intervals ADD COLUMN end_position INTEGER')

    # Databases written before seeking had one site position per film tick.
    connection.execute('''
        UPDATE playback_intervals
        SET start_position = start_tick
        WHERE start_position IS NULL
    ''')
    connection.execute('''
        UPDATE playback_intervals
        SET end_position = end_tick
        WHERE end_position IS NULL AND end_tick IS NOT NULL
    ''')


def record_start(
    connection: sqlite3.Connection, show_id: int, segment_id: str, tick: int,
    position: int | None = None,
) -> None:
    if position is None:
        position = tick
    connection.execute('''
        INSERT INTO playback_intervals
            (show_id, segment_id, start_tick, start_position)
        VALUES (?, ?, ?, ?)
    ''', (show_id, segment_id, tick, position))


def record_end(
    connection: sqlite3.Connection, show_id: int, segment_id: str, tick: int,
    position: int | None = None,
) -> None:
    if position is None:
        position = tick
    cursor = connection.execute('''
        UPDATE playback_intervals
        SET end_tick = ?, end_position = ?
        WHERE show_id = ? AND segment_id = ? AND end_tick IS NULL AND start_tick < ?
    ''', (tick, position, show_id, segment_id, tick))
    if cursor.rowcount != 1:
        raise RuntimeError('playback end requires an unfinished start')


def list_intervals(connection: sqlite3.Connection, show_id: int) -> tuple[PlaybackInterval, ...]:
    rows = connection.execute('''
        SELECT segment_id, start_tick, end_tick, start_position, end_position
        FROM playback_intervals
        WHERE show_id = ?
        ORDER BY start_position, segment_id
    ''', (show_id,)).fetchall()
    return tuple(PlaybackInterval(*row) for row in rows)


def interval_view(interval: PlaybackInterval, *, located: bool) -> dict:
    view = {
        'segment_id': interval.segment_id,
        'start_tick': interval.start_tick,
        'end_tick': interval.end_tick,
    }
    if located:
        view['start_position'] = interval.start_position
        view['end_position'] = interval.end_position
    return view
