import "server-only";

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);
const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "authorization",
  "content-length",
  "content-type",
  "cookie",
  "idempotency-key",
  "last-event-id",
  "origin",
  "x-csrf-token",
  "x-kolibri-filename",
  "x-kolibri-project-id",
  "x-kolibri-thread-id",
] as const;
const FORWARDED_RESPONSE_HEADERS = [
  "cache-control",
  "content-disposition",
  "content-length",
  "content-security-policy",
  "content-type",
  "etag",
  "location",
  "pragma",
  "x-accel-buffering",
  "x-ag-ui-protocol-version",
  "x-kolibri-content-sha256",
  "x-kolibri-estimate-version",
  "x-kolibri-run-id",
  "x-kolibri-source-sha256",
  "www-authenticate",
] as const;

export class V3BackendConfigurationError extends Error {
  constructor() {
    super("Kolibri V3 backend is not configured.");
    this.name = "V3BackendConfigurationError";
  }
}

function isLoopback(hostname: string) {
  const normalized = hostname
    .toLowerCase()
    .replace(/^\[(.*)\]$/, "$1")
    .replace(/\.$/, "");
  if (LOOPBACK_HOSTS.has(normalized)) return true;
  return /^127(?:\.\d{1,3}){3}$/.test(normalized);
}

export function resolveV3BackendBaseUrl(
  value = process.env.KOLIBRI_V3_BACKEND_URL,
) {
  const candidate = value?.trim();
  if (!candidate || candidate.length > 2_048) {
    throw new V3BackendConfigurationError();
  }

  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    throw new V3BackendConfigurationError();
  }

  const safeProtocol =
    url.protocol === "https:" ||
    (url.protocol === "http:" && isLoopback(url.hostname));
  if (
    !safeProtocol ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new V3BackendConfigurationError();
  }

  url.pathname = `${url.pathname.replace(/\/+$/, "")}/`;
  return url;
}

export function v3BackendUrl(pathname: string) {
  if (
    !pathname.startsWith("/v1/") ||
    pathname.includes("\\") ||
    pathname.split("/").includes("..")
  ) {
    throw new V3BackendConfigurationError();
  }
  return new URL(pathname.replace(/^\/+/, ""), resolveV3BackendBaseUrl());
}

function requestHeaders(request: Request) {
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

function appendSetCookies(target: Headers, source: Headers) {
  const withCookies = source as Headers & {
    getSetCookie?: () => string[];
  };
  const values = withCookies.getSetCookie?.() ?? [];
  if (values.length > 0) {
    for (const value of values) target.append("set-cookie", value);
    return;
  }

  const value = source.get("set-cookie");
  if (value) target.append("set-cookie", value);
}

export async function fetchV3Backend(
  request: Request,
  pathname: string,
  options: {
    body?: BodyInit | null;
    method?: string;
    signal?: AbortSignal;
  } = {},
) {
  const body =
    options.body === null ||
    options.body === undefined ||
    request.method === "GET" ||
    request.method === "HEAD"
      ? undefined
      : options.body;
  const init: RequestInit & { duplex?: "half" } = {
    method: options.method ?? request.method,
    headers: requestHeaders(request),
    body,
    cache: "no-store",
    redirect: "manual",
    signal: options.signal ?? request.signal,
  };
  if (body instanceof ReadableStream) init.duplex = "half";
  return fetch(v3BackendUrl(pathname), init);
}

export function relayV3BackendResponse(
  upstream: Response,
  body: BodyInit | null = upstream.body,
) {
  const headers = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  appendSetCookies(headers, upstream.headers);
  headers.set("x-content-type-options", "nosniff");

  return new Response(body, {
    status: upstream.status,
    headers,
  });
}

export function v3BackendUnavailableResponse() {
  return Response.json(
    {
      code: "v3_backend_unavailable",
      message: "Новый backend Kolibri сейчас недоступен.",
    },
    {
      status: 503,
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}

export async function readBoundedRequestBody(
  request: Request,
  maxBytes = 64 * 1_024,
) {
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > maxBytes) {
    throw new RangeError("Request body is too large.");
  }
  const body = await request.arrayBuffer();
  if (body.byteLength > maxBytes) {
    throw new RangeError("Request body is too large.");
  }
  return body;
}

export async function proxyV3JsonRequest(
  request: Request,
  pathname: string,
  options: {
    maxRequestBytes?: number;
    method?: string;
  } = {},
) {
  try {
    const method = options.method ?? request.method;
    const body =
      method === "GET" || method === "HEAD"
        ? null
        : await readBoundedRequestBody(
            request,
            options.maxRequestBytes ?? 64 * 1_024,
          );
    const upstream = await fetchV3Backend(request, pathname, {
      method,
      body,
    });
    return relayV3BackendResponse(upstream);
  } catch (error) {
    if (error instanceof RangeError) {
      return Response.json(
        {
          code: "request_too_large",
          message: "Запрос превышает допустимый размер.",
        },
        { status: 413, headers: { "Cache-Control": "no-store" } },
      );
    }
    return v3BackendUnavailableResponse();
  }
}
