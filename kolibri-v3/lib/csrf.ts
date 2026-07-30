const DEFAULT_CSRF_COOKIE_NAME = "kolibri_v3_csrf";
const SAFE_COOKIE_NAME = /^[A-Za-z0-9_-]{1,120}$/;
const SAFE_CSRF_TOKEN = /^[A-Za-z0-9_-]{32,512}$/;

const configuredCookieName =
  process.env.NEXT_PUBLIC_KOLIBRI_V3_CSRF_COOKIE_NAME?.trim() ?? "";

export const CSRF_COOKIE_NAME = SAFE_COOKIE_NAME.test(configuredCookieName)
  ? configuredCookieName
  : DEFAULT_CSRF_COOKIE_NAME;

const decodeCookiePart = (value: string) => {
  try {
    return decodeURIComponent(value);
  } catch {
    return "";
  }
};

/**
 * Reads only the public double-submit CSRF cookie. The opaque session cookie
 * remains HttpOnly and is never exposed to application JavaScript.
 */
export function readCsrfToken(
  cookieHeader =
    typeof document === "undefined" ? "" : document.cookie,
): string | null {
  for (const segment of cookieHeader.split(";")) {
    const separator = segment.indexOf("=");
    if (separator < 1) continue;

    const name = decodeCookiePart(segment.slice(0, separator).trim());
    if (name !== CSRF_COOKIE_NAME) continue;

    const token = decodeCookiePart(segment.slice(separator + 1).trim());
    return SAFE_CSRF_TOKEN.test(token) ? token : null;
  }
  return null;
}

export function withCsrfHeader(headers?: HeadersInit): Headers {
  const result = new Headers(headers);
  const token = readCsrfToken();
  if (token) result.set("x-csrf-token", token);
  return result;
}
