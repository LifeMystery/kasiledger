"""Read supplier invoices / till slips from a photo.

Free: Tesseract OCR. Works on clear, printed slips photographed flat.
Paid upgrade later: Azure AI Document Intelligence (prebuilt receipt/invoice model).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import config
from . import lexicon as lx
from .extractor import ExtractedItem

_SKIP = re.compile(r"\b(sub\s*total|vat|tax|change|cash|tender|card|balance|rounding|discount|tel|reg)\b", re.I)
_TOTAL = re.compile(r"\b(total|amount due|totaal)\b", re.I)
_AMOUNT_AT_END = re.compile(r"R?\s*(\d{1,6}[.,]\d{2})\s*$")
_QTY_AT_PRICE = re.compile(r"(\d+)\s*[xX@]\s*R?\s*(\d+[.,]\d{2})")
_LEADING_QTY = re.compile(r"^(\d{1,4})\s+([A-Za-z].*)$")


@dataclass
class InvoiceResult:
    supplier: str = ""
    items: list[ExtractedItem] = field(default_factory=list)
    total: float | None = None
    raw_text: str = ""


def _money(s: str) -> float:
    return float(s.replace(",", "."))


def _item_name(desc: str) -> str:
    words = re.findall(r"[a-z]+", desc.lower())
    for w in words:
        if w in lx.ITEMS:
            return lx.ITEMS[w]
    joined = " ".join(words)
    for phrase, std in lx.PHRASES.items():
        if phrase in joined:
            return lx.ITEMS.get(std, std)
    return " ".join(words[:3]) or "stock"


def parse_receipt_text(text: str) -> InvoiceResult:
    result = InvoiceResult(raw_text=text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        if not result.supplier and re.search(r"[A-Za-z]{3,}", ln) and not _AMOUNT_AT_END.search(ln):
            result.supplier = ln[:60]
            continue
        amount = _AMOUNT_AT_END.search(ln)
        if not amount:
            continue
        if _TOTAL.search(ln) and not re.search(r"sub\s*total", ln, re.I):
            result.total = _money(amount.group(1))
            continue
        if _SKIP.search(ln):
            continue
        desc = ln[: amount.start()].strip(" .:-")
        line_total = _money(amount.group(1))
        qty = 1.0
        unit = None
        m = _QTY_AT_PRICE.search(desc)
        if m:
            qty, unit = float(m.group(1)), _money(m.group(2))
            desc = (desc[: m.start()] + desc[m.end():]).strip()
        else:
            lead = _LEADING_QTY.match(desc)
            if lead:
                qty, desc = float(lead.group(1)), lead.group(2)
        if not re.search(r"[A-Za-z]", desc):
            continue
        result.items.append(
            ExtractedItem(name=_item_name(desc), quantity=qty, unit_price=unit, line_total=line_total)
        )
    if result.total is None and result.items:
        result.total = round(sum(i.line_total or 0 for i in result.items), 2)
    return result


class Ocr:
    name = "none"
    available = False

    def read_invoice(self, image_path: Path) -> InvoiceResult | None:
        return None


class TesseractOcr(Ocr):
    name = "tesseract"

    def __init__(self) -> None:
        try:
            import pytesseract

            if config.TESSERACT_CMD:
                pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
            pytesseract.get_tesseract_version()
            self.available = True
        except Exception:  # noqa: BLE001
            print("[ocr] Tesseract is not installed - see README for install steps")
            self.available = False

    def read_invoice(self, image_path: Path) -> InvoiceResult | None:
        if not self.available:
            return None
        import pytesseract
        from PIL import Image, ImageOps

        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img).convert("L")
        # Upscale small phone photos - Tesseract likes ~300 dpi text
        if img.width < 1200:
            factor = 1200 / img.width
            img = img.resize((int(img.width * factor), int(img.height * factor)))
        text = pytesseract.image_to_string(img, config="--psm 6")
        result = parse_receipt_text(text)
        return result if result.items else None


_instance: Ocr | None = None


def get_ocr() -> Ocr:
    global _instance
    if _instance is None:
        _instance = TesseractOcr() if config.OCR == "tesseract" else Ocr()
    return _instance
