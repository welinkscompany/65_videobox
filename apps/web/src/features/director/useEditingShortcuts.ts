import { useEffect, useRef } from "react";

function isEditable(target: EventTarget | null) {
  return target instanceof HTMLElement && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
}

export function useEditingShortcuts({ onUndo, onRedo }: { onUndo: () => void; onRedo: () => void }) {
  const composing = useRef(false);
  useEffect(() => {
    const onCompositionStart = () => { composing.current = true; };
    const onCompositionEnd = () => { composing.current = false; };
    const onKeyDown = (event: KeyboardEvent) => {
      if (composing.current || event.isComposing || isEditable(event.target) || !(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === "z") { event.preventDefault(); (event.shiftKey ? onRedo : onUndo)(); }
      if (key === "y") { event.preventDefault(); onRedo(); }
    };
    window.addEventListener("compositionstart", onCompositionStart, true);
    window.addEventListener("compositionend", onCompositionEnd, true);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("compositionstart", onCompositionStart, true);
      window.removeEventListener("compositionend", onCompositionEnd, true);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onRedo, onUndo]);
}
