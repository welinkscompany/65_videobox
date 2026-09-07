"""설치 없이 바로 쓰는 내레이션 엔진. 목소리는 복제하지 않는다.

## 왜 이게 있나

목소리를 복제하는 엔진(`chatterbox`)은 torch와 2GB짜리 모델이 필요한 무거운
선택 설치다. 그게 깔리기 전까지 **더빙 단추는 눌러도 아무 일이 안 일어난다.**
그건 완료가 아니다.

`espeak-ng`는 데비안 패키지 하나(수 MB)이고, 밖으로 나가지 않으며, 여러 언어를
읽는다. 그래서 더빙을 오늘 당장 써 볼 수 있게 하는 자리다.

## 감수하는 것

**소리가 기계적이다.** 사람 목소리처럼 들리지 않고, 창작자의 목소리는 더더욱
아니다. 그러니 이것은 기본값이자 비상용이고, **진짜 목소리는 `chatterbox`다** --
설치하면 같은 자리에 그대로 꽂힌다(`TTSEngineConfig.engine`만 바꾼다).

이 구분을 흐리지 마라. "더빙이 된다"와 "내 목소리로 더빙이 된다"는 다른 말이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from videobox_provider_interfaces.gtts_provider import TTSSynthesisError
from videobox_provider_interfaces.tts import TTSRequest, TTSResult


#: 우리가 쓰는 언어 코드를 espeak-ng의 목소리 이름으로 옮긴다.
#: 중국어만 이름이 다르다(`zh`가 아니라 `cmn`, 표준 중국어).
_ESPEAK_VOICES = {"ko": "ko", "en": "en", "ja": "ja", "zh": "cmn"}


@dataclass(slots=True)
class EspeakTTSProvider:
    provider_name: str = "espeak"
    language: str = "ko"
    binary: str = "espeak-ng"
    #: 분당 낱말 수. 기본값(175)보다 조금 느린 편이 알아듣기 좋다.
    words_per_minute: int = 155

    def synthesize(self, request: TTSRequest) -> TTSResult:
        text = request.text.strip()
        if not text:
            raise TTSSynthesisError("Cannot synthesize empty text.")
        language = request.language or self.language
        voice = _ESPEAK_VOICES.get(language)
        if voice is None:
            raise TTSSynthesisError(f"espeak-ng has no voice for language '{language}'.")

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                [
                    self.binary,
                    "-v", voice,
                    "-s", str(self.words_per_minute),
                    "-w", str(request.output_path),
                    # 읽을 글을 인자로 붙이지 않고 stdin으로 넘긴다. 자막에는
                    # 따옴표·괄호가 흔한데, 인자로 주면 셸이나 espeak의 옵션
                    # 해석과 섞인다.
                    "--stdin",
                ],
                input=text,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except FileNotFoundError as exc:
            raise TTSSynthesisError(
                f"'{self.binary}' not found. Install espeak-ng, or switch "
                "TTSEngineConfig.engine to an installed engine."
            ) from exc
        if result.returncode != 0 or not request.output_path.exists():
            raise TTSSynthesisError(f"espeak-ng failed: {result.stderr.strip()[:400]}")
        if request.output_path.stat().st_size == 0:
            raise TTSSynthesisError("espeak-ng produced an empty file.")
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)
