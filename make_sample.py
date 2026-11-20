"""Generate the self-contained sample PDF used by the demo.

Creates sample.pdf: a single page with a heading, two text columns,
a small table, and a figure with a caption. No external assets needed.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT = "sample.pdf"

LOREM = (
    "Document layout analysis is the task of locating and classifying "
    "regions of a page: headings, paragraphs, tables, figures, captions, "
    "and more. It is a core step in document AI pipelines because "
    "downstream OCR and parsing quality depends on knowing what each "
    "region is. Modern detectors treat this as an object detection "
    "problem over a rendered page image, the same family of problems as "
    "detecting parts on a conveyor belt or tools on a workbench."
).split()

LOREM2 = (
    "Two column layouts are a classic stress test because a naive top to "
    "bottom reading order interleaves the columns and scrambles the text. "
    "A good layout model assigns each block a position in the true "
    "reading order. Tables are another hard case: their dense ruled "
    "structure is easy to confuse with figures, and their cells should "
    "not be read as running prose. This sample page includes both."
).split()


def wrap_words(words, width_chars):
    lines, cur = [], []
    for w in words:
        if sum(len(x) + 1 for x in cur) + len(w) > width_chars:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def draw_column(c, words, x, y_top, width_chars, leading=13):
    c.setFont("Helvetica", 10)
    y = y_top
    for line in wrap_words(words, width_chars):
        c.drawString(x, y, line)
        y -= leading
    return y


def main():
    c = canvas.Canvas(OUT, pagesize=letter)
    w, h = letter  # 612 x 792

    # Heading
    c.setFont("Helvetica-Bold", 20)
    c.drawString(1 * inch, h - 1 * inch, "Layout Lens: A Two-Column Test Page")
    c.setFont("Helvetica", 11)
    c.drawString(1 * inch, h - 1.25 * inch, "Section 1. Why layout detection matters")

    # Two columns
    col_w_chars = 42
    left_x = 1 * inch
    right_x = 4.35 * inch
    y_top = h - 1.65 * inch
    draw_column(c, LOREM, left_x, y_top, col_w_chars)
    draw_column(c, LOREM2, right_x, y_top, col_w_chars)

    # Table
    table_y = h - 4.1 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_x, table_y + 14, "Table 1. Common block types")
    rows = [
        ["Block type", "Typical cue", "Hard case"],
        ["Heading", "Large bold font", "Short bold inline text"],
        ["Table", "Ruled grid lines", "Borderless tables"],
        ["Figure", "Non-text pixels", "Charts with much text"],
        ["Caption", "Small text near figure", "Footnotes"],
    ]
    row_h = 16
    col_ws = [1.3 * inch, 1.9 * inch, 2.1 * inch]
    tx, ty = left_x, table_y
    for r, row in enumerate(rows):
        cx = tx
        c.setFont("Helvetica-Bold" if r == 0 else "Helvetica", 9)
        for j, cell in enumerate(row):
            c.rect(cx, ty - row_h, col_ws[j], row_h)
            c.drawString(cx + 4, ty - row_h + 5, cell)
            cx += col_ws[j]
        ty -= row_h

    # Figure: simple bar chart drawn with rectangles
    fig_x = left_x
    fig_y = 1.6 * inch
    c.setLineWidth(1)
    c.rect(fig_x, fig_y, 3.4 * inch, 1.5 * inch)
    bars = [0.4, 0.9, 1.2, 0.7, 1.05]
    bw = 0.45 * inch
    for i, bh in enumerate(bars):
        c.setFillGray(0.3 + 0.1 * i)
        c.rect(fig_x + 0.25 * inch + i * (bw + 0.12 * inch), fig_y + 0.1 * inch,
               bw, bh * inch, fill=1)
    c.setFillGray(0)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(fig_x, fig_y - 14,
                 "Figure 1. Block counts per page in a synthetic corpus.")

    c.showPage()
    c.save()
    print("wrote " + OUT)


if __name__ == "__main__":
    main()
