import { useEffect, useState } from "react";

export const DIRECTOR_NARROW_MEDIA_QUERY = "(max-width: 760px)";
export const DIRECTOR_REDUCED_MOTION_MEDIA_QUERY = "(prefers-reduced-motion: reduce)";

function useMediaQuery(query: string) {
  const getMatches = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches;
  const [isNarrow, setIsNarrow] = useState(getMatches);

  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return;
    const update = () => setIsNarrow(media.matches);
    update();
    if (media.addEventListener) {
      media.addEventListener("change", update);
      return () => media.removeEventListener?.("change", update);
    }
    media.addListener?.(update);
    return () => media.removeListener?.(update);
  }, [query]);

  return isNarrow;
}

export function useResponsiveDirector() {
  return useMediaQuery(DIRECTOR_NARROW_MEDIA_QUERY);
}

export function useDirectorReducedMotion() {
  return useMediaQuery(DIRECTOR_REDUCED_MOTION_MEDIA_QUERY);
}
