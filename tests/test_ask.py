import json

import pytest

from conftest import FakeModel
from sheetsense.ask import CouldNotAnswer, ask, parse
from sheetsense.cli import main, table
from sheetsense.tables import load, open_db


def reply(sql, note="ok"):
    return json.dumps({"sql": sql, "note": note})


def test_the_figures_come_from_sqlite_not_the_model(messy_xlsx):
    db = open_db()
    tables = load(db, [messy_xlsx])
    model = FakeModel(reply("SELECT region, SUM(amount) AS total FROM orders GROUP BY region ORDER BY total DESC"))
    answer = ask("Sales by region?", db, tables, model)
    assert answer.result.rows == [("West", 2216.75), ("Central", 480.0), ("East", -25.0)]
    assert "Table orders" in model.seen[0][0]["content"]  # the model was shown the schema


def test_a_failed_query_goes_back_with_the_error_and_is_fixed(messy_xlsx):
    db = open_db()
    tables = load(db, [messy_xlsx])
    model = FakeModel(reply("SELECT total FROM orders"), reply("SELECT SUM(amount) FROM orders"))
    answer = ask("Total?", db, tables, model)
    assert answer.result.rows == [(2671.75,)]
    assert answer.attempts == ["SQLite: no such column: total"]
    assert "no such column: total" in model.seen[1][-1]["content"]


def test_a_write_is_refused_and_the_model_told_why(messy_xlsx):
    db = open_db()
    tables = load(db, [messy_xlsx])
    model = FakeModel(reply("DELETE FROM orders"), reply("SELECT COUNT(*) FROM orders"))
    assert ask("How many?", db, tables, model).result.rows == [(4,)]
    assert "can only read" in model.seen[1][-1]["content"] or "Only a SELECT" in model.seen[1][-1]["content"]


def test_it_gives_up_after_three_tries(messy_xlsx):
    db = open_db()
    tables = load(db, [messy_xlsx])
    model = FakeModel(*[reply("SELECT nope FROM orders")] * 3)
    with pytest.raises(CouldNotAnswer) as e:
        ask("?", db, tables, model)
    assert len(e.value.attempts) == 3


def test_a_sql_block_is_accepted_when_the_reply_isnt_json():
    assert parse("Here you go:\n```sql\nSELECT 1\n```") == ("SELECT 1", "")


def test_the_sql_command_prints_a_table(messy_xlsx, attendance_csv, capsys):
    sql = ("SELECT customer FROM attendance WHERE attended = 'yes' "
           "AND customer NOT IN (SELECT customer FROM orders) ORDER BY customer")
    assert main(["sql", str(messy_xlsx), str(attendance_csv), sql]) == 0
    assert capsys.readouterr().out.split() == ["customer", "─────────", "Driftwood"]


def test_the_sql_command_refuses_a_write(messy_xlsx):
    with pytest.raises(SystemExit) as e:
        main(["sql", str(messy_xlsx), "DELETE FROM orders"])
    assert "Only a SELECT" in str(e.value)


def test_numbers_line_up_on_the_right():
    from sheetsense.guard import Result

    out = table(Result(["region", "sales"], [("West", 62694.72), ("East", 5.0)])).splitlines()
    assert out[2] == "West    62,694.72"
    assert out[3] == "East            5"
