/** 편집하다가 설명 모션 한 편을 만드는 자리 (2026-10-08 결정 2단계).
 *
 *  **정해진 세 종류에 숫자·글만 적는다.** 모양은 저장소에 있는 템플릿이 정하고, 여기서는
 *  고르기와 적기만 한다(결정 방침 1 -- 아무도 그림 코드를 쓰지 않는다).
 *
 *  **만들면 이 프로젝트로 바로 가져온다.** 자료실 영상은 편집기 목록에 바로 안 뜬다 --
 *  가져와야(`materializeLibraryAsset`) 카드가 생기고 `적용`으로 장면 화면이 된다.
 *
 *  **기본 길이는 고른 장면 길이다.** 장면보다 짧으면 B-roll 기본값(반복)이라 숫자가
 *  처음부터 다시 올라간다.
 *
 *  스타일은 인포그래픽 패널의 것을 그대로 쓴다(팔레트·CSS를 새로 만들지 않는다). */
import { useEffect, useRef, useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { api, ApiRequestError, type MotionResult, type MotionTemplate } from "../../../api";

type BarRow = { label: string; value: string };
type Prefix = "₩" | "$" | "";
/** 서버는 다리를 240초 기다리고 nginx 벽은 600초다. 그 사이 화면이 영영 잠겨 있지 않게 280초에서 스스로 놓는다. */
const CLIENT_LIMIT_MS = 280_000;
const FORBIDDEN = /[<>]/;
const PREFIXES: { value: Prefix; label: string }[] = [{ value: "₩", label: "₩" }, { value: "$", label: "$" }, { value: "", label: "없음" }];

export function MotionPanel({ projectId, sceneSeconds = null, onMade, onBusyChange }: {
  projectId?: string;
  sceneSeconds?: number | null;
  onMade?: () => void;
  /** 만드는 동안 `true`. 팝업이 이걸 보고 닫기를 막는다 -- 닫았다 다시 열면 빈 칸만 보여 아무것도 안 도는 것 같다. */
  onBusyChange?: (busy: boolean) => void;
}) {
  const [templates, setTemplates] = useState<MotionTemplate[]>([]);
  const [key, setKey] = useState("");
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [unit, setUnit] = useState("");
  const [bars, setBars] = useState<BarRow[]>([{ label: "", value: "" }, { label: "", value: "" }]);
  const [lead, setLead] = useState("");
  const [amount, setAmount] = useState("");
  const [prefix, setPrefix] = useState<Prefix>("₩");
  const [suffix, setSuffix] = useState("");
  const [caption, setCaption] = useState("");
  const [steps, setSteps] = useState<string[]>(["", ""]);
  const [layout, setLayout] = useState<"full" | "overlay">("full");
  const [seconds, setSeconds] = useState("");
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState<{ result: MotionResult; inProject: boolean } | null>(null);
  const [failed, setFailed] = useState("");

  const alive = useRef(true);
  const running = useRef<AbortController | null>(null);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; running.current?.abort(); };
  }, []);

  useEffect(() => { onBusyChange?.(busy); }, [busy, onBusyChange]);
  useEffect(() => () => { onBusyChange?.(false); }, [onBusyChange]);

  useEffect(() => {
    let alive = true;
    api.listMotionTemplates()
      .then((reply) => {
        if (!alive) return;
        setTemplates(reply.templates);
        setKey((current) => current || reply.templates[0]?.key || "");
      })
      .catch(() => { if (alive) setFailed("모션 종류를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요."); });
    return () => { alive = false; };
  }, []);

  const template = templates.find((item) => item.key === key);
  const minimum = template?.min_duration_sec ?? 3;
  const maximum = template?.max_duration_sec ?? 30;
  useEffect(() => {
    if (!template) return;
    setSeconds((current) => current || String(defaultSeconds(sceneSeconds, template)));
  }, [template, sceneSeconds]);

  const limit = (name: string, fallback: number) => template?.limits[name] ?? fallback;
  const usableBars = bars.filter((row) => row.label.trim() && row.value.trim() && Number.isFinite(Number(row.value)));
  const usableSteps = steps.map((step) => step.trim()).filter(Boolean);
  const texts = key === "bar_compare" ? [title, subtitle, unit, ...bars.map((row) => row.label)]
    : key === "money_counter" ? [lead, suffix, caption] : [title, ...steps];
  const hasForbidden = texts.some((text) => FORBIDDEN.test(text));
  const duration = Number(seconds);
  const durationOk = seconds.trim() !== "" && Number.isFinite(duration) && duration >= minimum && duration <= maximum;
  const filled = key === "bar_compare" ? Boolean(title.trim()) && usableBars.length >= 2
    : key === "money_counter" ? /^\d{1,15}$/.test(amount.trim())
    : Boolean(title.trim()) && usableSteps.length >= 2;
  const ready = Boolean(template) && filled && durationOk && !hasForbidden && !busy;

  const capHint = key === "bar_compare" ? `글자 수: 제목 ${limit("title", 24)}자 · 작은 설명 ${limit("subtitle", 40)}자 · 이름 ${limit("label", 10)}자 · 단위 ${limit("unit", 4)}자`
    : key === "money_counter" ? `글자 수: 위 문구 ${limit("lead", 20)}자 · 뒤에 붙일 말 ${limit("suffix", 4)}자 · 아래 문구 ${limit("caption", 30)}자`
      : key === "step_list" ? `글자 수: 제목 ${limit("title", 24)}자 · 단계마다 ${limit("step", 24)}자` : "";

  const variables = (): Record<string, unknown> => (
    key === "bar_compare"
      ? { title: title.trim(), subtitle: subtitle.trim(), unit: unit.trim(), bars: usableBars.map((row) => ({ label: row.label.trim(), value: Number(row.value) })) }
      : key === "money_counter"
        ? { lead: lead.trim(), amount: parseInt(amount.trim(), 10), prefix, suffix: suffix.trim(), caption: caption.trim() }
        : { title: title.trim(), steps: usableSteps }
  );

  const create = async () => {
    // 다음 렌더를 기다리지 않고 부모에게 바로 알린다 -- 그 사이 팝업이 닫히면 안 된다.
    onBusyChange?.(true);
    setBusy(true);
    setFailed("");
    setMade(null);
    const controller = new AbortController();
    running.current = controller;
    const timer = setTimeout(() => controller.abort(), CLIENT_LIMIT_MS);
    try {
      // fetch가 취소를 못 알아듣고 매달려 있어도 화면은 놓여나도록 취소 신호와 겨룬다.
      const gone = new Promise<never>((_, reject) => controller.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
      const result = await Promise.race([api.createMotion({ template: key, variables: variables(), duration_sec: duration, layout }, controller.signal), gone]);
      if (controller.signal.aborted || !alive.current) return;
      let inProject = false;
      if (result.library_asset_id && projectId) {
        try {
          await api.materializeLibraryAsset(result.library_asset_id, projectId);
          inProject = true;
        } catch {
          inProject = false;
        }
      }
      if (result.library_asset_id) onMade?.();
      else if (result.library_error) console.warn("motion library save failed:", result.library_error);
      if (!alive.current || controller.signal.aborted) return;
      setMade({ result, inProject });
    } catch (error) {
      if (!alive.current) return;
      setFailed(controller.signal.aborted ? "너무 오래 걸려요. 잠시 뒤 자료실 영상을 확인해 보고, 없으면 다시 해 보세요. 만들어졌다면 그곳에 들어 있을 수 있어요." : messageFor(error));
    } finally {
      clearTimeout(timer);
      if (running.current === controller) running.current = null;
      if (alive.current) setBusy(false);
    }
  };

  return <div className="vb-infographic vb-motion">
    {templates.length > 0 ? <div className="vb-infographic__field" role="group" aria-label="모션 종류">
      <span>모션 종류</span>
      <div className="vb-infographic__styles">
        {templates.map((item) => <Button key={item.key} type="button" variant="ghost" className="vb-infographic__style"
          aria-pressed={key === item.key} disabled={busy}
          onClick={() => { setKey(item.key); setSeconds(""); }}>{item.korean_name}</Button>)}
      </div>
      <span className="vb-infographic__hint">{template?.description ?? ""}</span>
    </div> : null}

    {key === "bar_compare" || key === "step_list" ? <label className="vb-infographic__field">
      <span>제목</span>
      <Input value={title} disabled={busy} maxLength={limit("title", 24)} placeholder={key === "bar_compare" ? "월 수익 비교" : "처음 시작하는 3단계"}
        onChange={(event) => setTitle(event.target.value)} />
    </label> : null}

    {key === "bar_compare" ? <>
      <label className="vb-infographic__field">
        <span>작은 설명(선택)</span>
        <Input value={subtitle} disabled={busy} maxLength={limit("subtitle", 40)} placeholder="2026년 9월 · 단위 만 원" onChange={(event) => setSubtitle(event.target.value)} />
      </label>
      <label className="vb-infographic__field">
        <span>단위(선택)</span>
        <Input value={unit} disabled={busy} maxLength={limit("unit", 4)} placeholder="만" onChange={(event) => setUnit(event.target.value)} />
      </label>
      <div className="vb-infographic__facts" role="group" aria-label="막대">
        <p className="vb-infographic__hint">가장 큰 값이 다른 색으로 보여요.</p>
        {bars.map((row, index) => <div className="vb-infographic__fact" key={index}>
          <Input aria-label={`${index + 1}번째 이름`} value={row.label} disabled={busy} maxLength={limit("label", 10)} placeholder="쿠팡"
            onChange={(event) => setBars(replaceAt(bars, index, { ...row, label: event.target.value }))} />
          <Input aria-label={`${index + 1}번째 값`} value={row.value} disabled={busy} inputMode="decimal" placeholder="1280"
            onChange={(event) => setBars(replaceAt(bars, index, { ...row, value: event.target.value }))} />
          <Button type="button" variant="ghost" disabled={busy || bars.length <= limit("min_items", 2)} aria-label={`${index + 1}번째 줄 지우기`}
            onClick={() => setBars(bars.filter((_, at) => at !== index))}>지우기</Button>
        </div>)}
        <Button type="button" variant="outline" disabled={busy || bars.length >= limit("max_items", 5)}
          onClick={() => setBars([...bars, { label: "", value: "" }])}>막대 한 줄 더하기</Button>
      </div>
    </> : null}

    {key === "money_counter" ? <>
      <label className="vb-infographic__field">
        <span>위 문구(선택)</span>
        <Input value={lead} disabled={busy} maxLength={limit("lead", 20)} placeholder="첫 달 순매출" onChange={(event) => setLead(event.target.value)} />
      </label>
      <label className="vb-infographic__field">
        <span>금액</span>
        <Input value={amount} disabled={busy} inputMode="numeric" placeholder="12345678" onChange={(event) => setAmount(event.target.value)} />
      </label>
      <div className="vb-infographic__field" role="group" aria-label="금액 앞 기호">
        <span>금액 앞 기호</span>
        <div className="vb-infographic__styles">
          {PREFIXES.map((item) => <Button key={item.label} type="button" variant="ghost" className="vb-infographic__style"
            aria-pressed={prefix === item.value} disabled={busy} onClick={() => setPrefix(item.value)}>{item.label}</Button>)}
        </div>
      </div>
      <label className="vb-infographic__field">
        <span>뒤에 붙일 말(선택)</span>
        <Input value={suffix} disabled={busy} maxLength={limit("suffix", 4)} placeholder="원" onChange={(event) => setSuffix(event.target.value)} />
      </label>
      <label className="vb-infographic__field">
        <span>아래 문구(선택)</span>
        <Input value={caption} disabled={busy} maxLength={limit("caption", 30)} placeholder="광고비 · 수수료 제외 후" onChange={(event) => setCaption(event.target.value)} />
      </label>
    </> : null}

    {key === "step_list" ? <div className="vb-infographic__facts" role="group" aria-label="단계">
      {steps.map((step, index) => <div className="vb-infographic__fact vb-infographic__fact--wide" key={index}>
        <Input aria-label={`${index + 1}번째 단계`} value={step} disabled={busy} maxLength={limit("step", 24)} placeholder="상품 소싱하고 가격 정하기"
          onChange={(event) => setSteps(steps.map((current, at) => (at === index ? event.target.value : current)))} />
        <Button type="button" variant="ghost" disabled={busy || steps.length <= limit("min_items", 2)} aria-label={`${index + 1}번째 단계 지우기`}
          onClick={() => setSteps(steps.filter((_, at) => at !== index))}>지우기</Button>
      </div>)}
      <Button type="button" variant="outline" disabled={busy || steps.length >= limit("max_items", 5)}
        onClick={() => setSteps([...steps, ""])}>단계 한 줄 더하기</Button>
    </div> : null}

    {template ? <div className="vb-infographic__field" role="group" aria-label="모양">
      <span>모양</span>
      <div className="vb-infographic__styles">
        <Button type="button" variant="ghost" className="vb-infographic__style" aria-pressed={layout === "full"} disabled={busy}
          onClick={() => setLayout("full")}>전체 화면</Button>
        <Button type="button" variant="ghost" className="vb-infographic__style" aria-pressed={layout === "overlay"} disabled={busy}
          onClick={() => setLayout("overlay")}>작은 창(투명)</Button>
      </div>
      <span className="vb-infographic__hint">{layout === "overlay" ? "영상 위에 작게 얹어요. 바탕이 비쳐 보여요. 얹는 구간이 모션보다 길면 모션이 끝나고 사라져요." : "화면을 가득 채워요."}</span>
    </div> : null}

    {template ? <label className="vb-infographic__field">
      <span>길이(초)</span>
      <Input value={seconds} disabled={busy} inputMode="decimal" onChange={(event) => setSeconds(event.target.value)} />
      {!durationOk ? <span className="vb-infographic__hint">길이는 {minimum}초에서 {maximum}초 사이로 적어 주세요.</span> : null}
    </label> : null}

    {capHint ? <p className="vb-infographic__hint">{capHint}</p> : null}

    {hasForbidden ? <p className="vb-infographic__warning" role="alert">{"< > 기호는 쓸 수 없어요."}</p> : null}

    <Button type="button" disabled={!ready} title={busy ? "만드는 중이에요. 끝나면 다시 만들 수 있어요." : !template ? "모션 모양을 먼저 골라 주세요." : hasForbidden ? "< > 기호는 쓸 수 없어요." : !durationOk ? `길이는 ${minimum}초에서 ${maximum}초 사이로 적어 주세요.` : !filled ? "비어 있는 칸을 먼저 채워 주세요." : undefined} onClick={create} className="vb-infographic__make">
      {busy ? "만드는 중… 1분 안쪽으로 걸려요" : "모션 만들기"}
    </Button>

    {failed ? <p className="vb-infographic__failed" role="alert">{failed}</p> : null}
    {made ? <div className="vb-infographic__made" role="status">
      <p>
        {made.result.library_asset_id
          ? made.inProject
            ? made.result.layout === "overlay"
              ? <>다 만들었어요. 이 프로젝트 영상 목록에 넣어 뒀으니 장면을 고르고 <strong>화면에 얹기</strong>를 눌러 쓰세요. 크기·자리·나타나기는 오른쪽에서 고를 수 있어요.</>
              : <>다 만들었어요. 이 프로젝트 영상 목록에 넣어 뒀으니 <strong>장면을 고르고 적용</strong>을 눌러 쓰세요.</>
            : <>다 만들었어요. 자료실 영상에 넣어 뒀으니 <strong>자료실에서 가져오기</strong>로 꺼내 쓰세요.</>
          : <>모션은 만들었지만 자료실에 넣지 못했어요. 잠시 뒤 다시 만들어 주세요.</>}
      </p>
      <p className="vb-infographic__hint">적은 숫자와 글만 들어가요. 영상에 쓰기 전에 한 번 보고 읽어 보세요.</p>
    </div> : null}
  </div>;
}

