/** 편집하다가 인포그래픽 한 장을 만드는 자리 (owner 지시 2026-09-07).
 *
 *  > "인포그래픽 만들기 기능을 편집기화면에 붙여줘야 할거 같은데"
 *
 *  **미디어 패널의 `더하기` 줄에 붙는다.** 인포그래픽은 결국 `그림` 자산 하나라
 *  파일을 올리는 것·촬영본을 가져오는 것과 같은 성격이다. 왼쪽 띠에 일곱 번째
 *  탭을 새로 만들지 않은 이유가 그것이다 -- 캡컷에 없는 탭을 늘리지 않는다는
 *  규정(`decisions/2026-08-30-capcut-button-level-parity.ko.md`)에도 맞는다.
 *
 *  **숫자는 창작자가 직접 적는다.** 모델에게 숫자까지 맡기면 그럴듯한 거짓말을
 *  만든다 -- 2026-09-07 실측에서 `100,000원 판매 시` 예시를 통째로 지어냈다.
 *  적어 준 숫자만 쓰는지는 서버가 대조한다.
 *
 *  **1~2분 걸린다.** 만드는 동안 단추를 잠그고 무엇을 하고 있는지 말한다 --
 *  아무 말 없이 멈춰 있으면 창작자는 두 번 누른다. */
