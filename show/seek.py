from dataclasses import dataclass
import sqlite3

from release.feasibility import _single_schedule
from release.repository import get_issued_program
from show.repository import ShowSession, load_show, save_show_progress


class SeekConflict(Exception):
    pass


@dataclass(frozen=True)
class SeekRecord:
    position: int
    from_tick: int
    target_tick: int


@dataclass(frozen=True)
class SeekResult:
    show_id: int
    next_tick: int
    position: int


def initialize_seek_store(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS show_seeks (
            show_id INTEGER NOT NULL REFERENCES show_sessions(show_id),
            position INTEGER NOT NULL CHECK (position >= 0),
            from_tick INTEGER NOT NULL CHECK (from_tick >= 0),
            target_tick INTEGER NOT NULL CHECK (target_tick >= 0),
            PRIMARY KEY (show_id, position)
        )
    ''')


def record_seek(
    connection: sqlite3.Connection, show_id: int, position: int,
    from_tick: int, target_tick: int,
) -> SeekRecord:
    record = SeekRecord(position, from_tick, target_tick)
    connection.execute('''
        INSERT INTO show_seeks (show_id, position, from_tick, target_tick)
        VALUES (?, ?, ?, ?)
    ''', (show_id, position, from_tick, target_tick))
    return record


def list_seeks(connection: sqlite3.Connection, show_id: int) -> tuple[SeekRecord, ...]:
    rows = connection.execute('''
        SELECT position, from_tick, target_tick
        FROM show_seeks WHERE show_id = ? ORDER BY position
    ''', (show_id,)).fetchall()
    return tuple(SeekRecord(*row) for row in rows)


def current_position(show: ShowSession) -> int:
    return show.position if show.position is not None else show.next_tick


def seek_show(
    connection: sqlite3.Connection, show_id: int, position: int, target_tick: int,
) -> SeekResult:
    show = load_show(connection, show_id)
    if show.closed:
        raise SeekConflict('show_already_closed')
    if position != current_position(show):
        raise SeekConflict('stale_position')
    if show.edition_id is None:
        raise SeekConflict('edition_not_confirmed')
    if show.active is not None:
        raise SeekConflict('narration_active')

    issued = get_issued_program(connection, show.issue_id)
    edition = issued.revision.edition(show.edition_id)
    if target_tick >= edition.length:
        raise SeekConflict('target_tick_out_of_range')
    if target_tick == show.next_tick:
        raise SeekConflict('target_tick_unchanged')

    remaining = tuple(issued.revision.segment(segment_id) for segment_id in show.remaining)
    if _single_schedule(edition, remaining, target_tick) is None:
        raise SeekConflict('remaining_schedule_infeasible')

    record_seek(connection, show_id, position, show.next_tick, target_tick)
    updated = ShowSession(
        show_id=show.show_id,
        booth=show.booth,
        mount_id=show.mount_id,
        issue_id=show.issue_id,
        next_tick=target_tick,
        edition_id=show.edition_id,
        signal=show.signal,
        remaining=show.remaining,
        active=show.active,
        completed=show.completed,
        closed=show.closed,
        position=position + 1,
    )
    save_show_progress(connection, updated, expected_tick=show.next_tick)
    return SeekResult(show_id, target_tick, position + 1)
