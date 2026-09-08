"""잡 실패 기록이 호스트 파일 경로·외부 명령 출력을 그대로 담지 않게 한다.

이 값은 `_http_error`(HTTP 예외 응답)와 다른 자리다 -- 잡 실패는 DB에 저장된 뒤
**정상적인 200 조회**로 화면까지 나가므로 `_http_error`의 봉쇄를 안 거친다
(2026-09-07 전체 점검 §1-3). `library_media_facts.py`/`local_pipeline.py`의
`record_broll_media_facts`가 이미 겪은 것과 같은 문제다: ffprobe 예외 문구에
호스트 절대 경로가 섞여 나간 전례가 있다.

파일 경로·명령 출력을 **실제로 담고 있다고 확인된** 예외 종류만 고정 문구로
바꾼다. 그 밖의 예외(예: `OutputSourceStaleError` 같이 코드성 문구를 직접
만드는 것들, 그리고 이 저장소 시험 다수가 쓰는 `raise OSError("설명 문구")`류
주입 실패)는 그대로 둔다 -- 화면이 그 문구로 실패 사유를 사람이 읽게 보여주고,
시험 다수가 그 정확한 문구를 잰다.

**`OSError`를 통째로 잡지 않는다.** 처음엔 그렇게 짰다가 전체 pytest에서
`test_api.py::test_provider_trace_audit_endpoint_includes_review_guidance_attempt_entry`가
깨졌다 -- 이 저장소는 `raise OSError("review guidance persistence offline")`류로
저장소 장애를 흉내 내는 시험 더블이 40건 넘게 있고, 그 문구엔 경로가 없다.
`FileNotFoundError`·`PermissionError`(둘 다 실제로 `local_pipeline.py`/
`media_probe.py`가 경로를 실어 던지는 것을 직접 확인함)와
`subprocess.CalledProcessError`(ffprobe argv에 경로가 그대로 들어감)만 좁혀 잡는다.
"""

from __future__ import annotations

import logging
import subprocess

_LOGGER = logging.getLogger(__name__)


def safe_job_error_message(exc: BaseException) -> str:
    """잡 상태 칸에 남길 안전한 문구. 원문은 로그에만 남긴다."""
    if isinstance(exc, FileNotFoundError):
        code = "asset_file_missing"
    elif isinstance(exc, PermissionError):
        code = "asset_file_permission_denied"
    elif isinstance(exc, subprocess.CalledProcessError):
        code = "external_command_failed"
    else:
        return str(exc)
    _LOGGER.warning("job_failed(%s): %s", code, exc, exc_info=True)
    return code


__all__ = ["safe_job_error_message"]
