"""Turn a message ("sale bread 3 18") into a structured transaction.

Two free implementations behind one interface:
  - RuleBasedExtractor: keywords + patterns. Fast, predictable, needs a simple format.
  - OllamaExtractor:    a small local LLM that understands normal sentences. Falls back to rules.

A paid cloud LLM can be added later as another class with the same `extract` method.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import httpx

from .. import config
from . import lexicon as lx


@dataclass
class ExtractedItem:
    name: str
    quantity: float = 1
    unit_price: float | None = None
    line_total: float | None = None

    def as_dict(self) -> dict:
        price = self.unit_price
        if price is None and self.line_total is not None and self.quantity:
            price = round(self.line_total / self.quantity, 2)
        return {"name": self.name, "quantity": self.quantity, "unit_price": price}


@dataclass
class ExtractedTransaction:
    type: str  # sale | purchase | expense | repayment
    items: list[ExtractedItem] = field(default_factory=list)
    total: float | None = None
    on_credit: bool = False
    customer_name: str | None = None
    customer_phone: str | None = None
    note: str = ""
    confidence: float = 0.5
    extractor: str = "rule_based"

    @property
    def is_complete(self) -> bool:
        if self.total is None or self.total <= 0:
            return False
        if self.on_credit or self.type == "repayment":
            return bool(self.customer_name)
        return True


class Extractor:
    name = "base"

    def extract(self, text: str) -> ExtractedTransaction | None:  # pragma: no cover - interface
        raise NotImplementedError


# ---------------------------------------------------------------- rule-based parser

_PHONE_RE = re.compile(r"(?:\+?27|0)[6-8]\d{8}\b")
_MONEY_RE = re.compile(r"^r(\d+(?:[.,]\d{1,2})?)$")
_NUM_RE = re.compile(r"^\d+(?:[.,]\d{1,2})?$")
_QTY_X_RE = re.compile(r"^(\d+)x$|^x(\d+)$")


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def _number_word(tok: str) -> int | None:
    if tok in lx.NUMBER_WORDS:
        return lx.NUMBER_WORDS[tok]
    if len(tok) >= 5:
        for stem, value in lx.NUMBER_STEMS:
            if tok.endswith(stem):
                return value
    return None


def _detect_type(tok: str) -> str | None:
    for kind, words in lx.TYPE_WORDS.items():
        if tok in words:
            return kind
    for stem, kind in lx.TYPE_STEMS:
        if stem in tok:
            return kind
    return None


def normalise_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0"):
        digits = "27" + digits[1:]
    return "+" + digits


class RuleBasedExtractor(Extractor):
    name = "rule_based"

    def extract(self, text: str) -> ExtractedTransaction | None:
        if not text or not text.strip():
            return None
        original = text.strip()

        phone_match = _PHONE_RE.search(original)
        phone = normalise_phone(phone_match.group(0)) if phone_match else None
        work = _PHONE_RE.sub(" ", original)

        # isiZulu names often carry a noun prefix: "uSipho" -> "Sipho"
        work = re.sub(r"\bu([A-Z][a-z]+)", r"\1", work)
        # "R 60" -> "R60", "R60.00" kept
        work = re.sub(r"\b[Rr]\s+(\d)", r"R\1", work)

        lowered = work.lower()
        for phrase, joined in lx.PHRASES.items():
            lowered = lowered.replace(phrase, joined.replace(" ", "_"))
        lowered = re.sub(r"([,;=&+@])", r" \1 ", lowered)
        lowered = lowered.replace("-", " ")
        tokens = [t.strip(".!?:()\"'") for t in lowered.split()]
        tokens = [t.replace("_", " ") for t in tokens if t]

        # Keep the original casing per token to spot names (best effort).
        orig_tokens = re.sub(r"([,;=&+@])", r" \1 ", work.replace("-", " ")).split()
        capitalised = {t.strip(".!?:()\"'").lower() for t in orig_tokens if t[:1].isupper()}

        kind: str | None = None
        on_credit = False
        paid_seen = False
        for tok in tokens:
            t = _detect_type(tok)
            if t and kind is None:
                kind = t
            if tok == "paid":
                paid_seen = True

        # Customer name: first word that isn't a keyword, item, number or stopword.
        name: str | None = None
        for tok in tokens:
            if (
                tok in lx.STOPWORDS or tok in lx.SEPARATORS or tok in lx.ITEMS
                or _detect_type(tok) or _number_word(tok) is not None
                or _NUM_RE.match(tok) or _MONEY_RE.match(tok) or _QTY_X_RE.match(tok)
                or not tok.isalpha()
            ):
                continue
            name = tok.capitalize()
            break

        if kind is None and paid_seen:
            # "paid Sipho 20" (a customer paying back) vs "paid rent 1500" (an expense)
            kind = "repayment" if (name and name.lower() in capitalised) else "expense"
        if kind == "credit":
            kind, on_credit = "sale", True
        customer_word = name.lower() if name and (on_credit or kind == "repayment") else None

        segments: list[list[str]] = [[]]
        for tok in tokens:
            if tok in lx.SEPARATORS:
                segments.append([])
            else:
                segments[-1].append(tok)

        items: list[ExtractedItem] = []
        overall_total: float | None = None
        unknown_words: list[str] = []

        for seg in segments:
            item_name: str | None = None
            plain: list[float] = []
            money: list[tuple[float, str]] = []  # (value, role) role: total | each | money
            explicit_qty: float | None = None  # from number words ("ezintathu") or "3x"
            marker: str | None = None
            for tok in seg:
                if tok in lx.TOTAL_MARKERS:
                    marker = "total"
                    continue
                if tok in lx.EACH_MARKERS:
                    marker = "each"
                    continue
                m = _MONEY_RE.match(tok)
                if m:
                    money.append((_to_float(m.group(1)), marker or "money"))
                    marker = None
                    continue
                if _NUM_RE.match(tok):
                    if marker:
                        money.append((_to_float(tok), marker))
                        marker = None
                    else:
                        plain.append(_to_float(tok))
                    continue
                mx = _QTY_X_RE.match(tok)
                if mx:
                    explicit_qty = float(mx.group(1) or mx.group(2))
                    continue
                nw = _number_word(tok)
                if nw is not None:
                    explicit_qty = float(nw)
                    continue
                if tok in lx.ITEMS and item_name is None:
                    item_name = lx.ITEMS[tok]
                    continue
                if (
                    item_name is None and tok.isalpha() and tok not in lx.STOPWORDS
                    and not _detect_type(tok) and tok != customer_word
                ):
                    unknown_words.append(tok)

            if item_name is None and kind in ("sale", "purchase", "expense") and unknown_words and (plain or money):
                # Unknown item word - accept it as typed so new products still work.
                item_name = unknown_words.pop(0)
            unknown_words.clear()

            if item_name is None:
                # A segment with only money is an overall total: "..., R60"
                values = plain + [v for v, _ in money]
                if values:
                    overall_total = values[-1]
                continue

            item = ExtractedItem(name=item_name)
            numbers = plain[:]
            if explicit_qty is not None:
                numbers.insert(0, explicit_qty)
                if len(numbers) == 1:
                    item.quantity = explicit_qty
                    numbers = []
            if money:
                value, role = money[-1]
                if role == "each":
                    item.unit_price = value
                    if numbers:
                        item.quantity = numbers[0]
                elif numbers:
                    item.quantity = numbers[0]
                    item.line_total = value
                else:
                    item.line_total = value
            elif len(numbers) >= 2:
                item.quantity, item.unit_price = numbers[0], numbers[1]
            elif len(numbers) == 1:
                # One bare number: treat it as the amount ("sale bread 18")
                item.line_total = numbers[0]
            items.append(item)

        if kind is None:
            if not items and overall_total is None:
                return None
            kind = "sale"  # most common entry - shown to the owner for confirmation anyway

        line_totals: list[float] = []
        for it in items:
            if it.line_total is not None:
                line_totals.append(it.line_total)
            elif it.unit_price is not None:
                it.line_total = round(it.quantity * it.unit_price, 2)
                line_totals.append(it.line_total)

        total = overall_total
        if total is None and line_totals and len(line_totals) == len(items):
            total = round(sum(line_totals), 2)
        elif total is None and line_totals:
            total = round(sum(line_totals), 2)

        note = ""
        if kind in ("expense",) and items:
            note = ", ".join(i.name for i in items)
        if kind == "repayment":
            items = []

        result = ExtractedTransaction(
            type=kind,
            items=items,
            total=total,
            on_credit=on_credit,
            customer_name=name if (on_credit or kind == "repayment") else None,
            customer_phone=phone,
            note=note,
            extractor=self.name,
        )
        # Simple confidence: did we find a type keyword, items and an amount?
        score = 0.4
        if any(_detect_type(t) for t in tokens) or paid_seen:
            score += 0.3
        if items or kind == "repayment":
            score += 0.15
        if total:
            score += 0.15
        result.confidence = round(min(score, 1.0), 2)
        return result


# ---------------------------------------------------------------- local LLM (Ollama)

_LLM_PROMPT = """You turn a South African small-business owner's message into JSON.
Messages may mix English, isiZulu, Sesotho, Setswana and Afrikaans. Amounts are in Rand.
Return ONLY JSON with this shape:
{"type": "sale|purchase|expense|repayment", "on_credit": false,
 "items": [{"name": "bread", "quantity": 3, "unit_price": 18}],
 "total": 54, "customer_name": null}
