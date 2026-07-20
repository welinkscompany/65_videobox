from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ROOTS = (
    REPO_ROOT / "apps" / "web" / "src",
    REPO_ROOT / "apps" / "web" / "e2e",
    REPO_ROOT / "packages",
    REPO_ROOT / "services",
    REPO_ROOT / "tests",
)
EXCLUDED_PARTS = frozenset({"node_modules", "dist", "__pycache__"})
TEXT_SUFFIXES = frozenset({".py", ".pyi", ".ts", ".tsx", ".js", ".mjs", ".json"})
RETIRED_PROVIDER_TOKEN = "".join(("ge", "mini"))


def test_active_product_source_has_no_retired_provider_vocabulary() -> None:
    violations = [
        path.relative_to(REPO_ROOT).as_posix()
        for root in ACTIVE_ROOTS
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in TEXT_SUFFIXES
        and not EXCLUDED_PARTS.intersection(path.parts)
        # The contract constructs the token it scans for, so exclude only itself.
        and path != Path(__file__)
        and RETIRED_PROVIDER_TOKEN in path.read_text(encoding="utf-8").lower()
    ]

    assert violations == []