import { useEffect, useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { api, type InfographicFact, type InfographicResult, type InfographicStyle } from "../../../api";

/** 빈 줄 하나. 숫자를 글로 들고 있는 것은, 입력 중인 `-`나 `.`를 숫자로 바꾸면
 *  커서가 튀기 때문이다. 보낼 때만 숫자로 바꾼다. */
type FactRow = { label: string; value: string; unit: string };

const EMPTY_ROW: FactRow = { label: "", value: "", unit: "%" };
/** 여덟을 넘기면 1920x1080 안에 다 못 들어간다. 서버도 같은 값으로 막는다. */
const MAXIMUM_FACTS = 8;

export function InfographicPanel({ onMade }: { onMade?: () => void }) {
  const [styles, setStyles] = useState<InfographicStyle[]>([]);
  const [style, setStyle] = useState("");
  const [topic, setTopic] = useState("");
  const [rows, setRows] = useState<FactRow[]>([{ ...EMPTY_ROW }, { ...EMPTY_ROW }]);
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState<InfographicResult | null>(null);
  const [failed, setFailed] = useState("");

  useEffect(() => {
    let alive = true;
    api.listInfographicStyles()
      .then((reply) => {
        if (!alive) return;
        setStyles(reply.styles);
        // **지금 걸린 것을 같이 둔다.** 목록만 주고 고른 값을 안 두면 되돌릴 수가
        // 없다 -- 전환·색감에서 같은 함정을 두 번 밟았다.
        setStyle((current) => current || reply.styles[0]?.key || "");
      })
      .catch(() => { /* 결을 못 불러와도 만들 수는 있다. 서버가 첫째 결로 간다. */ });
    return () => { alive = false; };
  }, []);

  const usable = rows.filter((row) => row.label.trim() && row.value.trim() && Number.isFinite(Number(row.value)));
  const ready = topic.trim().length > 0 && usable.length > 0 && !busy;

  const make = async () => {
    setBusy(true);
    setFailed("");
    setMade(null);
    const facts: InfographicFact[] = usable.map((row) => ({
      label: row.label.trim(), value: Number(row.value), unit: row.unit.trim(),
    }));
    try {
      const result = await api.createInfographic({ topic: topic.trim(), facts, style: style || null });
      setMade(result);
      // 자료실에 들어갔으면 목록을 다시 읽게 한다 -- 만들고 나서 어디 갔는지
      // 안 보이면 만든 적 없는 것과 같다.
      if (result.library_asset_id) onMade?.();
    } catch (error) {
      setFailed(messageFor(error));
    } finally {
      setBusy(false);
    }
  };

  return <div className="vb-infographic">
    <label className="vb-infographic__field">
      <span>무엇에 대한 그림인가요</span>
      <Input value={topic} disabled={busy} placeholder="스마트스토어 판매 수수료 구조"
        onChange={(event) => setTopic(event.target.value)} />
    </label>

    <div className="vb-infographic__facts" role="group" aria-label="그림에 넣을 숫자">
      <p className="vb-infographic__hint">
        여기 적은 숫자만 그림에 들어갑니다. <strong>적지 않은 숫자는 만들지 않습니다.</strong>
      </p>
      {rows.map((row, index) => <div className="vb-infographic__fact" key={index}>
        <Input aria-label={`${index + 1}번째 이름`} value={row.label} disabled={busy} placeholder="네이버 결제 수수료"
          onChange={(event) => setRows(replaceAt(rows, index, { ...row, label: event.target.value }))} />
        <Input aria-label={`${index + 1}번째 값`} value={row.value} disabled={busy} inputMode="decimal" placeholder="3.4"
          onChange={(event) => setRows(replaceAt(rows, index, { ...row, value: event.target.value }))} />
        <Input aria-label={`${index + 1}번째 단위`} value={row.unit} disabled={busy} placeholder="%"
          onChange={(event) => setRows(replaceAt(rows, index, { ...row, unit: event.target.value }))} />
        <Button type="button" variant="ghost" disabled={busy || rows.length <= 1}
          aria-label={`${index + 1}번째 줄 지우기`}
          onClick={() => setRows(rows.filter((_, at) => at !== index))}>지우기</Button>
      </div>)}
      <Button type="button" variant="outline" disabled={busy || rows.length >= MAXIMUM_FACTS}
        onClick={() => setRows([...rows, { ...EMPTY_ROW }])}>숫자 한 줄 더하기</Button>
    </div>

    {styles.length > 0 ? <label className="vb-infographic__field">
      <span>그림의 결</span>
      <select className="vb-infographic__style" value={style} disabled={busy}
        onChange={(event) => setStyle(event.target.value)}>
        {styles.map((item) => <option key={item.key} value={item.key}>{item.korean_name}</option>)}
      </select>
      <span className="vb-infographic__hint">{styles.find((item) => item.key === style)?.direction ?? ""}</span>
    </label> : null}

    <Button type="button" disabled={!ready} onClick={make} className="vb-infographic__make">
      {busy ? "그리는 중입니다… 1~2분 걸립니다" : "인포그래픽 만들기"}
    </Button>

    {failed ? <p className="vb-infographic__failed" role="alert">{failed}</p> : null}
    {made ? <div className="vb-infographic__made" role="status">
      <p>
        {made.library_asset_id
          ? <>다 만들었습니다. <strong>자료실 그림</strong>에 넣어 두었습니다 — 위 <strong>그림</strong>에서 골라 쓰세요.</>
          : <>그림은 만들었지만 자료실에 넣지 못했습니다{made.library_error ? ` (${made.library_error})` : ""}.</>}
      </p>
      {made.attempts > 1 ? <p className="vb-infographic__hint">
        처음 것이 아쉬워서 한 번 고쳐 만들었습니다: {made.corrected.join(" / ")}
      </p> : null}
      {/* **기계가 못 보는 것을 말해 준다.** 숫자가 지어낸 것인지·판을 넘었는지는
          검사하지만, **글로 쓴 설명이 맞는 말인지는 검사하지 못한다.**
          2026-09-07에 모델이 준 적 없는 "연동은 무료입니다"를 써 넣었고, 그건
          같은 그림 안의 2%와 정면으로 어긋났다. 그 한계를 숨기면 창작자가
          거짓말을 영상에 싣는다. */}
      <p className="vb-infographic__hint">
        숫자와 자리는 검사했습니다. <strong>글로 쓴 설명은 검사하지 못하니 한 번 읽어 보세요.</strong>
      </p>
      {/* **아쉬운 점을 숨기지 않는다.** 시간이 모자라 더 못 고쳤을 때 채워져 온다.
          숨기면 창작자가 다 된 줄 알고 영상에 넣는다. */}
      {made.remaining_problems.length > 0 ? <p className="vb-infographic__warning" role="alert">
        아직 아쉬운 점이 있습니다: {made.remaining_problems.join(" / ")} — 보시고 다시 만들어도 됩니다.
      </p> : null}
    </div> : null}
  </div>;
}

function replaceAt(rows: FactRow[], index: number, row: FactRow): FactRow[] {
  return rows.map((current, at) => (at === index ? row : current));
}

/** 서버가 준 이유를 창작자의 말로 옮긴다. 개발 낱말을 그대로 보여 주지 않는다
 *  (§10.13 creator-language).
 *
 *  검사에 걸린 경우 `detail`은 `{reason, problems}` 꼴로 온다. **문자열로만
 *  다루면 `[object Object]`가 되어 어느 갈래에도 안 걸린다** -- 그러면 무엇이
 *  문제였는지 알 길이 없는 채로 "잠시 뒤 다시"만 뜬다. */
function messageFor(error: unknown): string {
  const raw = (error as { detail?: unknown })?.detail;
  const structured = raw && typeof raw === "object" ? (raw as { reason?: string; problems?: string }) : null;
  if (structured?.reason === "infographic_did_not_pass_checks") {
    return structured.problems
      ? `쓸 만한 그림이 안 나와서 버렸습니다 — ${structured.problems}. 주제나 숫자를 바꿔 다시 해 보세요.`
      : "쓸 만한 그림이 안 나왔습니다. 주제를 더 짧게 적고 다시 해 보세요.";
  }
  const detail = String(raw ?? (error as Error)?.message ?? "");
  if (detail.includes("bridge_not_configured") || detail.includes("generation_unavailable")) {
    return "인포그래픽 기능이 아직 켜져 있지 않습니다. VideoBox를 다시 켜 주세요.";
  }
  if (detail.includes("bridge_not_running")) {
    return "그림을 그리는 프로그램이 꺼져 있습니다. VideoBox를 다시 켜 주세요.";
  }
  if (detail.includes("took_too_long")) {
    return "만드는 데 너무 오래 걸렸습니다. 숫자를 줄이고 다시 해 보세요.";
  }
  if (detail.includes("did_not_pass_checks")) {
    return "쓸 만한 그림이 안 나왔습니다. 주제를 더 짧게 적고 다시 해 보세요.";
  }
  return "만들지 못했습니다. 잠시 뒤 다시 해 보세요.";
}
