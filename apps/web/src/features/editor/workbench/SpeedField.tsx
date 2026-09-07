import { useEffect, useState } from "react";

import { Input } from "../../../components/ui/input";
import { rippleDisplayDurationSec } from "../inspector/rippleDuration";

/** 렌더가 실제로 낼 수 있는 배속 범위. 엔진과 같은 값이다 --
 *  `editing_session.py`의 `MIN/MAX_RIPPLE_PLAYBACK_RATE`, 그리고 그 값의 출처인
 *  `ffmpeg_final_renderer.py`의 `_atempo_chain`("허용 범위(0.25~4)").
 *
 *  화면이 먼저 막는 이유: 엔진도 거부하지만, 거기까지 갔다 오면 창작자는 실패를
 *  한 번 보고 나서야 안다. */
export const MIN_RATE = 0.25;
export const MAX_RATE = 4;

/** 캡컷 `속도` 속성 칸. `속도 x`와 `기간 s`를 나란히 두고 연동한다.
 *
 *  `기간`은 읽기 전용이다 -- 길이를 직접 고치는 것은 구간 자르기이고 그 자리가
 *  따로 있다. 여기서 둘 다 고치게 하면 같은 값을 두 곳에서 바꾸게 된다. */
export function SpeedField({
  rate,
  displayedSec,
  disabled,
  onCommit,
}: {
  /** 지금 걸려 있는 배속. */
  rate: number;
  /** 지금 화면에 보이는 장면 길이(이미 `rate`가 걸린 값). */
  displayedSec: number;
  disabled?: boolean;
  onCommit: (rate: number) => void;
}) {
  // 타이핑 중에는 자유롭게 두고, 확정할 때만 검사한다 -- 글자를 지우는 중간
  // 상태("1.")마다 되돌리면 숫자를 고칠 수가 없다.
  const [draft, setDraft] = useState(String(rate));
  useEffect(() => { setDraft(String(rate)); }, [rate]);

  const parsed = Number(draft);
  const valid = Number.isFinite(parsed) && parsed >= MIN_RATE && parsed <= MAX_RATE;
  // 미리 보여 주는 기간은 타이핑 중인 값을 따라간다 -- 캡컷처럼 둘이 붙어 움직여야
  // "이 배속이면 몇 초가 되는지"를 넣기 전에 알 수 있다.
  const previewSec = valid
    ? rippleDisplayDurationSec({ displayedSec, currentRate: rate, nextRate: parsed })
    : rippleDisplayDurationSec({ displayedSec, currentRate: rate, nextRate: rate });

  const commit = () => {
    if (!valid || parsed === rate) { setDraft(String(rate)); return; }
    onCommit(parsed);
  };

  return <>
    <label className="vb-speed-field__row">
      <span>속도</span>
      <Input
        aria-label="속도"
        disabled={disabled}
        inputMode="decimal"
        max={MAX_RATE}
        min={MIN_RATE}
        onBlur={commit}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Enter") commit(); }}
        step="0.05"
        type="number"
        value={draft}
      />
      <span className="vb-speed-field__unit">x</span>
    </label>
    <label className="vb-speed-field__row">
      <span>기간</span>
      <Input aria-label="기간" readOnly tabIndex={-1} type="number" value={previewSec === null ? "" : Number(previewSec.toFixed(1))} />
      <span className="vb-speed-field__unit">s</span>
    </label>
    {!valid ? <p className="vb-speed-field__hint" role="alert">{`${MIN_RATE}배에서 ${MAX_RATE}배 사이로 넣어 주세요.`}</p> : null}
  </>;
}
