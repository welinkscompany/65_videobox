"""Contract tests for the editor OSS provenance gate.

The PowerShell verifier is intentionally implemented independently.  These
tests exercise both the checked-in contract and small malformed fixtures so a
future source copy cannot silently weaken the metadata rules.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MAP_PATH = ROOT / "docs/oss/editor-ui-source-map.json"
REGISTRY_LOCK_PATH = ROOT / "docs/oss/shadcn-registry-lock.json"
NOTICES_PATH = ROOT / "THIRD_PARTY_NOTICES.md"
VERIFY_SCRIPT = ROOT / "scripts/verify-editor-ui-source-provenance.ps1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
TASK14_PURE_PATHS = (
    "apps/web/src/features/editor/timeline/time-scale.ts",
    "apps/web/src/features/editor/timeline/timeline-geometry.ts",
    "apps/web/src/features/editor/timeline/snapping.ts",
    "apps/web/src/features/editor/timeline/hit-testing.ts",
)
TASK14_PURE_FORBIDDEN_TERMS = (
    "EditorCommandPort",
    "fetch(",
    "axios",
    "document",
    "window",
    "canvas",
)
TASK14_PURE_REACT_IMPORT = re.compile(
    r'''(?:from\s*|import\s*(?:\(\s*)?|require\(\s*)["'](?:react|react-dom)(?:/|["'])''',
    re.IGNORECASE,
)
TASK15_DOCK_PATH = "apps/web/src/features/editor/timeline/TimelineDock.tsx"
TIMELINE_DOCK_FORBIDDEN_TERMS = (
    "EditorCommandPort",
    "fetch(",
    "axios",
    "mutate(",
    "writePreview",
    "canvas",
)
TIMELINE_DOCK_FORBIDDEN_IMPORT = re.compile(
    r'''(?:from\s*|import\s*(?:\(\s*)?|require\(\s*)["'][^"']*(?:api|command)[^"']*["']''',
    re.IGNORECASE,
)

EXPECTED_PINS = {
    "shadcn-admin": "e16c87f213a5ba5e45964e9b67c792105ec74d26",
    "shadcn-ui": "4396d5b2a5ee4e2ad5705e9b2522f92112f811a0",
    "opencut-current": "bab8af831b354a0b5a98a4a6e818ab7d633b94df",
    "opencut-classic": "cf5e79e919144200294fb9fed22a222592a0aeea",
    "opencast-editor": "1208afb64d9de0ab50b321f84f9dd2695780db87",
    "supabase": "1c827c5cbb29cacc6e9052adff2e1659e3cb05fb",
    "pretendard": "5c41199ea0024a9e0b2cb31735265056e5472d76",
}
EXPECTED_PIN_POLICY = {
    "shadcn-admin": ("satnaing/shadcn-admin", "partial-port", "MIT", "https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/LICENSE"),
    "shadcn-ui": ("shadcn-ui/ui", "locked-source", "MIT", "https://github.com/shadcn-ui/ui/blob/4396d5b2a5ee4e2ad5705e9b2522f92112f811a0/LICENSE.md"),
    "opencut-current": ("OpenCut-app/OpenCut", "rejected-runtime", "AGPL-3.0-or-later", "https://github.com/OpenCut-app/OpenCut/blob/bab8af831b354a0b5a98a4a6e818ab7d633b94df/LICENSE"),
    "opencut-classic": ("OpenCut-app/opencut-classic", "partial-port", "MIT", "https://github.com/OpenCut-app/opencut-classic/blob/cf5e79e919144200294fb9fed22a222592a0aeea/LICENSE"),
    "opencast-editor": ("opencast/editor", "partial-port", "Apache-2.0", "https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/LICENSE"),
    "supabase": ("supabase/supabase", "reference-only", "Apache-2.0", "https://github.com/supabase/supabase/blob/1c827c5cbb29cacc6e9052adff2e1659e3cb05fb/LICENSE"),
    "pretendard": ("orioncactus/pretendard", "locked-binary", "SIL OFL-1.1", "https://github.com/orioncactus/pretendard/blob/5c41199ea0024a9e0b2cb31735265056e5472d76/LICENSE.txt"),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_task11_workbench_is_reference_only_and_has_no_runtime_imports():
    source_map = read_json(SOURCE_MAP_PATH)
    decisions = source_map["reference_only_decisions"]
    decision = next(item for item in decisions if item["task"] == "Task 11 editor workbench")
    assert decision["source_pin"] == "opencut-classic"
    assert decision["materialized_paths"] == []
    assert decision["forbidden_import_terms"] == ["EditorCore", "next/", "database", "renderer"]
    for relative in decision["local_paths"]:
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "Source-preservation header:" not in content
        assert not any(term.lower() in content.lower() for term in decision["forbidden_import_terms"])


def test_task14_timeline_math_is_reference_only():
    source_map = read_json(SOURCE_MAP_PATH)
    decisions = source_map["reference_only_decisions"]
    decision = next(item for item in decisions if item["task"] == "Task 14 timeline geometry")
    assert decision == {
        "task": "Task 14 timeline geometry",
        "source_pin": "opencut-classic",
        "reference": "classic pure timeline math inspected; independent TypeScript implementation only",
        "materialized_paths": [],
        "local_paths": [
            "apps/web/src/features/editor/timeline/time-scale.ts",
            "apps/web/src/features/editor/timeline/timeline-geometry.ts",
            "apps/web/src/features/editor/timeline/snapping.ts",
            "apps/web/src/features/editor/timeline/hit-testing.ts",
        ],
        "inspected_upstream_paths": [
            {"path": "apps/web/src/fps/utils.ts", "sha256": "b3d091725124abe21b348d34cb15643200fb8e650cbb2fab3ce16fb68c6dac28"},
            {"path": "apps/web/src/timeline/pixel-utils.ts", "sha256": "373bcd4b0d9fd88da7cffb05bd3ea3368c8aabcb13f275147cfceb59e70eaef0"},
            {"path": "apps/web/src/timeline/snapping/build.ts", "sha256": "7cf9b8dc203a691af38e99d16ceb401cb881055b93244f9f6afa65338ef46e1a"},
            {"path": "apps/web/src/timeline/snapping/resolve.ts", "sha256": "73f7865940cd914b09070ca3daa03325b03a31bd33ebb6766dc0975736c6fc0d"},
            {"path": "apps/web/src/timeline/snapping/threshold.ts", "sha256": "951ed0604bcd5960384a520a14cf66f554c2580f4e0098e0307939db73ced686"},
            {"path": "apps/web/src/timeline/zoom-utils.ts", "sha256": "00d105f58146956d915b4614ee1796a73513ff786bed90dd07d1245ee2fb84b6"},
        ],
        "forbidden_import_terms": [
            "EditorCore", "next/", "database", "renderer", "IndexedDB", "OPFS",
            "browser-export", "EditorCommandPort", "document", "window", "canvas",
        ],
    }
    for relative in decision["local_paths"]:
        path = ROOT / relative
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            assert "Source-preservation header:" not in content
            assert not any(term.lower() in content.lower() for term in decision["forbidden_import_terms"])


def test_task16_timeline_dock_keeps_local_pointer_drafts_and_task14_stays_pure() -> None:
    for relative in TASK14_PURE_PATHS:
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert not any(term.lower() in content.lower() for term in TASK14_PURE_FORBIDDEN_TERMS)
        assert TASK14_PURE_REACT_IMPORT.search(content) is None

    dock = (ROOT / TASK15_DOCK_PATH).read_text(encoding="utf-8")
    assert "onPointer" in dock
    assert not any(term.lower() in dock.lower() for term in TIMELINE_DOCK_FORBIDDEN_TERMS)
    assert TIMELINE_DOCK_FORBIDDEN_IMPORT.search(dock) is None


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def verifier_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    for relative in ("docs/oss", "scripts", "apps/web"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for relative in (
        "docs/oss/editor-ui-source-map.json",
        "docs/oss/shadcn-registry-lock.json",
        "scripts/verify-editor-ui-source-provenance.ps1",
        "apps/web/package.json",
        "apps/web/package-lock.json",
        "THIRD_PARTY_NOTICES.md",
    ):
        source, destination = ROOT / relative, root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return temp, root


def run_verifier(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "scripts/verify-editor-ui-source-provenance.ps1")],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def verifier_fixture_with_production_sources() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp, root = verifier_fixture()
    shutil.copytree(ROOT / "apps/web/src", root / "apps/web/src")
    return temp, root


def test_independent_verifier_requires_exact_task14_reference_decision() -> None:
    temp, root = verifier_fixture_with_production_sources()
    try:
        assert run_verifier(root).returncode == 0
        source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
        source_map["reference_only_decisions"] = [
            item for item in source_map["reference_only_decisions"]
            if item["task"] != "Task 14 timeline geometry"
        ]
        write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()

    for field, value in (
        ("path", "apps/web/src/timeline/tampered.ts"),
        ("sha256", "0" * 64),
    ):
        temp, root = verifier_fixture_with_production_sources()
        try:
            assert run_verifier(root).returncode == 0
            source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
            task14 = next(
                item for item in source_map["reference_only_decisions"]
                if item["task"] == "Task 14 timeline geometry"
            )
            task14["inspected_upstream_paths"][0][field] = value
            write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
            assert run_verifier(root).returncode != 0
        finally:
            temp.cleanup()


def test_independent_verifier_rejects_task14_impurity_and_task16_direct_runtime() -> None:
    for relative, forbidden_source in (
        (TASK14_PURE_PATHS[0], 'import { useMemo } from "react";\n'),
        (TASK14_PURE_PATHS[0], 'import "react";\n'),
        (TASK15_DOCK_PATH, 'import { EditorCommandPort } from "../EditorCommandPort";\n'),
        (TASK15_DOCK_PATH, 'import { client } from "../api/editor";\n'),
        (TASK15_DOCK_PATH, 'import "../api/editor";\n'),
        (TASK15_DOCK_PATH, "void fetch('/api/editor/mutate');\n"),
        (TASK15_DOCK_PATH, "void mutate();\n"),
        (TASK15_DOCK_PATH, "const writePreview = () => undefined;\n"),
        (TASK15_DOCK_PATH, "const canvas = document.createElement('canvas');\n"),
    ):
        temp, root = verifier_fixture_with_production_sources()
        try:
            target = root / relative
            target.write_text(target.read_text(encoding="utf-8") + forbidden_source, encoding="utf-8")
            result = run_verifier(root)
            assert result.returncode != 0, result.stdout + result.stderr
        finally:
            temp.cleanup()


def test_independent_verifier_only_task14_allows_absent_local_paths() -> None:
    temp, root = verifier_fixture_with_production_sources()
    try:
        assert run_verifier(root).returncode == 0
        source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
        task14 = next(
            item for item in source_map["reference_only_decisions"]
            if item["task"] == "Task 14 timeline geometry"
        )
        for relative in task14["local_paths"]:
            (root / relative).unlink(missing_ok=True)
        assert run_verifier(root).returncode == 0

        task11 = next(
            item for item in source_map["reference_only_decisions"]
            if item["task"] == "Task 11 editor workbench"
        )
        task11_path = root / task11["local_paths"][0]
        assert task11_path.is_file()
        task11_path.unlink()
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()


def test_independent_verifier_requires_exact_task11_forbidden_terms() -> None:
    for forbidden_terms in ([], ["EditorCore", "next/", "database", "wrong-term"]):
        temp, root = verifier_fixture_with_production_sources()
        try:
            assert run_verifier(root).returncode == 0
            source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
            task11 = next(
                item for item in source_map["reference_only_decisions"]
                if item["task"] == "Task 11 editor workbench"
            )
            task11["forbidden_import_terms"] = forbidden_terms
            write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
            assert run_verifier(root).returncode != 0
        finally:
            temp.cleanup()


def materialized_fixture(root: Path) -> dict:
    source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
    materialized = root / "apps/web/src/editor/geometry.ts"
    materialized.parent.mkdir(parents=True, exist_ok=True)
    materialized.write_text("export const snap = 1;\n", encoding="utf-8")
    test_path = root / "apps/web/src/editor/geometry.test.ts"
    test_path.write_text("export {};\n", encoding="utf-8")
    digest = hashlib.sha256(materialized.read_bytes()).hexdigest()
    source_map["materialized_files"] = [{
        "source_pin": "opencut-classic",
        "upstream_path": "src/editor/geometry.ts",
        "upstream_sha256": "a" * 64,
        "path": "apps/web/src/editor/geometry.ts",
        "normalized_sha256": digest,
        "test_path": "apps/web/src/editor/geometry.test.ts",
    }]
    write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
    return source_map


def validate_source_map(source_map: dict, root: Path) -> list[str]:
    """Return contract violations for a source-map fixture."""
    errors: list[str] = []
    pins = source_map.get("source_pins")
    if not isinstance(pins, list) or len(pins) != 7:
        return ["source_pins must contain exactly seven immutable pins"]
    seen: set[str] = set()
    for pin in pins:
        name = pin.get("name")
        seen.add(name)
        for field in ("repository", "commit", "license", "license_url", "notice_url", "decision"):
            if not pin.get(field):
                errors.append(f"{name}: missing {field}")
        if not COMMIT.fullmatch(str(pin.get("commit", ""))):
            errors.append(f"{name}: commit must be 40 lowercase hex characters")
        expected = EXPECTED_PIN_POLICY.get(name)
        if expected and (pin.get("repository"), pin.get("decision"), pin.get("license"), pin.get("license_url")) != expected:
            errors.append(f"{name}: immutable source policy drift")
        for upstream in pin.get("upstream_paths", []):
            if not upstream.get("path") or not SHA256.fullmatch(str(upstream.get("sha256", ""))):
                errors.append(f"{name}: upstream path and SHA256 are required")
        # A source pin may be metadata-only.  Raw upstream hashes become
        # mandatory only when a local or generated artifact exists.
        local_paths = pin.get("local_paths", [])
        if pin.get("decision") in {"reference-only", "rejected-runtime"} and local_paths:
            errors.append(f"{name}: {pin['decision']} pin cannot materialize local paths")
        for local in local_paths:
            path = local.get("path", "")
            if not path or Path(path).is_absolute() or ".." in Path(path).parts:
                errors.append(f"{name}: local path must be repository-relative")
            if not SHA256.fullmatch(str(local.get("sha256", ""))) or not local.get("test_path"):
                errors.append(f"{name}: local SHA256 and test_path are required")
            if not (root / path).is_file():
                errors.append(f"{name}: declared local path is absent")
        if name == "pretendard":
            expected_font = {
                "path": "apps/web/src/assets/fonts/PretendardVariable.woff2",
                "sha256": "9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4",
                "test_path": "apps/web/src/ui-system.test.tsx",
            }
            if pin.get("materialized") is not True or local_paths != [expected_font]:
                errors.append("pretendard: exact reviewed OFL binary materialization is required")
    if seen != set(EXPECTED_PINS):
        errors.append("immutable source pins do not match the approved set")
    known_pins = set(EXPECTED_PINS)
    pin_by_name = {pin["name"]: pin for pin in pins}
    for entry in [*source_map.get("materialized_files", []), *source_map.get("generated_items", [])]:
        for field in ("source_pin", "upstream_path", "upstream_sha256", "path", "normalized_sha256", "test_path"):
            if not entry.get(field):
                errors.append(f"materialized/generated file missing {field}")
        if entry.get("source_pin") not in known_pins:
            errors.append("materialized/generated file has an unknown source pin")
        source_pin = pin_by_name.get(entry.get("source_pin"), {})
        if source_pin.get("decision") in {"reference-only", "rejected-runtime"}:
            errors.append("materialized/generated file uses a non-materializable source pin")
        for field in ("upstream_sha256", "normalized_sha256"):
            if entry.get(field) and not SHA256.fullmatch(str(entry[field])):
                errors.append(f"materialized/generated file has invalid {field}")
        for field in ("path", "test_path"):
            value = entry.get(field, "")
            if value and (Path(value).is_absolute() or ".." in Path(value).parts):
                errors.append(f"materialized/generated file has unsafe {field}")
            elif value and not (root / value).is_file():
                errors.append(f"materialized/generated file {field} is absent")
        path = entry.get("path")
        if path and (root / path).is_file() and entry.get("normalized_sha256"):
            actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
            if actual != entry["normalized_sha256"]:
                errors.append("materialized/generated file normalized hash drift")
    for entry in source_map.get("apache_adaptations", []):
        for field in ("source_pin", "change_summary", "license_url", "notice_url", "attribution"):
            if not entry.get(field):
                errors.append(f"Apache adaptation missing {field}")
    for entry in [*source_map.get("materialized_files", []), *source_map.get("generated_items", [])]:
        source_pin = pin_by_name.get(entry.get("source_pin"), {})
        if source_pin.get("license") == "Apache-2.0":
            matched = [item for item in source_map.get("apache_adaptations", []) if item.get("source_pin") == entry.get("source_pin") and item.get("path") == entry.get("path")]
            if len(matched) != 1:
                errors.append("Apache materialized file requires exactly one matching attribution")
            elif any(matched[0].get(field) != source_pin.get(field) for field in ("license_url", "notice_url")):
                errors.append("Apache materialized file must link its direct upstream notices")
    return errors


def validate_registry_lock(lock: dict) -> list[str]:
    errors: list[str] = []
    for field in ("repository", "commit", "generated_items", "dependency_mapping"):
        if field not in lock:
            errors.append(f"missing {field}")
    if lock.get("repository") != "shadcn-ui/ui" or lock.get("commit") != EXPECTED_PINS["shadcn-ui"]:
        errors.append("registry must be tied to the pinned shadcn/ui repository and commit")
    if not isinstance(lock.get("generated_items"), list) or not isinstance(lock.get("dependency_mapping"), dict):
        errors.append("registry shape is invalid")
    for item in lock.get("generated_items", []):
        for field in ("name", "upstream_path", "upstream_sha256", "generated_path", "normalized_sha256", "test_path", "runtime_dependencies"):
            if not item.get(field):
                errors.append(f"generated item missing {field}")
        if not SHA256.fullmatch(str(item.get("upstream_sha256", ""))) or not SHA256.fullmatch(str(item.get("normalized_sha256", ""))):
            errors.append("generated item hash is invalid")
        for dependency in item.get("runtime_dependencies", []):
            mapping = lock.get("dependency_mapping", {}).get(dependency)
            if not isinstance(mapping, dict) or not all(mapping.get(k) for k in ("version", "license", "package_lock_entry")):
                errors.append(f"runtime dependency {dependency} lacks exact package-lock mapping")
    return errors


def test_checked_in_provenance_contract_has_all_immutable_pins_and_task4_materialization() -> None:
    source_map = read_json(SOURCE_MAP_PATH)
    assert not validate_source_map(source_map, ROOT)
    pins = {pin["name"]: pin for pin in source_map["source_pins"]}
    assert {name: pins[name]["commit"] for name in EXPECTED_PINS} == EXPECTED_PINS
    pretendard = pins["pretendard"]
    assert pretendard["upstream_paths"] == [{
        "path": "packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2",
        "sha256": "9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4",
    }]
    assert pretendard["materialized"] is True
    assert (pretendard["repository"], pretendard["decision"], pretendard["license"], pretendard["license_url"]) == EXPECTED_PIN_POLICY["pretendard"]


def test_task4_requires_the_pinned_pretendard_binary_to_be_materialized_with_its_raw_sha() -> None:
    """Task 4 must copy the reviewed OFL font, not merely permit a future copy."""
    source_map = read_json(SOURCE_MAP_PATH)
    pretendard = next(pin for pin in source_map["source_pins"] if pin["name"] == "pretendard")
    assert pretendard["materialized"] is True
    assert pretendard["local_paths"] == [{
        "path": "apps/web/src/assets/fonts/PretendardVariable.woff2",
        "sha256": "9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4",
        "test_path": "apps/web/src/ui-system.test.tsx",
    }]


def test_source_map_rejects_missing_fields_and_forbidden_reference_copy() -> None:
    source_map = read_json(SOURCE_MAP_PATH)
    fixture = json.loads(json.dumps(source_map))
    fixture["source_pins"][0]["commit"] = "short"
    fixture["source_pins"][0]["license_url"] = ""
    fixture["source_pins"][5]["local_paths"] = [{"path": "apps/web/src/copied.ts", "sha256": "0" * 64, "test_path": "tests/x.py"}]
    errors = validate_source_map(fixture, ROOT)
    assert any("commit" in error for error in errors)
    assert any("missing license_url" in error for error in errors)
    assert any("reference-only pin cannot materialize" in error for error in errors)


def test_source_map_rejects_incomplete_materialized_and_apache_adaptation_entries() -> None:
    source_map = read_json(SOURCE_MAP_PATH)
    fixture = json.loads(json.dumps(source_map))
    fixture["source_pins"][3]["local_paths"] = [{"path": "apps/web/src/editor/math.ts"}]
    fixture["materialized_files"] = [{"source_pin": "opencast-editor", "path": "apps/web/src/editor/cues.ts", "sha256": "0" * 64}]
    fixture["apache_adaptations"] = [{"source_pin": "opencast-editor"}]
    errors = validate_source_map(fixture, ROOT)
    assert any("local SHA256 and test_path" in error for error in errors)
    assert any("materialized/generated file missing upstream_path" in error for error in errors)
    assert any("Apache adaptation missing change_summary" in error for error in errors)


def test_registry_lock_rejects_incomplete_generated_item_and_hash_drift() -> None:
    lock = read_json(REGISTRY_LOCK_PATH)
    assert not validate_registry_lock(lock)
    fixture = json.loads(json.dumps(lock))
    fixture["generated_items"] = [{
        "name": "button", "upstream_path": "apps/v4/registry/new-york-v4/ui/button.tsx",
        "upstream_sha256": "0" * 64, "generated_path": "apps/web/src/components/ui/button.tsx",
        "normalized_sha256": "f" * 64, "test_path": "apps/web/src/components/ui/button.test.tsx",
        "runtime_dependencies": ["@radix-ui/react-slot"],
    }]
    errors = validate_registry_lock(fixture)
    assert any("package-lock mapping" in error for error in errors)
    fixture["dependency_mapping"] = {"@radix-ui/react-slot": {"version": "1.2.3", "license": "MIT", "package_lock_entry": "node_modules/@radix-ui/react-slot"}}
    assert not validate_registry_lock(fixture)
    fixture["generated_items"][0]["normalized_sha256"] = "not-a-hash"
    assert any("hash is invalid" in error for error in validate_registry_lock(fixture))


def test_notices_and_independent_powershell_verifier_enforce_the_checked_in_gate() -> None:
    notices = NOTICES_PATH.read_text(encoding="utf-8")
    assert "No Apache-2.0 source is materialized" in notices
    assert "change summary" in notices
    assert "live npx" in notices.lower()
    assert "SIL OFL-1.1" in notices
    assert EXPECTED_PIN_POLICY["pretendard"][3] in notices
    result = run_verifier(ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_independent_verifier_rejects_missing_required_materialization_fields() -> None:
    for field in ("commit", "license_url"):
        temp, root = verifier_fixture()
        try:
            source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
            source_map["source_pins"][0].pop(field)
            write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
            assert run_verifier(root).returncode != 0
        finally:
            temp.cleanup()
    for field in ("upstream_path", "upstream_sha256", "path", "normalized_sha256", "test_path"):
        temp, root = verifier_fixture()
        try:
            source_map = materialized_fixture(root)
            source_map["materialized_files"][0].pop(field)
            write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
            assert run_verifier(root).returncode != 0
        finally:
            temp.cleanup()


def test_independent_verifier_rejects_reference_copy_missing_notices_and_runtime_import() -> None:
    temp, root = verifier_fixture()
    try:
        source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
        source_map["source_pins"][5]["local_paths"] = [{"path": "apps/web/src/copied.ts"}]
        write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()
    temp, root = verifier_fixture()
    try:
        (root / "THIRD_PARTY_NOTICES.md").unlink()
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()
    temp, root = verifier_fixture()
    try:
        runtime = root / "apps/web/src/runtime.ts"
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text('import "opencut";\n', encoding="utf-8")
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()


def test_independent_verifier_rejects_real_generated_content_and_package_lock_drift() -> None:
    temp, root = verifier_fixture()
    try:
        source_map = materialized_fixture(root)
        source_map["generated_items"] = [source_map["materialized_files"][0].copy()]
        source_map["generated_items"][0]["path"] = "apps/web/src/editor/generated.ts"
        generated = root / source_map["generated_items"][0]["path"]
        generated.write_text("export const generated = true;\n", encoding="utf-8")
        source_map["generated_items"][0]["normalized_sha256"] = hashlib.sha256(generated.read_bytes()).hexdigest()
        write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
        lock = read_json(root / "docs/oss/shadcn-registry-lock.json")
        lock["generated_items"] = [{
            "name": "button", "upstream_path": "apps/v4/registry/new-york-v4/ui/button.tsx",
            "upstream_sha256": "b" * 64, "generated_path": source_map["generated_items"][0]["path"],
            "normalized_sha256": source_map["generated_items"][0]["normalized_sha256"],
            "test_path": source_map["generated_items"][0]["test_path"], "runtime_dependencies": ["react"],
        }]
        lock["dependency_mapping"] = {"react": {"version": "0.0.0", "license": "MIT", "package_lock_entry": "node_modules/react"}}
        write_json(root / "docs/oss/shadcn-registry-lock.json", lock)
        generated.write_text("export const generated = false;\n", encoding="utf-8")
        assert run_verifier(root).returncode != 0
        generated.write_text("export const generated = true;\n", encoding="utf-8")
        assert run_verifier(root).returncode != 0  # package-lock resolved version drift
    finally:
        temp.cleanup()


def test_independent_verifier_requires_existing_test_path_and_parsed_package_lock() -> None:
    temp, root = verifier_fixture()
    try:
        source_map = materialized_fixture(root)
        (root / source_map["materialized_files"][0]["test_path"]).unlink()
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()


def test_independent_verifier_rejects_immutable_policy_and_pretendard_contract_drift() -> None:
    temp, root = verifier_fixture()
    try:
        source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
        source_map["source_pins"][2]["decision"] = "partial-port"
        write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()


def test_independent_verifier_rejects_artifact_policy_bypass_and_apache_without_attribution() -> None:
    for pin_name in ("supabase", "opencut-current"):
        temp, root = verifier_fixture()
        try:
            source_map = materialized_fixture(root)
            source_map["materialized_files"][0]["source_pin"] = pin_name
            write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
            assert run_verifier(root).returncode != 0
        finally:
            temp.cleanup()
    temp, root = verifier_fixture()
    try:
        source_map = materialized_fixture(root)
        source_map["materialized_files"][0]["source_pin"] = "opencast-editor"
        write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()


def test_independent_verifier_rejects_apache_local_path_without_attribution() -> None:
    temp, root = verifier_fixture()
    try:
        source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
        local = root / "apps/web/src/editor/opencast.ts"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("export const cue = true;\n", encoding="utf-8")
        test_path = root / "apps/web/src/editor/opencast.test.ts"
        test_path.write_text("export {};\n", encoding="utf-8")
        source_map["source_pins"][4]["local_paths"] = [{
            "source_pin": "opencast-editor", "path": "apps/web/src/editor/opencast.ts",
            "sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
            "test_path": "apps/web/src/editor/opencast.test.ts",
        }]
        write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()


def test_independent_verifier_rejects_supabase_runtime_and_declared_dependency_references() -> None:
    for content in ('import "@supabase/supabase-js";\n', 'const x = require("@supabase/supabase-js");\n', 'const lazy = import("supabase");\n', 'const url = "https://cdn.example/supabase";\n'):
        temp, root = verifier_fixture()
        try:
            runtime = root / "apps/web/src/runtime.ts"
            runtime.parent.mkdir(parents=True, exist_ok=True)
            runtime.write_text(content, encoding="utf-8")
            assert run_verifier(root).returncode != 0
        finally:
            temp.cleanup()
    temp, root = verifier_fixture()
    try:
        package = read_json(root / "apps/web/package.json")
        package.setdefault("dependencies", {})["@supabase/supabase-js"] = "2.0.0"
        write_json(root / "apps/web/package.json", package)
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()
    temp, root = verifier_fixture()
    try:
        package_lock = read_json(root / "apps/web/package-lock.json")
        package_lock["packages"]["node_modules/@supabase/supabase-js"] = {"version": "2.0.0"}
        write_json(root / "apps/web/package-lock.json", package_lock)
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()
    temp, root = verifier_fixture()
    try:
        source_map = read_json(root / "docs/oss/editor-ui-source-map.json")
        pretendard = source_map["source_pins"][6]
        pretendard["release"] = "v1.3.8"
        pretendard["license"] = "MIT"
        pretendard["materialized"] = True
        write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()
    temp, root = verifier_fixture()
    try:
        source_map = materialized_fixture(root)
        generated_path = "apps/web/src/editor/generated.ts"
        generated = root / generated_path
        generated.write_text("export const generated = true;\n", encoding="utf-8")
        digest = hashlib.sha256(generated.read_bytes()).hexdigest()
        source_map["generated_items"] = [{
            "source_pin": "shadcn-ui", "upstream_path": "apps/v4/registry/new-york-v4/ui/button.tsx",
            "upstream_sha256": "b" * 64, "path": generated_path, "normalized_sha256": digest,
            "test_path": source_map["materialized_files"][0]["test_path"],
        }]
        write_json(root / "docs/oss/editor-ui-source-map.json", source_map)
        package_lock = read_json(root / "apps/web/package-lock.json")
        react = package_lock["packages"]["node_modules/react"]
        lock = read_json(root / "docs/oss/shadcn-registry-lock.json")
        lock["generated_items"] = [{
            "name": "button", "upstream_path": "apps/v4/registry/new-york-v4/ui/button.tsx",
            "upstream_sha256": "b" * 64, "generated_path": generated_path, "normalized_sha256": digest,
            "test_path": source_map["materialized_files"][0]["test_path"], "runtime_dependencies": ["react"],
        }]
        lock["dependency_mapping"] = {"react": {"version": react["version"], "license": "MIT", "package_lock_entry": "node_modules/react"}}
        write_json(root / "docs/oss/shadcn-registry-lock.json", lock)
        (root / "apps/web/package-lock.json").write_text('{"packages":{"node_modules/react":{"version":"' + react["version"] + '"}}} trailing', encoding="utf-8")
        assert run_verifier(root).returncode != 0
    finally:
        temp.cleanup()
