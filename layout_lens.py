"""layout-lens: run Surya layout detection on a PDF page and render the result.

Usage:
    python layout_lens.py sample.pdf --page 1 --out annotated.png

Runs entirely on CPU with no API keys. Surya downloads its model weights
from Hugging Face on first run (free, no account needed).

If --engine pdfplumber is passed, a simple word-clustering heuristic is
used instead of Surya (no models needed at all).
"""

import argparse
import sys
import time
from collections import Counter

from PIL import Image, ImageDraw, ImageFont

RENDER_SCALE = 2.0

PALETTE = {
    "Text": (46, 134, 222),
    "SectionHeader": (214, 48, 49),
    "Table": (0, 148, 50),
    "Figure": (155, 89, 182),
    "Picture": (155, 89, 182),
    "Caption": (230, 126, 34),
    "PageHeader": (127, 140, 141),
    "PageFooter": (127, 140, 141),
    "ListItem": (22, 160, 133),
    "Title": (192, 57, 43),
}
DEFAULT_COLOR = (52, 73, 94)


def render_page(pdf_path, page_num):
    """Render a 1-indexed PDF page to a PIL image with pypdfium2."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_path)
    if not (1 <= page_num <= len(doc)):
        sys.exit("page %d out of range (PDF has %d pages)" % (page_num, len(doc)))
    page = doc[page_num - 1]
    image = page.render(scale=RENDER_SCALE).to_pil().convert("RGB")
    doc.close()
    return image


def get_confidence(box):
    conf = getattr(box, "confidence", None)
    if conf is None:
        top_k = getattr(box, "top_k", None)
        if top_k:
            conf = max(top_k.values())
    return float(conf) if conf is not None else 1.0


def run_surya(image):
    """Run Surya layout detection. Returns list of dicts."""
    from surya.layout import LayoutPredictor

    try:
        predictor = LayoutPredictor()
    except TypeError:
        # Newer surya versions take a FoundationPredictor
        from surya.foundation import FoundationPredictor
        from surya.settings import settings

        predictor = LayoutPredictor(
            FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        )

    (prediction,) = predictor([image])
    blocks = []
    for box in prediction.bboxes:
        blocks.append(
            {
                "label": box.label,
                "confidence": get_confidence(box),
                "position": getattr(box, "position", len(blocks)),
                "bbox": [float(v) for v in box.bbox],
            }
        )
    blocks.sort(key=lambda b: b["position"])
    return blocks


def run_pdfplumber(pdf_path, page_num, image):
    """Fallback: group words into blocks with a gap heuristic. No ML."""
    import pdfplumber

    sx = image.width
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        scale = sx / float(page.width)
        words = page.extract_words()
        # cluster words into lines, then lines into blocks by vertical gap
        lines = {}
        for w in words:
            key = round(w["top"] / 4)
            lines.setdefault(key, []).append(w)
        line_boxes = []
        for key in sorted(lines):
            ws = lines[key]
            x0 = min(w["x0"] for w in ws)
            x1 = max(w["x1"] for w in ws)
            top = min(w["top"] for w in ws)
            bot = max(w["bottom"] for w in ws)
            size = max(w["bottom"] - w["top"] for w in ws)
            line_boxes.append([x0, top, x1, bot, size])
        blocks = []
        for lb in line_boxes:
            merged = False
            for b in blocks:
                # same block if vertical gap small and horizontal overlap
                if lb[1] - b["bbox"][3] < 8 and lb[0] < b["bbox"][2] and lb[2] > b["bbox"][0]:
                    b["bbox"] = [
                        min(b["bbox"][0], lb[0]),
                        min(b["bbox"][1], lb[1]),
                        max(b["bbox"][2], lb[2]),
                        max(b["bbox"][3], lb[3]),
                    ]
                    b["sizes"].append(lb[4])
                    merged = True
                    break
            if not merged:
                blocks.append({"bbox": lb[:4], "sizes": [lb[4]]})
        out = []
        for i, b in enumerate(blocks):
            label = "SectionHeader" if max(b["sizes"]) > 13 else "Text"
            out.append(
                {
                    "label": label,
                    "confidence": 1.0,
                    "position": i,
                    "bbox": [v * scale for v in b["bbox"]],
                }
            )
        return out


def annotate(image, blocks):
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for blk in blocks:
        color = PALETTE.get(blk["label"], DEFAULT_COLOR)
        x0, y0, x1, y1 = blk["bbox"]
        draw.rectangle([x0, y0, x1, y1], outline=color, width=3)
        tag = "%d. %s %.2f" % (blk["position"], blk["label"], blk["confidence"])
        tw = draw.textlength(tag, font=font)
        ty = max(0, y0 - 20)
        draw.rectangle([x0, ty, x0 + tw + 8, ty + 20], fill=color)
        draw.text((x0 + 4, ty + 2), tag, fill="white", font=font)
    return image


def report(blocks, elapsed, engine):
    print("engine: %s | %.1fs | %d blocks detected" % (engine, elapsed, len(blocks)))
    print()
    print("Blocks by type:")
    for label, n in Counter(b["label"] for b in blocks).most_common():
        print("  %-14s %d" % (label, n))
    print()
    print("Reading order:")
    for b in blocks:
        x0, y0, x1, y1 = b["bbox"]
        print(
            "  %2d. %-14s conf=%.2f  bbox=(%4.0f,%4.0f,%4.0f,%4.0f)"
            % (b["position"], b["label"], b["confidence"], x0, y0, x1, y1)
        )


def main():
    ap = argparse.ArgumentParser(description="Surya layout detection on a PDF page")
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, default=1, help="1-indexed page number")
    ap.add_argument("--out", default="annotated.png", help="annotated image path")
    ap.add_argument("--engine", choices=["surya", "pdfplumber"], default="surya")
    args = ap.parse_args()

    image = render_page(args.pdf, args.page)
    t0 = time.time()
    if args.engine == "surya":
        blocks = run_surya(image)
    else:
        blocks = run_pdfplumber(args.pdf, args.page, image)
    elapsed = time.time() - t0

    annotate(image, blocks).save(args.out)
    report(blocks, elapsed, args.engine)
    print()
    print("annotated image written to " + args.out)


if __name__ == "__main__":
    main()
