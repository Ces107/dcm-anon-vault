"""Core anonymization wrapper for dcm-anon-vault.

Imports from the dcm-anon package when installed.  The dcm-anon package uses a
flat-module layout (modules live at the top level, not inside a namespace package).
Add `dcm-anon>=0.3.1` to pyproject.toml dependencies once published to PyPI.

TODO: after PyPI publish, uncomment the dcm-anon dependency in pyproject.toml.
"""

from __future__ import annotations

import importlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditSummary:
    """Minimal audit summary returned by anonymize_files()."""

    files_processed: int
    files_failed: int
    audit_sha256: str


def anonymize_files(src_paths: list[Path], out_dir: Path) -> AuditSummary:
    """Anonymize a list of DICOM files into *out_dir*.

    Dynamically imports dcm-anon modules at call time so that the vault package
    can be installed and imported without dcm-anon present (import errors are
    deferred to the first actual anonymization request).

    Returns an :class:`AuditSummary` with the tamper-evident audit SHA-256.
    """
    try:
        # dcm-anon uses a flat-module layout; these module names are top-level.
        # TODO: after `pip install dcm-anon>=0.3.1`, these imports resolve automatically.
        _pipeline = importlib.import_module("pipeline")
        _uid_mapper = importlib.import_module("uid_mapper")
        _audit = importlib.import_module("audit")
    except ImportError as exc:
        raise ImportError(
            "dcm-anon is not installed. "
            "Run: pip install dcm-anon>=0.3.1 "
            "(or add it to pyproject.toml dependencies after PyPI publish)."
        ) from exc

    AnonymizationConfig = _pipeline.AnonymizationConfig
    anonymize_file = _pipeline.anonymize_file
    UIDMapper = _uid_mapper.UIDMapper
    audit_sha256 = _audit.audit_sha256

    out_dir.mkdir(parents=True, exist_ok=True)
    mapper = UIDMapper()
    config = AnonymizationConfig()
    records: list[object] = []
    failed = 0

    for src in src_paths:
        dst = out_dir / src.name
        try:
            record = anonymize_file(src, dst, mapper, keep_tags=config.keep_tags)
            records.append(record)
        except Exception:
            failed += 1

    sha: str = audit_sha256(records)
    return AuditSummary(
        files_processed=len(records),
        files_failed=failed,
        audit_sha256=sha,
    )


def anonymize_files_to_zip(src_paths: list[Path]) -> tuple[bytes, AuditSummary]:
    """Anonymize *src_paths* and return the ZIP bytes plus an AuditSummary."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        summary = anonymize_files(src_paths, out_dir)

        zip_base = Path(tmp) / "result"
        shutil.make_archive(str(zip_base), "zip", tmp, "out")
        zip_bytes = (zip_base.with_suffix(".zip")).read_bytes()

    return zip_bytes, summary
