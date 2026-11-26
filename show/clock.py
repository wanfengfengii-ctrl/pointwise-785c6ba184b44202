from dataclasses import dataclass, replace
import sqlite3

from record.ledger import record_end, record_start
from release.repository import get_issued_program
from show.playback import TickAction, apply_tick_action, decide_tick_action
from show.repository import ShowSession, load_show, save_show_progress
from show.signal_input import accept_signals


class AdvanceConflict(Exception):
    pass


@dataclass(frozen=True)
class AdvanceResult:
    tick: int
    action: TickAction
    show: ShowSession
    ended_segment: str | None


def require_next_tick(show: ShowSession, tick: int) -> None:
    if show.closed:
        raise AdvanceConflict('show_already_closed')
    if type(tick) is not int or tick != show.next_tick:
        # Before the first seek, retain the original malformed/stale-tick 400.
        if show.position is not None:
            raise AdvanceConflict(f'expected_next_tick_{show.next_tick}')
        raise ValueError(f'expected_next_tick_{show.next_tick}')


def advance_show(
    connection: sqlite3.Connection, show_id: int, tick: int, signal: str | None,
    position: int | None = None, position_present: bool = False,
) -> AdvanceResult:
    show = load_show(connection, show_id)
    require_next_tick(show, tick)

    current_position = show.position if show.position is not None else show.next_tick
    if show.position is not None and not position_present:
        raise AdvanceConflict('position_required')
    if position_present and position != current_position:
        raise AdvanceConflict(f'expected_position_{current_position}')

    issued = get_issued_program(connection, show.issue_id)
    observed = accept_signals(issued.revision, show, tick, signal)

    if observed.edition_id is None:
        horizon = min(edition.length for edition in issued.revision.editions)
    else:
        horizon = issued.revision.edition(observed.edition_id).length
    if tick >= horizon:
        raise AdvanceConflict('edition_has_ended')

    action = decide_tick_action(issued, observed)
    updated, ended_segment = apply_tick_action(issued, observed, action)
    if show.position is not None:
        updated = replace(updated, position=show.position + 1)

    if action.kind == 'start':
        record_start(connection, show_id, action.segment_id, tick, position=show.position)
    if ended_segment is not None:
        record_end(
            connection, show_id, ended_segment, updated.next_tick,
            position=updated.position,
        )
    save_show_progress(connection, updated, expected_tick=tick)
    return AdvanceResult(tick, action, updated, ended_segment)
