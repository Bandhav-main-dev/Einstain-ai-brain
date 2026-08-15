# =============================================================================
# EINSTEIN BRAIN V1
# STEPS 1 → 4A
# CONTROLLED, RERUNNABLE, GITHUB/GOOGLE-COLAB PIPELINE
# =============================================================================
#
# Purpose:
#   Consolidate the Einstein Brain V1 preprocessing pipeline into ONE executable
#   Python file so the project does not depend on repeatedly rerunning notebook
#   cells.
#
# Pipeline:
#
#   STEP 1   Acquisition manifest / source discovery
#   STEP 2   Corpus/extraction manifest validation
#   STEP 3   Corpus quality / provenance validation
#   STEP 3I   Formula/page-review handoff validation
#   STEP 4A  Canonical source-to-page dataset assembly
#
# IMPORTANT:
#   This script NEVER modifies authoritative PDFs.
#   Existing controlled manifests are treated as READ-ONLY.
#   Existing successful outputs are not silently overwritten.
#
# =============================================================================

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT = Path("/content/drive/MyDrive/Einstein_Brain_V1")

CORPUS = PROJECT / "corpus"
RAW = CORPUS / "raw"
EXTRACTED = CORPUS / "extracted"

MANIFESTS = PROJECT / "manifests"
REPORTS = MANIFESTS / "step_3I_4_reports"

STEP4A_DIR = CORPUS / "step_4A_dataset"
STEP4A_REPORT_DIR = REPORTS / "step_4A"

STEP4A_DIR.mkdir(parents=True, exist_ok=True)
STEP4A_REPORT_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# CONSTANTS
# =============================================================================

APPROVED_PDFS = {
    "EIN-003": {
        "filename": "EIN-003_A_New_Determination_of_Molecular_Dimensions.pdf",
        "sha256": "b08f5c7d5317dad2c9cfb2037fcba91f4a0b84c28bf2a60a134c4de5b441963f",
        "size": 588792,
        "pages": 15,
    },
    "EIN-004": {
        "filename": "EIN-004_On_the_Electrodynamics_of_Moving_Bodies.pdf",
        "sha256": "03c8f897e4d83ce48b6ae571dc32f0c48359f55078e059aa121974230d18744b",
        "size": 666806,
        "pages": 25,
    },
    "EIN-005": {
        "filename": "EIN-005_Does_the_Inertia_of_a_Body_Depend_Upon_Its_Energy-Content.pdf",
        "sha256": "f050c1f352803141fc2535984613bffd28afdeec627f0aa1d059eeaff209ce5b",
        "size": 106245,
        "pages": 3,
    },
    "EIN-007": {
        "filename": "EIN-007_On_the_Relativity_Principle_and_the_Conclusions_Drawn_from_It.pdf",
        "sha256": "e46861a7357e16e2ce0d26ac18966dc2299ba9fedbbe8f69bd61ca33001fc2a6",
        "size": 1139836,
        "pages": 14,
    },
}

EXPECTED_HANDOFF_SHA256 = (
    "253cd8096246287f43f077885eb79d073215cf8eeb57de5ecc81d2ae96d02c7d"
)

REQUIRED_DATASET_COLUMNS = [
    "source_id",
    "page_number",
    "canonical_key",
    "authoritative_pdf",
    "authoritative_pdf_sha256",
    "authoritative_pdf_size",
    "authoritative_pdf_page_count",
    "page_text_extractable_actual",
    "page_text_characters_actual",
    "handoff_pdf_text_extractable",
    "handoff_pdf_text_characters",
    "verified_ocr_present",
    "verified_ocr_path",
    "verified_ocr_sha256",
    "verified_ocr_size",
    "verified_ocr_characters",
    "formula_readability_closure",
    "human_decision",
    "reviewer_note",
    "reconciliation_status",
    "formula_correction_requested",
    "handoff_status",
    "source_provenance",
    "assembly_step",
]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def require_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(
            f"ABORT: Required {label} does not exist:\n{path}"
        )


def canonical_key(source_id: str, page_number: int) -> tuple[str, int]:
    return (str(source_id).strip(), int(page_number))


def safe_int(value) -> int:
    try:
        return int(value)
    except Exception:
        raise RuntimeError(f"ABORT: Invalid integer value: {value!r}")


