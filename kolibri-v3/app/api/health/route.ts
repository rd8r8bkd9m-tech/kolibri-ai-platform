import { v3BackendUrl } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const HEALTH_PATH = "/v1/ready";
const HEALTH_TIMEOUT_MS = 3_000;
const MAX_HEALTH_BODY_BYTES = 4_096;
const RELEASE_ID_FALLBACK = "unversioned";
const RELEASE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const RELEASE_COMMIT_PATTERN = /^[0-9a-f]{40}$/;
const RESPONSE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
  "Content-Type": "application/json; charset=utf-8",
  Pragma: "no-cache",
  "X-Content-Type-Options": "nosniff",
};

function releaseId() {
  const candidate = process.env.KOLIBRI_RELEASE_ID?.trim();
  return candidate && RELEASE_ID_PATTERN.test(candidate)
    ? candidate
    : RELEASE_ID_FALLBACK;
}

function releaseCommit() {
  const candidate = process.env.KOLIBRI_RELEASE_COMMIT?.trim();
  return candidate && RELEASE_COMMIT_PATTERN.test(candidate)
    ? candidate
    : undefined;
}

function releaseProvenance() {
  const rawId = process.env.KOLIBRI_RELEASE_ID?.trim();
  const rawCommit = process.env.KOLIBRI_RELEASE_COMMIT?.trim();
  if (!rawId && !rawCommit) {
    return {
      valid: true,
      payload: { releaseId: RELEASE_ID_FALLBACK },
    };
  }
  const id = releaseId();
  const commit = releaseCommit();
  if (id === RELEASE_ID_FALLBACK || !commit) {
    return {
      valid: false,
      payload: { releaseId: RELEASE_ID_FALLBACK },
    };
  }
  return {
    valid: true,
    payload: { releaseId: id, releaseCommit: commit },
  };
}

/** @param {Response} response */
async function readBoundedJson(response: Response) {
  const declaredLength = Number(response.headers.get("content-length"));
  if (
    Number.isFinite(declaredLength) &&
    declaredLength > MAX_HEALTH_BODY_BYTES
  ) {
    throw new RangeError("Health response is too large.");
  }

  if (!response.body) {
    throw new SyntaxError("Health response is empty.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let size = 0;
  let text = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_HEALTH_BODY_BYTES) {
        await reader.cancel().catch(() => undefined);
        throw new RangeError("Health response is too large.");
      }
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
  } finally {
    reader.releaseLock();
  }

  return JSON.parse(text);
}

/**
 * @param {unknown} value
 * @param {{ releaseId: string; releaseCommit?: string }} expected
 */
function isReadyHealth(
  value: unknown,
  expected: { releaseId: string; releaseCommit?: string },
) {
  const baseReady =
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    value.status === "ok" &&
    "service" in value &&
    value.service === "kolibri-v3";
  if (!baseReady) return false;
  if (expected.releaseId === RELEASE_ID_FALLBACK) {
    return !("releaseId" in value) && !("releaseCommit" in value);
  }
  return (
    "releaseId" in value &&
    value.releaseId === expected.releaseId &&
    "releaseCommit" in value &&
    value.releaseCommit === expected.releaseCommit
  );
}

/**
 * @param {number} status
 * @param {Record<string, string | undefined>} payload
 * @param {boolean} head
 */
function publicResponse(
  status: number,
  payload: Record<string, string | undefined>,
  head: boolean,
) {
  return new Response(head ? null : JSON.stringify(payload), {
    status,
    headers: RESPONSE_HEADERS,
  });
}

/** @param {boolean} head */
async function readinessResponse(head: boolean) {
  const provenance = releaseProvenance();
  try {
    if (!provenance.valid) {
      throw new Error("Release identity is not configured.");
    }
    const upstream = await fetch(v3BackendUrl(HEALTH_PATH), {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
    });
    if (
      !upstream.ok ||
      !isReadyHealth(await readBoundedJson(upstream), provenance.payload)
    ) {
      throw new Error("Backend is not ready.");
    }

    return publicResponse(
      200,
      {
        status: "ok",
        service: "kolibri-v3",
        ...provenance.payload,
      },
      head,
    );
  } catch {
    return publicResponse(
      503,
      {
        status: "unavailable",
        service: "kolibri-v3",
        ...provenance.payload,
        code: "backend_not_ready",
      },
      head,
    );
  }
}

export function GET() {
  return readinessResponse(false);
}

export function HEAD() {
  return readinessResponse(true);
}
