"""Render member cards to PDF: the same CR80 layout and barcode as the current cards.

Front: society name, member name and number, a Code128 barcode of the member
number, and the season of the membership held. Back: the shuttle QR code and
the print date. One page per card so a batch prints straight through.
"""

from dataclasses import dataclass
from datetime import date
from io import BytesIO

from reportlab.graphics.barcode import code128, qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

CARD_WIDTH = 86 * mm
CARD_HEIGHT = 54 * mm
SOCIETY = "Squamish Windsports Society"


@dataclass(frozen=True)
class CardData:
    member_number: int
    first_name: str
    last_name: str
    season_label: str  # e.g. "2026 member" or "No current membership"
    sports_label: str
    shuttle_url: str
    printed_on: date
    photo_jpeg: bytes | None = None


PHOTO_BOX = (5 * mm, 9 * mm, 22 * mm, 28 * mm)  # x, y, width, height


def _front(pdf: canvas.Canvas, card: CardData) -> None:
    pdf.setFillColorRGB(0.04, 0.42, 0.80)
    pdf.rect(0, CARD_HEIGHT - 11 * mm, CARD_WIDTH, 11 * mm, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(5 * mm, CARD_HEIGHT - 7.5 * mm, SOCIETY)

    px, py, pw, ph = PHOTO_BOX
    if card.photo_jpeg:
        pdf.drawImage(
            ImageReader(BytesIO(card.photo_jpeg)),
            px,
            py,
            pw,
            ph,
            preserveAspectRatio=True,
            anchor="c",
        )
    else:
        pdf.setStrokeColorRGB(0.7, 0.7, 0.7)
        pdf.rect(px, py, pw, ph, stroke=1, fill=0)
        pdf.setFillColorRGB(0.5, 0.5, 0.5)
        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString(px + pw / 2, py + ph / 2, "no photo")

    text_x = px + pw + 4 * mm
    text_width = CARD_WIDTH - text_x - 4 * mm
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(text_x, CARD_HEIGHT - 18 * mm, f"{card.first_name} {card.last_name}"[:26])
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(text_x, CARD_HEIGHT - 23 * mm, card.season_label)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(text_x, CARD_HEIGHT - 27.5 * mm, card.sports_label[:48])

    barcode = code128.Code128(str(card.member_number), barHeight=10 * mm, barWidth=0.3 * mm)
    x = text_x + (text_width - barcode.width) / 2
    barcode.drawOn(pdf, x, 10 * mm)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawCentredString(text_x + text_width / 2, 5 * mm, f"Member {card.member_number}")


def _back(pdf: canvas.Canvas, card: CardData) -> None:
    widget = qr.QrCodeWidget(card.shuttle_url)
    bounds = widget.getBounds()
    size = 30 * mm
    scale = size / (bounds[2] - bounds[0])
    drawing = Drawing(size, size, transform=[scale, 0, 0, scale, 0, 0])
    drawing.add(widget)
    from reportlab.graphics import renderPDF

    renderPDF.draw(drawing, pdf, (CARD_WIDTH - size) / 2, 14 * mm)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(CARD_WIDTH / 2, 10 * mm, "Shuttle and parking: scan for today's schedule")
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(CARD_WIDTH / 2, 4 * mm, f"Printed {card.printed_on.isoformat()}")


def render_cards(cards: list[CardData]) -> bytes:
    """A PDF with a front and a back page per card."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(CARD_WIDTH, CARD_HEIGHT))
    pdf.setTitle("SWS member cards")
    for card in cards:
        _front(pdf, card)
        pdf.showPage()
        _back(pdf, card)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()
