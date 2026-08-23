import { useEffect, useRef, useState } from "react";

import type { CaptionStyleScope } from "../../../api";
import { SCENE_FILTER_CHOICES, SCENE_FILTER_NONE } from "./sceneFilters";
import { Button } from "../../../components/ui/button";
import { CaptionFontPicker } from "./CaptionFontPicker";
import { CaptionPresetPicker, fromSnapshot } from "./CaptionPresetPicker";
import { SavedFormatPicker } from "./SavedFormatPicker";
import { Input } from "../../../components/ui/input";
import { NativeSelect } from "../../../components/ui/native-select";
import { Textarea } from "../../../components/ui/textarea";
import type { EditorCaptionStyle, EditorControls } from "../editorViewModel";
import {
  DEFAULT_SCENE_TRANSITION_DURATION_SEC,
  SCENE_TRANSITION_CHOICES,
  SCENE_TRANSITION_NONE,
} from "./sceneTransitions";
import { SHAPE_OVERLAY_CHOICES, SHAPE_OVERLAY_LABELS, SHAPE_OVERLAY_MOTION_CHOICES, SHAPE_OVERLAY_MOTION_LABELS, shapeMotion, shapeValue, type InspectorTarget, type ShapeOverlayValue } from "./inspectorRegistry";

type CutAction = "keep" | "remove";

export type InspectorAction =
  | Readonly<{ kind: "split-narration"; segmentId: string; splitSec: number }>
  | Readonly<{ kind: "merge-narration"; leftSegmentId: string; rightSegmentId: string }>
  | Readonly<{ kind: "set-cut-action"; segmentId: string; cutAction: CutAction }>
  // 앞 장면에서 이 장면으로 넘어오는 방법. `transition`이 null이면 끈다.
  | Readonly<{ kind: "set-transition"; segmentId: string; transition: Readonly<{ type: string; durationSec: number }> | null }>
  | Readonly<{ kind: "save-media"; mediaKind: "broll" | "bgm" | "sfx"; segmentId: string; assetId: string; controls: EditorControls }>
  | Readonly<{ kind: "clear-media"; mediaKind: "broll" | "bgm" | "sfx"; segmentId: string }>
  | Readonly<{ kind: "save-caption-style"; segmentIds: string[]; scope: CaptionStyleScope; style: EditorCaptionStyle }>
  | Readonly<{ kind: "save-overlay"; overlayKind: "explanation-card"; segmentId: string; title: string; body: string; text: string }>
  | Readonly<{ kind: "save-overlay"; overlayKind: "image"; segmentId: string; assetId: string; text: string }>
  | Readonly<{ kind: "save-overlay"; overlayKind: "table"; segmentId: string; columns: string[]; rows: string[][]; text: string }>
  // 정지 도형("여기를 보세요"). 프리셋만 보낸다 -- 자유 좌표는 범위 밖이다.
  | Readonly<{ kind: "save-overlay"; overlayKind: "shape"; segmentId: string; shape: ShapeOverlayValue["shape"]; vertical: ShapeOverlayValue["vertical"]; horizontal: ShapeOverlayValue["horizontal"]; size: ShapeOverlayValue["size"]; motion: ShapeOverlayValue["motion"] }>
  | Readonly<{ kind: "clear-overlay"; overlayKind: "explanation-card" | "image" | "table" | "shape"; segmentId: string }>
  | Readonly<{ kind: "apply-tts-candidate"; segmentId: string; candidateId: string; assetId: string }>
  | Readonly<{ kind: "clear-tts-candidate"; segmentId: string }>
  | Readonly<{ kind: "partial-preflight"; segmentIds: string[]; fields: string[] }>
  | Readonly<{ kind: "partial-run"; segmentIds: string[]; fields: string[] }>
  | Readonly<{ kind: "partial-resume"; segmentIds: string[]; fields: string[] }>;

type SelectedSegment = Readonly<{
  segmentId: string;
  startSec: number;
  endSec: number;
  nextSegmentId: string | null;
  /** 앞에 붙은 장면. 없으면 넘어올 경계가 없어서 전환을 고를 수 없다. */
  previousSegmentId?: string | null;
  cutAction: string;
  /** 지금 이 장면에 걸려 있는 전환. 안 골랐으면 없다. */
  transitionIn?: Readonly<{ type: string; durationSec: number }> | null;
  ttsReplacement?: Readonly<{ candidateId: string; assetId: string }> | null;
}>;

export type ApprovedTtsCandidate = Readonly<{
  candidateId: string;
  assetId: string;
  sourceText: string;
}>;

export type PartialRegenerationControls = Readonly<{
  fields: readonly string[];
  defaultFields?: readonly string[];
  preparedFields?: readonly string[];
  preparedSegmentId?: string;
  canRun: boolean;
  canResume: boolean;
}>;

type Props = Readonly<{
  /** 저장된 자막 모양을 읽으려면 필요하다. 없으면 그 절만 빠진다. */
  projectId?: string;
  target: InspectorTarget | null;
  selectedSegment: SelectedSegment | null;
  partialRegeneration?: PartialRegenerationControls;
  loadApprovedTtsCandidates?: (segmentId: string) => Promise<readonly ApprovedTtsCandidate[]>;
  ttsCandidateScopeKey?: string;
  disabled?: boolean;
  onAction: (action: InspectorAction) => void | Promise<void>;
}>;

