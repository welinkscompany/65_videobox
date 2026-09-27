"""AK 결재함의 대표님 결정을 VideoBox로 되읽어 오는 동기화 (AK W1215-2, 2026-09-28).

## 왜 이게 있나

VideoBox는 제목 후보·대본 확정·업로드 요청을 AK-System 결재함 연결 서버
(127.0.0.1:19680)에 **올리기만** 했다. 대표님이 결재함에서 고르고 누른 결과는
AK 저장소의 레지스트리 파일 세 개(`videobox-*-approval-registry.json`)의 `status`
·`selected_*`·`decided_at`에 남는다. AK 쪽 반영 워커(`apply-videobox-*-founder-
decision.ps1`)의 머리말이 "videobox 가 그 status 를 듣고 있는지는 모른다"고 적은
그대로, 듣는 쪽이 없었다. 이 모듈이 듣는 쪽이다.

## 어떻게 도나

1. AK 데이터 폴더의 `videobox-mcp-connector-config.json`에서 종류별 레지스트리
   파일 이름을 읽는다(파일 이름을 여기 다시 적지 않는다 -- 그쪽이 원본이다).
2. 각 레지스트리를 **읽기만** 한다. AK 파일은 한 바이트도 안 고친다.
3. 결정이 난 항목(`*_selected`/`*_confirmed`/`*_approved`/`*_rejected`)을 VideoBox
   API `POST /api/projects/{id}/founder-approval-decisions`로 보낸다. API가 결정
   번호로 한 번만 반영하므로 몇 번을 돌아도 된다.

레지스트리가 선언한 상태 이름(`allowed_statuses`)이 이 모듈이 아는 이름과 다르면
**멈춘다**(`AkRegistryContractError`). 한쪽만 이름을 바꾸면 결정이 조용히 안
돌아오는 것이 이 연결에서 가장 나쁜 실패이기 때문이다. 모르는 상태를 가진 항목은
건너뛰지 않고 `unrecognised`로 보고한다.

## 어떻게 켜나

호스트에서(컨테이너 안에서는 AK 폴더가 안 보인다):

```
$env:VIDEOBOX_AK_APPROVAL_REGISTRY_DIR = "<AK 저장소>\\docs\\ak-system\\data"
.\\scripts\\sync-ak-founder-decisions.ps1            # 한 번
.\\scripts\\sync-ak-founder-decisions.ps1 -IntervalSeconds 60   # 계속
```

**상시 실행은 아직 없다** -- 예약 작업을 새로 만드는 것은 owner 결정이다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

from videobox_domain_models.founder_approvals import (
    OUTCOME_BY_KIND_AND_STATUS,
    PENDING_STATUS_BY_KIND,
    SELECTION_FIELD_BY_KIND,
)

from .api_client import DEFAULT_API_BASE_URL, VideoBoxApiClient, VideoBoxApiError

CONNECTOR_CONFIG_FILENAME = "videobox-mcp-connector-config.json"
REGISTRY_DIR_ENV = "VIDEOBOX_AK_APPROVAL_REGISTRY_DIR"


class AkRegistryContractError(RuntimeError):
    """AK 레지스트리의 모양·상태 어휘가 이 모듈이 아는 것과 다르다."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise AkRegistryContractError(f"ak_registry_missing: {path.name}") from exc
    if not isinstance(value, dict):
        raise AkRegistryContractError(f"ak_registry_not_an_object: {path.name}")
    return value


def _registry_paths(registry_dir: Path) -> dict[str, Path]:
    config = _read_json(registry_dir / CONNECTOR_CONFIG_FILENAME)
    paths: dict[str, Path] = {}
    for tool in config.get("tools") or []:
        kind = str(tool.get("kind") or "")
        filename = str(tool.get("registry_filename") or "")
        if kind in OUTCOME_BY_KIND_AND_STATUS and filename:
            paths[kind] = registry_dir / filename
    missing = sorted(set(OUTCOME_BY_KIND_AND_STATUS) - set(paths))
    if missing:
        raise AkRegistryContractError(f"ak_connector_config_missing_kinds: {missing}")
    return paths


def _check_status_vocabulary(kind: str, registry: dict[str, Any]) -> None:
    declared = {str(item) for item in registry.get("allowed_statuses") or []}
    expected = {PENDING_STATUS_BY_KIND[kind], *OUTCOME_BY_KIND_AND_STATUS[kind]}
    if declared != expected:
        raise AkRegistryContractError(
            f"ak_registry_status_vocabulary_drift: {kind} declares {sorted(declared)}, "
            f"VideoBox understands {sorted(expected)}"
        )


def _decision_payload(kind: str, entry: dict[str, Any]) -> dict[str, Any]:
    selection_field = SELECTION_FIELD_BY_KIND.get(kind)
    selected_index = entry.get("selected_index")
    return {
        "decision_id": str(entry.get("decision_id") or ""),
        "kind": kind,
        "cycle_id": str(entry.get("cycle_id") or ""),
        "status": str(entry.get("status") or ""),
        "selected_index": int(selected_index) if selected_index is not None else None,
        "selected_text": entry.get(selection_field) if selection_field else None,
        "decided_at": entry.get("decided_at"),
        "decided_via": entry.get("decided_via"),
    }


async def sync_founder_decisions_once(
    client: VideoBoxApiClient, *, registry_dir: Path
) -> dict[str, Any]:
    """결정이 난 항목을 한 번 훑어 반영한다. 결과를 센 요약을 돌려준다."""
    registry_dir = Path(registry_dir)
    summary: dict[str, Any] = {
        "applied": 0,
        "already_applied": 0,
        "pending": 0,
        "unknown_project": 0,
        "unrecognised": [],
        "conflicts": [],
        "rejected_by_videobox": [],
    }
    for kind, path in _registry_paths(registry_dir).items():
        registry = _read_json(path)
        _check_status_vocabulary(kind, registry)
        for entry in registry.get("entries") or []:
            status = str(entry.get("status") or "")
            decision_id = str(entry.get("decision_id") or "")
            if status == PENDING_STATUS_BY_KIND[kind]:
                summary["pending"] += 1
                continue
            if status not in OUTCOME_BY_KIND_AND_STATUS[kind]:
                summary["unrecognised"].append(decision_id)
                continue
            project_id = str(entry.get("project_id") or "")
            try:
                result = await client.apply_founder_approval_decision(
                    project_id=project_id, decision=_decision_payload(kind, entry)
                )
            except VideoBoxApiError as exc:
                if exc.status_code == 404:
                    # 다른 VideoBox(또는 지운 프로젝트)의 결정이다. 여기서 반영할 곳이 없다.
                    summary["unknown_project"] += 1
                elif exc.status_code == 409:
                    summary["conflicts"].append(decision_id)
                else:
                    summary["rejected_by_videobox"].append({"decision_id": decision_id, "status_code": exc.status_code})
                continue
            if result.get("applied"):
                summary["applied"] += 1
            else:
                summary["already_applied"] += 1
    return summary


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AK 결재함의 대표님 결정을 VideoBox로 되읽어 온다.")
    parser.add_argument("--registry-dir", default=os.environ.get(REGISTRY_DIR_ENV, ""))
    parser.add_argument("--api-base-url", default=os.environ.get("VIDEOBOX_API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--interval-seconds", type=float, default=0.0, help="0이면 한 번만 돈다.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.registry_dir:
        print(f"{REGISTRY_DIR_ENV}(또는 --registry-dir)로 AK 레지스트리 폴더를 알려 주세요.", file=sys.stderr)
        return 2
    client = VideoBoxApiClient(base_url=args.api_base_url)
    while True:
        try:
            summary = asyncio.run(sync_founder_decisions_once(client, registry_dir=Path(args.registry_dir)))
            print(json.dumps(summary, ensure_ascii=False))
            failed = bool(summary["conflicts"] or summary["unrecognised"] or summary["rejected_by_videobox"])
        except (AkRegistryContractError, httpx.HTTPError, VideoBoxApiError) as exc:
            print(f"동기화 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
            failed = True
        if args.interval_seconds <= 0:
            return 1 if failed else 0
        import time

        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
