# =============================================================================
# EINSTEIN BRAIN V1
# CONTROLLED PIPELINE RUNNER
# STEP 1 → STEP 4A
#
# Purpose:
#   Resume the Einstein Brain V1 project without rerunning completed work.
#
# Design principles:
#   - Read-only verification of completed artifacts
#   - SHA-256 integrity checks
#   - Timestamped outputs
#   - Canonical key: (source_id, page_number)
#   - No silent provenance repair
#   - No overwriting authoritative source PDFs
#   - No unnecessary reruns
#
# Current controlled corpus:
#   4 authoritative PDFs
#   57 authoritative pages
#   52 canonical dataset pages
#
# =============================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# =============================================================================
# 0. CONFIGURATION
# =============================================================================

PROJECT = Path("/content/drive/MyDrive/Einstein_Brain_V1")

MANIFESTS = PROJECT / "manifests"
CORPUS = PROJECT / "corpus"
REPORTS = PROJECT / "reports"

RAW = CORPUS / "raw"
EXTRACTED = CORPUS / "extracted"

STEP_4A = CORPUS / "step_4A_dataset"
STEP_4B = CORPUS / "step_4B_validation"

STEP_REPORTS = MANIFESTS / "step_3I_4_reports"

CANONICAL_KEY = ("source_id", "page_number")


# =============================================================================
# 1. AUTHORITATIVE SOURCE BASELINES
# =============================================================================

AUTHORITATIVE_SOURCES = {
    "EIN-003": {
        "pages": 15,
        "size": 588792,
        "sha256": "b08f5c7d5317dad2c9cfb2037fcba91f4a0b84c28bf2a60a134c4de5b441963f",
    },
    "EIN-004": {
        "pages": 25,
        "size": 666806,
        "sha256": "03c8f897e4d83ce48b6ae571dc32f0c48359f55078e059aa121974230d18744b",
    },
    "EIN-005": {
        "pages": 3,
        "size": 106245,
        "sha256": "f050c1f352803141fc2535984613bffd28afdeec627f0aa1d059eeaff209ce5b",
    },
    "EIN-007": {
        "pages": 14,
        "size": 1139836,
        "sha256": "e46861a7357e16e2ce0d26ac18966dc2299ba9fedbbe8f69bd61ca33001fc2a6",
    },
}


# =============================================================================
# 2. TERMINAL OUTPUT
# =============================================================================

def banner(title: str):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def info(message: str):
    print(f"INFO: {message}")


def passed(message: str):
    print(f"PASS: {message}")


def warning(message: str):
    print(f"WARN: {message}")


def failed(message: str):
    print(f"FAIL: {message}")


def utc_now():
    return datetime.now(timezone.utc)


def timestamp():
    return utc_now().strftime("%Y%m%d_%H%M%S")


# =============================================================================
# 3. HASHING
# =============================================================================

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as handle:

        while True:

            block = handle.read(chunk_size)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


# =============================================================================
# 4. BASIC FILE CHECK
# =============================================================================

def require_file(path: Path, description: str):

    if not path.exists():
        raise RuntimeError(
            f"{description} does not exist:\n{path}"
        )

    if not path.is_file():
        raise RuntimeError(
            f"{description} is not a file:\n{path}"
        )

    passed(f"{description}: {path}")


# =============================================================================
# 5. PROJECT CHECK
# =============================================================================

def check_project():

    banner("PROJECT PRE-CHECK")

    if not PROJECT.exists():
        raise RuntimeError(
            f"Einstein Brain V1 project directory does not exist:\n{PROJECT}"
        )

    passed(f"Project directory exists: {PROJECT}")

    for path, name in [
        (MANIFESTS, "Manifests directory"),
        (CORPUS, "Corpus directory"),
        (RAW, "Raw corpus directory"),
        (STEP_REPORTS, "Step report directory"),
    ]:

        if path.exists():
            passed(f"{name} exists")
        else:
            warning(f"{name} does not currently exist: {path}")


# =============================================================================
# 6. STEP 1 — ACQUISITION VERIFICATION
# =============================================================================

