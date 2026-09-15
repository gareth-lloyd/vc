"""`legacy_db` URL parsing and row shaping (BUG-030 test-coverage sweep).
No SQL Server is reachable from tests, so `pymssql.connect` is stubbed."""

from __future__ import annotations

from typing import Any

import pytest

from data_migration import legacy_db


class _FakeCursor:
    description = (("Id",), ("Name",))

    def __init__(self) -> None:
        self.closed = False

    def __iter__(self) -> Any:
        return iter([(1, "Corfu"), (2, None)])

    def close(self) -> None:
        self.closed = True


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj

    def close(self) -> None:
        self.closed = True


def test_rows_as_dicts_zips_description_with_each_row() -> None:
    assert list(legacy_db.rows_as_dicts(_FakeCursor())) == [
        {"Id": 1, "Name": "Corfu"},
        {"Id": 2, "Name": None},
    ]


def test_rows_as_dicts_rejects_a_row_that_does_not_match_the_description() -> None:
    class _Ragged(_FakeCursor):
        def __iter__(self) -> Any:
            return iter([(1,)])

    with pytest.raises(ValueError):
        list(legacy_db.rows_as_dicts(_Ragged()))


def test_legacy_cursor_requires_the_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEGACY_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="LEGACY_DATABASE_URL"), legacy_db.legacy_cursor():
        pass


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("postgres://u:p@h/db", "scheme must be mssql"),
        ("mssql://h/db", "must include host, user, and database"),
        ("mssql://u:p@h", "must include host, user, and database"),
    ],
)
def test_legacy_cursor_rejects_malformed_urls(
    monkeypatch: pytest.MonkeyPatch, url: str, message: str
) -> None:
    monkeypatch.setenv("LEGACY_DATABASE_URL", url)
    with pytest.raises(RuntimeError, match=message), legacy_db.legacy_cursor():
        pass


def test_legacy_cursor_connects_with_the_parsed_parts_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    connection = _FakeConnection()

    def _connect(**kwargs: Any) -> _FakeConnection:
        seen.update(kwargs)
        return connection

    monkeypatch.setenv("LEGACY_DATABASE_URL", "sqlserver://res%40user:p%40ss@db.local:1444/ResDb")
    monkeypatch.setattr(legacy_db.pymssql, "connect", _connect)

    with legacy_db.legacy_cursor() as cursor:
        assert cursor is connection.cursor_obj

    assert seen == {
        "server": "db.local",
        "port": "1444",
        "user": "res@user",
        "password": "p@ss",
        "database": "ResDb",
    }
    assert connection.cursor_obj.closed
    assert connection.closed


def _patch_connect(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> tuple[dict[str, Any], _FakeConnection]:
    seen: dict[str, Any] = {}
    connection = _FakeConnection()

    def _connect(**kwargs: Any) -> _FakeConnection:
        seen.update(kwargs)
        return connection

    monkeypatch.setenv("LEGACY_DATABASE_URL", url)
    monkeypatch.setattr(legacy_db.pymssql, "connect", _connect)
    return seen, connection


def test_legacy_cursor_defaults_the_port_and_a_missing_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen, _ = _patch_connect(monkeypatch, "mssql://reader@db.local/ResDb")

    with legacy_db.legacy_cursor():
        pass

    assert seen["port"] == "1433"
    assert seen["password"] == ""


def test_legacy_cursor_closes_cursor_and_connection_when_the_body_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, connection = _patch_connect(monkeypatch, "mssql://reader:pw@db.local/ResDb")

    with pytest.raises(RuntimeError, match="boom"), legacy_db.legacy_cursor():
        raise RuntimeError("boom")

    assert connection.cursor_obj.closed
    assert connection.closed
