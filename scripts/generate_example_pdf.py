"""Generate the original two-page fixture; authoring-only ReportLab 4.4.9."""

from pathlib import Path
import textwrap

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / "examples/field-notes.txt").read_text(encoding="utf-8")
    output = ROOT / "examples/field-notes.pdf"
    pdf = canvas.Canvas(str(output), pagesize=A4, invariant=1, pageCompression=1)
    pdf.setTitle("Lumen Library - Fictional pilot notes")
    pdf.setAuthor("IntellectaEngine")
    pdf.setSubject("Original fictional example; no personal or third-party document data")
    width, height = A4
    pages = source.strip().split("\n---\n")
    for number, page in enumerate(pages, start=1):
        blocks = page.strip().split("\n\n")
        title, subtitle = blocks[0].splitlines()
        pdf.setFillColor(HexColor("#15283F"))
        pdf.rect(0, height - 145, width, 145, fill=1, stroke=0)
        pdf.setFillColor(HexColor("#FFFFFF"))
        pdf.setFont("Helvetica-Bold", 23)
        pdf.drawString(48, height - 69, title)
        pdf.setFont("Helvetica", 11)
        pdf.drawString(48, height - 96, subtitle)
        y = height - 190
        for block in blocks[1:]:
            heading, paragraph = block.split("\n", 1)
            pdf.setFillColor(HexColor("#155E75"))
            pdf.setFont("Helvetica-Bold", 13)
            pdf.drawString(48, y, heading)
            y -= 26
            pdf.setFillColor(HexColor("#253548"))
            pdf.setFont("Helvetica", 11)
            for line in textwrap.wrap(paragraph, width=82, break_on_hyphens=False):
                assert pdf.stringWidth(line, "Helvetica", 11) <= width - 96
                pdf.drawString(48, y, line)
                y -= 18
            y -= 26
        assert y > 80, "Source exceeds the reviewed one-page layout"
        pdf.setStrokeColor(HexColor("#CCD6E0"))
        pdf.line(48, 65, width - 48, 65)
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(HexColor("#526477"))
        pdf.drawString(48, 47, "FICTIONAL EXAMPLE  |  Original content  |  MIT license")
        pdf.drawRightString(width - 48, 47, f"{number} / {len(pages)}")
        pdf.showPage()
    pdf.save()
    print(output.name)


if __name__ == "__main__":
    main()
