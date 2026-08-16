#!/usr/bin/env python3
"""
================================================================================
EINSTEIN BRAIN V1
STEP 4 — EXTRACTION / INTEGRITY VALIDATION PIPELINE
================================================================================

Purpose
-------
GitHub-ready implementation of the validated Step 4 integrity workflow.

Includes:
    STEP 4A  - Project/source structure discovery
    STEP 4B  - Source and artifact inventory
    STEP 4C  - Hash/integrity verification
    STEP 4D  - Deterministic validation
    STEP 4E  - Synthetic regression tests + real integrity snapshot

Design principles
-----------------
1. READ-ONLY
   This script does not modify project data, source files, logs, audits,
   manifests, or extracted artifacts.

2. DETERMINISTIC
   The same project state should produce the same validation result.

3. SHA-256 INTEGRITY
   File integrity is checked using SHA-256 hashes.

4. FAIL-CLOSED
   Missing, duplicated, corrupted, or ambiguous records are reported as
   failures rather than silently accepted.

5. PROVENANCE SAFE
   Validation results identify the exact files and hashes being checked.

6. GITHUB READY
   No Google Colab-specific APIs are required.

Usage
-----
From the Einstein_Brain_V1 repository root:

    python step4/step4_integrity_validation.py

Optional:

    python step4/step4_integrity_validation.py --project-root /path/to/project

    python step4/step4_integrity_validation.py --json

    python step4/step4_integrity_validation.py --quiet

Exit codes
----------
0 = validation passed
1 = validation failed
2 = configuration/runtime error

================================================================================
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# =============================================================================
# VERSION
# =============================================================================

STEP_VERSION = "STEP 4E v6.3"
SCRIPT_VERSION = "4.0.0"


# =============================================================================
# DEFAULT PATHS
# =============================================================================

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE_DIRS = (
    "sources",
    "data",
    "documents",
    "pdfs",
    "html",
    "artifacts",
)

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ipynb_checkpoints",
    "node_modules",
}

DEFAULT_EXTENSIONS = {
    ".pdf",
    ".html",
    ".htm",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".jsonl",
    ".xml",
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass(frozen=True)
class FileRecord:
    """Immutable description of a discovered file."""

    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ValidationResult:
    """Single validation result."""

    name: str
    passed: bool
    details: str


@dataclass
class ValidationSummary:
    """Complete validation summary."""

    step: str
    script_version: str
    started_utc: str
    finished_utc: str
    project_root: str

    files_discovered: int
    directories_discovered: int

    validation_results: List[ValidationResult]

    overall_pass: bool

    def to_dict(self) -> dict:
        data = asdict(self)
        data["validation_results"] = [
            asdict(result) for result in self.validation_results
        ]
        return data


# =============================================================================
# OUTPUT
# =============================================================================

class Reporter:
    """Simple terminal reporter."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet

    def header(self, text: str) -> None:
        if self.quiet:
            return

        print()
        print("=" * 80)
        print(text)
        print("=" * 80)

    def info(self, text: str) -> None:
        if not self.quiet:
            print(text)

    def result(self, result: ValidationResult) -> None:
        if self.quiet:
            return

        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}: {result.details}")

    def footer(self, passed: bool) -> None:
        if self.quiet:
            return

        print()
        print("=" * 80)

        if passed:
            print("STEP 4 RESULT: PASS")
        else:
            print("STEP 4 RESULT: FAIL")

        print("=" * 80)


# =============================================================================
# HASHING
# =============================================================================

def sha256_file(
    path: Path,
    chunk_size: int = 1024 * 1024,
) -> str:
    """
    Calculate SHA-256 without loading the entire file into memory.
    """

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


# =============================================================================
# FILE DISCOVERY
# =============================================================================

