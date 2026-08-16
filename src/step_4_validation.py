from pathlib import Path
import json
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]

EXTRACTED = ROOT / "data" / "extracted"
VALIDATED = ROOT / "data" / "validated"
AUDIT = ROOT / "audit" / "step_4"

VALIDATED.mkdir(parents=True, exist_ok=True)
AUDIT.mkdir(parents=True, exist_ok=True)


def validate_record(record):

    errors = []

    if not record.get("source_id"):
        errors.append("missing_source_id")

    pages = record.get("pages")

    if not isinstance(pages, list):
        errors.append("pages_not_list")
        return errors

    expected_page = 1

    for page in pages:

        if page.get("page") != expected_page:
            errors.append(
                f"page_sequence_error:{expected_page}"
            )

        if not isinstance(page.get("text"), str):
            errors.append(
                f"page_text_invalid:{expected_page}"
            )

        expected_page += 1

    return errors


def main():

    results = []

    for path in sorted(EXTRACTED.glob("*_deterministic.json")):

        record = json.loads(
            path.read_text(encoding="utf-8")
        )

        errors = validate_record(record)

        passed = len(errors) == 0

        result = {
            "source_id": record["source_id"],
            "input": str(path.relative_to(ROOT)),
            "passed": passed,
            "errors": errors,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

        results.append(result)

        out = VALIDATED / path.name

        record["validation"] = result

        out.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        print(
            f"{record['source_id']}: "
            f"{'PASS' if passed else 'BLOCKED'}"
        )

    (AUDIT / "validation_summary.json").write_text(
        json.dumps(results, indent=2),
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()