Rules: "owes"/"on credit"/"kweleta" means a sale on credit (on_credit true, set customer_name).
A customer paying back money is "repayment". Use null when unsure - never guess.
Examples:
"Ngithengise izinkwa ezintathu ne-cooldrink, R60" -> {"type":"sale","on_credit":false,"items":[{"name":"bread","quantity":3,"unit_price":null},{"name":"cooldrink","quantity":1,"unit_price":null}],"total":60,"customer_name":null}
"Bought 20 loaves at R14 each from the wholesaler" -> {"type":"purchase","on_credit":false,"items":[{"name":"bread","quantity":20,"unit_price":14}],"total":280,"customer_name":null}
"Sipho took 2 milk on credit, R50" -> {"type":"sale","on_credit":true,"items":[{"name":"milk","quantity":2,"unit_price":25}],"total":50,"customer_name":"Sipho"}
"Paid taxi R30" -> {"type":"expense","on_credit":false,"items":[{"name":"transport","quantity":1,"unit_price":30}],"total":30,"customer_name":null}
Message: """


class OllamaExtractor(Extractor):
    name = "ollama"

    def __init__(self, fallback: Extractor | None = None):
        self.fallback = fallback or RuleBasedExtractor()

    def extract(self, text: str) -> ExtractedTransaction | None:
        try:
            resp = httpx.post(
                f"{config.OLLAMA_URL}/api/generate",
                json={"model": config.OLLAMA_MODEL, "prompt": _LLM_PROMPT + text, "format": "json", "stream": False,
                      "options": {"temperature": 0}},
                timeout=60,
            )
            resp.raise_for_status()
            data = json.loads(resp.json().get("response", "{}"))
            result = self._from_json(data, text)
            if result and result.is_complete:
                return result
        except Exception as exc:  # noqa: BLE001 - any failure falls back to rules
            print(f"[ollama] falling back to rules: {exc}")
        return self.fallback.extract(text)

    def _from_json(self, data: dict, text: str) -> ExtractedTransaction | None:
        kind = str(data.get("type") or "").lower()
        if kind not in {"sale", "purchase", "expense", "repayment"}:
            return None
        items = []
        for raw in data.get("items") or []:
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            name = str(raw["name"]).lower().strip()
            name = lx.ITEMS.get(name, name)
            qty = raw.get("quantity") or 1
            price = raw.get("unit_price")
            items.append(ExtractedItem(name=name, quantity=float(qty), unit_price=float(price) if price else None))
        total = data.get("total")
        if total is None and items and all(i.unit_price is not None for i in items):
            total = sum(i.quantity * (i.unit_price or 0) for i in items)
        phone = _PHONE_RE.search(text)
        return ExtractedTransaction(
            type=kind,
            items=items if kind != "repayment" else [],
            total=float(total) if total else None,
            on_credit=bool(data.get("on_credit")),
            customer_name=(str(data["customer_name"]).strip().capitalize() if data.get("customer_name") else None),
            customer_phone=normalise_phone(phone.group(0)) if phone else None,
            note=", ".join(i.name for i in items) if kind == "expense" else "",
            confidence=0.85,
            extractor=self.name,
        )


def get_extractor() -> Extractor:
    if config.EXTRACTOR == "ollama":
        return OllamaExtractor()
    return RuleBasedExtractor()
