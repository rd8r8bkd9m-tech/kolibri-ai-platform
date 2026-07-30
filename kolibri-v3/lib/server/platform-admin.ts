import "server-only";

const SAFE_PLATFORM_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$/;

export function isSafePlatformAdminId(value: string) {
  return SAFE_PLATFORM_ID.test(value);
}
