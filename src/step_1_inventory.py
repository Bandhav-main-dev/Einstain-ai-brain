from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
AUDIT_DIR = ROOT / "audit" / "step_1"

AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def main():

    pdfs = sorted(
        RAW_DIR.rglob("*.pdf"),
        key=lambda p: str(p.relative_to(ROOT)).lower()
    )

    print("=" * 80)
    print("EINSTEIN BRAIN V1 — STEP 1 PDF INVENTORY")
    print("=" * 80)

    print(f"PROJECT ROOT : {ROOT}")
    print(f"RAW DIR      : {RAW_DIR}")
    print(f"PDF COUNT    : {len(pdfs)}")
    print()

    records = []

    for i, pdf in enumerate(pdfs, 1):

        record = {
            "index": i,
            "relative_path": str(pdf.relative_to(ROOT)),
            "filename": pdf.name,
            "size_bytes": pdf.stat().st_size,
            "sha256": sha256_file(pdf),
            "exists": pdf.exists(),
        }

        records.append(record)

        print(
            f"[{i:03d}] "
            f"{record['relative_path']} "
            f"| {record['size_bytes']} bytes "
            f"| {record['sha256']}"
        )

    output = {
        "step": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pdf_count": len(records),
        "records": records,
    }

    out = AUDIT_DIR / "step_1_inventory.json"

    out.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8"
    )

    print()
    print(f"Audit written: {out}")


if __name__ == "__main__":
    main()