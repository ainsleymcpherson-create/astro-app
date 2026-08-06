"""
email_worker/pdf_utils.py

Self-contained PDF generation for readings emailed by this worker --
mirrors the branded PDF renderer in the main Streamlit app's app.py
(markdown_to_pdf_bytes, _ArcDivider, _pdf_footer), but lives here
independently since this worker doesn't import from the Streamlit app
(see this folder's own module-level docstring in app.py for why: it's
deployed as its own independent Render service and needs to be
self-contained).

Requires: pip install reportlab
Requires a fonts/ directory alongside this file (copy it from the
main app's fonts/ folder: LiberationSerif-Regular.ttf, -Bold.ttf,
-Italic.ttf, LiberationSans-Regular.ttf, -Bold.ttf) -- falls back to
reportlab's built-in Times-Roman/Helvetica if the bundled files are
missing, so a font problem degrades to "slightly less elegant" rather
than breaking every emailed PDF.
"""

import os
import re
import io

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_PDF_BRASS = colors.HexColor("#C9A66B")
_PDF_INDIGO = colors.HexColor("#1B2036")
_PDF_INDIGO_SOFT = colors.HexColor("#3A4266")

_PDF_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_PDF_FONTS_AVAILABLE = False
try:
    pdfmetrics.registerFont(TTFont("PDFSerif", os.path.join(_PDF_FONT_DIR, "LiberationSerif-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("PDFSerif-Bold", os.path.join(_PDF_FONT_DIR, "LiberationSerif-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("PDFSerif-Italic", os.path.join(_PDF_FONT_DIR, "LiberationSerif-Italic.ttf")))
    pdfmetrics.registerFont(TTFont("PDFSans", os.path.join(_PDF_FONT_DIR, "LiberationSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("PDFSans-Bold", os.path.join(_PDF_FONT_DIR, "LiberationSans-Bold.ttf")))
    _PDF_FONTS_AVAILABLE = True
except Exception:
    pass

_FONT_TITLE = "PDFSerif" if _PDF_FONTS_AVAILABLE else "Times-Roman"
_FONT_HEADING = "PDFSerif-Bold" if _PDF_FONTS_AVAILABLE else "Times-Bold"
_FONT_ITALIC = "PDFSerif-Italic" if _PDF_FONTS_AVAILABLE else "Times-Italic"
_FONT_BODY = "PDFSans" if _PDF_FONTS_AVAILABLE else "Helvetica"
_FONT_BODY_BOLD = "PDFSans-Bold" if _PDF_FONTS_AVAILABLE else "Helvetica-Bold"


class _ArcDivider(Flowable):
    """The app's signature wheel-arc, drawn as a vector shape between
    sections -- same visual language as the main app's PDF export."""
    def __init__(self, width=6.0 * inch, height=0.24 * inch):
        Flowable.__init__(self)
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setStrokeColor(_PDF_BRASS)
        c.setLineWidth(1)
        w, h = self.width, self.height
        p = c.beginPath()
        p.moveTo(0, h * 0.4)
        p.curveTo(w * 0.25, h * 1.3, w * 0.75, h * 1.3, w, h * 0.4)
        c.drawPath(p, stroke=1, fill=0)
        c.restoreState()

    def wrap(self, availWidth, availHeight):
        return (self.width, self.height)


def _pdf_footer(canvas_obj, doc):
    canvas_obj.saveState()
    canvas_obj.setFont(_FONT_BODY, 8)
    canvas_obj.setFillColor(_PDF_INDIGO_SOFT)
    canvas_obj.drawCentredString(
        letter[0] / 2, 0.5 * inch,
        f"Tenth House Readings  \u00b7  Page {doc.page}",
    )
    canvas_obj.restoreState()


def markdown_to_pdf_bytes(markdown_text: str, title: str, subtitle: str = "") -> bytes:
    """
    Converts the simple markdown structure readings use (## headers,
    **bold** inline, plain paragraphs) into a branded PDF -- identical
    styling to the main app's own PDF export, so a reading looks the
    same whether downloaded in-app or received by email.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=0.85 * inch, bottomMargin=0.85 * inch,
        leftMargin=0.85 * inch, rightMargin=0.85 * inch,
    )
    title_style = ParagraphStyle(
        "ReadingTitle", fontName=_FONT_TITLE, fontSize=23,
        textColor=_PDF_INDIGO, leading=27, spaceAfter=4,
    )
    byline_style = ParagraphStyle(
        "ReadingByline", fontName=_FONT_ITALIC, fontSize=11,
        textColor=_PDF_INDIGO_SOFT, leading=15, spaceAfter=14,
    )
    heading_style = ParagraphStyle(
        "ReadingHeading", fontName=_FONT_HEADING, fontSize=14,
        textColor=_PDF_BRASS, spaceBefore=4, spaceAfter=8, leading=17,
    )
    body_style = ParagraphStyle(
        "ReadingBody", fontName=_FONT_BODY, fontSize=10.5,
        textColor=_PDF_INDIGO, spaceAfter=10, leading=15.5,
    )

    story = [Paragraph(title, title_style)]
    if subtitle:
        story.append(Paragraph(subtitle, byline_style))
    story.append(_ArcDivider())
    story.append(Spacer(1, 14))

    def inline_format(text: str) -> str:
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"\*\*(.+?)\*\*", rf'<font name="{_FONT_BODY_BOLD}">\1</font>', text)
        return text

    _is_first_heading = True
    for raw_line in markdown_text.split("\n"):
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 6))
            continue
        if line.startswith("## ") or line.startswith("### "):
            heading_text = line[3:] if line.startswith("## ") else line[4:]
            if not _is_first_heading:
                story.append(Spacer(1, 4))
                story.append(_ArcDivider())
                story.append(Spacer(1, 10))
            _is_first_heading = False
            story.append(Paragraph(inline_format(heading_text), heading_style))
        else:
            story.append(Paragraph(inline_format(line), body_style))

    doc.build(story, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


SYNASTRY_READING_TYPES = (
    "Professional Synastry", "Relationship Synastry", "Parent/Child Synastry",
)


def build_pdf_title_and_subtitle(
    reading_type: str,
    person_name: str | None,
    datetime_str: str,
    location_str: str,
    person_name_b: str | None = None,
    datetime_str_b: str | None = None,
    location_str_b: str | None = None,
) -> tuple[str, str]:
    """
    Builds a reading's PDF title and byline for an emailed reading --
    mirrors the main app's own _pdf_title_and_subtitle, duplicated
    here since this worker doesn't import from that app directly.
    """
    if reading_type in SYNASTRY_READING_TYPES:
        name_a = person_name or "Person A"
        name_b = person_name_b or "Person B"
        title = f"{name_a} &amp; {name_b}'s {reading_type} Reading"
        subtitle = (
            f"{name_a}: {datetime_str} \u00b7 {location_str}<br/>"
            f"{name_b}: {datetime_str_b} \u00b7 {location_str_b}"
        )
        return title, subtitle
    else:
        title = f"{person_name}'s {reading_type} Reading" if person_name else f"{reading_type} Reading"
        subtitle = f"{datetime_str} \u00b7 {location_str}"
        return title, subtitle
