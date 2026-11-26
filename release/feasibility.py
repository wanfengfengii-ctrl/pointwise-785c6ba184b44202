from dataclasses import dataclass
from functools import lru_cache

from program.catalog import ProgramRevision
from program.editions import Edition, TickWindow, available_windows
from program.narration import NarrationSegment


Schedule = tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class DecisionBasis:
    confirmation_tick: int | None
    shared_starts: Schedule
    edition_starts: tuple[tuple[str, Schedule], ...]

    def segment_starting_at(self, tick: int, edition_id: str | None) -> str | None:
        if self.confirmation_tick is not None and tick < self.confirmation_tick:
            starts = self.shared_starts
        else:
            for candidate, schedule in self.edition_starts:
                if candidate == edition_id:
                    starts = schedule
                    break
            else:
                raise RuntimeError('the current edition has no issued schedule')
        return next((segment_id for start, segment_id in starts if start == tick), None)


@dataclass(frozen=True)
class FeasibilityResult:
    eligible: bool
    reason: str
    basis: DecisionBasis | None = None


def _common_windows(first: Edition, second: Edition) -> tuple[TickWindow, ...]:
    left = iter(available_windows(first))
    right = iter(available_windows(second))
    a, b = next(left, None), next(right, None)
    common = []
    while a is not None and b is not None:
        start, end = max(a.start, b.start), min(a.end, b.end)
        if start < end:
            common.append(TickWindow(start, end))
        if a.end <= b.end:
            a = next(left, None)
        else:
            b = next(right, None)
    return tuple(common)


def _first_start(windows, free_tick, length, deadline, before_tick):
    for window in windows:
        start = max(free_tick, window.start)
        if before_tick is not None and start >= before_tick:
            break
        if start + length <= min(window.end, deadline):
            return start
    return None


def _prefixes(segments, windows, deadlines, first_tick=0, before_tick=None):
    # With the same remaining segments, an earlier free tick can wait and copy
    # every continuation of a later one. Keep the earliest witness for each set.
    layer = {segments: (first_tick, ())}
    while layer:
        following = {}
        for remaining, (free_tick, prefix) in layer.items():
            yield remaining, free_tick, prefix
            for index, segment in enumerate(remaining):
                start = _first_start(
                    windows, free_tick, segment.length, deadlines[segment.segment_id], before_tick
                )
                if start is None:
                    continue
                rest = remaining[:index] + remaining[index + 1:]
                finish = start + segment.length
                old = following.get(rest)
                if old is None or finish < old[0]:
                    following[rest] = (finish, prefix + ((start, segment.segment_id),))
        layer = following


def _single_schedule(edition: Edition, segments: tuple[NarrationSegment, ...], first_tick: int) -> Schedule | None:
    deadlines = {segment.segment_id: segment.deadline_for(edition.edition_id) for segment in segments}
    for remaining, _, schedule in _prefixes(segments, available_windows(edition), deadlines, first_tick):
        if not remaining:
            return schedule
    return None


def find_single_edition_schedule(revision: ProgramRevision, edition_id: str) -> Schedule | None:
    return _single_schedule(revision.edition(edition_id), revision.segments, 0)


def assess_feasibility(revision: ProgramRevision) -> FeasibilityResult:
    first = revision.editions[0]
    if len(revision.editions) == 1:
        schedule = find_single_edition_schedule(revision, first.edition_id)
        if schedule is None:
            return FeasibilityResult(False, 'no_complete_schedule')
        return FeasibilityResult(True, 'feasible', DecisionBasis(None, (), ((first.edition_id, schedule),)))

    second = revision.editions[1]
    confirmation = revision.confirmation_tick
    deadlines = {
        segment.segment_id: min(segment.deadline_for(first.edition_id), segment.deadline_for(second.edition_id))
        for segment in revision.segments
    }
    suffix_for = lru_cache(maxsize=None)(_single_schedule)
    for remaining, free_tick, shared_starts in _prefixes(
        revision.segments, _common_windows(first, second), deadlines, before_tick=confirmation
    ):
        # A start before confirmation may still occupy later beats. Every
        # edition's suffix begins after both confirmation and that occupancy.
        suffix_tick = max(confirmation, free_tick)
        first_suffix = suffix_for(first, remaining, suffix_tick)
        if first_suffix is None:
            continue
        second_suffix = suffix_for(second, remaining, suffix_tick)
        if second_suffix is not None:
            return FeasibilityResult(True, 'feasible', DecisionBasis(
                confirmation, shared_starts,
                ((first.edition_id, first_suffix), (second.edition_id, second_suffix)),
            ))
    return FeasibilityResult(False, 'no_common_schedule')