def latest_file(directory: Path, pattern: str) -> Optional[Path]:
    files = list(directory.glob(pattern))

    if not files:
        return None

    files.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)

    return files[0]


def print_header(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


# =============================================================================
# STEP 1 — PROJECT / ACQUISITION VALIDATION
# =============================================================================

def step_1() -> Path:

    print_header("STEP 1 — CONTROLLED PROJECT / ACQUISITION VALIDATION")

    require_exists(PROJECT, "project directory")
    require_exists(RAW, "authoritative PDF directory")
    require_exists(MANIFESTS, "manifest directory")

    print(f"PASS: Project: {PROJECT}")
    print(f"PASS: Raw corpus: {RAW}")
    print(f"PASS: Manifests: {MANIFESTS}")

    acquisition_manifest = (
        MANIFESTS / "acquisition_manifest_batch1.csv"
    )

    if acquisition_manifest.exists():

        print(
            f"PASS: Acquisition manifest:\n"
            f"      {acquisition_manifest}"
        )

        df = pd.read_csv(acquisition_manifest)

        if "source_id" not in df.columns:
            raise RuntimeError(
                "ABORT: acquisition manifest missing source_id."
            )

        print(f"Acquisition rows: {len(df)}")

    else:

        print(
            "WARN: acquisition_manifest_batch1.csv not found."
        )

    # -------------------------------------------------------------------------
    # Validate authoritative PDFs.
    # -------------------------------------------------------------------------

    for source_id, expected in APPROVED_PDFS.items():

        pdf = RAW / expected["filename"]

        require_exists(
            pdf,
            f"authoritative PDF {source_id}"
        )

        actual_size = pdf.stat().st_size
        actual_hash = sha256_file(pdf)

        if actual_size != expected["size"]:

            raise RuntimeError(
                f"ABORT: {source_id} size mismatch.\n"
                f"Expected: {expected['size']}\n"
                f"Actual:   {actual_size}"
            )

        if actual_hash != expected["sha256"]:

            raise RuntimeError(
                f"ABORT: {source_id} SHA-256 mismatch.\n"
                f"Expected: {expected['sha256']}\n"
                f"Actual:   {actual_hash}"
            )

        print(
            f"PASS: {source_id} | "
            f"{actual_size} bytes | "
            f"{actual_hash}"
        )

    return acquisition_manifest


# =============================================================================
# STEP 2 — EXTRACTION / QUALITY MANIFEST VALIDATION
# =============================================================================

def step_2() -> None:

    print_header("STEP 2 — CONTROLLED EXTRACTION / QUALITY VALIDATION")

    extraction_manifest = (
        MANIFESTS / "extraction_manifest_batch1.csv"
    )

    extraction_quality_manifest = (
        MANIFESTS / "extraction_quality_manifest_batch1.csv"
    )

    if extraction_manifest.exists():

        df = pd.read_csv(extraction_manifest)

        print(
            f"PASS: Extraction manifest:\n"
            f"      {extraction_manifest}"
        )

        print(f"Extraction rows: {len(df)}")

    else:

        print(
            "WARN: extraction_manifest_batch1.csv not found."
        )

    if extraction_quality_manifest.exists():

        df = pd.read_csv(extraction_quality_manifest)

        print(
            f"PASS: Extraction quality manifest:\n"
            f"      {extraction_quality_manifest}"
        )

        print(
            f"Extraction-quality rows: {len(df)}"
        )

    else:

        print(
            "WARN: extraction_quality_manifest_batch1.csv "
            "not found."
        )

    verified_ocr = (
        EXTRACTED / "verified_ocr"
    )

    if verified_ocr.exists():

        txt_files = list(verified_ocr.rglob("*.txt"))

        print(
            f"Verified OCR TXT files discovered: "
            f"{len(txt_files)}"
        )

    else:

        print(
            "WARN: verified_ocr directory not found."
        )


# =============================================================================
# STEP 3 — CONTROLLED CORPUS VALIDATION
# =============================================================================

def step_3() -> None:

    print_header("STEP 3 — CONTROLLED CORPUS VALIDATION")

    quality_manifest = (
        MANIFESTS / "quality_manifest_batch1.csv"
    )

    if quality_manifest.exists():

        df = pd.read_csv(quality_manifest)

        print(
            f"PASS: Quality manifest:\n"
            f"      {quality_manifest}"
        )

        print(f"Quality rows: {len(df)}")

    else:

        print(
            "INFO: quality_manifest_batch1.csv does not exist."
        )

    ocr_manifest = (
        MANIFESTS / "ocr_page_manifest_batch1.csv"
    )

    if ocr_manifest.exists():

        df = pd.read_csv(ocr_manifest)

        print(
            f"PASS: OCR page manifest:\n"
            f"      {ocr_manifest}"
        )

        print(f"OCR manifest rows: {len(df)}")

    else:

        print(
            "WARN: OCR page manifest not found."
        )

    # -------------------------------------------------------------------------
    # Confirm all authoritative PDFs are still immutable.
    # -------------------------------------------------------------------------

    for source_id, expected in APPROVED_PDFS.items():

        pdf = RAW / expected["filename"]

        actual_hash = sha256_file(pdf)

        if actual_hash != expected["sha256"]:

            raise RuntimeError(
                f"ABORT: Authoritative PDF changed: {source_id}"
            )

    print(
        "PASS: All authoritative PDF hashes remain unchanged."
    )


# =============================================================================
# STEP 3I — CONTROLLED HANDOFF VALIDATION
# =============================================================================

def discover_handoff_manifest() -> Path:

    handoff = latest_file(
        REPORTS,
        "STEP_3I_4J_FINAL_HANDOFF_MANIFEST_*.csv"
    )

    if handoff is None:

        raise RuntimeError(
            "ABORT: No STEP 3I-4J final handoff manifest found."
        )

    return handoff


def step_3i() -> Path:

    print_header(
        "STEP 3I — CONTROLLED FORMULA REVIEW / HANDOFF VALIDATION"
    )

    handoff = discover_handoff_manifest()

    print(
        f"PASS: Handoff manifest discovered:\n"
        f"      {handoff}"
    )

    actual_hash = sha256_file(handoff)

    print(
        f"Handoff SHA-256:\n"
        f"  {actual_hash}"
    )

    # -------------------------------------------------------------------------
    # IMPORTANT:
    # We do NOT attempt to parse an old audit report for the SHA.
    #
    # This fixes the earlier bug:
    #
    #   final_audit_report undefined
    #
    # and also avoids the fragile:
    #
    #   "Could not locate recorded SHA in report"
    #
    # behavior.
    #
    # The controlled handoff SHA is verified directly against the known
    # successful Step 3I-4J handoff record.
    # -------------------------------------------------------------------------

    if actual_hash != EXPECTED_HANDOFF_SHA256:

        raise RuntimeError(
            "ABORT: Handoff manifest SHA-256 mismatch.\n"
            f"Expected controlled SHA: {EXPECTED_HANDOFF_SHA256}\n"
            f"Actual SHA:              {actual_hash}"
        )

    print(
        "PASS: Handoff SHA-256 matches controlled baseline."
    )

    df = pd.read_csv(handoff)

    print(f"Handoff rows: {len(df)}")

    required = [
        "source_id",
        "page_number",
        "authoritative_pdf",
        "authoritative_pdf_sha256",
        "authoritative_pdf_size",
        "authoritative_pdf_page_count",
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:

        raise RuntimeError(
            "ABORT: Handoff manifest missing columns:\n"
            + "\n".join(missing)
        )

    keys = set()

    for _, row in df.iterrows():

        key = canonical_key(
            row["source_id"],
            safe_int(row["page_number"])
        )

        if key in keys:

            raise RuntimeError(
                f"ABORT: Duplicate canonical key: {key}"
            )

        keys.add(key)

    print(
        f"PASS: {len(keys)} unique canonical pages."
    )

    if len(df) != 52:

        raise RuntimeError(
            "ABORT: Unexpected handoff row count.\n"
            f"Expected: 52\n"
            f"Actual:   {len(df)}"
        )

    print("PASS: 52-page controlled handoff.")

    return handoff


# =============================================================================
# STEP 4A — CANONICAL DATASET ASSEMBLY
# =============================================================================

def find_page_text(
    source_id: str,
    page_number: int,
) -> str:

    # -------------------------------------------------------------------------
    # Search common extraction locations.
    #
    # This function is deliberately conservative.
    # If page text cannot be found, the record is retained with empty text
    # rather than silently inventing text.
    # -------------------------------------------------------------------------

    candidate_dirs = [
        EXTRACTED,
        EXTRACTED / source_id,
        EXTRACTED / "text",
        EXTRACTED / "pages",
    ]

    candidates = []

    for directory in candidate_dirs:

        if not directory.exists():
            continue

        candidates.extend(
            directory.rglob(
                f"{source_id}_page_{page_number:03d}*.txt"
            )
        )

        candidates.extend(
            directory.rglob(
                f"{source_id}_page_{page_number}.txt"
            )
        )

    # Verified OCR is read-only and only used if present.

    verified_ocr = (
        EXTRACTED /
        "verified_ocr" /
        source_id
    )

    if verified_ocr.exists():

        candidates.extend(
            verified_ocr.glob(
                f"{source_id}_page_{page_number:03d}_verified_source.txt"
            )
        )

    # Remove duplicates while preserving order.

    seen = set()
    unique_candidates = []

    for path in candidates:

        if path not in seen:

            seen.add(path)
            unique_candidates.append(path)

    for path in unique_candidates:

        try:

            text = path.read_text(
                encoding="utf-8",
                errors="replace"
            )

            if text.strip():

                return text

        except Exception:

            continue

    return ""


def build_dataset(handoff_df: pd.DataFrame) -> pd.DataFrame:

    rows = []

    for _, handoff in handoff_df.iterrows():

        source_id = str(
            handoff["source_id"]
        ).strip()

        page_number = safe_int(
            handoff["page_number"]
        )

        key = canonical_key(
            source_id,
            page_number
        )

        expected_pdf = APPROVED_PDFS.get(source_id)

        if expected_pdf is None:

            raise RuntimeError(
                f"ABORT: Unapproved source in handoff: "
                f"{source_id}"
            )

        pdf_path = RAW / expected_pdf["filename"]

        actual_pdf_hash = sha256_file(pdf_path)

        if (
            actual_pdf_hash
            != expected_pdf["sha256"]
        ):

            raise RuntimeError(
                f"ABORT: PDF hash changed during "
                f"dataset assembly: {source_id}"
            )

        text = find_page_text(
            source_id,
            page_number
        )

        row = {
            "source_id": source_id,
            "page_number": page_number,
            "canonical_key":
                f"{source_id}:{page_number}",

            "authoritative_pdf":
                str(pdf_path),

            "authoritative_pdf_sha256":
                expected_pdf["sha256"],

            "authoritative_pdf_size":
                expected_pdf["size"],

            "authoritative_pdf_page_count":
                expected_pdf["pages"],

            "page_text_extractable_actual":
                bool(text.strip()),

            "page_text_characters_actual":
                len(text),

            "handoff_pdf_text_extractable":
                handoff.get(
                    "pdf_text_extractable",
                    ""
                ),

            "handoff_pdf_text_characters":
                handoff.get(
                    "pdf_text_characters",
                    ""
                ),

            "verified_ocr_present":
                False,

            "verified_ocr_path":
                "",

            "verified_ocr_sha256":
                "",

            "verified_ocr_size":
                0,

            "verified_ocr_characters":
                0,

            "formula_readability_closure":
                handoff.get(
                    "formula_readability_closure",
                    ""
                ),

            "human_decision":
                handoff.get(
                    "human_decision",
                    ""
                ),

            "reviewer_note":
                handoff.get(
                    "reviewer_note",
                    ""
                ),

            "reconciliation_status":
                handoff.get(
                    "reconciliation_status",
                    ""
                ),

            "formula_correction_requested":
                handoff.get(
                    "formula_correction_requested",
                    ""
                ),

            "handoff_status":
                handoff.get(
                    "handoff_status",
                    ""
                ),

            "source_provenance":
                (
                    f"STEP_3I_4J_HANDOFF;"
                    f"{source_id};"
                    f"page={page_number};"
                    f"pdf_sha256={expected_pdf['sha256']}"
                ),

            "assembly_step":
                "STEP_4A",
        }

        # ---------------------------------------------------------------------
        # If this page has verified OCR, record it without modifying it.
        # ---------------------------------------------------------------------

        ocr_path = (
            EXTRACTED /
            "verified_ocr" /
            source_id /
            f"{source_id}_page_{page_number:03d}_verified_source.txt"
        )

        if ocr_path.exists():

            ocr_text = ocr_path.read_text(
                encoding="utf-8",
                errors="replace"
            )

            row["verified_ocr_present"] = True
            row["verified_ocr_path"] = str(ocr_path)
            row["verified_ocr_sha256"] = sha256_file(
                ocr_path
            )
            row["verified_ocr_size"] = ocr_path.stat().st_size
            row["verified_ocr_characters"] = len(
                ocr_text
            )

        rows.append(row)

    return pd.DataFrame(rows)


def validate_dataset(
    df: pd.DataFrame,
    handoff_df: pd.DataFrame,
) -> None:

    print_header("STEP 4A — DATASET VALIDATION")

    missing = [
        c for c in REQUIRED_DATASET_COLUMNS
        if c not in df.columns
    ]

    if missing:

        raise RuntimeError(
            "ABORT: Dataset missing required columns:\n"
            + "\n".join(missing)
        )

    if len(df) != len(handoff_df):

        raise RuntimeError(
            "ABORT: Dataset/handoff row count mismatch.\n"
            f"Dataset: {len(df)}\n"
            f"Handoff: {len(handoff_df)}"
        )

    dataset_keys = {
        canonical_key(
            row["source_id"],
            row["page_number"]
        )
        for _, row in df.iterrows()
    }

    handoff_keys = {
        canonical_key(
            row["source_id"],
            row["page_number"]
        )
        for _, row in handoff_df.iterrows()
    }

    if dataset_keys != handoff_keys:

        raise RuntimeError(
            "ABORT: Dataset canonical keys do not "
            "match handoff canonical keys."
        )

    print(
        f"PASS: {len(df)} canonical dataset rows."
    )

    print(
        "PASS: Dataset canonical key set matches handoff."
    )

    # -------------------------------------------------------------------------
    # Validate every PDF provenance record.
    # -------------------------------------------------------------------------

    for source_id, expected in APPROVED_PDFS.items():

        subset = df[
            df["source_id"] == source_id
        ]

        if subset.empty:
            continue

        for _, row in subset.iterrows():

            if (
                row["authoritative_pdf_sha256"]
                != expected["sha256"]
            ):

                raise RuntimeError(
                    f"ABORT: Bad PDF provenance: "
                    f"{source_id}"
                )

            page = int(
                row["page_number"]
            )

            if not (
                1 <= page <= expected["pages"]
            ):

                raise RuntimeError(
                    f"ABORT: Invalid page number: "
                    f"{source_id} page {page}"
                )

    print(
        "PASS: Authoritative PDF provenance validated."
    )


def step_4a(handoff_path: Path) -> dict:

    print_header(
        "STEP 4A — CONTROLLED DATASET ASSEMBLY"
    )

    handoff_df = pd.read_csv(
        handoff_path
    )

    dataset = build_dataset(
        handoff_df
    )

    print(
        f"Dataset rows assembled: {len(dataset)}"
    )

    validate_dataset(
        dataset,
        handoff_df
    )

    ts = timestamp()

    dataset_path = (
        STEP4A_DIR /
        f"STEP_4A_DATASET_{ts}.csv"
    )

    index_path = (
        STEP4A_DIR /
        f"STEP_4A_CANONICAL_SOURCE_PAGE_INDEX_{ts}.csv"
    )

    verification_path = (
        STEP4A_REPORT_DIR /
        f"STEP_4A_HANDOFF_VERIFICATION_{ts}.json"
    )

    report_path = (
        STEP4A_REPORT_DIR /
        f"STEP_4A_DATASET_ASSEMBLY_{ts}.txt"
    )

    # -------------------------------------------------------------------------
    # Canonical dataset
    # -------------------------------------------------------------------------

    dataset.to_csv(
        dataset_path,
        index=False
    )

    # -------------------------------------------------------------------------
    # Canonical index
    # -------------------------------------------------------------------------

    index_columns = [
        c for c in REQUIRED_DATASET_COLUMNS
        if c in dataset.columns
    ]

    dataset[
        index_columns
    ].to_csv(
        index_path,
        index=False
    )

    dataset_sha = sha256_file(
        dataset_path
    )

    index_sha = sha256_file(
        index_path
    )

    verification = {
        "step": "STEP_4A",
        "created_utc": utc_now(),

        "handoff_manifest":
            str(handoff_path),

        "handoff_sha256":
            sha256_file(handoff_path),

        "recorded_3I_4J_sha256":
            EXPECTED_HANDOFF_SHA256,

        "sha256_match":
            sha256_file(handoff_path)
            == EXPECTED_HANDOFF_SHA256,

        "handoff_rows":
            len(handoff_df),

        "dataset_rows":
            len(dataset),

        "canonical_key":
            "(source_id, page_number)",

        "approved_authoritative_sources":
            list(APPROVED_PDFS.keys()),

        "authoritative_pdf_hashes_verified":
            True,

        "dataset_path":
            str(dataset_path),

        "dataset_sha256":
            dataset_sha,

        "index_path":
            str(index_path),

        "index_sha256":
            index_sha,

        "verified_ocr_files_discovered":
            int(
                dataset["verified_ocr_present"].sum()
            ),
    }

    verification_path.write_text(
        json.dumps(
            verification,
            indent=2
        ),
        encoding="utf-8"
    )

    # -------------------------------------------------------------------------
    # Human-readable provenance report
    # -------------------------------------------------------------------------

    report = f"""
================================================================================
STEP 4A — CONTROLLED DATASET ASSEMBLY
================================================================================

Project:
{PROJECT}

Timestamp UTC:
{utc_now()}

Handoff manifest:
{handoff_path}

Handoff SHA-256:
{verification["handoff_sha256"]}

Expected controlled handoff SHA-256:
{EXPECTED_HANDOFF_SHA256}

Handoff rows:
{len(handoff_df)}

Dataset rows:
{len(dataset)}

Canonical key:
(source_id, page_number)

Authoritative sources:
{", ".join(APPROVED_PDFS.keys())}

Dataset:
{dataset_path}

Dataset SHA-256:
{dataset_sha}

Canonical index:
{index_path}

Canonical index SHA-256:
{index_sha}

Verification JSON:
{verification_path}

Verified OCR references:
{verification["verified_ocr_files_discovered"]}

STATUS:
SUCCESS

================================================================================
"""

    report_path.write_text(
        report.strip() + "\n",
        encoding="utf-8"
    )

    print()
    print("PASS: STEP 4A dataset written:")
    print(dataset_path)

    print()
    print("PASS: STEP 4A canonical index written:")
    print(index_path)

    print()
    print("PASS: STEP 4A verification JSON written:")
    print(verification_path)

    print()
    print("PASS: STEP 4A provenance report written:")
    print(report_path)

    return {
        "dataset_path": dataset_path,
        "index_path": index_path,
        "verification_path": verification_path,
        "report_path": report_path,
    }


# =============================================================================
# MAIN
# =============================================================================

def main():

    print_header(
        "EINSTEIN BRAIN V1 — STEPS 1 → 4A"
    )

    print(
        f"Project: {PROJECT}"
    )

    print(
        f"Timestamp UTC: {utc_now()}"
    )

    # -------------------------------------------------------------------------
    # Step 1
    # -------------------------------------------------------------------------

    step_1()

    # -------------------------------------------------------------------------
    # Step 2
    # -------------------------------------------------------------------------

    step_2()

    # -------------------------------------------------------------------------
    # Step 3
    # -------------------------------------------------------------------------

    step_3()

    # -------------------------------------------------------------------------
    # Step 3I
    # -------------------------------------------------------------------------

    handoff = step_3i()

    # -------------------------------------------------------------------------
    # Step 4A
    # -------------------------------------------------------------------------

    outputs = step_4a(
        handoff
    )

    # -------------------------------------------------------------------------
    # Final
    # -------------------------------------------------------------------------

    print_header(
        "PIPELINE COMPLETE — STEPS 1 → 4A"
    )

    print(
        "STATUS: SUCCESS"
    )

    print()
    print(
        "STEP 4A DATASET:"
    )
    print(
        outputs["dataset_path"]
    )

    print()
    print(
        "STEP 4A CANONICAL INDEX:"
    )
    print(
        outputs["index_path"]
    )

    print()
    print(
        "STEP 4A VERIFICATION:"
    )
    print(
        outputs["verification_path"]
    )

    print()
    print(
        "STEP 4A REPORT:"
    )
    print(
        outputs["report_path"]
    )

    print()
    print(
        "No authoritative PDF was modified."
    )

    print(
        "No existing controlled input was modified."
    )


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\nABORT: Pipeline interrupted by user."
        )

        sys.exit(130)

    except Exception as exc:

        print()
        print("=" * 80)
        print("PIPELINE FAILED")
        print("=" * 80)
        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
