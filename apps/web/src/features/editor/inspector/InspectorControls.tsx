import { useEffect, useState } from "react";

import type { CaptionStyleScope } from "../../../api";
import type { EditorCaptionStyle, EditorControls } from "../editorViewModel";
import type { InspectorTarget } from "./inspectorRegistry";

type CutAction = "keep" | "remove";

export type InspectorAction =
  | Readonly<{ kind: "split-narration"; segmentId: string; splitSec: number }>
  | Readonly<{ kind: "merge-narration"; leftSegmentId: string; rightSegmentId: string }>
  | Readonly<{ kind: "set-cut-action"; segmentId: string; cutAction: CutAction }>
  | Readonly<{ kind: "save-media"; mediaKind: "bgm" | "sfx"; segmentId: string; assetId: string; controls: EditorControls }>
  | Readonly<{ kind: "clear-media"; mediaKind: "broll" | "bgm" | "sfx"; segmentId: string }>
  | Readonly<{ kind: "save-caption-style"; segmentIds: string[]; scope: CaptionStyleScope; style: EditorCaptionStyle }>
  | Readonly<{ kind: "save-overlay"; overlayKind: "explanation-card"; segmentId: string; title: string; body: string; text: string }>
  | Readonly<{ kind: "save-overlay"; overlayKind: "image"; segmentId: string; assetId: string; text: string }>
  | Readonly<{ kind: "save-overlay"; overlayKind: "table"; segmentId: string; columns: string[]; rows: string[][]; text: string }>
  | Readonly<{ kind: "clear-overlay"; overlayKind: "explanation-card" | "image" | "table"; segmentId: string }>
  | Readonly<{ kind: "partial-preflight"; segmentIds: string[]; fields: string[] }>
  | Readonly<{ kind: "partial-run"; segmentIds: string[]; fields: string[] }>
  | Readonly<{ kind: "partial-resume"; segmentIds: string[]; fields: string[] }>;

type SelectedSegment = Readonly<{
  segmentId: string;
  startSec: number;
  endSec: number;
  nextSegmentId: string | null;
  cutAction: string;
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
  target: InspectorTarget | null;
  selectedSegment: SelectedSegment | null;
  partialRegeneration?: PartialRegenerationControls;
  disabled?: boolean;
  onAction: (action: InspectorAction) => void | Promise<void>;
}>;

