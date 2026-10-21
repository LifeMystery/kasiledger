"""Lender-ready business report as a PDF (ReportLab - free and open source)."""
from __future__ import annotations

import hashlib
from datetime import datetime
from io import BytesIO

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from ..models import Business
from .ledger import analytics
from .verification import trust_score

INK = colors.HexColor("#1F2A24")
MUTED = colors.HexColor("#5F6B64")
ACCENT = colors.HexColor("#1E7A4F")
LINE = colors.HexColor("#D9DED9")
LEVEL_COLOURS = {"High": "#1E7A4F", "Medium": "#B7791F", "Low": "#B83232"}


def _r(v: float) -> str:
    return f"R {v:,.2f}".replace(",", " ")


def build_report(db: Session, business: Business) -> bytes:
    trust = trust_score(db, business.id)
    data = analytics(db, business.id)
    generated = datetime.now()
    report_id = hashlib.sha1(f"{business.id}-{generated:%Y%m%d%H%M}".encode()).hexdigest()[:10].upper()

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, textColor=INK, alignment=0, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12.5, textColor=INK, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5, textColor=INK, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=MUTED, leading=10.5)

    def table(rows, widths, header=True, align_right_from=1):
        t = Table(rows, colWidths=widths)
        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), INK),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"),
        ]
        if header:
            style += [("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED)]
        t.setStyle(TableStyle(style))
        return t

    story = []
    story.append(Paragraph("Verified Business Report", h1))
    story.append(Paragraph(f"KasiLedger &middot; Report {report_id} &middot; Generated {generated:%d %B %Y, %H:%M}", small))
    story.append(Spacer(1, 6 * mm))

    info = [
        ["Business", business.name or "-"],
        ["Owner", business.owner_name or "-"],
        ["Type", business.business_type or "-"],
        ["Location", business.location or "-"],
        ["Record keeping since", business.created_at.strftime("%d %B %Y")],
    ]
    story.append(table(info, [45 * mm, 120 * mm], header=False, align_right_from=2))

    level_col = colors.HexColor(LEVEL_COLOURS[trust["level"]])
    story.append(Spacer(1, 5 * mm))
    score_tbl = Table(
        [[
            Paragraph(f"<font size=26 color='{LEVEL_COLOURS[trust['level']]}'><b>{trust['score']}</b></font>"
                      f"<font size=11 color='#5F6B64'> / 100</font>", body),
            Paragraph(f"<b>Confidence: <font color='{LEVEL_COLOURS[trust['level']]}'>{trust['level']}</font></b><br/>"
                      f"Estimated monthly revenue: <b>{_r(trust['estimated_monthly_revenue'])}</b><br/>"
                      f"Sales recorded in the last {trust['period_days']} days: {_r(trust['revenue_in_period'])}", body),
        ]],
        colWidths=[40 * mm, 125 * mm],
    )
    score_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, level_col),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(score_tbl)

    story.append(Paragraph("How the trust score is made up", h2))
    rows = [["Evidence", "Detail", "Points"]]
    for c in trust["components"]:
        rows.append([c["label"], Paragraph(c["detail"], small), f"{c['points']:g} / {c['max']}"])
    story.append(table(rows, [55 * mm, 85 * mm, 25 * mm], align_right_from=2))

    if data["monthly"]:
        story.append(Paragraph("Monthly trading", h2))
        months = data["monthly"][-6:]
        d = Drawing(165 * mm, 45 * mm)
        chart = VerticalBarChart()
        chart.x, chart.y, chart.width, chart.height = 12 * mm, 6 * mm, 150 * mm, 36 * mm
        chart.data = [[m["sales"] for m in months]]
        chart.categoryAxis.categoryNames = [datetime.strptime(m["month"], "%Y-%m").strftime("%b %Y") for m in months]
        chart.categoryAxis.labels.fontSize = 7.5
        chart.valueAxis.labels.fontSize = 7.5
        chart.valueAxis.valueMin = 0
        chart.bars[0].fillColor = ACCENT
        chart.bars[0].strokeColor = None
        chart.barWidth = 6
        d.add(chart)
        story.append(d)
        rows = [["Month", "Sales", "Stock bought", "Expenses"]]
        for m in months:
            rows.append([datetime.strptime(m["month"], "%Y-%m").strftime("%B %Y"), _r(m["sales"]),
                         _r(m["purchases"]), _r(m["expenses"])])
        story.append(table(rows, [50 * mm, 38 * mm, 38 * mm, 38 * mm]))

    if data["top_items"]:
        story.append(Paragraph("Best-selling products (last 90 days)", h2))
        rows = [["Product", "Units sold", "Sales value"]]
        for it in data["top_items"][:6]:
            rows.append([it["name"].title(), f"{it['quantity']:g}", _r(it["revenue"])])
        story.append(table(rows, [70 * mm, 45 * mm, 50 * mm]))

    owed = data["outstanding_credit"]
    if owed:
        story.append(Paragraph("Money owed by customers", h2))
        total_owed = sum(o["amount"] for o in owed)
        confirmed = sum(o["confirmed_amount"] for o in owed)
        story.append(Paragraph(
            f"{len(owed)} customers owe {_r(total_owed)}; {_r(confirmed)} of this is confirmed by the customers themselves.",
            body))

    story.append(Paragraph("Entries flagged for review", h2))
    if trust["flags"]:
        rows = [["Date", "Reason", "Amount"]]
        for f in trust["flags"][:8]:
            rows.append([f["created_at"][:10], Paragraph("; ".join(f["reasons"]), small), _r(f["total"])])
        story.append(table(rows, [26 * mm, 109 * mm, 30 * mm], align_right_from=2))
        story.append(Paragraph("Flagged entries are excluded from revenue figures in this report.", small))
    else:
        story.append(Paragraph("No entries were flagged. Recorded sales are consistent with stock purchases and trading patterns.", body))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "How records are verified: every entry is confirmed by the owner when it is captured and time-stamped by "
        "KasiLedger. Sales are checked against supplier invoices and recorded stock, compared with the business's "
        "own trading pattern, matched against card/QR payment statements where available, and credit sales are "
        "confirmed directly by customers. This report summarises evidence; it is not an audited financial statement.",
        small))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=16 * mm, title=f"{business.name} - Verified Business Report",
                            author="KasiLedger")
    doc.build(story)
    return buf.getvalue()
