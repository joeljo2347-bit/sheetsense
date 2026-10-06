import sqlite3

import pytest

from sheetsense import guard
from sheetsense.tables import load, open_db


@pytest.mark.parametrize("sql", [
    "SELECT * FROM orders",
    "with t as (select 1) select * from t",
    "SELECT REPLACE(customer, 'Blue', 'Navy') FROM orders",  # a function, not a statement
    "SELECT 1; -- trailing comment",
    "SELECT printf('%.2f', 3.14159)",  # fixed widths are fine
    "SELECT 'it''s /* not a comment */ text'",
    "SELECT 1 /* unclosed; DELETE FROM orders",  # SQLite reads the rest as a comment
])
def test_reads_may_run(sql):
    assert guard.refuse(sql) is None


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "SELECT 1; DROP TABLE orders",
    "UPDATE orders SET amount = 0",
    "PRAGMA writable_schema = 1",
    "ATTACH DATABASE 'x.db' AS x",
    "INSERT INTO orders VALUES (1)",
    "SELECT '/*'; DELETE FROM orders; --*/'",  # a quote hiding a comment marker
    "SELECT zeroblob(500000000)",
    "SELECT randomblob(4)",
    "SELECT printf('%.*c', 400000000, 'x')",
])
def test_writes_never_run(sql):
    assert guard.refuse(sql) is not None


def test_stripping_a_dollar_sign_from_a_number_is_caught(messy_xlsx):
    tables = load(open_db(), [messy_xlsx])
    why = guard.misread("SELECT SUM(CAST(SUBSTR(amount, 2) AS REAL)) FROM orders", tables)
    assert why and "already a number" in why
    assert guard.misread("SELECT substr(date, 1, 7), SUM(amount) FROM orders GROUP BY 1", tables) is None


def test_the_connection_is_read_only_even_if_a_write_slipped_through(messy_xlsx):
    db = open_db()
    load(db, [messy_xlsx])
    guard.run(db, "SELECT 1")
    with pytest.raises(sqlite3.OperationalError):
        db.execute("DELETE FROM orders")


def test_a_runaway_query_is_stopped():
    db = open_db()
    with pytest.raises(sqlite3.OperationalError):
        guard.run(db, "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT COUNT(*) FROM n", seconds=0.2)


def test_a_second_statement_is_an_error_not_a_crash():
    db = open_db()
    with pytest.raises((sqlite3.Error, sqlite3.Warning)):
        guard.run(db, "SELECT 1; SELECT 2")
