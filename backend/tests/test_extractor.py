import pytest

from app.ai.extractor import RuleBasedExtractor

E = RuleBasedExtractor()


@pytest.mark.parametrize("text,kind,total,items", [
    ("sale bread 3 18", "sale", 54, [("bread", 3)]),
    ("Ngithengise izinkwa ezintathu ne-cooldrink, R60", "sale", 60, [("bread", 3), ("cooldrink", 1)]),
    ("sold 3 bread for 60", "sale", 60, [("bread", 3)]),
    ("buy bread 50 @ 12", "purchase", 600, [("bread", 50)]),
    ("sale bread 3 18, milk 2 25", "sale", 104, [("bread", 3), ("milk", 2)]),
    ("Ke rekisitse bohobe tse pedi R36", "sale", 36, [("bread", 2)]),
    ("expense taxi 30", "expense", 30, [("transport", 1)]),
    ("paid rent 1500", "expense", 1500, [("rent", 1)]),
    ("sale scones 2 5", "sale", 10, [("scones", 2)]),
])
def test_entries(text, kind, total, items):
    r = E.extract(text)
    assert r.type == kind
    assert r.total == total
    assert [(i.name, i.quantity) for i in r.items] == items


def test_credit_and_repayment():
    r = E.extract("Sipho owes R40 0821234567")
    assert r.on_credit and r.customer_name == "Sipho" and r.customer_phone == "+27821234567" and r.total == 40
    r = E.extract("uSipho uyangikweleta R40")
    assert r.on_credit and r.customer_name == "Sipho"
    r = E.extract("paid Sipho 20")
    assert r.type == "repayment" and r.customer_name == "Sipho" and r.total == 20


def test_not_understood():
    assert E.extract("hello") is None
    assert not E.extract("sale bread").is_complete