const defaultStyle: EditorCaptionStyle = {
  // 컨테이너에 실제로 들어 있는 글꼴이다. 예전에는 이 자리에 없는 글꼴이
  // 적혀 있어서 모든 자막이 조용히 다른 글꼴로 떨어졌다.
  fontFamily: "Pretendard",
  fontSizePx: 28,
  textColor: "#ffffff",
  outlineColor: "#000000",
  outlineWidthPx: 2,
  backgroundColor: "#00000000",
  positionXPercent: 50,
  positionYPercent: 90,
  horizontalAlign: "center",
  safeAreaEnabled: true,
  shadowBlurPx: 0,
};
const partialFieldLabels: Readonly<Record<string, string>> = {
  caption: "자막",
  cut_action: "컷 판단",
  broll: "B-roll",
  visual_overlay: "화면 요소",
  music: "배경 음악",
  sfx: "효과음",
  tts_replacement: "내레이션 음성",
};

function asCutAction(value: string): CutAction {
  return value === "remove" ? "remove" : "keep";
}

function numberValue(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

// `소리 크기` 슬라이더(0~100)와 gainDb 사이 변환. 중앙(50)이 `그대로`(0dB),
// 왼쪽 끝이 -18dB(조용히), 오른쪽 끝이 +6dB(크게)다. 줄이는 폭이 늘리는 폭보다
// 넓어야 해서 중앙을 0에 고정한 조각 선형으로 잇는다. §10.13: dB는 내부 단위라
// 화면에는 쓰지 않는다. 백엔드 `normalize_media_controls`는 유한값이면 다
// 받으므로 경계는 화면이 정한다.
const QUIETEST_GAIN_DB = -18;
const LOUDEST_GAIN_DB = 6;

function gainSliderPosition(gainDb: number): number {
  const clamped = Math.min(LOUDEST_GAIN_DB, Math.max(QUIETEST_GAIN_DB, gainDb));
  return clamped <= 0
    ? 50 - (clamped / QUIETEST_GAIN_DB) * 50
    : 50 + (clamped / LOUDEST_GAIN_DB) * 50;
}

function gainDbFromSlider(position: number): number {
  const clamped = Math.min(100, Math.max(0, position));
  const gainDb = clamped <= 50
    ? ((50 - clamped) / 50) * QUIETEST_GAIN_DB
    : ((clamped - 50) / 50) * LOUDEST_GAIN_DB;
  const rounded = Math.round(gainDb * 10) / 10;
  return Object.is(rounded, -0) ? 0 : rounded;
}

function parseColumns(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseRows(value: string): string[][] {
  return value.split(/\r?\n/).map((row) => row.split("|").map((item) => item.trim())).filter((row) => row.some(Boolean));
}

export function InspectorControls({
  projectId,
  target,
  selectedSegment,
  partialRegeneration,
  loadApprovedTtsCandidates,
  ttsCandidateScopeKey = "",
  disabled = false,
  onAction,
}: Props) {
  const [cutAction, setCutAction] = useState<CutAction>(() => asCutAction(selectedSegment?.cutAction ?? "keep"));
  const [transition, setTransition] = useState<string>(
    () => selectedSegment?.transitionIn?.type ?? SCENE_TRANSITION_NONE,
  );
  const [fadeInSec, setFadeInSec] = useState(0);
  const [fadeOutSec, setFadeOutSec] = useState(0);
  const [inSec, setInSec] = useState(0);
  const [outSec, setOutSec] = useState(0);
  // Both rode in the command port from the start with no screen offering
  // them. Phone B-roll is routinely too long and too loud.
  const [speed, setSpeed] = useState(1);
  const [volume, setVolume] = useState(1);
  // 색감. 안 고른 상태는 `none`이고, 저장할 때 `null`로 바뀐다.
  const [look, setLook] = useState<string>(SCENE_FILTER_NONE);
  // 말할 때 음악이 비켜서기(덕킹). 렌더러는 처음부터 이걸 할 수 있었는데
  // 켜고 끄는 자리가 화면에 없었다.
  const [ducking, setDucking] = useState(false);
  // 이 클립의 원래 소리를 살릴지. **`소리 크기`와 한 벌이다** -- 이게 꺼져 있으면
  // 섞일 소리가 없어서 음량을 아무리 바꿔도 결과가 같다.
  const [preserveSourceAudio, setPreserveSourceAudio] = useState(false);
  // 배경 음악·효과음의 `소리 크기`. 상태는 dB로 든다 -- 슬라이더 눈금으로 들면
  // 손대지 않은 저장이 저장돼 있던 값을 눈금에 반올림해 몰래 옮긴다.
  const [gainDb, setGainDb] = useState(0);
  const [captionStyle, setCaptionStyle] = useState<EditorCaptionStyle>(defaultStyle);
  const [overlayTitle, setOverlayTitle] = useState("");
  const [overlayBody, setOverlayBody] = useState("");
  const [overlayText, setOverlayText] = useState("");
  const [tableColumns, setTableColumns] = useState("");
  const [tableRows, setTableRows] = useState("");
  // 정지 도형의 프리셋 선택. 저장된 값에서 시작하므로 손대지 않은 저장이
  // 값을 옮기지 않는다.
  const [shapeOverlay, setShapeOverlay] = useState<ShapeOverlayValue>({
    shape: "highlight_box", vertical: "middle", horizontal: "center", size: "medium", motion: "none",
  });
  const [selectedPartialFields, setSelectedPartialFields] = useState<readonly string[]>(() =>
    partialRegeneration?.defaultFields ?? partialRegeneration?.fields ?? [],
  );
  const [ttsCandidates, setTtsCandidates] = useState<readonly ApprovedTtsCandidate[]>([]);
  const [selectedTtsCandidateId, setSelectedTtsCandidateId] = useState("");
  const [ttsLoadState, setTtsLoadState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [ttsRetryToken, setTtsRetryToken] = useState(0);
  // 속성이 기본으로 펴지면서 이 조회가 **편집기를 여는 것만으로** 나갔다.
  // `편집기를 열었을 뿐인데 아무 일도 하지 않는다`를 지키는 테스트가 그걸
  // 잡았다. 청취 승인 음성은 자주 쓰는 길이 아니므로 부를 때만 부른다.
  //
  // "요청했다"를 **어느 장면에 대해** 요청했는지까지 함께 들고 있는다. 그냥
  // boolean으로 두고 장면이 바뀔 때 effect에서 끄면, 조회 effect가 같은 commit에서
  // 아직 켜져 있는 옛 값을 읽어 **묻지도 않은 새 장면의 후보를 한 번 불러온다.**
  const [ttsRequest, setTtsRequest] = useState<string | null>(null);
  const ttsScope = `${selectedSegment?.segmentId ?? ""}|${ttsCandidateScopeKey ?? ""}`;
  const ttsRequested = ttsRequest === ttsScope;
  const ttsLoadOperation = useRef(0);
  const ttsLoaderRef = useRef(loadApprovedTtsCandidates);
  ttsLoaderRef.current = loadApprovedTtsCandidates;
  const targetIdentity = target ? JSON.stringify(target) : "";
  const partialFieldIdentity = partialRegeneration?.fields.join("|") ?? "";
  const defaultPartialFieldIdentity = partialRegeneration?.defaultFields?.join("|") ?? "";

  useEffect(() => {
    setCutAction(asCutAction(selectedSegment?.cutAction ?? "keep"));
  }, [selectedSegment?.cutAction, selectedSegment?.segmentId]);

  // 장면을 바꿔 고르면 그 장면에 실제로 걸린 값으로 되돌린다. 안 하면 앞
  // 장면에서 고르던 값이 남아, 저장하지도 않은 전환이 걸린 것처럼 보인다.
  useEffect(() => {
    setTransition(selectedSegment?.transitionIn?.type ?? SCENE_TRANSITION_NONE);
  }, [selectedSegment?.transitionIn?.type, selectedSegment?.segmentId]);

  useEffect(() => {
    if (target?.kind === "media") {
      setFadeInSec(target.controls.fadeInSec ?? 0);
      setFadeOutSec(target.controls.fadeOutSec ?? 0);
      setInSec(target.controls.inSec ?? 0);
      setOutSec(target.controls.outSec ?? 0);
      setSpeed(target.controls.speed ?? 1);
      setVolume(target.controls.volume ?? 1);
      setLook(target.controls.filter?.type ?? SCENE_FILTER_NONE);
      setDucking(target.controls.ducking ?? false);
      setPreserveSourceAudio(target.controls.preserveSourceAudio ?? false);
      setGainDb(target.controls.gainDb ?? 0);
    }
    if (target?.kind === "caption") setCaptionStyle(target.style);
    if (target?.kind === "overlay") {
      if (target.overlayKind !== "shape") setOverlayText(target.value.text);
      if (target.overlayKind === "explanation-card") {
        setOverlayTitle(target.value.title);
        setOverlayBody(target.value.body);
      } else if (target.overlayKind === "table") {
        setTableColumns(target.value.columns.join(", "));
        setTableRows(target.value.rows.map((row) => row.join(" | ")).join("\n"));
      } else if (target.overlayKind === "shape") {
        setShapeOverlay(target.value);
      }
    }
  }, [targetIdentity]);
  useEffect(() => {
    const available = new Set(partialRegeneration?.fields ?? []);
    setSelectedPartialFields((current) => {
      const retained = current.filter((field) => available.has(field));
      if (retained.length) return retained;
      return (partialRegeneration?.defaultFields ?? partialRegeneration?.fields ?? []).filter((field) => available.has(field));
    });
  }, [defaultPartialFieldIdentity, partialFieldIdentity]);
  useEffect(() => {
    const loader = ttsLoaderRef.current;
    const segmentId = selectedSegment?.segmentId;
    const operationId = ttsLoadOperation.current + 1;
    ttsLoadOperation.current = operationId;
    if (!loader || !segmentId || !ttsRequested) {
      setTtsCandidates([]);
      setSelectedTtsCandidateId("");
      setTtsLoadState("idle");
      return;
    }
    setTtsLoadState("loading");
    void loader(segmentId).then((candidates) => {
      if (ttsLoadOperation.current !== operationId) return;
      setTtsCandidates(candidates);
      setSelectedTtsCandidateId((current) => {
        const applied = selectedSegment.ttsReplacement?.candidateId;
        if (applied && candidates.some((candidate) => candidate.candidateId === applied)) return applied;
        if (candidates.some((candidate) => candidate.candidateId === current)) return current;
        return candidates[0]?.candidateId ?? "";
      });
      setTtsLoadState("ready");
    }).catch(() => {
      if (ttsLoadOperation.current !== operationId) return;
      setTtsCandidates([]);
      setSelectedTtsCandidateId("");
      setTtsLoadState("error");
    });
    return () => {
      if (ttsLoadOperation.current === operationId) ttsLoadOperation.current += 1;
    };
  }, [selectedSegment?.segmentId, ttsCandidateScopeKey, ttsRequested, ttsRetryToken]);

  const emit = (action: InspectorAction) => {
    void onAction(action);
  };
  const partialAction = (kind: "partial-preflight" | "partial-run" | "partial-resume") => {
    if (!selectedSegment || !selectedPartialFields.length) return;
    emit({ kind, segmentIds: [selectedSegment.segmentId], fields: [...selectedPartialFields] });
  };
  const preparedFieldsMatch = !partialRegeneration?.preparedFields
    || (
      partialRegeneration.preparedFields.length === selectedPartialFields.length
      && partialRegeneration.preparedFields.every((field, index) => field === selectedPartialFields[index])
    );
  const preparedSegmentMatches = !partialRegeneration?.preparedSegmentId
    || partialRegeneration.preparedSegmentId === selectedSegment?.segmentId;

  // 이름을 바꾼 이유: 2026-08-17 첫 사용 점검이 `선택 구간 편집`을 "찾을 수 없는
  // 이름"으로 지적했다. 컷편집을 찾는 사람은 이 낱말에 닿지 않는다.
  //
  // 툴바의 컷 도구와 **겹치지 않는다.** 툴바 `나누기`는 재생 위치에서 나누므로
  // 재생 위치가 고른 장면 안에 있어야 켜진다. 여기 있는 것은 그때도 되는 대체
  // 경로이고, `유지/삭제`는 **뺀 장면을 되살리는 유일한 길**이다.
  return (
    <section aria-label="고른 장면">
      <h3>고른 장면</h3>
      {/* 두 문장을 한 줄로 줄였다. `나누기`가 재생 위치에서 자른다는 것은 눌러 보면
          알고, 여기서 꼭 알아야 하는 것은 **이 아래가 언제 필요한가**뿐이다. */}
      <p>재생 위치가 이 장면 밖일 때 아래를 씁니다</p>
      {selectedSegment ? (
        <>
          <p>{`${selectedSegment.startSec.toFixed(2)}–${selectedSegment.endSec.toFixed(2)}초 구간`}</p>
          <div>
            <Button
              disabled={disabled || selectedSegment.endSec <= selectedSegment.startSec}
              onClick={() => emit({
                kind: "split-narration",
                segmentId: selectedSegment.segmentId,
                splitSec: (selectedSegment.startSec + selectedSegment.endSec) / 2,
              })}
              type="button"
            >
              구간 중간에서 나누기
            </Button>
            <Button
              disabled={disabled || !selectedSegment.nextSegmentId}
              onClick={() => {
                if (selectedSegment.nextSegmentId) emit({
                  kind: "merge-narration",
                  leftSegmentId: selectedSegment.segmentId,
                  rightSegmentId: selectedSegment.nextSegmentId,
                });
              }}
              type="button"
            >
              다음 구간과 합치기
            </Button>
          </div>
          <label>
            선택 구간 처리
            <NativeSelect aria-label="선택 구간 처리" disabled={disabled} onChange={(event) => setCutAction(asCutAction(event.target.value))} value={cutAction}>
              <option value="keep">유지</option>
              <option value="remove">삭제</option>
            </NativeSelect>
          </label>
          <Button disabled={disabled} onClick={() => emit({ kind: "set-cut-action", segmentId: selectedSegment.segmentId, cutAction })} type="button">
            컷 저장
          </Button>
          {/*
            앞 장면이 붙어 있을 때만 보여 준다. 첫 장면에는 넘어올 앞 장면이
            없어서 고를 수 있는 척하면 배치가 거짓말을 한다.
          */}
          {selectedSegment.previousSegmentId ? (
            <fieldset>
              <legend>앞 장면에서 넘어오기</legend>
              <label>
                넘기는 방법
                <NativeSelect
                  aria-label="넘기는 방법"
                  disabled={disabled}
                  onChange={(event) => setTransition(event.target.value)}
                  value={transition}
                >
                  <option value={SCENE_TRANSITION_NONE}>바로 넘기기</option>
                  {SCENE_TRANSITION_CHOICES.map((choice) => (
                    <option key={choice.value} value={choice.value}>{choice.label}</option>
                  ))}
                </NativeSelect>
              </label>
              <Button
                disabled={disabled}
                onClick={() => emit({
                  kind: "set-transition",
                  segmentId: selectedSegment.segmentId,
                  transition: transition === SCENE_TRANSITION_NONE ? null : {
                    type: transition,
                    durationSec: selectedSegment.transitionIn?.durationSec ?? DEFAULT_SCENE_TRANSITION_DURATION_SEC,
                  },
                })}
                type="button"
              >
                넘기기 저장
              </Button>
            </fieldset>
          ) : null}
          {loadApprovedTtsCandidates ? (
            <fieldset>
              <legend>내레이션 음성</legend>
              {selectedSegment.ttsReplacement ? <p>청취 승인한 음성이 적용되어 있어요.</p> : <p>청취 승인한 후보를 골라 명시적으로 적용할 수 있어요.</p>}
              {!ttsRequested ? <Button disabled={disabled} onClick={() => setTtsRequest(ttsScope)} type="button">승인한 음성 불러오기</Button> : null}
              {ttsLoadState === "loading" ? <p>승인한 음성을 불러오는 중이에요.</p> : null}
              {ttsLoadState === "error" ? (
                <>
                  <p>승인한 음성을 불러오지 못했어요. 직접 편집은 계속할 수 있어요.</p>
                  <Button disabled={disabled} onClick={() => setTtsRetryToken((current) => current + 1)} type="button">승인한 음성 다시 불러오기</Button>
                </>
              ) : null}
              {ttsLoadState === "ready" && !ttsCandidates.length ? <p>이 구간에는 청취 승인된 음성이 없어요.</p> : null}
              {ttsCandidates.length ? (
                <label>
                  승인한 음성
                  <NativeSelect aria-label="승인한 음성" disabled={disabled} onChange={(event) => setSelectedTtsCandidateId(event.target.value)} value={selectedTtsCandidateId}>
                    {ttsCandidates.map((candidate, index) => <option key={candidate.candidateId} value={candidate.candidateId}>{`승인 후보 ${index + 1} · ${candidate.sourceText}`}</option>)}
                  </NativeSelect>
                </label>
              ) : null}
              <Button
                disabled={disabled || !selectedTtsCandidateId}
                onClick={() => {
                  const candidate = ttsCandidates.find((item) => item.candidateId === selectedTtsCandidateId);
                  if (candidate) emit({ kind: "apply-tts-candidate", segmentId: selectedSegment.segmentId, candidateId: candidate.candidateId, assetId: candidate.assetId });
                }}
                type="button"
              >
                승인한 음성 적용
              </Button>
              {selectedSegment.ttsReplacement ? <Button disabled={disabled} onClick={() => emit({ kind: "clear-tts-candidate", segmentId: selectedSegment.segmentId })} type="button">적용한 음성 해제</Button> : null}
            </fieldset>
          ) : null}
        </>
      ) : <p>먼저 편집할 구간을 선택해 주세요.</p>}

      {target?.kind === "media" ? (
        <fieldset>
          <legend>{target.label}</legend>
          <p>현재 자산이 연결되어 있어요.</p>
          {!target.clearOnly ? (
            <>
              {target.fields.includes("fadeInSec") ? (
                <>
                  <label>
                    {/* 소리 페이드와 화면 페이드는 다른 것이다. B-roll에 거는 것은
                        장면이 부드럽게 바뀌는 쪽(디졸브)이므로 그렇게 부른다. */}
                    {target.mediaKind === "broll" ? `${target.label} 서서히 나타나기` : `${target.label} 페이드 인`}
                    <Input disabled={disabled} min="0" onChange={(event) => setFadeInSec(numberValue(event.target.value, fadeInSec))} step="0.05" type="number" value={fadeInSec} />
                  </label>
                  <label>
                    {target.mediaKind === "broll" ? `${target.label} 서서히 사라지기` : `${target.label} 페이드 아웃`}
                    <Input disabled={disabled} min="0" onChange={(event) => setFadeOutSec(numberValue(event.target.value, fadeOutSec))} step="0.05" type="number" value={fadeOutSec} />
                  </label>
                </>
              ) : null}
              {/* 배경 음악·효과음의 음량. 렌더러는 처음부터 클립별 gain_db를
                  반영했는데 화면에 입력 자리만 없었다. §10.13: `gain`·`dB` 같은
                  내부 용어 대신 `소리 크기`와 `조용히/크게`로 적는다. */}
              {target.fields.includes("gainDb") ? (
                <label>
                  {`${target.label} 소리 크기`}
                  <span aria-hidden="true">조용히</span>
                  <Input
                    aria-label={`${target.label} 소리 크기`}
                    disabled={disabled}
                    max="100"
                    min="0"
                    onChange={(event) => setGainDb(gainDbFromSlider(numberValue(event.target.value, gainSliderPosition(gainDb))))}
                    step="1"
                    type="range"
                    value={gainSliderPosition(gainDb)}
                  />
                  <span aria-hidden="true">크게</span>
                </label>
              ) : null}
              {target.fields.includes("inSec") ? (
                <>
                  <label>
                    {`${target.label} 쓸 구간 시작`}
                    <Input disabled={disabled} min="0" onChange={(event) => setInSec(numberValue(event.target.value, inSec))} step="0.1" type="number" value={inSec} />
                  </label>
                  <label>
                    {`${target.label} 쓸 구간 끝`}
                    <Input disabled={disabled} min="0" onChange={(event) => setOutSec(numberValue(event.target.value, outSec))} step="0.1" type="number" value={outSec} />
                  </label>
                </>
              ) : null}
              {target.fields.includes("speed") ? (
                <label>
                  {`${target.label} 재생 속도`}
                  <Input disabled={disabled} max="4" min="0.25" onChange={(event) => setSpeed(numberValue(event.target.value, speed))} step="0.05" type="number" value={speed} />
                </label>
              ) : null}
              {target.fields.includes("volume") ? (
                <label>
                  {`${target.label} 소리 크기`}
                  <Input disabled={disabled} max="2" min="0" onChange={(event) => setVolume(numberValue(event.target.value, volume))} step="0.05" type="number" value={volume} />
                </label>
              ) : null}
              {/* 색감(`sceneFilters.ts`). 만든 여섯 개만 보여 준다 -- 캡컷 필터
                  탭의 이름표는 캡컷 서버 자원이라 우리 렌더러가 못 그린다. */}
              {target.fields.includes("filter") ? (
                <label>
                  {`${target.label} 색감`}
                  <NativeSelect
                    aria-label={`${target.label} 색감`}
                    disabled={disabled}
                    onChange={(event) => setLook(event.target.value)}
                    value={look}
                  >
                    <option value={SCENE_FILTER_NONE}>원본 그대로</option>
                    {SCENE_FILTER_CHOICES.map((choice) => (
                      <option key={choice.value} value={choice.value}>{choice.label}</option>
                    ))}
                  </NativeSelect>
                </label>
              ) : null}
              {/* 음량 바로 아래. 이게 꺼져 있으면 `소리 크기`는 아무 일도 하지
                  않는다 -- 섞일 소리가 없기 때문이다. §10.13: `소스 오디오` 같은
                  말 대신 무엇을 쓰겠다는 건지로 적는다. */}
              {target.fields.includes("preserveSourceAudio") ? (
                <label>
                  <Input
                    checked={preserveSourceAudio}
                    disabled={disabled}
                    onChange={(event) => setPreserveSourceAudio(event.target.checked)}
                    type="checkbox"
                  />
                  이 영상의 원래 소리도 함께 쓰기
                </label>
              ) : null}
              {/* 말이 음악에 묻히는 것은 완성본에서 가장 자주 걸리는 문제다.
                  §10.13: `사이드체인`·`덕킹` 같은 말 대신 무슨 일이 일어나는지로
                  적는다. 끄고 켜는 것뿐이므로 숫자를 묻지 않는다. */}
              {target.fields.includes("ducking") ? (
                <label>
                  <Input
                    checked={ducking}
                    disabled={disabled}
                    onChange={(event) => setDucking(event.target.checked)}
                    type="checkbox"
                  />
                  말할 때 배경 음악 낮추기
                </label>
              ) : null}
              {/* `쓸 구간`을 **안 정한 것**(둘 다 0)과 **잘못 정한 것**(끝이 시작보다
                  앞)은 다르다. 예전에는 둘을 같이 취급해서, 구간을 지정하지 않은
                  B-roll은 저장 단추가 영영 잠겨 있었다 -- 배속·음량·페이드·소리
                  스위치 어느 것도 저장할 수 없었고, 화면에는 값이 남아 있어서
                  저장된 것처럼 보였다(2026-08-18 실제 화면에서 확인).
                  안 정했으면 구간을 아예 보내지 않는다. 서버는 `끝 > 시작`을
                  요구하므로 0/0을 실어 보내면 거절당한다. */}
              <Button
                disabled={disabled || (target.fields.includes("inSec") && outSec > 0 && outSec <= inSec)}
                onClick={() => emit({
                  kind: "save-media",
                  mediaKind: target.mediaKind,
                  segmentId: target.segmentId,
                  assetId: target.assetId,
                  controls: {
                    ...target.controls,
                    // 페이드와 구간은 **따로** 판단한다. 예전에는 하나의 삼항으로
                    // 묶여 있어서, 구간을 가진 B-roll은 페이드를 고쳐도 payload에
                    // 옛 값이 실렸다 -- 화면에서 바꾼 것이 조용히 사라졌다.
                    ...(target.fields.includes("fadeInSec") ? { fadeInSec, fadeOutSec } : {}),
                    ...(target.fields.includes("gainDb") ? { gainDb } : {}),
                    ...(target.fields.includes("inSec") && outSec > 0 ? { inSec, outSec } : {}),
                    ...(target.fields.includes("speed") ? { speed } : {}),
                    ...(target.fields.includes("volume") ? { volume } : {}),
                    ...(target.fields.includes("filter") ? { filter: look === SCENE_FILTER_NONE ? null : { type: look } } : {}),
                    ...(target.fields.includes("ducking") ? { ducking } : {}),
                    ...(target.fields.includes("preserveSourceAudio") ? { preserveSourceAudio } : {}),
                  },
                })}
                type="button"
              >
                {`${target.label} 설정 저장`}
              </Button>
            </>
          ) : null}
          <Button disabled={disabled} onClick={() => emit({ kind: "clear-media", mediaKind: target.mediaKind, segmentId: target.segmentId })} type="button">
            {`${target.label} 지우기`}
          </Button>
        </fieldset>
      ) : null}

      {target?.kind === "caption" ? (
        <fieldset>
          <legend>자막 스타일</legend>
          {projectId ? <CaptionPresetPicker
            projectId={projectId}
            /* 지금 잡아 놓은 모양 **전부**를 CaptionStyle 정본 이름으로 넘긴다.
               세 값만 넘기면 외곽선·배경·위치가 빠진 모양이 저장되고, owner는
               적용해 보고서야 안다. 이름을 섞으면(font_size와 shadow_blur_px)
               다음 사람이 어느 어휘가 맞는지 알 수 없다. */
            currentStyle={{
              font_family: captionStyle.fontFamily,
              font_size_px: captionStyle.fontSizePx,
              text_color: captionStyle.textColor,
              outline_color: captionStyle.outlineColor,
              outline_width_px: captionStyle.outlineWidthPx,
              background_color: captionStyle.backgroundColor,
              position_x_percent: captionStyle.positionXPercent,
              position_y_percent: captionStyle.positionYPercent,
              horizontal_align: captionStyle.horizontalAlign,
              safe_area_enabled: captionStyle.safeAreaEnabled,
              shadow_blur_px: captionStyle.shadowBlurPx,
            }}
            onApply={(style) => setCaptionStyle((current) => ({ ...current, ...fromSnapshot(style) }))}
          /> : null}
          {/* 포맷은 프리셋과 같은 길로 들어온다 -- 화면 값에 넣고 아래 저장이 커밋한다. */}
          <SavedFormatPicker onApply={(style) => setCaptionStyle((current) => ({ ...current, ...fromSnapshot(style) }))} />
          {/* 자유 입력이던 칸이다. 없는 글꼴을 쳐도 화면은 받아들이고 완성본만
              다른 글꼴로 나왔다. 이제 설치된 글꼴 중에서만 고른다. */}
          <CaptionFontPicker
            disabled={disabled}
            onSelect={(family) => setCaptionStyle((current) => ({ ...current, fontFamily: family }))}
            value={captionStyle.fontFamily}
          />
          <label>글자 크기<Input disabled={disabled} min="1" onChange={(event) => setCaptionStyle((current) => ({ ...current, fontSizePx: numberValue(event.target.value, current.fontSizePx) }))} type="number" value={captionStyle.fontSizePx} /></label>
          <label>글자 색<Input disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, textColor: event.target.value }))} value={captionStyle.textColor} /></label>
          <label>외곽선 색<Input disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, outlineColor: event.target.value }))} value={captionStyle.outlineColor} /></label>
          <label>외곽선 두께<Input disabled={disabled} min="0" onChange={(event) => setCaptionStyle((current) => ({ ...current, outlineWidthPx: numberValue(event.target.value, current.outlineWidthPx) }))} type="number" value={captionStyle.outlineWidthPx} /></label>
          <label>배경 색<Input disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, backgroundColor: event.target.value }))} value={captionStyle.backgroundColor} /></label>
          <label>가로 위치<Input disabled={disabled} max="100" min="0" onChange={(event) => setCaptionStyle((current) => ({ ...current, positionXPercent: numberValue(event.target.value, current.positionXPercent) }))} type="number" value={captionStyle.positionXPercent} /></label>
          <label>세로 위치<Input disabled={disabled} max="100" min="0" onChange={(event) => setCaptionStyle((current) => ({ ...current, positionYPercent: numberValue(event.target.value, current.positionYPercent) }))} type="number" value={captionStyle.positionYPercent} /></label>
          <label>
            가로 정렬
            <NativeSelect aria-label="가로 정렬" disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, horizontalAlign: event.target.value as EditorCaptionStyle["horizontalAlign"] }))} value={captionStyle.horizontalAlign}>
              <option value="left">왼쪽</option><option value="center">가운데</option><option value="right">오른쪽</option>
            </NativeSelect>
          </label>
          <label>안전 영역 사용<Input checked={captionStyle.safeAreaEnabled} disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, safeAreaEnabled: event.target.checked }))} type="checkbox" /></label>
          {/* `그림자 흐림` 칸은 뺐다. 자막을 굽는 ASS에는 그림자를 흐리게 하는
              값이 없고, CapCut으로 내보내는 길도 "지원하지 않는다"고 경고만
              남기고 있었다. 즉 어느 길에서도 아무 일이 없는 칸이었다. 값 자체는
              저장된 것을 그대로 들고 다닌다. */}
          <Button disabled={disabled} onClick={() => emit({ kind: "save-caption-style", segmentIds: [target.segmentId], scope: "current_caption", style: captionStyle })} type="button">
            자막 스타일 저장
          </Button>
        </fieldset>
      ) : null}

      {target?.kind === "overlay" ? (
        <fieldset>
          <legend>{target.label}</legend>
          {target.overlayKind === "explanation-card" ? (
            <>
              <label>제목<Input disabled={disabled} onChange={(event) => setOverlayTitle(event.target.value)} value={overlayTitle} /></label>
              <label>본문<Textarea disabled={disabled} onChange={(event) => setOverlayBody(event.target.value)} value={overlayBody} /></label>
            </>
          ) : null}
          {target.overlayKind === "table" ? (
            <>
              <label>열 이름<Input disabled={disabled} onChange={(event) => setTableColumns(event.target.value)} value={tableColumns} /></label>
              <label>표 행<Textarea disabled={disabled} onChange={(event) => setTableRows(event.target.value)} value={tableRows} /></label>
            </>
          ) : null}
          {/* 도형·아이콘: "여기를 보세요"용 강조 상자·밑줄과 화살표 등.
              자유 좌표 대신 프리셋만 준다 -- 좌표를 찍는 편집기와 키프레임은
              계획서 §4 범위 밖이다. 아이콘도 같은 위치·크기 프리셋을 쓴다.
              `움직임`은 2026-08-20 승인(5항)으로 열린 등장·퇴장·이동이며,
              여기서도 고르는 것은 프리셋뿐이다. */}
          {target.overlayKind === "shape" ? (
            <>
              <p>장면 위에 얹어 "여기를 보세요"를 표시해요. 장면이 보이는 동안 함께 나와요.</p>
              <label>
                모양
                <NativeSelect aria-label="모양" disabled={disabled} onChange={(event) => setShapeOverlay((current) => ({ ...current, shape: shapeValue(event.target.value) }))} value={shapeOverlay.shape}>
                  {SHAPE_OVERLAY_CHOICES.map((choice) => (
                    <option key={choice} value={choice}>{SHAPE_OVERLAY_LABELS[choice]}</option>
                  ))}
                </NativeSelect>
              </label>
              <label>
                세로 위치
                <NativeSelect aria-label="세로 위치" disabled={disabled} onChange={(event) => setShapeOverlay((current) => ({ ...current, vertical: event.target.value === "top" || event.target.value === "bottom" ? event.target.value : "middle" }))} value={shapeOverlay.vertical}>
                  <option value="top">위</option>
                  <option value="middle">가운데</option>
                  <option value="bottom">아래</option>
                </NativeSelect>
              </label>
              <label>
                가로 위치
                <NativeSelect aria-label="가로 위치" disabled={disabled} onChange={(event) => setShapeOverlay((current) => ({ ...current, horizontal: event.target.value === "left" || event.target.value === "right" ? event.target.value : "center" }))} value={shapeOverlay.horizontal}>
                  <option value="left">왼쪽</option>
                  <option value="center">가운데</option>
                  <option value="right">오른쪽</option>
                </NativeSelect>
              </label>
              <label>
                크기
                <NativeSelect aria-label="크기" disabled={disabled} onChange={(event) => setShapeOverlay((current) => ({ ...current, size: event.target.value === "small" || event.target.value === "large" ? event.target.value : "medium" }))} value={shapeOverlay.size}>
                  <option value="small">작게</option>
                  <option value="medium">보통</option>
                  <option value="large">크게</option>
                </NativeSelect>
              </label>
              <label>
                움직임
                <NativeSelect aria-label="움직임" disabled={disabled} onChange={(event) => setShapeOverlay((current) => ({ ...current, motion: shapeMotion(event.target.value) }))} value={shapeOverlay.motion}>
                  {SHAPE_OVERLAY_MOTION_CHOICES.map((choice) => (
                    <option key={choice} value={choice}>{SHAPE_OVERLAY_MOTION_LABELS[choice]}</option>
                  ))}
                </NativeSelect>
              </label>
            </>
          ) : null}
          {target.overlayKind !== "shape" ? (
            <label>설명<Textarea disabled={disabled} onChange={(event) => setOverlayText(event.target.value)} value={overlayText} /></label>
          ) : null}
          <Button
            disabled={disabled || (target.overlayKind === "image" && !target.value.assetId)}
            onClick={() => {
              if (target.overlayKind === "explanation-card") emit({ kind: "save-overlay", overlayKind: target.overlayKind, segmentId: target.segmentId, title: overlayTitle, body: overlayBody, text: overlayText });
              else if (target.overlayKind === "image") emit({ kind: "save-overlay", overlayKind: target.overlayKind, segmentId: target.segmentId, assetId: target.value.assetId, text: overlayText });
              else if (target.overlayKind === "shape") emit({ kind: "save-overlay", overlayKind: target.overlayKind, segmentId: target.segmentId, ...shapeOverlay });
              else emit({ kind: "save-overlay", overlayKind: target.overlayKind, segmentId: target.segmentId, columns: parseColumns(tableColumns), rows: parseRows(tableRows), text: overlayText });
            }}
            type="button"
          >
            {`${target.label} 저장`}
          </Button>
          {/* 아직 없는 오버레이(빈 편집 자리)에는 지울 것이 없다. */}
          {!target.isNew ? (
            <Button disabled={disabled} onClick={() => emit({ kind: "clear-overlay", overlayKind: target.overlayKind, segmentId: target.segmentId })} type="button">
              {`${target.label} 지우기`}
            </Button>
          ) : null}
        </fieldset>
      ) : null}

      {partialRegeneration && selectedSegment ? (
        <fieldset>
          <legend>부분 재생성</legend>
          {partialRegeneration.fields.map((field) => <label key={field}>
            <Input
              checked={selectedPartialFields.includes(field)}
              disabled={disabled}
              onChange={(event) => setSelectedPartialFields((current) => event.target.checked
                ? partialRegeneration.fields.filter((candidate) => candidate === field || current.includes(candidate))
                : current.filter((candidate) => candidate !== field))}
              type="checkbox"
            />
            {partialFieldLabels[field] ?? field}
          </label>)}
          <Button disabled={disabled || selectedPartialFields.length === 0} onClick={() => partialAction("partial-preflight")} type="button">재생성 범위 미리보기</Button>
          <Button disabled={disabled || !partialRegeneration.canRun || !preparedFieldsMatch || !preparedSegmentMatches} onClick={() => partialAction("partial-run")} type="button">부분 재생성 실행</Button>
          <Button disabled={disabled || !partialRegeneration.canResume} onClick={() => partialAction("partial-resume")} type="button">이전 결과 열기</Button>
        </fieldset>
      ) : null}
    </section>
  );
}
