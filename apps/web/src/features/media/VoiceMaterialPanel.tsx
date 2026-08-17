import { NarrationAudioSection } from "./NarrationAudioSection";
import { VoiceTtsSettings } from "../settings/VoiceTtsSettings";

/** 내레이션은 영상·음악·효과음과 같은 **재료**다.
 *
 * 2026-08-16까지 목소리는 `설정 › 목소리`에만 있었다. 장면을 골라 내레이션을 만들고
 * 들어보는 **명백한 편집 작업**인데 설정 서랍에 들어가 있었고, 그래서 자산 단계에는
 * 사람 목소리만 빠져 있었다. 첫 완성본이 무음(-91dB)으로 나간 것도 같은 뿌리다 —
 * 내레이션이 무음 자산이었는데 **제작 흐름 어디에도 그것을 볼 자리가 없었다.**
 *
 * **이 패널은 기능을 새로 만들지 않는다.** 목소리 등록·후보 생성·청취 승인은
 * `VoiceTtsSettings`에 이미 다 있다. 처음에 여기 업로드를 하나 더 붙였다가
 * 같은 화면에 올리는 길이 두 개가 되어 걷어냈다 — 고쳐야 할 것은 기능이 아니라
 * **어느 단계에서 만나는가**였다.
 */
export function VoiceMaterialPanel({ projectId }: { projectId: string }) {
  return (
    <div className="grid gap-4">
      <section aria-labelledby="narration-material-heading">
        <h2 id="narration-material-heading">내레이션</h2>
        {/* 목소리를 왜 등록하는지 여기서 말해 준다. 아래 화면은 "아직 저장한 목소리가
            없어요"까지만 말해서, 처음 온 사람은 무엇을 넣어야 할지 알 수 없다. */}
        <p>내 목소리를 등록하면 대본을 내 목소리로 읽어 줘요. 조용한 곳에서 30초쯤 말한 파일이 좋아요.</p>
      </section>
      {/* 이미 녹음해 둔 내레이션을 넣는 길이 프로젝트를 만들 때뿐이었다.
          여기서 지금 들어 있는 것을 듣고 바꿀 수 있어야 무음 완성본을 미리 잡는다. */}
      <NarrationAudioSection projectId={projectId} />
      {/* `key`가 있어야 프로젝트를 바꿀 때 앞 프로젝트의 입력이 화면에서 즉시 사라진다.
          없으면 React가 같은 인스턴스를 재사용해, B가 불러오는 동안 A에 타이핑한 경로가
          그대로 남는다. 설정 화면에 있던 것을 옮겨 오면서 이걸 빠뜨렸고 테스트가 잡았다. */}
      <VoiceTtsSettings key={projectId} projectId={projectId} />
    </div>
  );
}
