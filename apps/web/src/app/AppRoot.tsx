import { Toaster } from "../components/ui/sonner";
import { AppRouter } from "./AppRouter";

export function AppRoot() {
  return (
    <div className="vb-ui min-h-screen">
      <AppRouter />
      {/* 편집마다 뜨는 '저장하고 있어요 -> 저장했어요' 알림 자리(편집기 `editorFeedback.ts`). */}
      <Toaster position="bottom-center" />
    </div>
  );
}
