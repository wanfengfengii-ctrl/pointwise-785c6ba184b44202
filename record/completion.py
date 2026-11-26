from dataclasses import dataclass

from program.editions import fits_narration
from record.ledger import PlaybackInterval
from release.repository import IssuedProgram
from show.repository import ShowSession
from show.seek import SeekRecord


@dataclass(frozen=True)
class CompletionResult:
    missing: tuple[str, ...]
    unfinished: tuple[str, ...]
    inconsistent: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not (self.missing or self.unfinished or self.inconsistent)


def evaluate_completion(
    issued: IssuedProgram,
    show: ShowSession,
    intervals: tuple[PlaybackInterval, ...],
    seeks: tuple[SeekRecord, ...] = (),
) -> CompletionResult:
    required = {segment.segment_id: segment for segment in issued.revision.segments}
    seen = {interval.segment_id for interval in intervals}
    completed = set(show.completed)

    missing = set(required) - seen
    unfinished = set(show.remaining)
    if show.active is not None:
        unfinished.add(show.active.segment_id)

    inconsistent = (seen | completed | unfinished) - set(required)
    editions = issued.revision.editions
    if show.edition_id is not None:
        editions = (issued.revision.edition(show.edition_id),)

    previous_film_end = 0
    previous_site_end = 0
    seek_positions = tuple(record.position for record in seeks)

    for interval in intervals:
        segment_id = interval.segment_id
        if interval.end_tick is None:
            unfinished.add(segment_id)
            if segment_id in completed:
                inconsistent.add(segment_id)
            continue

        segment = required.get(segment_id)
        film_constraints_ok = all(
            fits_narration(
                edition,
                interval.start_tick,
                segment.length,
                segment.deadline_for(edition.edition_id),
            )
            for edition in editions
        ) if segment is not None else False

        if seeks:
            site_constraints_ok = (
                interval.start_position is not None
                and interval.end_position is not None
                and interval.end_position - interval.start_position
                == interval.end_tick - interval.start_tick
                and interval.start_position >= previous_site_end
                and not any(
                    interval.start_position <= position < interval.end_position
                    for position in seek_positions
                )
            )
        else:
            # Preserve the original film-tick reconciliation for unlocated shows.
            site_constraints_ok = True
            film_constraints_ok = (
                film_constraints_ok
                and interval.start_tick >= previous_film_end
                and interval.end_tick <= show.next_tick
            )

        if (
            segment is None
            or segment_id not in completed
            or interval.end_tick - interval.start_tick != segment.length
            or not film_constraints_ok
            or not site_constraints_ok
        ):
            inconsistent.add(segment_id)

        previous_film_end = max(previous_film_end, interval.end_tick)
        if interval.end_position is not None:
            previous_site_end = max(previous_site_end, interval.end_position)

    return CompletionResult(
        tuple(sorted(missing)),
        tuple(sorted(unfinished)),
        tuple(sorted(inconsistent)),
    )
