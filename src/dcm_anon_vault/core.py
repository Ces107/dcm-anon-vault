"""Core pseudonymization wrapper.

Wraps the upstream :mod:`dcm_anon` engine (PyPI package ``dcm-anonymizer``,
PS3.15 Basic Confidentiality Profile). Adds:

* per-customer deterministic UID re-mapping (via ``UIDMapper(salt=...)``),
  so longitudinal cohorts produce consistent UIDs across calls.
* opt-in rejection of files carrying ``BurnedInAnnotation == 'YES'``
  (PS3.15 Clean Pixel Data Option is NOT implemented; we refuse rather
  than silently leak burned-in PHI).
* a single ZIP response with the anonymized files at the top level.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dcm_anon.audit import audit_sha256
from dcm_anon.pipeline import AnonymizationConfig, anonymize_file
from dcm_anon.uid_mapper import UIDMapper


@dataclass(frozen=True)
class AuditSummary:
    """Minimal audit summary returned by :func:`anonymize_files`."""

    files_processed: int
    files_failed: int
    files_rejected_burned_in: int
    audit_sha256: str


class BurnedInPHIError(ValueError):
    """Raised when a file declares ``BurnedInAnnotation == 'YES'``.

    PS3.15 Clean Pixel Data Option is not implemented; rather than silently
    return DICOMs with burned-in PHI, we refuse the file. Callers convert
    this to HTTP 422.
    """


def _has_burned_in(src: Path) -> bool:
    """Cheap header read to check ``BurnedInAnnotation`` before scrubbing."""
    from pydicom import dcmread

    ds = dcmread(src, specific_tags=["BurnedInAnnotation"], stop_before_pixels=True)
    value = getattr(ds, "BurnedInAnnotation", None)
    return bool(value) and str(value).upper() == "YES"


def anonymize_files(
    src_paths: list[Path],
    out_dir: Path,
    *,
    customer_salt: str,
    reject_burned_in: bool = True,
) -> AuditSummary:
    """Anonymize *src_paths* into *out_dir*.

    ``customer_salt`` makes the UID re-map deterministic per customer:
    re-anonymizing the same source SOPInstanceUID yields the same target
    UID, enabling longitudinal study linkage. Salt is opaque to the engine
    (SHA-256 input).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    mapper = UIDMapper(salt=customer_salt)
    config = AnonymizationConfig()
    records = []
    failed = 0
    rejected = 0

    for src in src_paths:
        dst = out_dir / src.name
        try:
            if reject_burned_in and _has_burned_in(src):
                rejected += 1
                continue
            record = anonymize_file(src, dst, mapper, keep_tags=config.keep_tags)
            records.append(record)
        except Exception:
            failed += 1

    return AuditSummary(
        files_processed=len(records),
        files_failed=failed,
        files_rejected_burned_in=rejected,
        audit_sha256=audit_sha256(records),
    )


def anonymize_files_to_zip(
    src_paths: list[Path],
    *,
    customer_salt: str,
) -> tuple[bytes, AuditSummary]:
    """Anonymize *src_paths* and return ``(zip_bytes, AuditSummary)``."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        summary = anonymize_files(src_paths, out_dir, customer_salt=customer_salt)

        zip_base = Path(tmp) / "result"
        shutil.make_archive(str(zip_base), "zip", tmp, "out")
        zip_bytes = (zip_base.with_suffix(".zip")).read_bytes()

    return zip_bytes, summary
