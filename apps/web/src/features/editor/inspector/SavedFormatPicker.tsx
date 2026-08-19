import { useEffect, useState } from "react";

import { api, type CaptionStyleSnapshot, type FormatTemplate } from "../../../api";
import { Button } from "../../../components/ui/button";

/** 마음에 들었던 완성본의 포맷을 이 편집본에 입힌다.
 *
 * 옆의 `자막 모양`(프리셋)과 다르다. 프리셋은 손으로 만든 자막 스타일 하나이고,
 * 포맷은 **완성본에서 떠낸 만드는 방식**이라 화면 크기·호흡·음악까지 함께 기억한다.
 *
 * 적용은 프리셋과 **똑같이** 화면 값에 넣고 기존 `자막 스타일 저장`이 커밋한다.
 * 여기서 저장소를 따로 부르면 같은 변경이 두 경로를 갖게 되고, 그중 하나가 조용히 낡는다.
 * 자막 밖의 것(크기·음악)은 적용하지 않고 **무엇이 걸려 있는지 보여만 준다** —
 * 크기를 실제로 바꾸는 검증된 경로가 없어서, 카드가 그 사실을 화면에서 직접 말한다.
 * 말하지 않으면 크기 표시가 "적용하면 이 크기가 된다"는 약속처럼 읽힌다.
 */
export function SavedFormatPicker({ onApply }: { onApply: (style: CaptionStyleSnapshot) => void }) {
  const [templates, setTemplates] = useState<readonly FormatTemplate[]>([]);
  const [ready, setReady] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void api.listFormatTemplates()
      .then((next) => { if (active) setTemplates(next); })
      .catch(() => { if (active) setMessage("저장한 포맷을 불러오지 못했어요."); })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, []);

  if (!ready) return null;
  return (
    <section className="vb-saved-formats" aria-labelledby="saved-formats-heading">
      <h3 id="saved-formats-heading">저장한 포맷</h3>
      {templates.length ? (
        // 크기·음악 표시가 약속처럼 읽히지 않게, 실제로 바뀌는 것을 먼저 말한다.
        <p>적용하면 자막 모양만 바뀌어요. 화면 크기와 음악은 그대로예요.</p>
      ) : null}
      {message ? <p role="status">{message}</p> : null}
      {templates.length ? templates.map((template) => (
        <article key={template.template_id} aria-label={`${template.name} 포맷`}>
          <strong>{template.name}</strong>
          {/* 무엇이 걸려 있는지 미리 말해 준다. 눌러 보고 알게 하지 않는다. */}
          <span>
            {template.width && template.height ? `${template.width}×${template.height} · ` : ""}
            {template.scene_count ? `장면 ${template.scene_count}개` : "장면 정보 없음"}
          </span>
          <Button
            type="button"
            variant="outline"
            onClick={() => onApply((template.caption_style ?? {}) as CaptionStyleSnapshot)}
          >
            {`${template.name} 자막 모양 적용`}
          </Button>
        </article>
      )) : <p>아직 저장한 포맷이 없어요. 마음에 든 완성본에서 저장해 보세요.</p>}
    </section>
  );
}
