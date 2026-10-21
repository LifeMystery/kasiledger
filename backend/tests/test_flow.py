"""End-to-end test of the demo flow through the simulator API.  Run:  pytest -q"""
import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="kasiledger-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.environ['DATA_DIR']}/test.db"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["WHATSAPP_TOKEN"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.main import app  # noqa: E402

OWNER = "+27820000001"
CUSTOMER = "+27821110001"


def last_reply(client, phone):
    msgs = client.get("/api/messages", params={"address": f"sim:{phone}"}).json()
    return [m for m in msgs if m["direction"] == "out"][-1]["text"]


def send(client, phone, text="", file=None):
    files = {"file": file} if file else None
    r = client.post("/api/simulator/send", data={"phone": phone, "text": text}, files=files)
    assert r.status_code == 200, r.text


def test_demo_flow():
    seed.main()
    with TestClient(app) as client:
        assert client.get("/api/config").json()["extractor"] == "rule_based"

        # Normal sale -> confirm -> saved
        send(client, OWNER, "sale bread 3 18")
        assert "54" in last_reply(client, OWNER)
        send(client, OWNER, "1")
        assert "Saved" in last_reply(client, OWNER)

        # Mixed-language sale
        send(client, OWNER, "Ngithengise izinkwa ezimbili ne-cooldrink, R66")
        reply = last_reply(client, OWNER)
        assert "bread" in reply and "R66" in reply
        send(client, OWNER, "yebo")

        # Fake huge sale gets flagged
        send(client, OWNER, "sale bread 500 18")
        send(client, OWNER, "1")
        assert "flagged" in last_reply(client, OWNER)
        trust = client.get("/api/businesses/1/trust").json()
        assert trust["flags"][0]["total"] == 9000

        # Credit -> customer gets asked -> customer confirms
        send(client, OWNER, f"owe Sipho 40 {CUSTOMER}")
        send(client, OWNER, "1")
        assert "owe" in last_reply(client, CUSTOMER)
        send(client, CUSTOMER, "YES")
        assert "confirmed" in last_reply(client, OWNER)

        # Supplier slip photo -> purchase
        from scripts.make_demo_receipt import main as make_receipt

        path = make_receipt(os.path.join(os.environ["DATA_DIR"], "slip.png"))
        with open(path, "rb") as fh:
            send(client, OWNER, file=("slip.png", fh, "image/png"))
        assert "bread" in last_reply(client, OWNER)
        send(client, OWNER, "1")

        # Commands
        for cmd, expected in [("summary", "Sales"), ("stock", "bread"), ("owed", "owed"), ("score", "Trust score")]:
            send(client, OWNER, cmd)
            assert expected in last_reply(client, OWNER), cmd

        # Report
        send(client, OWNER, "report")
        pdf = client.get("/api/businesses/1/report.pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

        # New business onboarding
        send(client, "+27829999999", "hi")
        assert "business called" in last_reply(client, "+27829999999")
        send(client, "+27829999999", "Kasi Car Wash")
        assert "Kasi Car Wash" in last_reply(client, "+27829999999")

        # Dashboard endpoints
        assert len(client.get("/api/businesses").json()) == 3
        assert client.get("/api/businesses/1/analytics").json()["daily"]
        assert client.get("/api/businesses/1/transactions").json()[0]["business_id"] == 1

        # WebSocket receives live events
        with client.websocket_connect("/ws") as ws:
            send(client, OWNER, "sale milk 1 25")
            event = ws.receive_json()
            assert event["type"] in ("message", "transaction")
