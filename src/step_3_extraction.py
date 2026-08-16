from pathlib import Path
import fitz
import json
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "extracted"
AUDIT_DIR = ROOT / "audit" / "step_3"

OUT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def extract_pdf(pdf_path):

    doc = fitz.open(pdf_path)

    pages = []

    for page_number, page in enumerate(doc, 1):

        text = page.get_text("text")

        pages.append({
            "page": page_number,
            "text": text,
            "text_length": len(text),
            "blocks": len(page.get_text("blocks")),
        })

    return pages


def main():

    pdfs = sorted(
        RAW_DIR.glob("*.pdf"),
        key=lambda p: p.name.lower()
    )

    summary = []

    for pdf in pdfs:

        source_id = pdf.stem.split("_")[0]

        print("=" * 80)
        print(f"EXTRACTING {pdf.name}")
        print("=" * 80)

        pages = extract_pdf(pdf)

        output = {
            "source_id": source_id,
            "filename": pdf.name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "method": "PyMuPDF",
            "authoritative": True,
            "pages": pages,
        }

        out = OUT_DIR / f"{source_id}_deterministic.json"

        out.write_text(
            json.dumps(output, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        summary.append({
            "source_id": source_id,
            "pages": len(pages),
            "output": str(out.relative_to(ROOT)),
        })

        print(f"Pages extracted: {len(pages)}")
        print(f"Output: {out}")

    (AUDIT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()