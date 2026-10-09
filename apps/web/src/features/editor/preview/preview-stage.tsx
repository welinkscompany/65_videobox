import { type KeyboardEvent, type RefObject, useEffect, useLayoutEffect, useRef, useState } from "react";

import { toExactPreviewState, type ExactPreviewInput } from "./exact-preview-state";
import { PreviewCoordinator, type AuditionMedia, type PreviewMode, type TimelineRange } from "./preview-coordinator";
import { isAllowedLocalUrl } from "../../../lib/network-guard";
import { capturePreviewStill } from "./previewStill";
import type { PlaybackClock } from "./playbackClock";
import { isSwallowedRepeat, playbackShortcutFor } from "./playbackShortcuts";
import { applyPlaybackRate, formatPlaybackRate, markRateHintSeen, maxPlaybackRate, PLAYBACK_RATES, readPlaybackRate, readRateHintSeen, stepPlaybackRate, writePlaybackRate, type PlaybackRate } from "./playbackRate";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";

export type AuditionSource = AuditionMedia & Readonly<{ label: string }>;
export type AuditionRequest = Readonly<{ requestId: number; source: AuditionSource }>;
export type PreviewCaption = Readonly<{ text: string; startSec: number; endSec: number }>;
type MediaNode = HTMLVideoElement | HTMLAudioElement;

