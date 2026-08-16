from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

MANIFEST_DIR = ROOT / "manifests"
AUDIT_DIR = ROOT / "audit" / "step_2"

MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


TARGETS = [
    "EIN-003",
    "EIN-004",
    "EIN-005",
    "EIN-007",
]


def sha256_file(path):

    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def find_pdf(source_id):

    matches = sorted(
        RAW_DIR.rglob(f"{source_id}*.pdf"),
        key=lambda p: str(p).lower()
    )

    if not matches:
        return None

    return matches[0]


def main():

    manifest = []

    for source_id in TARGETS:

        pdf = find_pdf(source_id)

        if pdf is None:

            manifest.append({
                "source_id": source_id,
                "status": "MISSING",
                "path": None,
            })

            continue

        manifest.append({
            "source_id": source_id,
            "status": "READY",
            "filename": pdf.name,
            "path": str(pdf.relative_to(ROOT)),
            "size_bytes": pdf.stat().st_size,
            "sha256": sha256_file(pdf),
        })

    output = {
        "manifest_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": manifest,
    }

    manifest_path = MANIFEST_DIR / "master_sources.json"

    manifest_path.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8"
    )

    print("=" * 80)
    print("EINSTEIN BRAIN V1 — STEP 2 SOURCE MANIFEST")
    print("=" * 80)

    for item in manifest:
        print(
            f"{item['source_id']:8} "
            f"{item['status']:8} "
            f"{item.get('path', '')}"
        )

    print()
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()