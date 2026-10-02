from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook


@pytest.fixture
def messy_xlsx(tmp_path: Path) -> Path:
    """A title above the headings, money typed as text, a duplicate heading and a Total row."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Orders"
    sheet.append(["Acme Orders 2025"])
    sheet.append([])
    sheet.append(["Date", "Customer", "Region", "Amount", "Status", "Amount"])
    sheet.append([date(2025, 3, 1), "Blue Harbor", "West", 1216.5, "Paid", 1])
    sheet.append([date(2025, 3, 9), "Cedar Point", "Central", "$480.00", "unpaid", 2])
    sheet.append([date(2025, 4, 2), "Blue Harbor", "West", "$1,000.25", "Unpaid", 3])
    sheet.append([date(2025, 4, 20), "Elmstead", "East", "(25.00)", "Paid", 4])
    sheet.append(["Total", None, None, 2671.75, None, None])
    path = tmp_path / "orders.xlsx"
    book.save(path)
    return path


@pytest.fixture
def attendance_csv(tmp_path: Path) -> Path:
    path = tmp_path / "attendance.csv"
    path.write_text("Date,Customer,Attended\n2025-02-15,Blue Harbor,Yes\n2025-02-15,Driftwood,Yes\n2025-04-15,Foxglove,No\n")
    return path


class FakeModel:
    """Plays the model: hands back the replies it was given, one per call, and keeps what it was sent."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.seen = []

    def complete(self, messages):
        self.seen.append(messages)
        return self.replies.pop(0)
