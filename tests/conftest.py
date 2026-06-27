from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_PATHS = [
    ROOT / "services" / "api" / "src",
    ROOT / "packages" / "domain-models" / "src",
    ROOT / "packages" / "storage-abstractions" / "src",
    ROOT / "packages" / "provider-interfaces" / "src",
    ROOT / "packages" / "timeline-schema" / "src",
    ROOT / "packages" / "core-engine" / "src",
    ROOT / "packages" / "capcut-export" / "src",
]

for src_path in SRC_PATHS:
    sys.path.insert(0, str(src_path))