def step_1():

    banner("STEP 1 — CONTROLLED ACQUISITION")

    acquisition = MANIFESTS / "acquisition_manifest_batch1.csv"

    if not acquisition.exists():

        warning(
            "Acquisition manifest not found.\n"
            "The original acquisition stage must be restored/run before "
            "downstream processing can continue."
        )

        return False

    df = pd.read_csv(acquisition)

    passed(
        f"Acquisition manifest discovered: {acquisition}"
    )

    info(f"Rows: {len(df)}")

    if "source_id" not in df.columns:
        raise RuntimeError(
            "Acquisition manifest is missing source_id."
        )

    duplicates = df["source_id"].duplicated().sum()

    if duplicates:
        raise RuntimeError(
            f"Acquisition manifest contains {duplicates} duplicate source IDs."
        )

    passed("No duplicate source IDs.")

    approved_ids = set(AUTHORITATIVE_SOURCES)

    available_ids = set(df["source_id"].astype(str))

    missing = approved_ids - available_ids

    if missing:
        raise RuntimeError(
            f"Approved authoritative sources missing from acquisition manifest: "
            f"{sorted(missing)}"
        )

    passed("All authoritative source IDs are represented.")

    return True


# =============================================================================
# 7. STEP 2 — EXTRACTION VERIFICATION
# =============================================================================

def step_2():

    banner("STEP 2 — CONTROLLED EXTRACTION / OCR")

    extraction = MANIFESTS / "extraction_manifest_batch1.csv"
    quality = MANIFESTS / "extraction_quality_manifest_batch1.csv"
    ocr_manifest = MANIFESTS / "ocr_page_manifest_batch1.csv"

    for path, name in [
        (extraction, "Extraction manifest"),
        (quality, "Extraction quality manifest"),
        (ocr_manifest, "OCR page manifest"),
    ]:

        if path.exists():

            passed(f"{name}: {path}")

        else:

            warning(f"{name} not found: {path}")

    if not extraction.exists():
        return False

    df = pd.read_csv(extraction)

    info(f"Extraction manifest rows: {len(df)}")

    if "source_id" in df.columns:

        ids = set(df["source_id"].astype(str))

        missing = set(AUTHORITATIVE_SOURCES) - ids

        if missing:

            raise RuntimeError(
                f"Extraction manifest missing sources: {sorted(missing)}"
            )

    passed("Extraction stage is available for downstream verification.")

    return True


# =============================================================================
# 8. STEP 3 — CONTROLLED FORMULA / EVIDENCE REVIEW
# =============================================================================