function defaultSeconds(sceneSeconds: number | null, template: MotionTemplate): number {
  if (sceneSeconds === null || !Number.isFinite(sceneSeconds) || sceneSeconds <= 0) return template.default_duration_sec;
  const rounded = Math.round(sceneSeconds * 10) / 10;
  return Math.min(template.max_duration_sec, Math.max(template.min_duration_sec, rounded));
}

function replaceAt(rows: BarRow[], index: number, row: BarRow): BarRow[] {
  return rows.map((current, at) => (at === index ? row : current));
}

/** 서버가 준 이유를 창작자의 말로 옮긴다(§10.13). 문제 목록이 객체로 와도 `ApiRequestError`는
 *  이유 이름만 들고 온다 -- 그래서 이유 이름으로 가른다. */
function messageFor(error: unknown): string {
  const reason = error instanceof ApiRequestError ? (error.reason ?? error.detail ?? "") : "";
  if (reason === "motion_generation_unavailable" || reason === "motion_bridge_not_configured") return "모션 만들기가 아직 꺼져 있어요. VideoBox를 다시 켜 주세요.";
  if (reason === "motion_bridge_not_running") return "모션 만드는 프로그램이 꺼져 있어요. VideoBox를 다시 켜 주세요.";
  if (reason === "motion_engine_not_prepared") return "모션 도구를 처음 한 번 준비하는 중이에요. 몇 분 뒤 다시 해 보세요.";
  if (reason === "motion_busy") return "다른 모션을 만드는 중이에요. 끝나면 다시 눌러 주세요.";
  if (reason === "motion_took_too_long") return "너무 오래 걸렸어요. 길이를 줄이고 다시 해 보세요.";
  if (reason === "motion_variables_invalid" || reason === "motion_template_unknown") return "적은 내용을 다시 확인해 주세요. 글이 너무 길 수 있어요.";
  return "만들지 못했어요. 잠시 뒤 다시 해 보세요.";
}
