export const PUBLIC_ROUTES = new Set([
  "/",
  "/platform",
  "/performance",
  "/contact",
  "/subscription/success",
  "/subscription/cancelled",
  "/manage-subscription",
  "/manage-subscription/access",
  "/legal-notice",
  "/terms",
  "/privacy",
  "/cookie-policy",
  "/risk-disclosure",
  "/refund-policy",
  "/cancellation-policy",
  "/withdrawal-policy",
]);

export const LEGACY_CUSTOMER_ROUTES = new Set([
  "/signup",
  "/login",
  "/forgot-password",
  "/reset-password",
  "/subscribe",
  "/onboarding",
  "/dashboard",
  "/history",
  "/settings",
]);

export type RoutePolicyResult = "public" | "admin" | "legacy" | "redirect-home";

export function resolveRoutePolicy(
  pathname: string,
  legacyEnabled: boolean,
  hasExistingToken = false
): RoutePolicyResult {
  void legacyEnabled;
  void hasExistingToken;
  if (PUBLIC_ROUTES.has(pathname)) return "public";
  if (LEGACY_CUSTOMER_ROUTES.has(pathname)) {
    return "redirect-home";
  }
  return "redirect-home";
}