const defaultStyle: EditorCaptionStyle = {
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

function parseColumns(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseRows(value: string): string[][] {
  return value.split(/\r?\n/).map((row) => row.split("|").map((item) => item.trim())).filter((row) => row.some(Boolean));
}

export function InspectorControls({
  target,
  selectedSegment,
  partialRegeneration,
  disabled = false,
  onAction,
}: Props) {
  const [cutAction, setCutAction] = useState<CutAction>(() => asCutAction(selectedSegment?.cutAction ?? "keep"));
  const [fadeInSec, setFadeInSec] = useState(0);
  const [fadeOutSec, setFadeOutSec] = useState(0);
  const [captionStyle, setCaptionStyle] = useState<EditorCaptionStyle>(defaultStyle);
  const [overlayTitle, setOverlayTitle] = useState("");
  const [overlayBody, setOverlayBody] = useState("");
  const [overlayText, setOverlayText] = useState("");
  const [tableColumns, setTableColumns] = useState("");
  const [tableRows, setTableRows] = useState("");
  const [selectedPartialFields, setSelectedPartialFields] = useState<readonly string[]>(() =>
    partialRegeneration?.defaultFields ?? partialRegeneration?.fields ?? [],
  );
  const targetIdentity = target ? JSON.stringify(target) : "";
  const partialFieldIdentity = partialRegeneration?.fields.join("|") ?? "";
  const defaultPartialFieldIdentity = partialRegeneration?.defaultFields?.join("|") ?? "";

  useEffect(() => {
    setCutAction(asCutAction(selectedSegment?.cutAction ?? "keep"));
  }, [selectedSegment?.cutAction, selectedSegment?.segmentId]);

  useEffect(() => {
    if (target?.kind === "media") {
      setFadeInSec(target.controls.fadeInSec ?? 0);
      setFadeOutSec(target.controls.fadeOutSec ?? 0);
    }
    if (target?.kind === "caption") setCaptionStyle(target.style);
    if (target?.kind === "overlay") {
      setOverlayText(target.value.text);
      if (target.overlayKind === "explanation-card") {
        setOverlayTitle(target.value.title);
        setOverlayBody(target.value.body);
      } else if (target.overlayKind === "table") {
        setTableColumns(target.value.columns.join(", "));
        setTableRows(target.value.rows.map((row) => row.join(" | ")).join("\n"));
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

  return (
    <section aria-label="선택 구간 편집">
      <h3>선택 구간 편집</h3>
      {selectedSegment ? (
        <>
          <p>{`${selectedSegment.startSec.toFixed(2)}–${selectedSegment.endSec.toFixed(2)}초 구간`}</p>
          <div>
            <button
              disabled={disabled || selectedSegment.endSec <= selectedSegment.startSec}
              onClick={() => emit({
                kind: "split-narration",
                segmentId: selectedSegment.segmentId,
                splitSec: (selectedSegment.startSec + selectedSegment.endSec) / 2,
              })}
              type="button"
            >
              구간 중간에서 나누기
            </button>
            <button
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
            </button>
          </div>
          <label>
            선택 구간 처리
            <select disabled={disabled} onChange={(event) => setCutAction(asCutAction(event.target.value))} value={cutAction}>
              <option value="keep">유지</option>
              <option value="remove">삭제</option>
            </select>
          </label>
          <button disabled={disabled} onClick={() => emit({ kind: "set-cut-action", segmentId: selectedSegment.segmentId, cutAction })} type="button">
            컷 저장
          </button>
        </>
      ) : <p>먼저 편집할 구간을 선택해 주세요.</p>}

      {target?.kind === "media" ? (
        <fieldset>
          <legend>{target.label}</legend>
          <p>현재 자산이 연결되어 있어요.</p>
          {!target.clearOnly ? (
            <>
              <label>
                {`${target.label} 페이드 인`}
                <input disabled={disabled} min="0" onChange={(event) => setFadeInSec(numberValue(event.target.value, fadeInSec))} step="0.05" type="number" value={fadeInSec} />
              </label>
              <label>
                {`${target.label} 페이드 아웃`}
                <input disabled={disabled} min="0" onChange={(event) => setFadeOutSec(numberValue(event.target.value, fadeOutSec))} step="0.05" type="number" value={fadeOutSec} />
              </label>
              <button
                disabled={disabled}
                onClick={() => {
                  if (target.mediaKind !== "broll") emit({
                    kind: "save-media",
                    mediaKind: target.mediaKind,
                    segmentId: target.segmentId,
                    assetId: target.assetId,
                    controls: { ...target.controls, fadeInSec, fadeOutSec },
                  });
                }}
                type="button"
              >
                {`${target.label} 설정 저장`}
              </button>
            </>
          ) : null}
          <button disabled={disabled} onClick={() => emit({ kind: "clear-media", mediaKind: target.mediaKind, segmentId: target.segmentId })} type="button">
            {`${target.label} 지우기`}
          </button>
        </fieldset>
      ) : null}

      {target?.kind === "caption" ? (
        <fieldset>
          <legend>자막 스타일</legend>
          <label>글꼴<input disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, fontFamily: event.target.value }))} value={captionStyle.fontFamily} /></label>
          <label>글자 크기<input disabled={disabled} min="1" onChange={(event) => setCaptionStyle((current) => ({ ...current, fontSizePx: numberValue(event.target.value, current.fontSizePx) }))} type="number" value={captionStyle.fontSizePx} /></label>
          <label>글자 색<input disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, textColor: event.target.value }))} value={captionStyle.textColor} /></label>
          <label>외곽선 색<input disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, outlineColor: event.target.value }))} value={captionStyle.outlineColor} /></label>
          <label>외곽선 두께<input disabled={disabled} min="0" onChange={(event) => setCaptionStyle((current) => ({ ...current, outlineWidthPx: numberValue(event.target.value, current.outlineWidthPx) }))} type="number" value={captionStyle.outlineWidthPx} /></label>
          <label>배경 색<input disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, backgroundColor: event.target.value }))} value={captionStyle.backgroundColor} /></label>
          <label>가로 위치<input disabled={disabled} max="100" min="0" onChange={(event) => setCaptionStyle((current) => ({ ...current, positionXPercent: numberValue(event.target.value, current.positionXPercent) }))} type="number" value={captionStyle.positionXPercent} /></label>
          <label>세로 위치<input disabled={disabled} max="100" min="0" onChange={(event) => setCaptionStyle((current) => ({ ...current, positionYPercent: numberValue(event.target.value, current.positionYPercent) }))} type="number" value={captionStyle.positionYPercent} /></label>
          <label>
            가로 정렬
            <select disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, horizontalAlign: event.target.value as EditorCaptionStyle["horizontalAlign"] }))} value={captionStyle.horizontalAlign}>
              <option value="left">왼쪽</option><option value="center">가운데</option><option value="right">오른쪽</option>
            </select>
          </label>
          <label>안전 영역 사용<input checked={captionStyle.safeAreaEnabled} disabled={disabled} onChange={(event) => setCaptionStyle((current) => ({ ...current, safeAreaEnabled: event.target.checked }))} type="checkbox" /></label>
          <label>그림자 흐림<input disabled={disabled} min="0" onChange={(event) => setCaptionStyle((current) => ({ ...current, shadowBlurPx: numberValue(event.target.value, current.shadowBlurPx) }))} type="number" value={captionStyle.shadowBlurPx} /></label>
          <button disabled={disabled} onClick={() => emit({ kind: "save-caption-style", segmentIds: [target.segmentId], scope: "current_caption", style: captionStyle })} type="button">
            자막 스타일 저장
          </button>
        </fieldset>
      ) : null}

      {target?.kind === "overlay" ? (
        <fieldset>
          <legend>{target.label}</legend>
          {target.overlayKind === "explanation-card" ? (
            <>
              <label>제목<input disabled={disabled} onChange={(event) => setOverlayTitle(event.target.value)} value={overlayTitle} /></label>
              <label>본문<textarea disabled={disabled} onChange={(event) => setOverlayBody(event.target.value)} value={overlayBody} /></label>
            </>
          ) : null}
          {target.overlayKind === "table" ? (
            <>
              <label>열 이름<input disabled={disabled} onChange={(event) => setTableColumns(event.target.value)} value={tableColumns} /></label>
              <label>표 행<textarea disabled={disabled} onChange={(event) => setTableRows(event.target.value)} value={tableRows} /></label>
            </>
          ) : null}
          <label>설명<textarea disabled={disabled} onChange={(event) => setOverlayText(event.target.value)} value={overlayText} /></label>
          <button
            disabled={disabled || (target.overlayKind === "image" && !target.value.assetId)}
            onClick={() => {
              if (target.overlayKind === "explanation-card") emit({ kind: "save-overlay", overlayKind: target.overlayKind, segmentId: target.segmentId, title: overlayTitle, body: overlayBody, text: overlayText });
              else if (target.overlayKind === "image") emit({ kind: "save-overlay", overlayKind: target.overlayKind, segmentId: target.segmentId, assetId: target.value.assetId, text: overlayText });
              else emit({ kind: "save-overlay", overlayKind: target.overlayKind, segmentId: target.segmentId, columns: parseColumns(tableColumns), rows: parseRows(tableRows), text: overlayText });
            }}
            type="button"
          >
            {`${target.label} 저장`}
          </button>
          <button disabled={disabled} onClick={() => emit({ kind: "clear-overlay", overlayKind: target.overlayKind, segmentId: target.segmentId })} type="button">
            {`${target.label} 지우기`}
          </button>
        </fieldset>
      ) : null}

      {partialRegeneration && selectedSegment ? (
        <fieldset>
          <legend>부분 재생성</legend>
          {partialRegeneration.fields.map((field) => <label key={field}>
            <input
              checked={selectedPartialFields.includes(field)}
              disabled={disabled}
              onChange={(event) => setSelectedPartialFields((current) => event.target.checked
                ? partialRegeneration.fields.filter((candidate) => candidate === field || current.includes(candidate))
                : current.filter((candidate) => candidate !== field))}
              type="checkbox"
            />
            {partialFieldLabels[field] ?? field}
          </label>)}
          <button disabled={disabled || selectedPartialFields.length === 0} onClick={() => partialAction("partial-preflight")} type="button">재생성 범위 미리보기</button>
          <button disabled={disabled || !partialRegeneration.canRun || !preparedFieldsMatch || !preparedSegmentMatches} onClick={() => partialAction("partial-run")} type="button">부분 재생성 실행</button>
          <button disabled={disabled || !partialRegeneration.canResume} onClick={() => partialAction("partial-resume")} type="button">이전 결과 열기</button>
        </fieldset>
      ) : null}
    </section>
  );
}
