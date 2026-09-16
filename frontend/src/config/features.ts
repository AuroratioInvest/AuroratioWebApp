const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);

export function parseBooleanFlag(value: unknown): boolean {
  if (typeof value !== "string") return false;
  return TRUE_VALUES.has(value.trim().toLowerCase());
}

export const legacyCustomerAppEnabled = parseBooleanFlag(
  import.meta.env?.LEGACY_CUSTOMER_APP_ENABLED
);
