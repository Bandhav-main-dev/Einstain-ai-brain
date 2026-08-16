from pathlib import Path
import json
import re
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]

VALIDATED = ROOT / "data" / "validated"
OUT = ROOT / "data" / "validated"
AUDIT = ROOT / "audit" / "step_5"

AUDIT.mkdir(parents=True, exist_ok=True)


FORMULA_RE = re.compile(
    r"(=|≈|∝|\\frac|\\sqrt|"
    r"\b[A-Za-z]\s*=\s*[A-Za-z0-9]"
)


def detect_formula_candidates(text):

    candidates = []

    for line_no, line in enumerate(
        text.splitlines(), 1
    ):

        if FORMULA_RE.search(line):

            candidates.append({
                "line": line_no,
                "text": line.strip(),
                "method": "deterministic_regex",
            })

    return candidates


def process_file(path):

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    formula_candidates = []

    for page in data.get("pages", []):

        found = detect_formula_candidates(
            page.get("text", "")
        )

        for candidate in found:

            candidate["page"] = page["page"]

            formula_candidates.append(candidate)

    result = {
        "source_id": data["source_id"],
        "deterministic_formula_candidates":
            formula_candidates,
        "deterministic_formula_count":
            len(formula_candidates),
        "gemini_required": len(formula_candidates) > 0,
        "authoritative": True,
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
    }

    return result


def main():

    all_results = []

    for path in sorted(
        VALIDATED.glob("*_deterministic.json")
    ):

        result = process_file(path)

        all_results.append(result)

        print(
            f"{result['source_id']}: "
            f"{result['deterministic_formula_count']} "
            f"formula candidates"
        )

    output = {
        "step": "5",
        "results": all_results,
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
    }

    out = AUDIT / "step_5_deterministic_summary.json"

    out.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print()
    print(f"Step 5 audit: {out}")


if __name__ == "__main__":
    main()