from sheetsense.tables import as_number, describe, load, open_db


def test_a_messy_sheet_loads_as_clean_typed_columns(messy_xlsx):
    db = open_db()
    [t] = load(db, [messy_xlsx])
    assert t.name == "orders"
    assert t.rows == 4 and t.skipped_totals == 1
    assert [(c.name, c.kind) for c in t.columns] == [
        ("date", "date"), ("customer", "text"), ("region", "text"), ("amount", "number"), ("status", "text"), ("amount_2", "number"),
    ]
    total = db.execute("SELECT SUM(amount) FROM orders").fetchone()[0]
    assert total == 2671.75  # "$480.00", "$1,000.25" and "(25.00)" became numbers; the Total row wasn't counted twice


def test_text_matches_ignore_case(messy_xlsx):
    db = open_db()
    load(db, [messy_xlsx])
    assert db.execute("SELECT COUNT(*) FROM orders WHERE status = 'Unpaid'").fetchone()[0] == 2


def test_dates_are_iso_text(messy_xlsx):
    db = open_db()
    load(db, [messy_xlsx])
    months = [r[0] for r in db.execute("SELECT DISTINCT substr(date, 1, 7) FROM orders ORDER BY 1")]
    assert months == ["2025-03", "2025-04"]


def test_the_description_lists_a_short_columns_values(messy_xlsx, attendance_csv):
    db = open_db()
    text = describe(load(db, [messy_xlsx, attendance_csv]))
    assert "Table orders: 4 rows" in text and "1 total row(s) left out" in text
    assert "values: 'Paid', 'unpaid'" in text
    assert "Table attendance: 3 rows" in text


def test_money_formats():
    assert as_number("$1,216.50") == 1216.5
    assert as_number("(25.00)") == -25.0
    assert as_number("-$3") == -3.0
    assert as_number("12 boxes") is None
    assert as_number(True) is None