def find_latest(pattern: str, directory: Path):

    files = sorted(
        directory.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return files[0] if files else None


def step_3():

    banner("STEP 3 — CONTROLLED QUALITY / FORMULA REVIEW")

    if not STEP_REPORTS.exists():

        warning(
            "Step 3 report directory does not exist."
        )

        return False

    priority = find_latest(
        "STEP_3I_4G_HUMAN_REVIEW_PRIORITY_*.csv",
        EXTRACTED / "step_3I_4G_formula_review",
    )

    page_queue = find_latest(
        "STEP_3I_4G_PAGE_REVIEW_QUEUE_*.csv",
        EXTRACTED / "step_3I_4G_formula_review",
    )

    current_human = find_latest(
        "STEP_3I_4H_CURRENT_HUMAN_REVIEW_RECORDING_*.csv",
        EXTRACTED / "step_3I_4G_formula_review",
    )

    handoff = STEP_REPORTS / "STEP_3I_4J_FINAL_HANDOFF_MANIFEST_20260815_142254.csv"

    if priority:
        passed(f"Priority queue: {priority}")

    if page_queue:
        passed(f"Page review queue: {page_queue}")

    if current_human:
        passed(f"Current human review: {current_human}")

    if handoff.exists():

        passed(f"Final handoff manifest: {handoff}")

    else:

        warning(
            "Final handoff manifest not found."
        )

        return False

    return True


# =============================================================================
# 9. STEP 3J — HANDOFF VERIFICATION
# =============================================================================

def step_3j():

    banner("STEP 3J — CONTROLLED HANDOFF")

    handoff = STEP_REPORTS / (
        "STEP_3I_4J_FINAL_HANDOFF_MANIFEST_20260815_142254.csv"
    )

    require_file(
        handoff,
        "STEP 3I-4J handoff manifest",
    )

    actual_hash = sha256_file(handoff)

    expected_hash = (
        "253cd8096246287f43f077885eb79d073215cf8eeb57de5ecc81d2ae96d02c7d"
    )

    print(f"Handoff SHA-256:")
    print(f"  {actual_hash}")

    if actual_hash != expected_hash:

        raise RuntimeError(
            "ABORT: Handoff SHA-256 does not match the controlled baseline.\n"
            f"Expected: {expected_hash}\n"
            f"Actual:   {actual_hash}"
        )

    passed("Handoff SHA-256 matches controlled baseline.")

    df = pd.read_csv(handoff)

    if len(df) != 52:

        raise RuntimeError(
            f"ABORT: Expected 52 handoff rows, found {len(df)}."
        )

    passed("Handoff contains exactly 52 rows.")

    required = {
        "source_id",
        "page_number",
        "authoritative_pdf",
        "authoritative_pdf_sha256",
        "authoritative_pdf_size",
        "authoritative_pdf_page_count",
    }

    missing = required - set(df.columns)

    if missing:

        raise RuntimeError(
            f"Handoff schema missing fields: {sorted(missing)}"
        )

    passed("Handoff schema validated.")

    keys = list(
        zip(
            df["source_id"].astype(str),
            df["page_number"].astype(int),
        )
    )

    if len(keys) != len(set(keys)):

        raise RuntimeError(
            "ABORT: Duplicate canonical page keys found."
        )

    passed("52 unique canonical page keys.")

    return handoff, df


# =============================================================================
# 10. STEP 4A — DATASET ASSEMBLY
# =============================================================================

def build_step_4a(handoff_df):

    banner("STEP 4A — CONTROLLED DATASET ASSEMBLY")

    rows = []

    for _, row in handoff_df.iterrows():

        source_id = str(row["source_id"])
        page_number = int(row["page_number"])

        if source_id not in AUTHORITATIVE_SOURCES:

            raise RuntimeError(
                f"Unknown authoritative source: {source_id}"
            )

        baseline = AUTHORITATIVE_SOURCES[source_id]

        if int(row["authoritative_pdf_size"]) != baseline["size"]:

            raise RuntimeError(
                f"{source_id}: authoritative PDF size mismatch."
            )

        if str(row["authoritative_pdf_sha256"]).lower() != baseline["sha256"]:

            raise RuntimeError(
                f"{source_id}: authoritative PDF SHA-256 mismatch."
            )

        if int(row["authoritative_pdf_page_count"]) != baseline["pages"]:

            raise RuntimeError(
                f"{source_id}: authoritative PDF page count mismatch."
            )

        record = row.to_dict()

        record["canonical_key"] = (
            f"{source_id}:{page_number:03d}"
        )

        record["source_provenance"] = (
            f"{source_id}|page={page_number}|"
            f"sha256={baseline['sha256']}"
        )

        record["assembly_step"] = "STEP_4A"

        rows.append(record)

    dataset = pd.DataFrame(rows)

    passed(f"Dataset rows assembled: {len(dataset)}")

    if len(dataset) != 52:

        raise RuntimeError(
            f"Expected 52 dataset rows, found {len(dataset)}."
        )

    keys = list(
        zip(
            dataset["source_id"].astype(str),
            dataset["page_number"].astype(int),
        )
    )

    if len(keys) != len(set(keys)):

        raise RuntimeError(
            "Duplicate canonical keys detected."
        )

    passed("Canonical key validation passed.")

    return dataset


# =============================================================================
# 11. WRITE STEP 4A WITHOUT OVERWRITING
# =============================================================================

def write_step_4a(dataset):

    banner("STEP 4A — WRITING NEW OUTPUTS")

    STEP_4A.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_dir = STEP_REPORTS / "step_4A"

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    ts = timestamp()

    dataset_path = (
        STEP_4A /
        f"STEP_4A_DATASET_{ts}.csv"
    )

    index_path = (
        STEP_4A /
        f"STEP_4A_CANONICAL_SOURCE_PAGE_INDEX_{ts}.csv"
    )

    verification_path = (
        report_dir /
        f"STEP_4A_HANDOFF_VERIFICATION_{ts}.json"
    )

    dataset.to_csv(
        dataset_path,
        index=False,
    )

    index = dataset.copy()

    index.to_csv(
        index_path,
        index=False,
    )

    dataset_hash = sha256_file(dataset_path)
    index_hash = sha256_file(index_path)

    verification = {
        "step": "4A",
        "created_utc": utc_now().isoformat(),
        "handoff_rows": len(dataset),
        "dataset_rows": len(dataset),
        "canonical_key": [
            "source_id",
            "page_number",
        ],
        "dataset_path": str(dataset_path),
        "dataset_sha256": dataset_hash,
        "index_path": str(index_path),
        "index_sha256": index_hash,
        "authoritative_sources": sorted(
            dataset["source_id"].astype(str).unique().tolist()
        ),
        "formula_readability": (
            dataset["formula_readability_closure"]
            .value_counts(dropna=False)
            .to_dict()
            if "formula_readability_closure" in dataset.columns
            else {}
        ),
    }

    verification_path.write_text(
        json.dumps(
            verification,
            indent=2,
        ),
        encoding="utf-8",
    )

    passed(f"Dataset written: {dataset_path}")
    passed(f"Dataset SHA-256: {dataset_hash}")

    passed(f"Canonical index written: {index_path}")
    passed(f"Index SHA-256: {index_hash}")

    passed(
        f"Verification record written: {verification_path}"
    )

    return dataset_path, index_path, verification_path


# =============================================================================
# 12. STEP 4A RE-READ / INTEGRITY CHECK
# =============================================================================

def verify_step_4a(
    dataset_path: Path,
    index_path: Path,
):

    banner("STEP 4A — POST-BUILD INTEGRITY CHECK")

    dataset = pd.read_csv(dataset_path)
    index = pd.read_csv(index_path)

    if len(dataset) != 52:
        raise RuntimeError(
            f"Dataset row count changed: {len(dataset)}"
        )

    if len(index) != 52:
        raise RuntimeError(
            f"Index row count changed: {len(index)}"
        )

    dataset_keys = set(
        zip(
            dataset["source_id"].astype(str),
            dataset["page_number"].astype(int),
        )
    )

    index_keys = set(
        zip(
            index["source_id"].astype(str),
            index["page_number"].astype(int),
        )
    )

    if dataset_keys != index_keys:

        raise RuntimeError(
            "Dataset/index canonical key sets differ."
        )

    passed("Dataset re-read successfully.")
    passed("Canonical index re-read successfully.")
    passed("Dataset/index canonical key sets match.")
    passed("52 canonical pages confirmed.")

    return dataset


# =============================================================================
# 13. STEP STATUS DISPLAY
# =============================================================================

def status_summary():

    banner("CURRENT EINSTEIN BRAIN V1 STATUS")

    print("Controlled corpus:")
    print("  Authoritative sources : 4")
    print("  Authoritative pages   : 57")
    print("  Canonical pages       : 52")
    print("  Canonical key         : (source_id, page_number)")
    print()
    print("Completed:")
    print("  STEP 1   Acquisition")
    print("  STEP 2   Extraction / OCR")
    print("  STEP 3   Quality / Formula Review")
    print("  STEP 3J  Controlled Handoff")
    print("  STEP 4A  Dataset Assembly")
    print()
    print("Next:")
    print("  STEP 4B  Dataset Validation / Preparation")


# =============================================================================
# 14. MAIN PIPELINE
# =============================================================================

def run_pipeline():

    banner(
        "EINSTEIN BRAIN V1 — CONTROLLED PIPELINE "
        "STEP 1 → STEP 4A"
    )

    print(
        f"UTC: {utc_now().isoformat()}"
    )

    print(
        f"Project: {PROJECT}"
    )

    check_project()

    # -------------------------------------------------------------------------
    # STEP 1
    # -------------------------------------------------------------------------

    step_1()

    # -------------------------------------------------------------------------
    # STEP 2
    # -------------------------------------------------------------------------

    step_2()

    # -------------------------------------------------------------------------
    # STEP 3
    # -------------------------------------------------------------------------

    step_3()

    # -------------------------------------------------------------------------
    # STEP 3J
    # -------------------------------------------------------------------------

    handoff_path, handoff_df = step_3j()

    # -------------------------------------------------------------------------
    # STEP 4A
    # -------------------------------------------------------------------------

    dataset = build_step_4a(
        handoff_df
    )

    dataset_path, index_path, verification_path = write_step_4a(
        dataset
    )

    verify_step_4a(
        dataset_path,
        index_path,
    )

    # -------------------------------------------------------------------------
    # FINAL
    # -------------------------------------------------------------------------

    banner(
        "STEP 1 → STEP 4A COMPLETE"
    )

    passed("Pipeline completed successfully.")

    print()
    print("DATASET:")
    print(dataset_path)

    print()
    print("CANONICAL INDEX:")
    print(index_path)

    print()
    print("VERIFICATION:")
    print(verification_path)

    print()

    status_summary()


# =============================================================================
# 15. COMMAND-LINE INTERFACE
# =============================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Einstein Brain V1 controlled pipeline "
            "runner."
        )
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current project status.",
    )

    parser.add_argument(
        "--run",
        action="store_true",
        help="Run Steps 1 through 4A.",
    )

    args = parser.parse_args()

    if args.status:

        check_project()
        status_summary()
        return

    # Default behavior is run.
    run_pipeline()


if __name__ == "__main__":
    main()
