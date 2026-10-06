import json

import pytest

pytest.importorskip("multipart")
web = pytest.importorskip("sheetsense.web")
from conftest import FakeModel  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def reply(sql):
    return json.dumps({"sql": sql, "note": "Sums it"})


@pytest.fixture
def client(monkeypatch):
    web.asked.clear()
    monkeypatch.setattr(web, "waiting", 0)
    return TestClient(web.app)


def test_the_page_and_examples_load(client):
    assert "sheetsense" in client.get("/").text
    data = client.get("/api/examples").json()
    assert [f["name"] for f in data["files"]] == ["sales_2025.xlsx", "webinar_attendance.csv"]
    assert data["tables"][0]["rows"] == 289


def test_a_question_on_the_examples(client, monkeypatch):
    monkeypatch.setattr(web, "model", FakeModel(reply("SELECT COUNT(*) AS orders FROM sales_2025")))
    r = client.post("/api/ask", data={"question": "How many orders?", "examples": "sales_2025.xlsx"})
    assert r.status_code == 200
    assert r.json()["rows"] == [[289]] and r.json()["columns"] == ["orders"]


def test_an_upload_is_read_and_answered(client, monkeypatch, tmp_path):
    monkeypatch.setattr(web, "model", FakeModel(reply("SELECT team, SUM(hours) FROM hours GROUP BY team ORDER BY team")))
    files = {"files": ("hours.csv", b"Team,Hours\nDesign,12\nDesign,7.5\nOps,20\n", "text/csv")}
    r = client.post("/api/ask", data={"question": "Hours by team?"}, files=files)
    assert r.json()["rows"] == [["Design", 19.5], ["Ops", 20.0]]


@pytest.mark.parametrize("name,content,message", [
    ("notes.txt", b"hi", "only .xlsx and .csv"),
    ("fake.xlsx", b"not a zip", "isn't a valid .xlsx"),
    ("big.csv", b"a,b\n" + b"1,2\n" * 600_000, "over 2 MB"),
])
def test_bad_uploads_are_refused_before_the_model(client, monkeypatch, name, content, message):
    monkeypatch.setattr(web, "model", FakeModel())  # would fail if called
    r = client.post("/api/ask", data={"question": "?"}, files={"files": (name, content, "application/octet-stream")})
    assert r.status_code == 400 and message in r.json()["error"]


def test_each_visitor_gets_a_limited_number_of_questions(client, monkeypatch):
    monkeypatch.setattr(web, "PER_VISITOR", 2)
    monkeypatch.setattr(web, "model", FakeModel(*[reply("SELECT 1")] * 3))
    codes = [client.post("/api/ask", data={"question": "?", "examples": "sales_2025.xlsx"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_a_full_queue_turns_people_away_politely(client, monkeypatch):
    monkeypatch.setattr(web, "waiting", web.MAX_WAITING)
    r = client.post("/api/ask", data={"question": "?", "examples": "sales_2025.xlsx"})
    assert r.status_code == 503 and "busy" in r.json()["error"]


def test_the_model_being_down_is_a_message_not_a_crash(client, monkeypatch):
    class Down:
        def complete(self, messages):
            raise ConnectionError("no")

    monkeypatch.setattr(web, "model", Down())
    r = client.post("/api/ask", data={"question": "?", "examples": "sales_2025.xlsx"})
    assert r.status_code == 503 and "isn't available" in r.json()["error"]


def test_only_the_examples_can_be_downloaded(client):
    assert client.get("/examples/sales_2025.xlsx").status_code == 200
    assert client.get("/examples/..%2Fpyproject.toml").status_code == 404
    assert client.get("/docs").status_code == 404


def test_binary_values_are_sent_as_a_note():
    assert web.cell(b"\x00\xff\x10") == "<3 bytes>" and web.cell("text") == "text" and web.cell(4.5) == 4.5


def test_two_uploads_with_the_same_name_are_both_read(client, monkeypatch):
    monkeypatch.setattr(web, "model", FakeModel(reply("SELECT 1")))
    files = [("files", ("hours.csv", b"Team,Hours\nDesign,12\n", "text/csv")),
             ("files", ("hours.csv", b"Team,Hours\nOps,20\n", "text/csv"))]
    r = client.post("/api/ask", data={"question": "Hours?"}, files=files)
    assert r.status_code == 200 and len(r.json()["tables"]) == 2
