const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

export function getScrollBehavior(): ScrollBehavior {
  if (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(REDUCED_MOTION_QUERY).matches
  ) {
    return "auto";
  }

  return "smooth";
}
