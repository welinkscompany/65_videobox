"""폴링 경로에서 실패를 삼킬 때 쓰는 한 번만 기록기.

게이트웨이 준비 상태는 화면이 계속 되묻는다. 실패할 때마다 한 줄씩 찍으면
30초마다 같은 문장이 쌓여 로그가 못 쓰게 되고, 아무 줄도 안 찍으면 유진이
왜 안 뜨는지 알 방법이 없다. 그래서 **사유가 달라질 때만** 남긴다.

한 번 성공하면 잊어야 한다(`clear`). 그러지 않으면 회복 뒤에 다시 터진
장애가 조용해진다 -- 이 저장소가 고치려는 바로 그 증상이다.
"""

from __future__ import annotations

import logging

# 사유 문자열이 매번 달라져도(포트 번호 같은 것) 무한히 자라지 않게 막는다.
_MAX_REMEMBERED_FAULTS = 64


class FaultReporter:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._reported: set[str] = set()

    @staticmethod
    def cause(error: BaseException) -> str:
        return f"{type(error).__name__}|{error}"

    def report_once(
        self,
        error: BaseException,
        message: str,
        *args: object,
    ) -> None:
        cause = self.cause(error)
        if cause in self._reported:
            return
        if len(self._reported) >= _MAX_REMEMBERED_FAULTS:
            self._reported.clear()
        self._reported.add(cause)
        self._logger.warning(message, *args, exc_info=error)

    def clear(self) -> None:
        """한 번 성공했다는 뜻. 다음 장애는 다시 기록한다."""
        self._reported.clear()
