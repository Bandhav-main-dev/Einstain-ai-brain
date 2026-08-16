#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
EINSTEIN BRAIN V1 — STEP 6
GEMINI × DETERMINISTIC RECONCILIATION AND CLOSURE
================================================================================

FILE:
    STEP_6_GEMINI_DETERMINISTIC_RECONCILIATION_AND_CLOSURE.py

DESCRIPTION:
    Final Gemini × deterministic field-level reconciliation, provenance/
    fabrication validation, fail-closed safety checks, and Step 6 closure-gate
    auditing.

TARGETS:
    EIN-003
    EIN-004
    EIN-005
    EIN-007

MODE:
    READ-ONLY / FAIL-CLOSED

IMPORTANT SAFETY RULES:
    1. Gemini is NEVER authoritative.
    2. Gemini output is NEVER promoted automatically.
    3. Source PDFs and deterministic extraction artifacts are NEVER modified.
    4. Audit outputs are written only under audit/step_6_final/.
    5. Any unresolved provenance, conflict, fabrication, or unverifiable
       condition causes BLOCKED.
    6. PASS means only that reconciliation/closure conditions were satisfied;
       it does not promote Gemini data into the canonical corpus.

================================================================================
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(
    "/content/drive/MyDrive/Einstein_Brain_V1"
).resolve()

AUDIT_ROOT = PROJECT_ROOT / "audit"

FINAL_AUDIT_ROOT = (
    AUDIT_ROOT
    / "step_6_final"
    / "final_reconciliation"
)

TARGETS = [
    "EIN-003",
    "EIN-004",
    "EIN-005",
    "EIN-007",
]

GEMINI_AUDIT_ROOTS = [
    AUDIT_ROOT / "step_6_3g",
    AUDIT_ROOT / "step_6_4_fix",
    AUDIT_ROOT / "step_6_4_fix_4",
]

ALLOWED_DETERMINISTIC_SUFFIXES = {
    ".json",
    ".jsonl",
    ".csv",
    ".parquet",
    ".pkl",
    ".pickle",
    ".txt",
}

# These are deliberately excluded from deterministic source selection.
EXCLUDED_PATH_TERMS = {
    "audit",
    "gemini",
    "backup",
    "review",
    "diagnostic",
    "summary",
    "report",
    "log",
    "logs",
    "queue",
    "priority",
    "integrity",
    "validation",
    "validated",
    "closure",
    "reconciliation",
    "reconcile",
    "comparison",
    "compare",
    "regression",
    "snapshot",
    "manifest_provenance",
}

# Stronger exclusion terms for obviously non-source files.
HARD_EXCLUDE_TERMS = {
    "gemini",
    "audit",
    "backup",
    "diagnostic",
    "summary",
    "closure",
    "reconciliation",
    "reconcile",
    "step_6",
    "step6",
}

PAGE_KEYS = [
    "page",
    "page_number",
    "page_num",
    "page_index",
    "pdf_page",
    "source_page",
    "physical_page",
]

EVIDENCE_KEYS = [
    "evidence",
    "evidence_text",
    "text",
    "ocr_text",
    "page_text",
    "content",
    "extracted_text",
    "raw_text",
    "formula",
    "formula_text",
    "transcription",
    "transcribed_text",
]

PROVENANCE_KEYS = [
    "source",
    "source_id",
    "source_path",
    "source_file",
    "document",
    "document_id",
    "pdf",
    "pdf_path",
    "file",
    "filename",
    "provenance",
    "page_source",
]

SEMANTIC_POSITION_KEYS = [
    "position",
    "record_position",
    "sequence",
    "sequence_number",
    "index",
    "record_index",
    "block_index",
    "evidence_index",
    "item_index",
]

IGNORE_COMPARE_KEYS = {
    "timestamp",
    "created_at",
    "updated_at",
    "run_id",
    "audit_id",
    "hash",
    "sha256",
    "sha_256",
    "score",
    "confidence",
}

GEMINI_IS_AUTHORITATIVE = False
PROMOTION_ALLOWED = False
SOURCE_MUTATION = False


# =============================================================================
# GENERAL UTILITIES
# =============================================================================

def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


RUN_ID = utc_run_id()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except Exception:
        return str(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def safe_json_load(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, bool):
        return str(value).lower()

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, (list, tuple)):
        return " ".join(clean_text(x) for x in value)

    if isinstance(value, dict):
        return " ".join(
            f"{k} {clean_text(v)}"
            for k, v in value.items()
        )

    text = str(value)

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", " ")

    return re.sub(r"\s+", " ", text).strip()