def is_excluded(path: Path, project_root: Path) -> bool:
    """
    Determine whether a path belongs to an excluded directory.
    """

    try:
        relative = path.relative_to(project_root)
    except ValueError:
        return True

    return any(
        component in DEFAULT_EXCLUDED_DIRS
        for component in relative.parts
    )


def iter_project_files(
    project_root: Path,
) -> Iterable[Path]:
    """
    Yield project files in deterministic order.
    """

    for path in sorted(project_root.rglob("*")):

        if not path.is_file():
            continue

        if is_excluded(path, project_root):
            continue

        yield path


def discover_files(
    project_root: Path,
) -> List[FileRecord]:
    """
    Discover relevant project files and calculate SHA-256 hashes.
    """

    records: List[FileRecord] = []

    for path in iter_project_files(project_root):

        if path.suffix.lower() not in DEFAULT_EXTENSIONS:
            continue

        relative = path.relative_to(project_root).as_posix()

        records.append(
            FileRecord(
                relative_path=relative,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )

    return records


# =============================================================================
# DIRECTORY SNAPSHOT
# =============================================================================

def discover_directories(
    project_root: Path,
) -> List[str]:
    """
    Discover project directories deterministically.
    """

    directories = []

    for path in sorted(project_root.rglob("*")):

        if not path.is_dir():
            continue

        if is_excluded(path, project_root):
            continue

        relative = path.relative_to(project_root).as_posix()

        if relative:
            directories.append(relative)

    return directories


# =============================================================================
# DUPLICATE DETECTION
# =============================================================================

def find_duplicate_hashes(
    records: Sequence[FileRecord],
) -> Dict[str, List[str]]:
    """
    Find multiple files having the same SHA-256 hash.
    """

    by_hash: Dict[str, List[str]] = {}

    for record in records:
        by_hash.setdefault(record.sha256, []).append(
            record.relative_path
        )

    return {
        digest: paths
        for digest, paths in by_hash.items()
        if len(paths) > 1
    }


# =============================================================================
# SYNTHETIC REGRESSION TESTS
# =============================================================================

def synthetic_hash_test() -> ValidationResult:
    """
    Verify SHA-256 implementation against a known value.
    """

    payload = b"Einstein Brain V1 synthetic regression test"

    expected = hashlib.sha256(payload).hexdigest()

    with tempfile.TemporaryDirectory() as temp_dir:

        path = Path(temp_dir) / "synthetic.txt"
        path.write_bytes(payload)

        actual = sha256_file(path)

    passed = actual == expected

    return ValidationResult(
        name="Synthetic SHA-256 verification",
        passed=passed,
        details=(
            "Known payload hash matches."
            if passed
            else f"Hash mismatch: expected {expected}, got {actual}"
        ),
    )


def synthetic_duplicate_detection_test() -> ValidationResult:
    """
    Verify duplicate hash detection.
    """

    records = [
        FileRecord(
            relative_path="a.txt",
            size_bytes=10,
            sha256="abc123",
        ),
        FileRecord(
            relative_path="b.txt",
            size_bytes=10,
            sha256="abc123",
        ),
        FileRecord(
            relative_path="c.txt",
            size_bytes=11,
            sha256="def456",
        ),
    ]

    duplicates = find_duplicate_hashes(records)

    passed = (
        "abc123" in duplicates
        and duplicates["abc123"] == ["a.txt", "b.txt"]
    )

    return ValidationResult(
        name="Synthetic duplicate detection",
        passed=passed,
        details=(
            "Duplicate hash detection behaves as expected."
            if passed
            else "Duplicate hash regression test failed."
        ),
    )


def synthetic_ordering_test() -> ValidationResult:
    """
    Verify deterministic record ordering.
    """

    records = [
        FileRecord("z.txt", 1, "z"),
        FileRecord("a.txt", 1, "a"),
        FileRecord("m.txt", 1, "m"),
    ]

    ordered = sorted(
        records,
        key=lambda record: record.relative_path,
    )

    paths = [
        record.relative_path
        for record in ordered
    ]

    expected = ["a.txt", "m.txt", "z.txt"]

    passed = paths == expected

    return ValidationResult(
        name="Synthetic deterministic ordering",
        passed=passed,
        details=(
            "Deterministic ordering verified."
            if passed
            else f"Unexpected ordering: {paths}"
        ),
    )


def synthetic_read_only_test(
    project_root: Path,
) -> ValidationResult:
    """
    Verify that the validation code itself does not create a mutation
    in the project directory.

    This test records the set of project paths before and after discovery.
    """

    before = sorted(
        path.relative_to(project_root).as_posix()
        for path in project_root.rglob("*")
        if not is_excluded(path, project_root)
    )

    # Perform read-only discovery.
    _ = discover_files(project_root)
    _ = discover_directories(project_root)

    after = sorted(
        path.relative_to(project_root).as_posix()
        for path in project_root.rglob("*")
        if not is_excluded(path, project_root)
    )

    passed = before == after

    return ValidationResult(
        name="Synthetic read-only filesystem test",
        passed=passed,
        details=(
            "Project path set unchanged."
            if passed
            else "Project path set changed during validation."
        ),
    )


# =============================================================================
# REAL PROJECT VALIDATION
# =============================================================================

def validate_project_exists(
    project_root: Path,
) -> ValidationResult:

    passed = project_root.exists() and project_root.is_dir()

    return ValidationResult(
        name="Project root",
        passed=passed,
        details=(
            str(project_root)
            if passed
            else f"Project root does not exist: {project_root}"
        ),
    )


def validate_hash_format(
    records: Sequence[FileRecord],
) -> ValidationResult:

    invalid = [
        record.relative_path
        for record in records
        if len(record.sha256) != 64
        or any(
            char not in "0123456789abcdef"
            for char in record.sha256.lower()
        )
    ]

    passed = not invalid

    return ValidationResult(
        name="SHA-256 format validation",
        passed=passed,
        details=(
            f"{len(records)} hashes have valid SHA-256 format."
            if passed
            else f"Invalid hashes: {invalid[:10]}"
        ),
    )


def validate_unique_paths(
    records: Sequence[FileRecord],
) -> ValidationResult:

    paths = [
        record.relative_path
        for record in records
    ]

    duplicates = sorted(
        {
            path
            for path in paths
            if paths.count(path) > 1
        }
    )

    passed = not duplicates

    return ValidationResult(
        name="Unique relative paths",
        passed=passed,
        details=(
            f"{len(paths)} records have unique paths."
            if passed
            else f"Duplicate paths detected: {duplicates[:10]}"
        ),
    )


def validate_no_hash_collisions(
    records: Sequence[FileRecord],
) -> ValidationResult:

    duplicates = find_duplicate_hashes(records)

    """
    Identical hashes can legitimately occur for identical content.

    Therefore this validation reports them rather than automatically
    declaring them corruption.

    The test fails only if the same hash is associated with files of
    different sizes, which indicates an internal inconsistency.
    """

    suspicious = []

    for digest, paths in duplicates.items():

        sizes = {
            record.size_bytes
            for record in records
            if record.sha256 == digest
        }

        if len(sizes) > 1:
            suspicious.append(
                {
                    "sha256": digest,
                    "paths": paths,
                    "sizes": sorted(sizes),
                }
            )

    passed = not suspicious

    if passed:
        if duplicates:
            details = (
                f"No suspicious hash collisions. "
                f"{len(duplicates)} duplicate-content hash group(s) "
                f"were detected and preserved as informational."
            )
        else:
            details = "No duplicate SHA-256 groups detected."
    else:
        details = f"Suspicious hash groups: {suspicious[:5]}"

    return ValidationResult(
        name="Hash collision/inconsistency check",
        passed=passed,
        details=details,
    )


def validate_files_rehash(
    project_root: Path,
    records: Sequence[FileRecord],
) -> ValidationResult:

    failures = []

    for record in records:

        path = project_root / record.relative_path

        if not path.exists():
            failures.append(
                f"{record.relative_path}: missing"
            )
            continue

        actual = sha256_file(path)

        if actual != record.sha256:
            failures.append(
                f"{record.relative_path}: "
                f"expected={record.sha256}, actual={actual}"
            )

    passed = not failures

    return ValidationResult(
        name="Real SHA-256 revalidation",
        passed=passed,
        details=(
            f"{len(records)} file hash(es) successfully revalidated."
            if passed
            else f"{len(failures)} integrity failure(s): "
                 f"{failures[:5]}"
        ),
    )


def validate_nonempty_files(
    project_root: Path,
    records: Sequence[FileRecord],
) -> ValidationResult:

    empty_files = []

    for record in records:

        path = project_root / record.relative_path

        if path.exists() and path.stat().st_size == 0:
            empty_files.append(record.relative_path)

    passed = not empty_files

    return ValidationResult(
        name="Non-empty artifact validation",
        passed=passed,
        details=(
            "No zero-byte relevant artifacts detected."
            if passed
            else f"Zero-byte files: {empty_files[:10]}"
        ),
    )


# =============================================================================
# CONTENT TYPE VALIDATION
# =============================================================================

def validate_pdf_files(
    project_root: Path,
    records: Sequence[FileRecord],
) -> ValidationResult:

    pdfs = [
        record
        for record in records
        if record.relative_path.lower().endswith(".pdf")
    ]

    invalid = []

    for record in pdfs:

        path = project_root / record.relative_path

        try:
            with path.open("rb") as handle:
                header = handle.read(5)

            if header != b"%PDF-":
                invalid.append(record.relative_path)

        except OSError:
            invalid.append(record.relative_path)

    passed = not invalid

    return ValidationResult(
        name="PDF signature validation",
        passed=passed,
        details=(
            f"{len(pdfs)} PDF file(s) have valid PDF signatures."
            if passed
            else f"Invalid PDF signature(s): {invalid[:10]}"
        ),
    )


def validate_html_files(
    project_root: Path,
    records: Sequence[FileRecord],
) -> ValidationResult:

    htmls = [
        record
        for record in records
        if record.relative_path.lower().endswith(
            (".html", ".htm")
        )
    ]

    invalid = []

    for record in htmls:

        path = project_root / record.relative_path

        try:
            raw = path.read_bytes()

            if not raw.strip():
                invalid.append(record.relative_path)
                continue

            text = raw.decode(
                "utf-8",
                errors="ignore",
            ).lower()

            html_indicators = (
                "<html",
                "<!doctype html",
                "<head",
                "<body",
            )

            if not any(
                indicator in text
                for indicator in html_indicators
            ):
                invalid.append(record.relative_path)

        except OSError:
            invalid.append(record.relative_path)

    passed = not invalid

    return ValidationResult(
        name="HTML content validation",
        passed=passed,
        details=(
            f"{len(htmls)} HTML file(s) passed structural checks."
            if passed
            else f"Invalid HTML artifact(s): {invalid[:10]}"
        ),
    )


# =============================================================================
# SNAPSHOT
# =============================================================================

def create_integrity_snapshot(
    project_root: Path,
    records: Sequence[FileRecord],
    directories: Sequence[str],
) -> dict:
    """
    Create an in-memory integrity snapshot.

    IMPORTANT:
        This function does not write the snapshot to disk.
    """

    return {
        "step": STEP_VERSION,
        "script_version": SCRIPT_VERSION,
        "mode": "IN-MEMORY / READ-ONLY",
        "filesystem_mutation": False,
        "log_mutation": False,
        "audit_mutation": False,
        "project_root": str(project_root),
        "project_files_captured": len(records),
        "project_directories_captured": len(directories),
        "files": [
            asdict(record)
            for record in records
        ],
    }


def compare_snapshots(
    before: dict,
    after: dict,
) -> ValidationResult:

    passed = before == after

    return ValidationResult(
        name="Integrity snapshot stability",
        passed=passed,
        details=(
            "Before/after in-memory snapshots are identical."
            if passed
            else "Before/after integrity snapshots differ."
        ),
    )


# =============================================================================
# PIPELINE
# =============================================================================

def run_step4(
    project_root: Path,
    reporter: Reporter,
) -> ValidationSummary:

    started = datetime.now(timezone.utc)

    reporter.header(
        "EINSTEIN BRAIN V1 — STEP 4"
    )

    reporter.info(
        f"Version             : {STEP_VERSION}"
    )

    reporter.info(
        f"Script version      : {SCRIPT_VERSION}"
    )

    reporter.info(
        "Mode                : IN-MEMORY / READ-ONLY"
    )

    reporter.info(
        "Filesystem mutation : DISABLED"
    )

    reporter.info(
        "Log mutation        : DISABLED"
    )

    reporter.info(
        "Audit mutation      : DISABLED"
    )

    reporter.info(
        f"Project root        : {project_root}"
    )

    # -------------------------------------------------------------------------
    # PROJECT EXISTENCE
    # -------------------------------------------------------------------------

    results: List[ValidationResult] = []

    project_result = validate_project_exists(project_root)
    results.append(project_result)
    reporter.result(project_result)

    if not project_result.passed:

        finished = datetime.now(timezone.utc)

        return ValidationSummary(
            step=STEP_VERSION,
            script_version=SCRIPT_VERSION,
            started_utc=started.isoformat(),
            finished_utc=finished.isoformat(),
            project_root=str(project_root),
            files_discovered=0,
            directories_discovered=0,
            validation_results=results,
            overall_pass=False,
        )

    # -------------------------------------------------------------------------
    # BEFORE SNAPSHOT
    # -------------------------------------------------------------------------

    before_records = discover_files(project_root)
    before_directories = discover_directories(project_root)

    reporter.info("")
    reporter.info("BEFORE INTEGRITY SNAPSHOT")
    reporter.info("-" * 80)
    reporter.info(
        f"Project files captured      : {len(before_records)}"
    )
    reporter.info(
        f"Project directories captured: {len(before_directories)}"
    )

    before_snapshot = create_integrity_snapshot(
        project_root,
        before_records,
        before_directories,
    )

    # -------------------------------------------------------------------------
    # STEP 4A
    # -------------------------------------------------------------------------

    reporter.header("STEP 4A — PROJECT STRUCTURE")

    result = validate_unique_paths(before_records)
    results.append(result)
    reporter.result(result)

    # -------------------------------------------------------------------------
    # STEP 4B
    # -------------------------------------------------------------------------

    reporter.header("STEP 4B — ARTIFACT INVENTORY")

    result = validate_nonempty_files(
        project_root,
        before_records,
    )
    results.append(result)
    reporter.result(result)

    result = validate_pdf_files(
        project_root,
        before_records,
    )
    results.append(result)
    reporter.result(result)

    result = validate_html_files(
        project_root,
        before_records,
    )
    results.append(result)
    reporter.result(result)

    # -------------------------------------------------------------------------
    # STEP 4C
    # -------------------------------------------------------------------------

    reporter.header("STEP 4C — HASH INTEGRITY")

    result = validate_hash_format(before_records)
    results.append(result)
    reporter.result(result)

    result = validate_no_hash_collisions(before_records)
    results.append(result)
    reporter.result(result)

    result = validate_files_rehash(
        project_root,
        before_records,
    )
    results.append(result)
    reporter.result(result)

    # -------------------------------------------------------------------------
    # STEP 4D
    # -------------------------------------------------------------------------

    reporter.header("STEP 4D — DETERMINISTIC VALIDATION")

    result = synthetic_hash_test()
    results.append(result)
    reporter.result(result)

    result = synthetic_duplicate_detection_test()
    results.append(result)
    reporter.result(result)

    result = synthetic_ordering_test()
    results.append(result)
    reporter.result(result)

    # -------------------------------------------------------------------------
    # STEP 4E
    # -------------------------------------------------------------------------

    reporter.header(
        "STEP 4E v6.3 — SYNTHETIC REGRESSION TEST + REAL INTEGRITY SNAPSHOT"
    )

    result = synthetic_read_only_test(project_root)
    results.append(result)
    reporter.result(result)

    # -------------------------------------------------------------------------
    # AFTER SNAPSHOT
    # -------------------------------------------------------------------------

    after_records = discover_files(project_root)
    after_directories = discover_directories(project_root)

    after_snapshot = create_integrity_snapshot(
        project_root,
        after_records,
        after_directories,
    )

    snapshot_result = compare_snapshots(
        before_snapshot,
        after_snapshot,
    )

    results.append(snapshot_result)
    reporter.result(snapshot_result)

    # -------------------------------------------------------------------------
    # FINAL COUNTS
    # -------------------------------------------------------------------------

    if len(before_records) != len(after_records):

        result = ValidationResult(
            name="File-count stability",
            passed=False,
            details=(
                f"Before={len(before_records)}, "
                f"After={len(after_records)}"
            ),
        )

    else:

        result = ValidationResult(
            name="File-count stability",
            passed=True,
            details=(
                f"File count remained stable at "
                f"{len(before_records)}."
            ),
        )

    results.append(result)
    reporter.result(result)

    if len(before_directories) != len(after_directories):

        result = ValidationResult(
            name="Directory-count stability",
            passed=False,
            details=(
                f"Before={len(before_directories)}, "
                f"After={len(after_directories)}"
            ),
        )

    else:

        result = ValidationResult(
            name="Directory-count stability",
            passed=True,
            details=(
                f"Directory count remained stable at "
                f"{len(before_directories)}."
            ),
        )

    results.append(result)
    reporter.result(result)

    # -------------------------------------------------------------------------
    # FINAL RESULT
    # -------------------------------------------------------------------------

    overall_pass = all(
        result.passed
        for result in results
    )

    finished = datetime.now(timezone.utc)

    summary = ValidationSummary(
        step=STEP_VERSION,
        script_version=SCRIPT_VERSION,
        started_utc=started.isoformat(),
        finished_utc=finished.isoformat(),
        project_root=str(project_root),
        files_discovered=len(before_records),
        directories_discovered=len(before_directories),
        validation_results=results,
        overall_pass=overall_pass,
    )

    reporter.footer(overall_pass)

    return summary


# =============================================================================
# CLI
# =============================================================================

def parse_args(
    argv: Optional[Sequence[str]] = None,
) -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Einstein Brain V1 — Step 4 integrity validation"
        )
    )

    parser.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_PROJECT_ROOT,
        help=(
            "Einstein Brain V1 project root. "
            "Defaults to the repository root."
        ),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the final validation summary as JSON.",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress normal terminal output.",
    )

    return parser.parse_args(argv)


def main(
    argv: Optional[Sequence[str]] = None,
) -> int:

    args = parse_args(argv)

    project_root = args.project_root.resolve()

    reporter = Reporter(
        quiet=args.quiet
    )

    try:

        summary = run_step4(
            project_root=project_root,
            reporter=reporter,
        )

    except KeyboardInterrupt:

        print(
            "\nValidation interrupted by user.",
            file=sys.stderr,
        )

        return 2

    except Exception as exc:

        print(
            "\nSTEP 4 ERROR:",
            file=sys.stderr,
        )

        print(
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

        return 2

    if args.json:

        print(
            json.dumps(
                summary.to_dict(),
                indent=2,
                sort_keys=True,
            )
        )

    return 0 if summary.overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
