"""Generate a demo DICOM file with populated PHI tags.

Reads pydicom's bundled CT_small.dcm, overwrites the patient-identifying
tags with explicitly fake but recognisable PHI (so the demo output makes
the scrubbing obvious), and writes the result to the requested path.

Usage::

    python scripts/make_demo_dicom.py demo/sample_with_phi.dcm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pydicom
from pydicom.data import get_testdata_file


def build_demo_dicom(out_path: Path) -> None:
    source = get_testdata_file("CT_small.dcm")
    if source is None:
        raise SystemExit("pydicom test data not available; pip install pydicom")
    ds = pydicom.dcmread(source)
    ds.PatientName = "DEMO^Jane"
    ds.PatientID = "DEMO-PATIENT-001"
    ds.PatientBirthDate = "19800101"
    ds.PatientSex = "F"
    ds.ReferringPhysicianName = "SMITH^John"
    ds.InstitutionName = "Demo Hospital Madrid"
    ds.StudyDescription = "Demo abdominal CT for dcm-anon-vault docs"
    ds.AccessionNumber = "ACC-2026-0001"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(out_path, enforce_file_format=True)
    print(f"Wrote demo DICOM to {out_path}")
    print(f"  PatientName       : {ds.PatientName}")
    print(f"  PatientID         : {ds.PatientID}")
    print(f"  PatientBirthDate  : {ds.PatientBirthDate}")
    print(f"  ReferringPhysician: {ds.ReferringPhysicianName}")
    print(f"  Institution       : {ds.InstitutionName}")
    print(f"  StudyInstanceUID  : {ds.StudyInstanceUID}")
    print(f"  SOPInstanceUID    : {ds.SOPInstanceUID}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Destination DICOM path")
    args = parser.parse_args(argv)
    build_demo_dicom(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