def normalize_value(value: Any) -> str:
    text = clean_text(value)

    text = unicodedata.normalize(
        "NFKC",
        text
    ).casefold()

    text = re.sub(
        r"[\u2010-\u2015]",
        "-",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = re.sub(
        r"\s*([,;:])\s*",
        r"\1",
        text,
    )

    return text.strip()


def is_nonempty(value: Any) -> bool:
    return bool(clean_text(value))


def recursive_dicts(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj

        for value in obj.values():
            yield from recursive_dicts(value)

    elif isinstance(obj, list):
        for item in obj:
            yield from recursive_dicts(item)


def first_value(
    record: Dict[str, Any],
    keys: Iterable[str],
) -> Any:
    lowered = {
        str(k).casefold(): v
        for k, v in record.items()
    }

    for key in keys:
        if key.casefold() in lowered:
            value = lowered[key.casefold()]

            if is_nonempty(value):
                return value

    return None


def first_key(
    record: Dict[str, Any],
    keys: Iterable[str],
) -> Optional[str]:
    lowered = {
        str(k).casefold(): k
        for k in record.keys()
    }

    for key in keys:
        if key.casefold() in lowered:
            return lowered[key.casefold()]

    return None


def page_number(record: Dict[str, Any]) -> Optional[int]:
    value = first_value(record, PAGE_KEYS)

    if value is None:
        return None

    try:
        return int(float(str(value).strip()))
    except Exception:
        match = re.search(r"\b(\d{1,4})\b", str(value))

        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None

    return None


def semantic_position(record: Dict[str, Any]) -> Optional[str]:
    value = first_value(
        record,
        SEMANTIC_POSITION_KEYS,
    )

    if value is None:
        return None

    return normalize_value(value)


def evidence_value(record: Dict[str, Any]) -> str:
    values = []

    for key in EVIDENCE_KEYS:
        actual = first_key(record, [key])

        if actual is not None:
            value = record.get(actual)

            if is_nonempty(value):
                values.append(clean_text(value))

    return " ".join(values).strip()


def provenance_values(record: Dict[str, Any]) -> List[str]:
    values = []

    for key in PROVENANCE_KEYS:
        actual = first_key(record, [key])

        if actual is not None:
            value = record.get(actual)

            if is_nonempty(value):
                values.append(clean_text(value))

    return values


def has_provenance(record: Dict[str, Any]) -> bool:
    return bool(provenance_values(record))


# =============================================================================
# RECORD EXTRACTION
# =============================================================================

def looks_like_record(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False

    has_page = page_number(obj) is not None
    has_evidence = bool(evidence_value(obj))
    has_provenance_value = has_provenance(obj)

    return (
        has_page
        and has_evidence
        and has_provenance_value
    )


def extract_records_from_object(
    obj: Any,
    path: str = "$",
) -> List[Tuple[str, Dict[str, Any]]]:

    results = []

    if isinstance(obj, list):

        for i, item in enumerate(obj):
            child_path = f"{path}[{i}]"

            if looks_like_record(item):
                results.append(
                    (child_path, item)
                )

            elif isinstance(item, (dict, list)):
                results.extend(
                    extract_records_from_object(
                        item,
                        child_path,
                    )
                )

        return results

    if isinstance(obj, dict):

        # Prefer explicit record arrays.
        preferred_keys = [
            "records",
            "pages",
            "extracted_records",
            "extraction",
            "extracted_evidence",
            "evidence",
            "items",
            "data",
        ]

        for key in preferred_keys:
            if key in obj:
                value = obj[key]

                if isinstance(value, list):
                    explicit = []

                    for i, item in enumerate(value):
                        child_path = f"{path}.{key}[{i}]"

                        if looks_like_record(item):
                            explicit.append(
                                (child_path, item)
                            )

                    if explicit:
                        return explicit

        # Fall back to recursive discovery.
        for key, value in obj.items():

            child_path = f"{path}.{key}"

            if isinstance(value, (dict, list)):
                results.extend(
                    extract_records_from_object(
                        value,
                        child_path,
                    )
                )

        return results

    return results


# =============================================================================
# CSV / JSON / JSONL / PARQUET / PICKLE / TXT
# =============================================================================

def load_tabular_records(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.casefold()

    if suffix == ".csv":

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as f:

            reader = csv.DictReader(f)

            return [
                dict(row)
                for row in reader
            ]

    if suffix == ".jsonl":

        records = []

        with path.open(
            "r",
            encoding="utf-8",
        ) as f:

            for line in f:

                line = line.strip()

                if not line:
                    continue

                try:
                    obj = json.loads(line)

                    if isinstance(obj, dict):
                        records.append(obj)

                except Exception:
                    continue

        return records

    if suffix == ".json":

        obj, error = safe_json_load(path)

        if error:
            return []

        extracted = extract_records_from_object(obj)

        return [
            record
            for _, record in extracted
        ]

    if suffix in {".parquet"}:

        try:
            import pandas as pd

            df = pd.read_parquet(path)

            return df.fillna("").to_dict(
                orient="records"
            )

        except Exception:
            return []

    if suffix in {".pkl", ".pickle"}:

        try:
            import pickle

            with path.open("rb") as f:
                obj = pickle.load(f)

            extracted = extract_records_from_object(obj)

            if extracted:
                return [
                    record
                    for _, record in extracted
                ]

            if isinstance(obj, list):
                return [
                    x
                    for x in obj
                    if isinstance(x, dict)
                ]

        except Exception:
            return []

        return []

    if suffix == ".txt":

        records = []

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            lines = text.splitlines()

            for line_no, line in enumerate(lines, 1):

                line = line.strip()

                if not line:
                    continue

                page_match = re.search(
                    r"(?:page|pg)\s*[:=#]?\s*(\d+)",
                    line,
                    flags=re.I,
                )

                if page_match:

                    records.append(
                        {
                            "page": int(
                                page_match.group(1)
                            ),
                            "text": line,
                            "source_file": str(path),
                            "line": line_no,
                        }
                    )

        except Exception:
            pass

        return records

    return []


# =============================================================================
# TARGET IDENTIFICATION
# =============================================================================

def target_ids_from_path(path: Path) -> List[str]:
    text = safe_rel(path).upper()

    found = []

    for target in TARGETS:
        if target in text:
            found.append(target)

    return found


def target_id_from_record(
    record: Dict[str, Any]
) -> Optional[str]:

    text = " ".join(
        provenance_values(record)
    ).upper()

    for target in TARGETS:

        if target in text:
            return target

    return None


# =============================================================================
# DETERMINISTIC ARTIFACT DISCOVERY
# =============================================================================

def is_excluded_deterministic(path: Path) -> bool:

    relative = safe_rel(path).casefold()

    parts = set(
        p.casefold()
        for p in path.parts
    )

    if any(
        term in relative
        for term in HARD_EXCLUDE_TERMS
    ):
        return True

    if any(
        term in parts
        for term in {
            "audit",
            "logs",
            "log",
            "backup",
        }
    ):
        return True

    name = path.name.casefold()

    if any(
        term in name
        for term in {
            "gemini",
            "audit",
            "backup",
            "diagnostic",
            "summary",
            "closure",
            "reconciliation",
        }
    ):
        return True

    return False


def inventory_deterministic_artifacts() -> List[Path]:

    artifacts = []

    for path in PROJECT_ROOT.rglob("*"):

        if not path.is_file():
            continue

        if path.suffix.casefold() not in (
            ALLOWED_DETERMINISTIC_SUFFIXES
        ):
            continue

        if is_excluded_deterministic(path):
            continue

        artifacts.append(path)

    return sorted(
        artifacts,
        key=lambda p: safe_rel(p).casefold()
    )


# =============================================================================
# CANDIDATE VALIDATION / RANKING
# =============================================================================

def candidate_profile(
    path: Path,
    target: str,
) -> Dict[str, Any]:

    records = load_tabular_records(path)

    if not records:
        return {
            "path": str(path),
            "relative_path": safe_rel(path),
            "target": target,
            "records": [],
            "record_count": 0,
            "page_count": 0,
            "evidence_count": 0,
            "provenance_count": 0,
            "complete_count": 0,
            "valid": False,
            "eligible": False,
            "score": -999999,
        }

    target_records = []

    path_has_target = target in safe_rel(path).upper()

    for record in records:

        record_target = target_id_from_record(record)

        if record_target == target:
            target_records.append(record)

        elif record_target is None and path_has_target:
            target_records.append(record)

    if not target_records:
        return {
            "path": str(path),
            "relative_path": safe_rel(path),
            "target": target,
            "records": [],
            "record_count": 0,
            "page_count": 0,
            "evidence_count": 0,
            "provenance_count": 0,
            "complete_count": 0,
            "valid": False,
            "eligible": False,
            "score": -999999,
        }

    page_count = sum(
        page_number(r) is not None
        for r in target_records
    )

    evidence_count = sum(
        bool(evidence_value(r))
        for r in target_records
    )

    provenance_count = sum(
        has_provenance(r)
        for r in target_records
    )

    complete_count = sum(
        (
            page_number(r) is not None
            and bool(evidence_value(r))
            and has_provenance(r)
        )
        for r in target_records
    )

    count = len(target_records)

    valid = (
        count > 0
        and page_count == count
        and evidence_count == count
        and provenance_count == count
        and complete_count == count
    )

    relative = safe_rel(path).casefold()

    score = 0

    score += complete_count * 20
    score += page_count * 5
    score += evidence_count * 10
    score += provenance_count * 10

    # Prefer canonical page extraction artifacts.
    if "pages" in path.name.casefold():
        score += 100

    if "extracted" in relative:
        score += 50

    if "manifests" in relative:
        score += 20

    # Penalize suspicious classes.
    for term in EXCLUDED_PATH_TERMS:
        if term in relative:
            score -= 100

    return {
        "path": str(path),
        "relative_path": safe_rel(path),
        "target": target,
        "records": target_records,
        "record_count": count,
        "page_count": page_count,
        "evidence_count": evidence_count,
        "provenance_count": provenance_count,
        "complete_count": complete_count,
        "valid": valid,
        "eligible": valid,
        "score": score,
    }


def resolve_deterministic_sources() -> Dict[str, Dict[str, Any]]:

    artifacts = inventory_deterministic_artifacts()

    print(
        f"Eligible deterministic artifacts : {len(artifacts)}"
    )

    resolved = {}

    for target in TARGETS:

        candidates = []

        for path in artifacts:

            if target not in safe_rel(path).upper():
                continue

            profile = candidate_profile(
                path,
                target,
            )

            if profile["record_count"] > 0:
                candidates.append(profile)

        candidates.sort(
            key=lambda x: (
                x["eligible"],
                x["complete_count"],
                x["score"],
                x["record_count"],
                x["relative_path"],
            ),
            reverse=True,
        )

        selected = None

        for candidate in candidates:

            if candidate["eligible"]:
                selected = candidate
                break

        if selected is None:

            resolved[target] = {
                "status": "BLOCKED",
                "candidates": candidates,
            }

        else:

            resolved[target] = {
                "status": "RESOLVED",
                "selected": selected,
                "candidates": candidates,
            }

    return resolved


# =============================================================================
# GEMINI PAYLOAD DISCOVERY
# =============================================================================

def discover_gemini_audits() -> List[Path]:

    files = []

    for root in GEMINI_AUDIT_ROOTS:

        if not root.exists():
            continue

        for path in root.rglob("*.json"):

            if path.is_file():
                files.append(path)

    return sorted(
        set(files),
        key=lambda p: safe_rel(p).casefold()
    )


def resolve_gemini_payload(
    path: Path,
    target: str,
) -> Optional[Dict[str, Any]]:

    obj, error = safe_json_load(path)

    if error:
        return None

    candidates = []

    # Explicit known locations first.
    explicit_paths = [
        (
            "$.extracted_evidence.records",
            lambda x:
                x.get("extracted_evidence", {})
                if isinstance(x, dict)
                else {},
        ),
        (
            "$.records",
            lambda x:
                x if isinstance(x, dict)
                else {},
        ),
    ]

    for payload_path, getter in explicit_paths:

        try:

            container = getter(obj)

            if payload_path.endswith(
                "extracted_evidence.records"
            ):

                records = (
                    container.get("records")
                    if isinstance(container, dict)
                    else None
                )

            else:

                records = (
                    container.get("records")
                    if isinstance(container, dict)
                    else None
                )

            if isinstance(records, list):

                valid_records = [
                    r
                    for r in records
                    if isinstance(r, dict)
                ]

                if valid_records:

                    score = (
                        len(valid_records) * 5
                    )

                    candidates.append(
                        {
                            "path": payload_path,
                            "records": valid_records,
                            "score": score,
                        }
                    )

        except Exception:
            pass

    # Recursive fallback.
    for p, record in extract_records_from_object(obj):

        candidates.append(
            {
                "path": p.rsplit("[", 1)[0],
                "records": [],
                "score": 1,
            }
        )

    if not candidates:
        return None

    # Prefer explicit extraction payloads.
    candidates.sort(
        key=lambda x: (
            x["score"],
            "extracted_evidence" in x["path"],
            x["path"],
        ),
        reverse=True,
    )

    selected = candidates[0]

    return {
        "audit_path": str(path),
        "payload_path": selected["path"],
        "records": selected["records"],
        "record_count": len(selected["records"]),
        "score": selected["score"],
    }


def resolve_best_gemini_sources() -> Dict[str, Any]:

    audits = discover_gemini_audits()

    print(
        f"Gemini audit candidates discovered : {len(audits)}"
    )

    resolved = {}

    for target in TARGETS:

        candidates = []

        for audit in audits:

            if target not in audit.name.upper():
                continue

            payload = resolve_gemini_payload(
                audit,
                target,
            )

            if payload is not None:
                candidates.append(payload)

        candidates.sort(
            key=lambda x: (
                x["record_count"],
                x["score"],
                x["audit_path"],
            ),
            reverse=True,
        )

        if candidates:

            resolved[target] = candidates[0]

        else:

            resolved[target] = None

    return resolved


# =============================================================================
# RECORD MATCHING
# =============================================================================

def page_index(
    records: List[Dict[str, Any]]
) -> Dict[int, List[Dict[str, Any]]]:

    result = defaultdict(list)

    for record in records:

        page = page_number(record)

        if page is not None:
            result[page].append(record)

    return result


def semantic_text(record: Dict[str, Any]) -> str:
    return normalize_value(
        evidence_value(record)
    )


def text_similarity(
    a: str,
    b: str,
) -> float:

    a_tokens = set(
        normalize_value(a).split()
    )

    b_tokens = set(
        normalize_value(b).split()
    )

    if not a_tokens or not b_tokens:
        return 0.0

    intersection = len(
        a_tokens & b_tokens
    )

    union = len(
        a_tokens | b_tokens
    )

    return intersection / union if union else 0.0


def match_record(
    gemini_record: Dict[str, Any],
    deterministic_records: List[Dict[str, Any]],
) -> Tuple[
    Optional[Dict[str, Any]],
    str,
]:

    g_page = page_number(gemini_record)
    g_position = semantic_position(
        gemini_record
    )

    # 1. Exact page + semantic position.
    candidates = []

    for record in deterministic_records:

        d_page = page_number(record)
        d_position = semantic_position(
            record
        )

        if (
            g_page is not None
            and d_page == g_page
            and g_position
            and d_position
            and g_position == d_position
        ):
            candidates.append(record)

    if len(candidates) == 1:
        return candidates[0], "PAGE_POSITION"

    # 2. Exact page with only one deterministic record.
    page_candidates = [
        record
        for record in deterministic_records
        if (
            g_page is not None
            and page_number(record) == g_page
        )
    ]

    if len(page_candidates) == 1:
        return (
            page_candidates[0],
            "PAGE",
        )

    # 3. Page + semantic text similarity.
    if page_candidates:

        best = None
        best_score = 0.0

        g_text = semantic_text(
            gemini_record
        )

        for record in page_candidates:

            d_text = semantic_text(record)

            score = text_similarity(
                g_text,
                d_text,
            )

            if score > best_score:

                best_score = score
                best = record

        if best is not None and best_score >= 0.80:

            return (
                best,
                "PAGE_TEXT",
            )

    return None, "UNMATCHED"


# =============================================================================
# FIELD RECONCILIATION
# =============================================================================

def comparable_fields(
    gemini_record: Dict[str, Any],
    deterministic_record: Dict[str, Any],
) -> List[str]:

    fields = []

    all_keys = set(
        str(k)
        for k in gemini_record.keys()
    ) | set(
        str(k)
        for k in deterministic_record.keys()
    )

    for key in sorted(all_keys):

        normalized_key = key.casefold()

        if normalized_key in IGNORE_COMPARE_KEYS:
            continue

        if normalized_key in {
            k.casefold()
            for k in PAGE_KEYS
        }:
            continue

        if normalized_key in {
            k.casefold()
            for k in PROVENANCE_KEYS
        }:
            continue

        if normalized_key in {
            k.casefold()
            for k in SEMANTIC_POSITION_KEYS
        }:
            continue

        fields.append(key)

    return fields


def find_field(
    record: Dict[str, Any],
    key: str,
) -> Any:

    for actual_key, value in record.items():

        if (
            str(actual_key).casefold()
            == str(key).casefold()
        ):
            return value

    return None


def compare_field(
    gemini_value: Any,
    deterministic_value: Any,
) -> str:

    g = normalize_value(gemini_value)
    d = normalize_value(deterministic_value)

    if not g or not d:
        return "UNVERIFIABLE"

    if g == d:
        return "MATCH"

    # Conservative normalizable comparison.
    g_compact = re.sub(
        r"[\s\W_]+",
        "",
        g,
        flags=re.UNICODE,
    )

    d_compact = re.sub(
        r"[\s\W_]+",
        "",
        d,
        flags=re.UNICODE,
    )

    if (
        g_compact
        and d_compact
        and g_compact == d_compact
    ):
        return "NORMALIZABLE_MATCH"

    # Numeric equivalence.
    try:

        g_num = float(
            re.sub(
                r"[^\d.+-eE]",
                "",
                g,
            )
        )

        d_num = float(
            re.sub(
                r"[^\d.+-eE]",
                "",
                d,
            )
        )

        if abs(g_num - d_num) <= 1e-12:
            return "NORMALIZABLE_MATCH"

    except Exception:
        pass

    return "CONFLICT"


def reconcile_record(
    gemini_record: Dict[str, Any],
    deterministic_record: Optional[Dict[str, Any]],
) -> Dict[str, Any]:

    result = {
        "gemini_record": gemini_record,
        "deterministic_record": deterministic_record,
        "match_method": None,
        "overall_status": None,
        "field_results": {},
    }

    if deterministic_record is None:

        result["overall_status"] = "UNVERIFIABLE"

        return result

    field_statuses = []

    fields = comparable_fields(
        gemini_record,
        deterministic_record,
    )

    for field in fields:

        g_value = find_field(
            gemini_record,
            field,
        )

        d_value = find_field(
            deterministic_record,
            field,
        )

        status = compare_field(
            g_value,
            d_value,
        )

        result["field_results"][field] = {
            "gemini": g_value,
            "deterministic": d_value,
            "status": status,
        }

        field_statuses.append(status)

    if not field_statuses:

        result["overall_status"] = (
            "UNVERIFIABLE"
        )

    elif "CONFLICT" in field_statuses:

        result["overall_status"] = (
            "CONFLICT"
        )

    elif all(
        status == "MATCH"
        for status in field_statuses
    ):

        result["overall_status"] = "MATCH"

    elif all(
        status in {
            "MATCH",
            "NORMALIZABLE_MATCH",
        }
        for status in field_statuses
    ):

        result["overall_status"] = (
            "NORMALIZABLE_MATCH"
        )

    else:

        result["overall_status"] = (
            "UNVERIFIABLE"
        )

    return result


# =============================================================================
# PROVENANCE / FABRICATION VALIDATION
# =============================================================================

def validate_gemini_provenance(
    target: str,
    record: Dict[str, Any],
) -> Tuple[bool, List[str]]:

    issues = []

    values = provenance_values(
        record
    )

    if not values:

        issues.append(
            "NO_PROVENANCE_FIELD"
        )

        return False, issues

    combined = " ".join(values).upper()

    # Gemini target identity must not contradict target.
    for other in TARGETS:

        if (
            other != target
            and other in combined
        ):
            issues.append(
                f"PROVENANCE_TARGET_CONFLICT_{other}"
            )

    # If a target is explicitly stated, require consistency.
    explicit_target = (
        target in combined
    )

    if not explicit_target:

        issues.append(
            "GEMINI_TARGET_ID_NOT_EXPLICIT_IN_PROVENANCE"
        )

    return not issues, issues


def detect_fabrication(
    target: str,
    gemini_records: List[Dict[str, Any]],
    deterministic_records: List[Dict[str, Any]],
) -> Tuple[bool, List[str]]:

    issues = []

    deterministic_pages = Counter(
        page_number(r)
        for r in deterministic_records
        if page_number(r) is not None
    )

    gemini_pages = Counter(
        page_number(r)
        for r in gemini_records
        if page_number(r) is not None
    )

    # A Gemini page that does not exist in the deterministic source
    # is suspicious, but not automatically fabrication unless there
    # is strong contradiction.
    unknown_pages = [
        page
        for page in gemini_pages
        if page not in deterministic_pages
    ]

    if unknown_pages:
        issues.append(
            "GEMINI_PAGES_ABSENT_FROM_DETERMINISTIC_SOURCE"
        )

    # Explicit target contradiction.
    for record in gemini_records:

        for value in provenance_values(record):

            upper = value.upper()

            for other in TARGETS:

                if (
                    other != target
                    and other in upper
                ):
                    issues.append(
                        f"RECORD_PROVENANCE_TARGET_CONFLICT_{other}"
                    )

    return bool(issues), sorted(
        set(issues)
    )


# =============================================================================
# TARGET RECONCILIATION
# =============================================================================

def reconcile_target(
    target: str,
    deterministic_info: Dict[str, Any],
    gemini_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:

    result = {
        "target": target,
        "run_id": RUN_ID,
        "timestamp_utc": now_iso(),
        "decision": "BLOCKED",
        "closure_status": "OPEN",

        "gemini_authoritative": False,
        "promotion_allowed": False,
        "source_mutation": False,

        "deterministic": {},
        "gemini": {},

        "structural_validation": False,
        "provenance_validation": False,
        "fabrication_detected": False,

        "counts": {
            "MATCH": 0,
            "NORMALIZABLE_MATCH": 0,
            "CONFLICT": 0,
            "UNVERIFIABLE": 0,
        },

        "block_reasons": [],
        "record_reconciliation": [],
    }

    if (
        deterministic_info.get("status")
        != "RESOLVED"
    ):

        result["block_reasons"].append(
            "DETERMINISTIC_SOURCE_NOT_RESOLVED"
        )

        return result

    deterministic_selected = (
        deterministic_info["selected"]
    )

    deterministic_records = (
        deterministic_selected["records"]
    )

    result["deterministic"] = {
        "source_path": deterministic_selected["path"],
        "relative_path": deterministic_selected[
            "relative_path"
        ],
        "record_count": len(
            deterministic_records
        ),
        "record_array": "$[CSV_ROWS]",
        "sha256": sha256_file(
            Path(
                deterministic_selected["path"]
            )
        ),
    }

    # -------------------------------------------------------------------------
    # Deterministic structural validation
    # -------------------------------------------------------------------------

    deterministic_structure_ok = True

    for record in deterministic_records:

        if page_number(record) is None:
            deterministic_structure_ok = False

        if not evidence_value(record):
            deterministic_structure_ok = False

        if not has_provenance(record):
            deterministic_structure_ok = False

    if not deterministic_structure_ok:

        result["block_reasons"].append(
            "DETERMINISTIC_STRUCTURAL_VALIDATION_FAILED"
        )

    # -------------------------------------------------------------------------
    # Gemini payload validation
    # -------------------------------------------------------------------------

    if gemini_info is None:

        result["block_reasons"].append(
            "GEMINI_PAYLOAD_NOT_RESOLVED"
        )

        return result

    gemini_records = gemini_info["records"]

    result["gemini"] = {
        "audit_path": gemini_info["audit_path"],
        "payload_path": gemini_info["payload_path"],
        "record_count": len(gemini_records),
        "selection_score": gemini_info["score"],
    }

    structural_ok = True

    for record in gemini_records:

        if not isinstance(record, dict):
            structural_ok = False

        if page_number(record) is None:
            structural_ok = False

        if not evidence_value(record):
            structural_ok = False

    result["structural_validation"] = (
        deterministic_structure_ok
        and structural_ok
    )

    if not result["structural_validation"]:

        result["block_reasons"].append(
            "STRUCTURAL_VALIDATION_FAILED"
        )

    # -------------------------------------------------------------------------
    # Provenance validation
    # -------------------------------------------------------------------------

    provenance_ok = True

    provenance_issues = []

    for record in gemini_records:

        valid, issues = validate_gemini_provenance(
            target,
            record,
        )

        if not valid:
            provenance_ok = False

        provenance_issues.extend(
            issues
        )

    result["provenance_validation"] = (
        provenance_ok
    )

    result["gemini"]["provenance_issues"] = sorted(
        set(provenance_issues)
    )

    if not provenance_ok:

        result["block_reasons"].append(
            "PROVENANCE_VALIDATION_FAILED"
        )

    # -------------------------------------------------------------------------
    # Fabrication validation
    # -------------------------------------------------------------------------

    fabrication, fabrication_issues = (
        detect_fabrication(
            target,
            gemini_records,
            deterministic_records,
        )
    )

    result["fabrication_detected"] = (
        fabrication
    )

    result["gemini"]["fabrication_issues"] = (
        fabrication_issues
    )

    if fabrication:

        result["block_reasons"].append(
            "FABRICATION_DETECTED"
        )

    # -------------------------------------------------------------------------
    # Record-level reconciliation
    # -------------------------------------------------------------------------

    used_deterministic = set()

    for index, gemini_record in enumerate(
        gemini_records
    ):

        matched_record = None
        match_method = "UNMATCHED"

        # Try normal matching first.
        matched_record, match_method = match_record(
            gemini_record,
            deterministic_records,
        )

        # Avoid reusing the same deterministic record
        # where another candidate is available.
        if matched_record is not None:

            matched_id = id(
                matched_record
            )

            if matched_id in used_deterministic:

                alternatives = [
                    r
                    for r in deterministic_records
                    if id(r)
                    not in used_deterministic
                ]

                alt_match, alt_method = (
                    match_record(
                        gemini_record,
                        alternatives,
                    )
                )

                if alt_match is not None:

                    matched_record = alt_match
                    match_method = alt_method

        if matched_record is not None:

            used_deterministic.add(
                id(matched_record)
            )

        record_result = reconcile_record(
            gemini_record,
            matched_record,
        )

        record_result["gemini_index"] = index
        record_result["match_method"] = (
            match_method
        )

        status = record_result[
            "overall_status"
        ]

        if status not in result["counts"]:
            status = "UNVERIFIABLE"

        result["counts"][status] += 1

        result["record_reconciliation"].append(
            record_result
        )

    # -------------------------------------------------------------------------
    # Fail-closed decision
    # -------------------------------------------------------------------------

    if result["counts"]["CONFLICT"] > 0:

        result["block_reasons"].append(
            "FIELD_CONFLICTS_PRESENT"
        )

    if result["counts"]["UNVERIFIABLE"] > 0:

        result["block_reasons"].append(
            "UNVERIFIABLE_FIELDS_PRESENT"
        )

    if not result["structural_validation"]:

        result["block_reasons"].append(
            "STRUCTURAL_VALIDATION_NOT_PASS"
        )

    if not result["provenance_validation"]:

        result["block_reasons"].append(
            "PROVENANCE_VALIDATION_NOT_PASS"
        )

    if result["fabrication_detected"]:

        result["block_reasons"].append(
            "FABRICATION_DETECTED"
        )

    result["block_reasons"] = sorted(
        set(result["block_reasons"])
    )

    # Gemini can NEVER make the decision authoritative.
    result["gemini_authoritative"] = False
    result["promotion_allowed"] = False
    result["source_mutation"] = False

    # PASS is deliberately strict.
    if (
        result["structural_validation"]
        and result["provenance_validation"]
        and not result["fabrication_detected"]
        and result["counts"]["CONFLICT"] == 0
        and result["counts"]["UNVERIFIABLE"] == 0
        and len(result["block_reasons"]) == 0
    ):

        result["decision"] = "PASS"
        result["closure_status"] = "CLOSED"

    else:

        result["decision"] = "BLOCKED"
        result["closure_status"] = "OPEN"

    return result


# =============================================================================
# AUDIT OUTPUT
# =============================================================================

def ensure_audit_directory() -> None:

    FINAL_AUDIT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )


def save_json(
    path: Path,
    obj: Any,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            obj,
            f,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:

    print("=" * 80)
    print(
        "EINSTEIN BRAIN V1 — STEP 6"
    )
    print(
        "GEMINI × DETERMINISTIC RECONCILIATION AND CLOSURE"
    )
    print("=" * 80)

    print()
    print(
        f"PROJECT ROOT        : {PROJECT_ROOT}"
    )
    print(
        f"RUN ID              : {RUN_ID}"
    )
    print(
        "MODE                : READ_ONLY / FAIL_CLOSED"
    )
    print(
        "SOURCE MUTATION     : False"
    )
    print(
        "GEMINI AUTHORITATIVE: False"
    )
    print(
        "PROMOTION ALLOWED   : False"
    )

    if not PROJECT_ROOT.exists():

        print(
            "\nERROR: Project root does not exist."
        )

        return 1

    ensure_audit_directory()

    # -------------------------------------------------------------------------
    # 1. Deterministic source resolution
    # -------------------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "STEP 6A — DETERMINISTIC SOURCE RESOLUTION"
    )
    print("=" * 80)

    deterministic_sources = (
        resolve_deterministic_sources()
    )

    for target in TARGETS:

        print()
        print(target)

        info = deterministic_sources[target]

        if info["status"] != "RESOLVED":

            print(
                "  STATUS : BLOCKED"
            )

            continue

        selected = info["selected"]

        print(
            "  STATUS : RESOLVED"
        )

        print(
            f"  SOURCE : {selected['path']}"
        )

        print(
            f"  RECORDS: {selected['record_count']}"
        )

        print(
            f"  PAGE   : "
            f"{selected['page_count']}/"
            f"{selected['record_count']}"
        )

        print(
            f"  EVIDENCE: "
            f"{selected['evidence_count']}/"
            f"{selected['record_count']}"
        )

        print(
            f"  PROVENANCE: "
            f"{selected['provenance_count']}/"
            f"{selected['record_count']}"
        )

    # -------------------------------------------------------------------------
    # 2. Gemini payload resolution
    # -------------------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "STEP 6B — GEMINI EXTRACTION PAYLOAD RESOLUTION"
    )
    print("=" * 80)

    gemini_sources = (
        resolve_best_gemini_sources()
    )

    for target in TARGETS:

        print()
        print(target)

        info = gemini_sources[target]

        if info is None:

            print(
                "  STATUS : BLOCKED"
            )

            continue

        print(
            "  STATUS : RESOLVED"
        )

        print(
            f"  AUDIT  : {info['audit_path']}"
        )

        print(
            f"  PAYLOAD: {info['payload_path']}"
        )

        print(
            f"  RECORDS: {info['record_count']}"
        )

    # -------------------------------------------------------------------------
    # 3. Final reconciliation
    # -------------------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "STEP 6C — FINAL FIELD-LEVEL RECONCILIATION"
    )
    print("=" * 80)

    results = {}

    global_counts = Counter()

    for target in TARGETS:

        print()
        print(
            f"RECONCILING {target}"
        )
        print("-" * 80)

        result = reconcile_target(
            target,
            deterministic_sources[target],
            gemini_sources[target],
        )

        results[target] = result

        for status, count in result[
            "counts"
        ].items():

            global_counts[status] += count

        print(
            f"Decision              : "
            f"{result['decision']}"
        )

        print(
            f"Structural validation : "
            f"{result['structural_validation']}"
        )

        print(
            f"Provenance validation : "
            f"{result['provenance_validation']}"
        )

        print(
            f"Fabrication detected  : "
            f"{result['fabrication_detected']}"
        )

        print(
            f"MATCH                 : "
            f"{result['counts']['MATCH']}"
        )

        print(
            f"NORMALIZABLE_MATCH    : "
            f"{result['counts']['NORMALIZABLE_MATCH']}"
        )

        print(
            f"CONFLICT              : "
            f"{result['counts']['CONFLICT']}"
        )

        print(
            f"UNVERIFIABLE          : "
            f"{result['counts']['UNVERIFIABLE']}"
        )

        if result["block_reasons"]:

            print(
                "Block reasons:"
            )

            for reason in result[
                "block_reasons"
            ]:

                print(
                    f"  - {reason}"
                )

        # Save per-PDF audit.
        output_path = (
            FINAL_AUDIT_ROOT
            / (
                f"step_6_final_"
                f"{target}_"
                f"{RUN_ID}.json"
            )
        )

        save_json(
            output_path,
            result,
        )

        print(
            f"Audit saved           : "
            f"{output_path}"
        )

    # -------------------------------------------------------------------------
    # 4. Global closure gate
    # -------------------------------------------------------------------------

    passed = sum(
        result["decision"] == "PASS"
        for result in results.values()
    )

    blocked = len(TARGETS) - passed

    global_block_reasons = set()

    for result in results.values():

        global_block_reasons.update(
            result["block_reasons"]
        )

    if blocked > 0:

        global_block_reasons.add(
            "ONE_OR_MORE_PDFS_BLOCKED"
        )

    if global_counts["CONFLICT"] > 0:

        global_block_reasons.add(
            "FIELD_CONFLICTS_PRESENT"
        )

    if global_counts["UNVERIFIABLE"] > 0:

        global_block_reasons.add(
            "UNVERIFIABLE_FIELDS_PRESENT"
        )

    if any(
        not result["provenance_validation"]
        for result in results.values()
    ):

        global_block_reasons.add(
            "PROVENANCE_VALIDATION_FAILED"
        )

    if any(
        result["fabrication_detected"]
        for result in results.values()
    ):

        global_block_reasons.add(
            "FABRICATION_DETECTED"
        )

    global_decision = (
        "PASS"
        if passed == len(TARGETS)
        and not global_block_reasons
        else "BLOCKED"
    )

    closure_status = (
        "CLOSED"
        if global_decision == "PASS"
        else "OPEN"
    )

    combined = {
        "step": "6",
        "name": (
            "GEMINI_DETERMINISTIC_RECONCILIATION"
            "_AND_CLOSURE"
        ),
        "run_id": RUN_ID,
        "timestamp_utc": now_iso(),

        "project_root": str(
            PROJECT_ROOT
        ),

        "mode": "READ_ONLY_FAIL_CLOSED",

        "safety": {
            "gemini_authoritative": False,
            "promotion_allowed": False,
            "source_mutation": False,
        },

        "targets": TARGETS,

        "pdfs_processed": len(TARGETS),
        "pdfs_pass": passed,
        "pdfs_blocked": blocked,

        "global_counts": dict(
            global_counts
        ),

        "global_decision": global_decision,
        "closure_status": closure_status,

        "global_block_reasons": sorted(
            global_block_reasons
        ),

        "per_pdf": {
            target: {
                "decision": results[target][
                    "decision"
                ],
                "closure_status": results[target][
                    "closure_status"
                ],
                "counts": results[target][
                    "counts"
                ],
                "structural_validation":
                    results[target][
                        "structural_validation"
                    ],
                "provenance_validation":
                    results[target][
                        "provenance_validation"
                    ],
                "fabrication_detected":
                    results[target][
                        "fabrication_detected"
                    ],
                "block_reasons":
                    results[target][
                        "block_reasons"
                    ],
                "deterministic_source":
                    results[target][
                        "deterministic"
                    ],
                "gemini_payload":
                    results[target][
                        "gemini"
                    ],
            }
            for target in TARGETS
        },
    }

    combined_path = (
        FINAL_AUDIT_ROOT
        / (
            "step_6_closure_summary_"
            f"{RUN_ID}.json"
        )
    )

    save_json(
        combined_path,
        combined,
    )

    # -------------------------------------------------------------------------
    # 5. Final console report
    # -------------------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "EINSTEIN BRAIN V1 — STEP 6 FINAL CLOSURE GATE"
    )
    print("=" * 80)

    print()
    print(
        f"PDFs processed             : "
        f"{len(TARGETS)}"
    )

    print(
        f"PDFs PASS                  : "
        f"{passed}"
    )

    print(
        f"PDFs BLOCKED               : "
        f"{blocked}"
    )

    print()
    print(
        f"MATCH                      : "
        f"{global_counts['MATCH']}"
    )

    print(
        f"NORMALIZABLE_MATCH         : "
        f"{global_counts['NORMALIZABLE_MATCH']}"
    )

    print(
        f"CONFLICT                   : "
        f"{global_counts['CONFLICT']}"
    )

    print(
        f"UNVERIFIABLE               : "
        f"{global_counts['UNVERIFIABLE']}"
    )

    print()
    print(
        "GEMINI AUTHORITATIVE       : False"
    )

    print(
        "PROMOTION ALLOWED          : False"
    )

    print(
        "SOURCE MUTATION            : False"
    )

    print()
    print(
        "=" * 80
    )

    print(
        f"STEP 6 GLOBAL DECISION     : "
        f"{global_decision}"
    )

    print(
        f"STEP 6 CLOSURE STATUS      : "
        f"{closure_status}"
    )

    if global_block_reasons:

        print()
        print(
            "CLOSURE BLOCK REASONS"
        )

        print("-" * 80)

        for reason in sorted(
            global_block_reasons
        ):

            print(
                f"  - {reason}"
            )

    print()
    print(
        f"Combined summary:"
    )

    print(
        str(combined_path)
    )

    print()
    print("=" * 80)
    print(
        "END STEP 6"
    )
    print("=" * 80)

    # -------------------------------------------------------------------------
    # Exit status
    # -------------------------------------------------------------------------

    # Fail closed: a blocked reconciliation is a valid audit result,
    # not a Python execution error. Therefore return 0 after successfully
    # producing the audit.
    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )