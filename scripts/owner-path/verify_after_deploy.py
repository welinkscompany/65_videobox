"""배포 뒤 실제로 밟아 보는 확인. 초록 하나가 아니라 자리마다 무엇을 봤는지 적는다.

자동 검사가 초록인 것을 근거로 쓰지 않는다 -- 이 저장소가 가장 비싸게 배운 것이다.
여기서 재는 것은 전부 **도는 컨테이너**에 대고 묻는 것이다.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from drive import BASE, call

PROJECT = "project-318cc020"
SESSION = "editing_session_draft_315088e76623"
results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str) -> None:
    results.append((label, passed, detail))
    print(f"{'  ' if passed else '!!'} {label}: {detail}")
    sys.stdout.flush()


def health() -> None:
    code, body = call("GET", "/health")
    check("컨테이너가 떠 있는가", code == 200 and body.get("status") == "ok", f"{code} {body}")


def upload_ceiling() -> None:
    """1MB 벽. 앱이 아니라 그 앞의 프록시가 자르던 자리다."""
    from upload_probe import measure

    passed, detail = measure(BASE, PROJECT)
    check("큰 영상이 업로드되는가", passed, detail)


def failure_reason_reaches_the_screen() -> None:
    code, jobs = call("GET", f"/api/projects/{PROJECT}/jobs")
    items = jobs if isinstance(jobs, list) else next((v for v in jobs.values() if isinstance(v, list)), [])
    failed = [j for j in items if j.get("job_type") == "final_render" and j.get("status") == "failed"]
    if not failed:
        check("완성본 실패 이유가 화면까지 가는가", False, "실패한 렌더가 없어 못 쟀다")
        return
    code, body = call("GET", f"/api/projects/{PROJECT}/final-renders/{failed[-1]['job_id']}")
    reason = body.get("error_message")
    check("완성본 실패 이유가 화면까지 가는가", bool(reason), f"{reason!r}")


def memory_round_trip() -> None:
    """저장하고, **다른 대화에서** 꺼내 쓰는지까지."""
    code, first = call("POST", f"/api/projects/{PROJECT}/director/conversations", {"session_id": SESSION})
    if code != 201:
        check("기억 저장", False, f"대화를 못 열었다: {code} {first}")
        return
    conversation = first["conversation_id"]
    code, exchange = call(
        "POST", f"/api/projects/{PROJECT}/director/conversations/{conversation}/messages",
        {"session_id": SESSION, "client_message_id": "msg-" + uuid.uuid4().hex[:12],
         "text": "배경 음악은 항상 작게 깔아 줘. 목소리를 덮으면 안 돼."}, timeout=300.0)
    message_id = ((exchange or {}).get("user_message") or {}).get("message_id")
    if not message_id:
        check("기억 저장", False, f"내 말 id를 못 찾았다: {code}")
        return
    code, candidate = call("POST", f"/api/projects/{PROJECT}/director/memory-candidates", {
        "conversation_id": conversation, "client_request_id": "cand-" + uuid.uuid4().hex[:12],
        "source_message_ids": [message_id], "memory_scope": "creator", "category": "audio",
        "proposed_text": "배경 음악은 목소리를 덮지 않게 작게 까는 것을 좋아한다.",
    })
    if not (200 <= code < 300):
        check("기억 저장", False, f"{code} {json.dumps(candidate, ensure_ascii=False)[:200]}")
        return
    candidate_id = candidate["candidate_id"]
    call("POST", f"/api/projects/{PROJECT}/director/memory-candidates/{candidate_id}/approve", {})
    code, stored = call("POST", f"/api/projects/{PROJECT}/director/memory-candidates/{candidate_id}/store",
                        {"client_request_id": "store-" + uuid.uuid4().hex[:12]}, timeout=300.0)
    check("기억 저장", stored.get("storage_status") == "stored", f"{code} {stored.get('storage_status')}")

    # **다른 대화**에서 묻는다. 여기가 오늘 넓힌 자리다.
    code, second = call("POST", f"/api/projects/{PROJECT}/director/conversations", {"session_id": SESSION})
    code, reply = call(
        "POST", f"/api/projects/{PROJECT}/director/conversations/{second['conversation_id']}/messages",
        {"session_id": SESSION, "client_message_id": "msg-" + uuid.uuid4().hex[:12],
         "text": "배경 음악 크기는 내가 어떻게 해 달라고 했지?"}, timeout=300.0)
    text = str(((reply or {}).get("assistant_message") or {}).get("text") or "")
    recalled = any(word in text for word in ("작게", "덮지", "낮게"))
    check("다른 대화에서 그 기억을 꺼내는가", recalled, text[:160] or f"{code}")


def yujin_sees_the_project() -> None:
    code, conversation = call("POST", f"/api/projects/{PROJECT}/director/conversations", {"session_id": SESSION})
    code, reply = call(
        "POST", f"/api/projects/{PROJECT}/director/conversations/{conversation['conversation_id']}/messages",
        {"session_id": SESSION, "client_message_id": "msg-" + uuid.uuid4().hex[:12],
         "text": "지금 이 영상 첫 장면 자막이 뭐야?"}, timeout=300.0)
    text = str(((reply or {}).get("assistant_message") or {}).get("text") or "")
    # 되묻지 않고 실제 대본을 인용해야 한다.
    knows = "프로그램" in text or "서너" in text
    check("유진이 열어 놓은 영상을 보는가", knows, text[:160])


for step in (health, upload_ceiling, failure_reason_reaches_the_screen, yujin_sees_the_project, memory_round_trip):
    try:
        step()
    except Exception as error:  # noqa: BLE001 - 한 자리가 막혀도 나머지는 잰다
        check(step.__name__, False, f"확인 중 막힘: {error!r}")

print()
failed = [label for label, passed, _ in results if not passed]
print(f"{len(results) - len(failed)}/{len(results)} 통과")
if failed:
    print("못 통과한 자리:", ", ".join(failed))
    raise SystemExit(1)
