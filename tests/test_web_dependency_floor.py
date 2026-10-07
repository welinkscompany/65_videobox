"""웹 개발 도구의 바닥 버전과 배포 묶음 경계 (2026-10-02, 점검 후속 A1).

`@tailwindcss/vite`가 `dependencies`에 있으면 그 peer인 vite가 배포 묶음으로 잡혀
`npm audit --omit=dev`에 high가 뜬다. vite 5.4.x는 패치로도 advisory 범위를 못 벗어나므로
(owner 결정: 패치 버전만), 배포 묶음에서 빼는 것이 이 경고를 닫는 실제 방법이다.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("-")[0].split("."))


def test_dev_tools_are_patched_and_stay_out_of_the_shipped_tree() -> None:
    manifest = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "apps/web/package-lock.json").read_text(encoding="utf-8"))["packages"]

    assert "@tailwindcss/vite" not in manifest["dependencies"]
    assert "@tailwindcss/vite" in manifest["devDependencies"]
    assert lock["node_modules/@tailwindcss/vite"].get("dev") is True
    assert lock["node_modules/vite"].get("dev") is True

    assert (5, 4, 21) <= _version(lock["node_modules/vite"]["version"]) < (5, 5, 0)
    vitest = lock["node_modules/vitest"]["version"]
    assert (2, 1, 9) <= _version(vitest) < (2, 2, 0)
    # vitest는 자기 짝 패키지와 같은 버전이어야 한다. 하나만 올라가면 실행 중에 깨진다.
    for name in ("@vitest/expect", "@vitest/mocker", "@vitest/runner", "@vitest/snapshot", "@vitest/spy", "@vitest/utils", "vite-node"):
        assert lock[f"node_modules/{name}"]["version"] == vitest, name
