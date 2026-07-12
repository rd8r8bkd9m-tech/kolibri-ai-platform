"""Small SQLite lifecycle helpers shared by compatibility stores.

``sqlite3.Connection`` is a transaction context manager, but leaving its
``with`` block only commits or rolls back; it does not close the connection.
Long-lived API processes therefore need an explicit close boundary around
every short-lived transaction.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager


@contextmanager
def closing_sqlite_transaction(
    connect: Callable[[], sqlite3.Connection],
) -> Iterator[sqlite3.Connection]:
    """Yield one transaction and always close it after commit or rollback."""

    connection = connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()
