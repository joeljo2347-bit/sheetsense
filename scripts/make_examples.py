"""Make the example files: a fictional company's 2025 orders and webinar attendance.

The orders sheet is messy on purpose, the way real exports are: a title above the
headings, some amounts typed as text ("$1,216.50"), and a Total row at the bottom.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

OUT = Path(__file__).resolve().parent.parent / "examples"
rng = random.Random(2025)

CUSTOMERS = {
    "Alder & Finch Architects": "West", "Blue Harbor Dental": "West", "Cedar Point Logistics": "Central",
    "Driftwood Studios": "West", "Elmstead Library": "East", "Foxglove Bakery": "East",
    "Granite Ridge Clinic": "Central", "Halcyon Labs": "East", "Ironwood Law Group": "Central",
    "Juniper Schools": "East", "Kestrel Outdoor": "West", "Larkspur Hotel": "Central",
    "Marlow Accounting": "East", "Northgate Realty": "Central", "Oakhaven Vet": "West",
}
REPS = {"West": ["Maya Chen", "Luis Ortega"], "Central": ["Priya Shah", "Tom Becker"], "East": ["Grace Kim", "Sam Okafor"]}
PRODUCTS = {"Copy paper (case)": 42.0, "Toner cartridge": 89.5, "Desk chair": 249.0, "Standing desk": 529.0,
            "Monitor arm": 119.0, "Label printer": 159.99, "Whiteboard": 74.25}


def orders() -> list[list]:
    rows, day, n = [], date(2025, 1, 2), 0
    while day.year == 2025:
        for _ in range(rng.choice([0, 0, 1, 1, 1, 2])):
            n += 1
            customer = rng.choice(list(CUSTOMERS)[:12])  # the last three only ever come to webinars
            region = CUSTOMERS[customer]
            product = rng.choice(list(PRODUCTS))
            qty = rng.choice([1, 1, 2, 3, 4, 6, 10])
            amount = round(PRODUCTS[product] * qty * (1.12 if day.month in (9, 10, 11) else 1.0), 2)
            paid = "Paid" if day < date(2025, 11, 1) or rng.random() < 0.4 else "Unpaid"
            shown = f"${amount:,.2f}" if rng.random() < 0.25 else amount  # some typed as text
            rows.append([day, f"LS-{n:04d}", customer, region, rng.choice(REPS[region]), product, qty, shown, paid])
        day += timedelta(days=1)
    return rows


def write_orders(rows: list[list]) -> None:
    book = Workbook()
    book.properties.creator = "Joel Jo"
    sheet = book.active
    sheet.title = "Orders"
    sheet.append(["Lumen Supply Co. Orders 2025"])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([])
    sheet.append(["Date", "Order", "Customer", "Region", "Rep", "Product", "Qty", "Amount", "Status"])
    for cell in sheet[3]:
        cell.font = Font(bold=True)
    for r in rows:
        sheet.append(r)
    total = sum(float(str(r[7]).replace("$", "").replace(",", "")) for r in rows)
    sheet.append(["Total", None, None, None, None, None, sum(r[6] for r in rows), round(total, 2), None])
    for col, width in zip("ABCDEFGHI", (12, 9, 26, 9, 13, 20, 6, 12, 8)):
        sheet.column_dimensions[col].width = width
    for r in sheet.iter_rows(min_row=4, max_col=1):
        r[0].number_format = "yyyy-mm-dd"
    book.save(OUT / "sales_2025.xlsx")


def write_attendance() -> None:
    sessions = [(date(2025, m, 15), t) for m, t in [(2, "Hybrid office setup"), (4, "Ergonomics 101"), (6, "Going paperless"),
                                                     (9, "Budgeting for Q4"), (11, "Year-end ordering")]]
    with (OUT / "webinar_attendance.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Session", "Customer", "Attended"])
        for when, title in sessions:
            for customer in rng.sample(list(CUSTOMERS), 7):
                w.writerow([when.isoformat(), title, customer, "Yes" if rng.random() < 0.75 else "No"])


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    data = orders()
    write_orders(data)
    write_attendance()
    print(f"Wrote {len(data)} orders and the webinar attendance to {OUT}")
