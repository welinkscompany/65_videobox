from __future__ import annotations

from hashlib import sha256
from json import loads
from pathlib import Path
from sys import argv, exit


root = Path(__file__).parent
manifest = loads((root / "manifest.json").read_text(encoding="utf-8"))
for filename, expected_digest in manifest["assets"].items():
    actual_digest = sha256((root / filename).read_bytes()).hexdigest()
    if actual_digest != expected_digest:
        exit(f"VideoBox Yujin asset hash mismatch: {filename}")

if argv[1:] == ["--target", "/opt/data"]:
    for filename in ("SOUL.md", "AGENTS.md", "mem0.json"):
        expected_digest = manifest["assets"][filename]
        actual_digest = sha256((Path("/opt/data") / filename).read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            exit(f"VideoBox Yujin applied asset hash mismatch: {filename}")
elif argv[1:]:
    exit("usage: verify_assets.py [--target /opt/data]")
