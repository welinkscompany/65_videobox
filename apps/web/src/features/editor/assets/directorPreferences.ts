import { useCallback, useEffect, useRef, useState } from "react";

import { api, type DirectorPreferences } from "../../../api";

/** 유진이 자산을 고를 때 쓰는 owner의 취향.
 *
 * 백엔드는 이 네 목록을 이미 읽고 있었다 -- 뺀 자산은 후보에서 아예 빠지고,
 * 항상 쓰기로 둔 자산은 점수를 더 받는다. 그런데 저장하는 화면이 없어서 입력이
 * 영원히 비어 있었고, 두 항목은 늘 0이었다.
 */
export type StoredDirectorPreferences = Required<DirectorPreferences>;

export type DirectorPreferenceList = keyof StoredDirectorPreferences;

/** 한 자산에 대한 owner의 선택. */
export type AssetPreferenceChoice = "always" | "never" | "none";

const listNames: readonly DirectorPreferenceList[] = [
  "pin_asset",
  "exclude_asset",
  "exclude_creator",
  "exclude_tag",
];

export const directorPreferenceLoadError = "추천 취향을 불러오지 못했어요. 편집은 계속할 수 있어요.";
export const directorPreferenceSaveError = "추천 취향을 저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.";

export function emptyDirectorPreferences(): StoredDirectorPreferences {
  return { pin_asset: [], exclude_asset: [], exclude_creator: [], exclude_tag: [] };
}

/** 서버가 준 값을 네 목록이 모두 있는 모양으로 맞춘다.
 *
 * 저장된 적이 없는 프로젝트는 키가 통째로 빠져 오기도 한다. 빠진 키를 그대로
 * 두면 다음 저장에서 그 목록이 요청에 실리지 않고, 서버는 키가 없는 목록을
 * 건드리지 않으므로 화면이 보여준 것과 저장된 것이 어긋난다.
 */
export function normalizeDirectorPreferences(
  preferences: DirectorPreferences | null | undefined,
): StoredDirectorPreferences {
  const normalized = emptyDirectorPreferences();
  for (const name of listNames) {
    const values = preferences?.[name];
    if (!Array.isArray(values)) continue;
    normalized[name] = [...new Set(
      values.filter((value): value is string => typeof value === "string" && value.trim() !== "")
        .map((value) => value.trim()),
    )];
  }
  return normalized;
}

/** 목록 하나에 값을 넣거나 뺀다. 나머지 세 목록은 그대로 실어 보낸다.
 *
 * 서버는 요청에 실린 키만 병합하되 **그 키의 목록은 통째로 갈아끼운다**.
 * 방금 누른 값 하나만 보내면 앞서 뺀 자산이 조용히 되살아난다.
 */
export function withPreferenceMember(
  preferences: StoredDirectorPreferences,
  name: DirectorPreferenceList,
  value: string,
  enabled: boolean,
): StoredDirectorPreferences {
  const trimmed = value.trim();
  const next = { ...preferences, [name]: [...preferences[name]] };
  if (!trimmed) return next;
  next[name] = enabled
    ? [...new Set([...preferences[name], trimmed])]
    : preferences[name].filter((item) => item !== trimmed);
  return next;
}

export function assetPreferenceChoice(
  preferences: StoredDirectorPreferences,
  assetId: string,
): AssetPreferenceChoice {
  if (preferences.exclude_asset.includes(assetId)) return "never";
  if (preferences.pin_asset.includes(assetId)) return "always";
  return "none";
}

/** 한 자산을 "항상 쓰기" 또는 "쓰지 않기"로 둔다.
 *
 * 두 상태는 같이 설 수 없다 -- 항상 쓰라고 한 자산을 동시에 빼 두면 백엔드는
 * 후보에서 빼 버리고, 화면은 owner가 고른 것과 다른 결과를 설명할 수 없다.
 */
export function withAssetPreferenceChoice(
  preferences: StoredDirectorPreferences,
  assetId: string,
  choice: AssetPreferenceChoice,
): StoredDirectorPreferences {
  const cleared = withPreferenceMember(
    withPreferenceMember(preferences, "pin_asset", assetId, false),
    "exclude_asset",
    assetId,
    false,
  );
  if (choice === "always") return withPreferenceMember(cleared, "pin_asset", assetId, true);
  if (choice === "never") return withPreferenceMember(cleared, "exclude_asset", assetId, true);
  return cleared;
}

/** 태그는 소문자로 맞춰 저장한다.
 *
 * 자산의 태그는 비교 전에 소문자로 내려간다. 대문자가 섞인 채로 저장하면
 * owner는 뺐다고 보는데 후보에는 계속 남는다.
 */
export function canonicalPreferenceTag(tag: string): string {
  return tag.trim().toLowerCase();
}

export type DirectorPreferenceControls = Readonly<{
  preferences: StoredDirectorPreferences;
  ready: boolean;
  error: string | null;
  isSaving: boolean;
  setAssetChoice: (assetId: string, choice: AssetPreferenceChoice) => void | Promise<void>;
  setListMember: (
    name: DirectorPreferenceList,
    value: string,
    enabled: boolean,
  ) => void | Promise<void>;
}>;

/** 저장된 취향을 읽어 두고, 바꿀 때마다 네 목록을 통째로 다시 보낸다. */
export function useDirectorPreferences(projectId?: string): DirectorPreferenceControls {
  const [preferences, setPreferences] = useState<StoredDirectorPreferences>(emptyDirectorPreferences);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  // 저장할 값은 마지막으로 확인된 저장본에서 계산한다. state 갱신 함수는 다음
  // 렌더에서야 돌기 때문에, 그 안에서 보낼 값을 만들면 첫 클릭이 빈 목록을
  // 보내고 나머지 세 목록을 통째로 지운다.
  const latest = useRef<StoredDirectorPreferences>(emptyDirectorPreferences());
  const commit = (value: StoredDirectorPreferences) => {
    latest.current = value;
    setPreferences(value);
  };

  useEffect(() => {
    if (!projectId) {
      commit(emptyDirectorPreferences());
      setReady(false);
      return;
    }
    let active = true;
    setReady(false);
    setError(null);
    void api.getDirectorPreferences(projectId)
      .then((saved) => {
        if (!active) return;
        commit(normalizeDirectorPreferences(saved));
        setReady(true);
      })
      .catch(() => { if (active) setError(directorPreferenceLoadError); });
    return () => { active = false; };
  }, [projectId]);

  const save = useCallback(async (
    change: (current: StoredDirectorPreferences) => StoredDirectorPreferences,
  ) => {
    if (!projectId) return;
    const previous = latest.current;
    const next = change(previous);
    commit(next);
    setError(null);
    setIsSaving(true);
    try {
      // 네 목록을 전부 실어 보낸다. 방금 바뀐 것만 보내면 나머지가 남아 있는지
      // 요청만 봐서는 알 수 없고, 서버는 실린 키만 갈아끼운다.
      const saved = await api.updateDirectorPreferences(projectId, next);
      commit(normalizeDirectorPreferences(saved));
    } catch {
      commit(previous);
      setError(directorPreferenceSaveError);
    } finally {
      setIsSaving(false);
    }
  }, [projectId]);

  return {
    preferences,
    ready,
    error,
    isSaving,
    setAssetChoice: (assetId, choice) =>
      save((current) => withAssetPreferenceChoice(current, assetId, choice)),
    setListMember: (name, value, enabled) =>
      save((current) => withPreferenceMember(current, name, value, enabled)),
  };
}