export function PreviewStage({ expectedRevision, exactPreview, captions = [], sources, auditionRequest, onRefresh, playbackSec, onPlaybackTimeChange, fps, loopRange, durationSec, projectIsEmpty = false, playbackClock }: {
  expectedRevision: number;
  /** 타임라인에 아직 아무것도 없는가. 참이면 미리보기 자리에 실패 대신 다음에
   *  할 일을 안내한다 -- 갓 만든 프로젝트의 첫인상이 오류가 되지 않게. */
  projectIsEmpty?: boolean;
  exactPreview: ExactPreviewInput;
  captions?: readonly PreviewCaption[];
  sources: readonly AuditionSource[];
  auditionRequest?: AuditionRequest | null;
  onRefresh?: () => void | Promise<void>;
  playbackSec?: number;
  onPlaybackTimeChange?: (seconds: number) => void;
  /** 타임라인이 실제로 쓰는 프레임률. 한 프레임씩 움직이는 폭이 여기서 나온다. */
  fps?: Readonly<{ num: number; den: number }>;
  /** 고른 장면의 구간. 화면이 `적용 구간`으로 보여 주는 것과 같은 값이다. */
  loopRange?: Readonly<{ startSec: number; endSec: number }> | null;
  /** 편집본 전체 길이. 재생 위치 옆에 `/ 전체` 로 붙인다(`capcut-observed`
   *  기록 §2: "아래 00:00:00:00 / 00:10:00:00"). 캡컷처럼 프레임 단위
   *  타임코드까지는 만들지 않는다 -- 이 화면은 이미 초 단위로 말하고, 여기만
   *  다른 단위를 쓰면 두 표기가 섞인다. 없으면(길이를 모르면) 예전처럼 재생
   *  위치만 보인다. */
  durationSec?: number;
  /** 재생 중 화면 프레임마다 재생기 시각을 알리는 곳. 없으면 예전과 똑같이 `timeupdate`로만 움직인다. */
  playbackClock?: PlaybackClock;
}) {
  const exact = toExactPreviewState(exactPreview, expectedRevision);
  const localSources = sources.filter((source) => isAllowedLocalUrl(source.url));
  const coordinatorRef = useRef(new PreviewCoordinator());
  const mediaRef = useRef<MediaNode>(null);
  // 새 미리보기가 만들어지는 동안 재생기가 사라진다 -- 바뀌기 전 마지막 장면을 그림으로 남긴다.
  const stillRef = useRef<string | null>(null);
  const rememberStill = (video: HTMLVideoElement) => {
    // 현재 미리보기가 아닐 때(정리하느라 처음으로 되감는 중)는 잡지 않는다 -- 0초 장면이 남는다.
    if (exact.kind !== "current") return;
    stillRef.current = capturePreviewStill(video) ?? stillRef.current;
  };
  // **재생 위치가 바뀌어 재생기를 다른 자리로 옮기라고 할 때(2026-09-20
  // 실물 재현), 옮기기 직전 자리를 잠깐 들고 있는다** -- "지금 옮겨 가는
  // 중인 옛 자리"다. 렌더 도중(커밋 전) 채운다 -- `useEffect`에서 채우면
  // 이미 늦다(그 효과가 실제 `<video>.currentTime`을 옮기는 건 커밋 *뒤*라,
  // 그 틈에 재생기가 스스로 `timeupdate`를 옛 위치로 보내면 `updateTimeline`이
  // 그 옛 위치로 장면을 다시 고르는 바깥 로직을 불러 방금 고른 장면을
  // 덮어쓴다 -- 전환 탭이 다시 "첫 장면"으로 보였다). `updateTimeline`은
  // 재생기가 아직 이 옛 자리를 그대로 들고 있는 신호만 무시한다. 자연 재생으로
  // 더 나아간 값(옛 자리도 아니고 아직 새 자리에 정확히 안 닿은 값 포함)은
  // 그대로 믿는다 -- 그래야 `다음 프레임`처럼 목표에 딱 안 떨어지는 정상
  // 진행을 막지 않는다.
  const previousPendingSeekSecondsRef = useRef<number | null>(null);
  const staleSeekBaselineRef = useRef<number | null>(null);
  // 이 미리보기가 마지막으로 위로 올려보낸 타임라인 시각. `playbackSec`가 이 값 그대로 돌아오면
  // 메아리다 -- 재생기는 그새 앞으로 갔으니 옮기면 되감는다(2026-10-09 실측: 20초에 67~74번,
  // 실제 속도 0.62~0.70배). 진단: docs/superpowers/2026-10-09-playback-diagnosis.ko.md 원인 1.
  const lastReportedTimelineSecRef = useRef<number | null>(null);
  const [mode, setMode] = useState<PreviewMode>(() => exact.kind === "current" ? coordinatorRef.current.showExact({ id: exactMediaId(exact), url: exact.url, timelineRange: exact.timelineRange }) : coordinatorRef.current.state);
  const [timelineTime, setTimelineTime] = useState(() => exact.kind === "current" ? exact.timelineRange.startSec : 0);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [auditionIssue, setAuditionIssue] = useState<string | null>(null);
  const [repeating, setRepeating] = useState(false);
  // 브라우저 기본 `controls`를 끄면서 그 안에 있던 음소거 단추도 같이
  // 사라졌다(2026-08-28 코드리뷰로 발견). 재생·탐색은 이 컴포넌트가 옮겨
  // 받았지만 음소거는 옮기지 않아 소리를 끌 방법이 아예 없어졌다.
  const [muted, setMuted] = useState(false);
  // 마지막 확인은 크게 봐야 한다. 영상 요소만 키우면 재생·프레임 단추를 잃으므로
  // 판 전체를 전체화면으로 올린다. 켜짐 여부는 브라우저가 정답이다 -- Esc로도
  // 나갈 수 있어서 우리 상태만 믿으면 단추가 거짓말을 한다.
  const stageRef = useRef<HTMLElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  useEffect(() => {
    const sync = () => setIsFullscreen(document.fullscreenElement === stageRef.current && stageRef.current !== null);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);
  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      const attempt = document.exitFullscreen?.();
      if (attempt && typeof attempt.catch === "function") void attempt.catch(() => undefined);
      return;
    }
    const attempt = stageRef.current?.requestFullscreen?.();
    if (attempt && typeof attempt.catch === "function") void attempt.catch(() => undefined);
  };
  // 재생 빠르기: 보는 속도만 바뀐다. 소스가 바뀌면 재생기가 1배로 돌아가므로 새로 열릴 때마다 다시 건다.
  const [rate, setRate] = useState<PlaybackRate>(() => readPlaybackRate());
  const rateRef = useRef(rate);
  rateRef.current = rate;
  const [hintSeen, setHintSeen] = useState(() => readRateHintSeen());
  const changeRate = (next: PlaybackRate) => {
    rateRef.current = next;
    setRate(next);
    markRateHintSeen();
    setHintSeen(true);
    writePlaybackRate(next);
  };
  // 단축키 안내: 대화 상자가 아니다. 초점을 가두지 않고 키 처리도 막지 않는다(문지기는 aria-modal만 비킨다).
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const shortcutsButtonRef = useRef<HTMLButtonElement>(null);
  const shortcutsNoteRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!shortcutsOpen) return;
    const onKey = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") setShortcutsOpen(false); };
    const onPointer = (event: Event) => {
      const target = event.target as Node | null;
      if (target && (shortcutsNoteRef.current?.contains(target) || shortcutsButtonRef.current?.contains(target))) return;
      setShortcutsOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => { window.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onPointer); };
  }, [shortcutsOpen]);
  const frameSec = fps && fps.num > 0 && fps.den > 0 ? fps.den / fps.num : 1 / 30;

  // 재생 시계: 재생 중에만 화면 프레임마다 재생기 시각을 읽어 알린다. 멈추면 고리도 멈춘다(rAF를 남겨 두지 않는다).
  // React 상태는 건드리지 않는다 -- 재생 머리·시간 글자가 시계를 듣고 DOM만 직접 고친다.
  const clockFrameRef = useRef<number | null>(null);
  const clockLoop = useRef<() => void>(() => undefined);
  const stopClockLoop = () => {
    if (clockFrameRef.current !== null) window.cancelAnimationFrame(clockFrameRef.current);
    clockFrameRef.current = null;
  };
  clockLoop.current = () => {
    clockFrameRef.current = null;
    const media = mediaRef.current;
    if (!playbackClock || !media) return;
    if (media.paused || media.ended) { publishClock(media); return; }
    // 옮기는 중에는 재생기가 옛 자리나 새 자리를 오락가락 알려 준다 -- 건너뛰고 가라앉은 뒤 읽는다.
    if (!media.seeking) playbackClock.publish(coordinatorRef.current.timelineTime(media.currentTime), true);
    clockFrameRef.current = window.requestAnimationFrame(() => clockLoop.current());
  };
  /** 재생기의 지금 상태를 시계에 맞춘다. 재생 중이면 고리를 돌리고, 아니면 멈춘 시각을 알리고 고리를 거둔다. */
  const publishClock = (media: MediaNode) => {
    if (!playbackClock) return;
    const playing = !media.paused && !media.ended;
    if (!media.seeking || !playing) playbackClock.publish(coordinatorRef.current.timelineTime(media.currentTime), playing);
    if (!playing) { stopClockLoop(); return; }
    if (clockFrameRef.current === null) clockFrameRef.current = window.requestAnimationFrame(() => clockLoop.current());
  };
  useEffect(() => () => {
    stopClockLoop();
    playbackClock?.publish(playbackClock.read().seconds, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playbackClock]);
  // 시간 글자: React는 이 `<span>`을 자식 없이 그려 두고, 글자는 여기서만 쓴다. 재생 중에는 시계가, 그 밖에는 렌더마다 상태가 정답이다.
  const readoutRef = useRef<HTMLSpanElement>(null);
  const writeReadout = (text: string) => { const node = readoutRef.current; if (node && node.textContent !== text) node.textContent = text; };
  useLayoutEffect(() => {
    const reading = playbackClock?.read();
    writeReadout((reading?.playing ? reading.seconds : timelineTime).toFixed(1));
  });
  useEffect(() => playbackClock?.subscribe((reading) => writeReadout(reading.seconds.toFixed(1))), [playbackClock]);

  const stopActiveMedia = () => {
    lastReportedTimelineSecRef.current = null;
    const media = mediaRef.current;
    if (media) {
      try { media.pause(); } catch { /* native playback may already be detached */ }
      try { media.currentTime = 0; } catch { /* media can be released by a browser during teardown */ }
    }
  };
  const showExact = () => {
    if (exact.kind !== "current") return;
    stopActiveMedia();
    setAuditionIssue(null);
    setMode(coordinatorRef.current.showExact({ id: exactMediaId(exact), url: exact.url, timelineRange: exact.timelineRange }));
    setTimelineTime(exact.timelineRange.startSec);
  };
  const showAudition = (source: AuditionSource) => {
    stopActiveMedia();
    setAuditionIssue(null);
    setMode(coordinatorRef.current.showAudition(source));
    setTimelineTime(source.timelineRange.startSec);
  };

  useEffect(() => {
    if (exact.kind !== "current") {
      // 되감기 전에, 아직 붙어 있는 재생기에서 지금 장면을 잡아 둔다.
      const media = mediaRef.current;
      if (media instanceof HTMLVideoElement) stillRef.current = capturePreviewStill(media) ?? stillRef.current;
      stopActiveMedia();
      setMode(coordinatorRef.current.stop());
      return;
    }
    stillRef.current = null;
    if (mode.kind !== "audition" && (mode.kind !== "exact" || mode.media.url !== exact.url)) showExact();
    // Deliberately keep a user-selected audition active while the manifest refreshes unchanged.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exact.kind, exact.kind === "current" ? exact.url : null, expectedRevision]);
  useEffect(() => {
    if (!auditionRequest || !isAllowedLocalUrl(auditionRequest.source.url)) return;
    showAudition(auditionRequest.source);
    // requestId deliberately permits re-auditioning the same source after exact-preview return.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auditionRequest?.requestId]);
  // 언마운트 때만 멈춘다. 예전에는 초점이 밖으로 가거나(blur) 창이 구르면(scroll)
  // 멈추고 0초로 되감았다 -- 2026-10-09 실측: 재생 중 타임라인 제목을 누르면
  // 2.2초 -> 0초·정지(타임라인 위치는 옛 값 그대로). 캡컷도 다른 곳을 눌러도
  // 재생이 이어지므로 그 두 리스너를 없앴다(의도된 행동 변경).
  useLayoutEffect(() => () => stopActiveMedia(), []);
  // 렌더 도중(커밋 전) 동기로 채운다 -- `useEffect`에서 채우면 이미 늦다.
  {
    const nextPendingSeekSeconds = !Number.isFinite(playbackSec) || mode.kind === "idle" || (mode.kind === "audition" && mode.media.mediaKind === "image")
      ? null
      : Math.min(mode.media.timelineRange.endSec, Math.max(mode.media.timelineRange.startSec, playbackSec!)) - mode.media.timelineRange.startSec;
    const previous = previousPendingSeekSecondsRef.current;
    if (nextPendingSeekSeconds === null) staleSeekBaselineRef.current = null;
    else if (previous !== null && Math.abs(nextPendingSeekSeconds - previous) > 0.001) staleSeekBaselineRef.current = previous;
    previousPendingSeekSecondsRef.current = nextPendingSeekSeconds;
  }
  useEffect(() => {
    if (!Number.isFinite(playbackSec) || mode.kind === "idle" || (mode.kind === "audition" && mode.media.mediaKind === "image")) return;
    const timelineSeconds = Math.min(mode.media.timelineRange.endSec, Math.max(mode.media.timelineRange.startSec, playbackSec!));
    setTimelineTime(timelineSeconds);
    // 메아리: 내가 방금 올려보낸 위치가 그대로 돌아온 것이다. 재생기는 그새 앞으로 갔으니 옮기면 되감는다.
    if (lastReportedTimelineSecRef.current !== null && Math.abs(timelineSeconds - lastReportedTimelineSecRef.current) <= 1e-6) return;
    // 메아리가 아닌 값(진짜 탐색)이면 표식을 지운다 -- 같은 위치를 다시 눌러도 옮겨야 한다.
    lastReportedTimelineSecRef.current = null;
    // 여기서 되돌려 올려보내지 않는다. 예전에는 구간 밖 재생 위치를 자기 구간 안으로
    // 밀어 올렸는데, 그러면 타임라인을 눌러도 재생 위치가 붙박여 `나누기`를 쓸 수 없다.
    // 미리보기가 스스로 알리는 위치는 `updateTimeline`이 따로 올려보낸다.
    const media = mediaRef.current;
    const mediaSeconds = timelineSeconds - mode.media.timelineRange.startSec;
    if (media && Math.abs(media.currentTime - mediaSeconds) > 0.001) {
      try { media.currentTime = mediaSeconds; } catch { /* the browser can reject a not-yet-seekable media element */ }
    }
    // onPlaybackTimeChange는 매 렌더 새 함수다 -- deps에 두면 무관한 렌더마다 이 효과가 다시 돌아 되감았다(2026-10-09).
    // 이 효과는 그 콜백을 쓰지도 않는다.
  }, [mode, playbackSec]);

  const currentMedia = mode.kind === "idle" ? null : mode.media;
  const isImageAudition = mode.kind === "audition" && mode.media.mediaKind === "image";
  useEffect(() => {
    if (mediaRef.current) applyPlaybackRate(mediaRef.current, rate);
  }, [rate, currentMedia?.url]);
  const visibleAuditionIssue = mode.kind === "audition" ? auditionIssue : null;
  const mediaLabel = mode.kind === "audition" ? `${sourceLabel(localSources, auditionRequest, mode.media.id)} 원본 재생` : "편집본 미리보기";
  const activeCaption = mode.kind === "exact" ? captions.find((caption) => timelineTime >= caption.startSec && timelineTime < caption.endSec) : null;
  // 재생 위치를 더는 되돌리지 않으므로, 화면에 보이는 순간과 재생 위치가 갈릴 수 있다.
  // 갈렸으면 말해 준다 -- 말없이 다른 순간을 보여 주는 것이 되돌리는 것보다 나쁘다.
  const showsADifferentMoment = currentMedia !== null && !isImageAudition && Number.isFinite(playbackSec)
    && Math.abs((playbackSec as number) - timelineTime) > 0.05;
  const updateTimeline = (node: MediaNode) => {
    // 자리를 옮겨 달라고 하면 플레이어는 잠깐 **옛 위치**를 그대로 알려 준다. 그걸
    // 위로 올리면 소유자가 옛 위치를 되돌려 보내고, 두 쪽이 서로 밀며 제자리를 맴돈다.
    // 실제 컨테이너에서 `다음 프레임`을 눌렀을 때 새 위치 → 옛 위치 → 새 위치가
    // 번갈아 찍혔다. 가라앉은 뒤에 오는 `seeked`만 믿는다.
    if (node.seeking) return;
    // **낡은 재생 위치 신호는 무시한다(2026-09-20 실물 재현).** 바깥에서 방금
    // 다른 장면을 골라 재생 위치(`playbackSec`)를 옮기라고 하면 그 직전
    // 자리를 `staleSeekBaselineRef`에 잠깐 남겨 둔다. 이
    // 재생기가 실제로는 아직 그 옛 자리에 있는데도 스스로 `timeupdate`를
    // 보내면 `node.seeking`은 여전히 false라 위 가드를 통과한다 -- 그 옛
    // 위치를 믿고 올려보내면 "재생 위치로 장면을 다시 고른다"는 아래 경로가
    // 방금 고른 장면을 덮어쓴다(전환 탭이 다시 "첫 장면"으로 보였다).
    // **목표 자리와 다르다고 무조건 막지는 않는다** -- 자연 재생은 목표를
    // 딱 맞히지 않고 지나쳐 계속 나아가는 게 정상이라, 그런 진행까지 막으면
    // "가라앉은 뒤 재생이 다시 안 올라온다"는 다른 결함이 생긴다. 옛 자리
    // 그대로일 때만 무시하고, 조금이라도 움직였으면(목표에 못 미쳐도) 믿는다.
    if (staleSeekBaselineRef.current !== null && Math.abs(node.currentTime - staleSeekBaselineRef.current) <= 0.05) return;
    staleSeekBaselineRef.current = null;
    // 반복이 켜져 있으면 구간 끝에서 되감는다. 자막·재생 위치를 갱신하기 전에 처리해야
    // 구간 밖 한 순간이 잠깐 보였다 사라지는 일이 없다.
    // 담고 있지 않은 구간은 반복하지 않는다. 부분 구간 미리보기(예: 4~8초)를 보는
    // 중에 9~12초 장면을 고르면, 되감을 자리가 이 미리보기 안에 없어서 매 tick마다
    // 닿을 수 없는 곳을 노리고 재생이 그 자리에 붙박인다.
    if (repeating && loopRange && mode.kind !== "idle" && rangesOverlap(loopRange, mode.media.timelineRange)) {
      const timelineSeconds = coordinatorRef.current.timelineTime(node.currentTime);
      if (timelineSeconds >= loopRange.endSec || timelineSeconds < loopRange.startSec) {
        seekTimelineTo(node, loopRange.startSec);
        return;
      }
    }
    const nextSeconds = coordinatorRef.current.timelineTime(node.currentTime);
    lastReportedTimelineSecRef.current = nextSeconds;
    setTimelineTime(nextSeconds);
    onPlaybackTimeChange?.(nextSeconds);
  };
  /** 미리보기가 실제로 담고 있는 구간 안으로만 옮긴다. 밖은 갖고 있지 않다. */
  const seekTimelineTo = (media: MediaNode, timelineSeconds: number) => {
    if (mode.kind === "idle") return;
    const range = mode.media.timelineRange;
    const clamped = Math.min(range.endSec, Math.max(range.startSec, timelineSeconds));
    try { media.currentTime = clamped - range.startSec; } catch { return; }
    lastReportedTimelineSecRef.current = clamped;
    setTimelineTime(clamped);
    onPlaybackTimeChange?.(clamped);
  };
  const stepFrame = (direction: -1 | 1) => {
    const media = mediaRef.current;
    if (!media || mode.kind === "idle") return;
    try { media.pause(); } catch { /* native playback may already be detached */ }
    seekTimelineTo(media, coordinatorRef.current.timelineTime(media.currentTime) + direction * frameSec);
  };
  const togglePlayback = () => {
    const media = mediaRef.current;
    if (!media) return;
    if (media.paused) {
      const attempt = media.play();
      if (attempt && typeof attempt.catch === "function") void attempt.catch(() => undefined);
    } else {
      // **일시정지는 위치를 지키지 않는다** -- `stopActiveMedia`(소스를 바꿀 때
      // 쓰는 함수)를 여기서도 재사용했더니 스페이스로 멈출 때마다 재생 위치가
      // 0초로 튀었다(owner 실사용 제보, 2026-09-01). 소스 전환(`showExact`/
      // `showAudition`)은 위치 초기화가 맞는 동작이라 그쪽은 그대로 둔다 --
      // 여기는 순수 일시정지만 한다.
      try { media.pause(); } catch { /* 이미 해제된 미디어일 수 있다 */ }
    }
  };
  const playMedia = () => {
    const media = mediaRef.current;
    if (!media) return;
    const attempt = media.play();
    if (attempt && typeof attempt.catch === "function") void attempt.catch(() => undefined);
  };
  const onStageKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    // 스페이스는 아래 창 처리기 하나만 받는다(둘이 받으면 서로 상쇄했다).
    if (event.key !== "Enter") return;
    if (event.target !== event.currentTarget) return;
    event.preventDefault();
    togglePlayback();
  };
  // 스페이스는 **어디서 눌러도** 재생/일시정지다. 예전에는 미리보기 판을 클릭해
  // 둔 상태에서만 들어서, 타임라인을 만지다 누르면 아무 일도 없었다.
  //
  // 다만 글을 쓰는 중이면 띄어쓰기이고 단추 위에서는 그 단추를 누르는 것이다 --
  // 거기서 가로채면 접근성이 깨진다. 플레이어를 가진 이 컴포넌트가 직접 듣는다:
  // 소유자에게 올려 두면 재생 상태가 두 군데에 생긴다.
  // 창 처리기는 한 번만 달고(StrictMode 안전) 최신 togglePlayback은 ref로 부른다.
  const toggleRef = useRef(togglePlayback);
  toggleRef.current = togglePlayback;
  // 키 명령은 전부 이 한 곳에서 실행한다(문지기 `playbackShortcutFor`가 자리를 가린다).
  const runCommandRef = useRef((_command: NonNullable<ReturnType<typeof playbackShortcutFor>>) => undefined as void);
  runCommandRef.current = (command) => {
    const media = mediaRef.current;
    if (!media) return;
    switch (command.type) {
      case "toggle": togglePlayback(); return;
      case "pause": try { media.pause(); } catch { /* 이미 해제된 미디어일 수 있다 */ } return;
      case "step": stepFrame(command.frames); return;
      case "faster":
        // 멈춰 있으면 단계 없이 지금 빠르기로 재생한다. 재생 중일 때만 한 단계 빠르게.
        if (media.paused) playMedia(); else changeRate(stepPlaybackRate(rateRef.current, 1));
        return;
      case "slower":
        changeRate(stepPlaybackRate(rateRef.current, -1));
        if (media.paused) playMedia();
        return;
    }
  };
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (!mediaRef.current) return;
      if (isSwallowedRepeat(event)) { event.preventDefault(); return; }
      const command = playbackShortcutFor(event);
      if (!command) return;
      event.preventDefault();
      runCommandRef.current(command);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
  const refresh = async () => {
    if (!onRefresh || refreshing) return;
    setRefreshing(true);
    setRefreshError(null);
    try { await onRefresh(); } catch { setRefreshError("미리보기를 다시 요청하지 못했어요."); } finally { setRefreshing(false); }
  };
  // 길이를 알면 `4.0 / 20.0초`, 모르면 예전처럼 `4.0초`뿐이다 -- 단위(초)는
  // 어느 쪽이든 한 번만 붙는다.
  const timelineTimeSuffix = Number.isFinite(durationSec) && (durationSec as number) > 0
    ? ` / ${(durationSec as number).toFixed(1)}초`
    : "초";
  const syncRateFromMedia = (node: MediaNode) => {
    const next = PLAYBACK_RATES.find((value) => value === node.playbackRate);
    if (next !== undefined && next !== rateRef.current) { rateRef.current = next; setRate(next); }
  };
  const checkAuditionVideo = (video: HTMLVideoElement) => {
    if (mode.kind !== "audition" || mode.media.mediaKind !== "video") return;
    if (video.videoWidth > 0 && video.videoHeight > 0) return;
    try { video.pause(); } catch { /* the browser may already have detached an unsupported source */ }
    setAuditionIssue("이 원본은 여기서 화면을 열 수 없어요. 적용한 뒤 편집본 미리보기에서 확인해 주세요.");
  };

  return <section ref={stageRef} className="vb-preview-stage" aria-label="미리보기" tabIndex={0} onKeyDown={onStageKeyDown}>
    <header className="vb-preview-stage__header"><div><p className="vb-preview-stage__eyebrow">{mode.kind === "audition" ? "원본 미리보기" : "편집본 미리보기"}</p><h2>{mode.kind === "audition" ? "원본 보기" : "편집 결과"}</h2></div>{mode.kind === "audition" && exact.kind === "current" && <button data-native-control="return-exact" type="button" onClick={showExact}>편집본으로 돌아가기</button>}</header>
    <div className="vb-preview-stage__media-shell" aria-busy={exact.kind === "pending" || exact.kind === "running"}>
      {visibleAuditionIssue
        ? <div className="vb-preview-stage__empty"><strong>원본 화면을 열지 못했어요</strong><p role="alert">{visibleAuditionIssue}</p></div>
        : currentMedia && (isImageAudition
        ? <img aria-label={mediaLabel} src={currentMedia.url} alt="" />
        : mode.kind === "audition" && mode.media.mediaKind === "audio"
        // **재생바를 하나만 둔다(owner 지적: 재생 조작이 복잡하다).** 브라우저
        // 기본 `controls`를 켜 두면 그 아래 우리 재생바(이전 프레임·재생·다음
        // 프레임·반복·전체화면)와 겹쳐서 두 벌이 뜬다 -- 탐색바도 재생 버튼도
        // 둘씩이었다. 재생·탐색은 이 컴포넌트가 이미 다 다룬다
        // (`togglePlayback`·`stepFrame`·타임라인 재생헤드 끌기), 기본
        // 컨트롤은 끈다. **다만 기본 컨트롤 안에만 있던 음소거는 옮겨 받지
        // 못해 소리 끌 방법이 통째로 사라졌었다**(2026-08-28 코드리뷰로
        // 발견) -- `muted` state와 아래 음소거 단추로 되살렸다.
        // 영상은 `preload="auto"`다(2026-10-09 실측). `metadata`면 멈춘 채 탐색할 때마다
        // 브라우저가 범위 요청을 7~8개로 쪼개 보내서 탐색 p95가 0.7~8.5초였다 -- auto는 1~2개.
        ? <audio ref={mediaRef as RefObject<HTMLAudioElement>} aria-label={mediaLabel} src={currentMedia.url} preload="metadata" muted={muted} onLoadedMetadata={(event) => applyPlaybackRate(event.currentTarget, rateRef.current)} onRateChange={(event) => syncRateFromMedia(event.currentTarget)} onTimeUpdate={(event) => updateTimeline(event.currentTarget)} onSeeking={(event) => updateTimeline(event.currentTarget)} onSeeked={(event) => { updateTimeline(event.currentTarget); publishClock(event.currentTarget); }} onPlay={(event) => publishClock(event.currentTarget)} onPause={(event) => publishClock(event.currentTarget)} onEnded={(event) => publishClock(event.currentTarget)} />
        : <video ref={mediaRef as RefObject<HTMLVideoElement>} aria-label={mediaLabel} src={currentMedia.url} preload="auto" playsInline muted={muted} onLoadedMetadata={(event) => { applyPlaybackRate(event.currentTarget, rateRef.current); checkAuditionVideo(event.currentTarget); }} onRateChange={(event) => syncRateFromMedia(event.currentTarget)} onLoadedData={(event) => rememberStill(event.currentTarget)} onPause={(event) => { rememberStill(event.currentTarget); publishClock(event.currentTarget); }} onPlay={(event) => publishClock(event.currentTarget)} onEnded={(event) => publishClock(event.currentTarget)} onTimeUpdate={(event) => updateTimeline(event.currentTarget)} onSeeking={(event) => updateTimeline(event.currentTarget)} onSeeked={(event) => { updateTimeline(event.currentTarget); rememberStill(event.currentTarget); publishClock(event.currentTarget); }} />)}
      {/* **아직 아무것도 안 넣었으면 실패라고 말하지 않는다(2026-09-04).**
          owner가 제일 먼저 막힌 자리다 -- "처음에 뭘 어떤걸 눌러야할지도
          모르겠고". 갓 만든 프로젝트를 열면 첫 화면이 "미리보기를 만들지
          못했어요"를 두 번 말했다. 백엔드가 빈 타임라인의 미리보기를 `failed`로
          표시하기 때문인데, **빈 프로젝트를 그리는 데 실패한 게 아니라 그릴 것이
          아직 없는 것**이다. 첫인상이 오류면 "내가 뭘 잘못했나"부터 생각하게 된다.
          진짜 실패는 그대로 실패라고 말한다 -- 안내가 고장까지 덮으면 안 된다. */}
      {!currentMedia && (projectIsEmpty
        ? <div className="vb-preview-stage__empty"><strong>여기에 영상이 나와요</strong><p>왼쪽 <b>미디어</b>에서 파일을 더하면 이 자리에 보여요.</p></div>
        : (() => {
          const still = exact.kind === "pending" || exact.kind === "running" || exact.kind === "stale" ? stillRef.current : null;
          const waiting = exact.kind === "pending" || exact.kind === "running";
          const empty = <div className="vb-preview-stage__empty"><strong>{exact.label}</strong><p>{exact.copy}</p>{still && waiting && <p role="status">새 미리보기를 만드는 중이에요 · 바뀌기 전 화면</p>}<button data-native-control="refresh-exact" type="button" onClick={() => void refresh()} disabled={!onRefresh || refreshing}>{refreshing ? "미리보기 만드는 중" : "미리보기 새로 만들기"}</button>{refreshError && <p role="alert">{refreshError}</p>}</div>;
          return still
            ? <div className="vb-preview-stage__waiting"><img className="vb-preview-stage__still" src={still} alt="" />{empty}</div>
            : empty;
        })())}
    </div>
    {/* **재생줄은 사라지지 않는다(2026-09-04).** owner: "스페이스바를 누르면
        멈춰야 되는데 그것도 안되고". 기능은 원래 있었는데(전역 핸들러) 재생할
        미디어가 없으면 이 줄이 통째로 안 그려져서 **"눌러도 아무 일이 없다"로
        보였다** -- 왜인지 알 방법이 없었다. 캡컷은 재생 단추가 늘 있다.
        눌리지 않는 단추라도 있는 편이 낫다: 없으면 고장인지 내 잘못인지 모른다.
        (실시간 타임라인 재생은 별개의 큰 일이라 이번 범위가 아니다.) */}
    {!isImageAudition && !visibleAuditionIssue && <div className="vb-preview-stage__playback" data-idle={currentMedia ? undefined : "true"}><div className="vb-preview-stage__transport"><button data-native-control="step-back" type="button" disabled={!currentMedia} onClick={() => stepFrame(-1)} aria-label="이전 프레임" title="← 키">◀｜</button><button data-native-control="toggle-playback" type="button" disabled={!currentMedia} onClick={togglePlayback} aria-label="재생 또는 일시정지" title="스페이스바">재생 / 일시정지</button><button data-native-control="step-forward" type="button" disabled={!currentMedia} onClick={() => stepFrame(1)} aria-label="다음 프레임" title="→ 키">｜▶</button><button data-native-control="toggle-mute" type="button" disabled={!currentMedia} onClick={() => setMuted((current) => !current)} aria-label={muted ? "음소거 해제" : "음소거"} aria-pressed={muted}>{muted ? "음소거 해제" : "음소거"}</button>{loopRange && <button data-native-control="toggle-repeat" type="button" onClick={() => setRepeating((current) => !current)} aria-label="선택한 장면 반복" aria-pressed={repeating}>반복</button>}<button data-native-control="toggle-fullscreen" type="button" disabled={!currentMedia} onClick={toggleFullscreen} aria-label="미리보기 전체화면" aria-pressed={isFullscreen}>전체화면</button><label className="vb-preview-stage__rate" title={`보는 속도만 바뀌어요. 영상은 바뀌지 않아요 · J 키 느리게 · L 키 빠르게(최대 ${formatPlaybackRate(maxPlaybackRate())}) · K 키 멈춤`}><span>재생 빠르기</span><NativeSelect aria-label="재생 빠르기" value={String(rate)} disabled={!currentMedia} onChange={(event) => changeRate(Number(event.target.value) as PlaybackRate)}>{PLAYBACK_RATES.map((value) => <option key={value} value={String(value)}>{formatPlaybackRate(value)}</option>)}</NativeSelect></label>{currentMedia && !hintSeen && rate === 1 && <span className="vb-preview-stage__rate-hint">빠르게 보려면 L 키를 눌러요</span>}<Button ref={shortcutsButtonRef} type="button" variant="ghost" size="sm" aria-expanded={shortcutsOpen} aria-controls="vb-playback-shortcuts" onClick={() => setShortcutsOpen((open) => !open)}>단축키</Button></div>{currentMedia ? <output aria-live="off">타임라인 <span ref={readoutRef} />{timelineTimeSuffix}</output> : <output aria-live="off">아직 재생할 영상이 없어요</output>}{shortcutsOpen && <div ref={shortcutsNoteRef} id="vb-playback-shortcuts" role="note" aria-label="재생 단축키" className="vb-preview-stage__shortcuts"><ul><li>스페이스바 — 재생 / 일시정지</li><li>K 키 — 멈춤</li><li>L 키 — 재생, 누를수록 빠르게(최대 {formatPlaybackRate(maxPlaybackRate())})</li><li>J 키 — 느리게(최소 0.25배)</li><li>← → — 한 프레임씩</li></ul><p>빠르기는 보는 속도예요. 영상은 바뀌지 않아요.</p></div>}</div>}
    {showsADifferentMoment && <p role="status" aria-label="미리보기 위치 안내" aria-live="polite" className="vb-preview-stage__elsewhere">지금 화면은 타임라인 {timelineTime.toFixed(1)}초 모습이에요. 재생 위치는 아직 미리보기 밖이에요.</p>}
    {mode.kind === "exact" && <p role="status" aria-label="현재 캡션" aria-live="polite" aria-atomic="true" className="vb-preview-stage__caption-transcript vb-preview-stage__visually-hidden">{activeCaption ? `현재 캡션: ${activeCaption.text}` : "현재 캡션 없음"}</p>}
    <p role="status" aria-live="polite" className="vb-preview-stage__status">{mode.kind === "exact" ? `캡션도 함께 재생돼요. ${exact.copy} 타임라인 ${timelineTime.toFixed(1)}초` : mode.kind === "audition" ? isImageAudition ? "원본 그림 미리보기" : `원본 미리보기 · 타임라인 ${timelineTime.toFixed(1)}초` : `${projectIsEmpty ? "아직 넣은 영상이 없어요." : exact.copy} 타임라인 ${timelineTime.toFixed(1)}초`}</p>
  </section>;
}

function rangesOverlap(left: Readonly<{ startSec: number; endSec: number }>, right: TimelineRange): boolean {
  return left.startSec < right.endSec && right.startSec < left.endSec;
}

function exactMediaId(exact: Extract<ReturnType<typeof toExactPreviewState>, { kind: "current" }>): string {
  return `exact:${exact.url}`;
}
function sourceLabel(sources: readonly AuditionSource[], auditionRequest: AuditionRequest | null | undefined, id: string): string {
  return sources.find((source) => source.id === id)?.label ?? (auditionRequest?.source.id === id ? auditionRequest.source.label : "고른 원본");
}
