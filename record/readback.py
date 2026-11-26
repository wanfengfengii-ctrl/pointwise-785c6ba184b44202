from dataclasses import asdict
import sqlite3

from record.closeout import closeout_view, find_closeout_by_number, find_closeout_by_show
from record.ledger import interval_view, list_intervals
from show.repository import load_show, show_view
from show.seek import list_seeks


def read_show_record(
    connection: sqlite3.Connection, *, show_id: int | None = None, closeout_id: int | None = None
) -> dict:
    if (show_id is None) == (closeout_id is None):
        raise ValueError('provide exactly one of show_id and closeout_id')
    if closeout_id is not None:
        summary = find_closeout_by_number(connection, closeout_id)
        if summary is None:
            raise LookupError('closeout_not_found')
        show_id = summary.show_id
    else:
        summary = find_closeout_by_show(connection, show_id)

    show = load_show(connection, show_id)
    if summary is not None:
        summary_document = closeout_view(summary)
        intervals = summary_document['intervals']
        seeks = summary.seeks
        closeout = summary_document
    else:
        seeks = list_seeks(connection, show_id)
        intervals = [
            interval_view(interval, located=bool(seeks))
            for interval in list_intervals(connection, show_id)
        ]
        closeout = None

    record = {
        'show': show_view(show),
        'intervals': intervals,
        'closeout': closeout,
    }
    if seeks:
        record['seeks'] = [asdict(seek) for seek in seeks]
    return record
