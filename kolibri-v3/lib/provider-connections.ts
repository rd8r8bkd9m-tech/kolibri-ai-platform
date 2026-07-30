export const PROVIDER_IDS = ["mimo-code", "codex-cli"] as const;

export type ProviderId = (typeof PROVIDER_IDS)[number];

/**
 * The BFF only validates the fixed route segment. Authentication, CSRF,
 * tenant ownership, idempotency and persistence are all enforced by the V3
 * Product/Data backend; Next holds no Provider Authority credential.
 */
export function isProviderId(value: unknown): value is ProviderId {
  return (
    typeof value === "string" &&
    (PROVIDER_IDS as readonly string[]).includes(value)
  );
}
