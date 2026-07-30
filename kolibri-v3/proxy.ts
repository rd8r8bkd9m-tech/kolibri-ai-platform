import { type NextRequest, NextResponse } from "next/server";

const MOBILE_PREVIEW_COOKIE = "__kolibri_mobile_preview";
const MOBILE_USER_AGENT =
  /Android|iPhone|iPad|iPod|Mobile|Silk|Kindle|BlackBerry|Opera Mini|IEMobile/i;
const STATIC_MOBILE_RESOURCE =
  /^\/app\/(?:_expo\/|assets\/|manifest\.json$|metadata\.json$|favicon\.ico$)/;

function wantsMobileClient(request: NextRequest) {
  const forcedClient = request.nextUrl.searchParams.get("client");
  if (forcedClient === "mobile") return true;
  if (request.cookies.get(MOBILE_PREVIEW_COOKIE)?.value === "1") return true;
  if (request.headers.get("sec-ch-ua-mobile") === "?1") return true;
  return MOBILE_USER_AGENT.test(request.headers.get("user-agent") ?? "");
}

function withPreviewCookie(response: NextResponse, request: NextRequest) {
  if (request.nextUrl.searchParams.get("client") === "mobile") {
    response.cookies.set(MOBILE_PREVIEW_COOKIE, "1", {
      httpOnly: true,
      maxAge: 60 * 60,
      sameSite: "lax",
      secure: request.nextUrl.protocol === "https:",
    });
  }
  return response;
}

export function proxy(request: NextRequest) {
  if (request.nextUrl.searchParams.get("client") === "desktop") {
    const response = NextResponse.next();
    response.cookies.delete(MOBILE_PREVIEW_COOKIE);
    return response;
  }
  if (!wantsMobileClient(request)) return NextResponse.next();

  const mobileDevelopmentOrigin =
    process.env.KOLIBRI_MOBILE_WEB_ORIGIN?.trim();
  if (mobileDevelopmentOrigin) {
    const destination = new URL(
      `${request.nextUrl.pathname}${request.nextUrl.search}`,
      mobileDevelopmentOrigin,
    );
    return withPreviewCookie(NextResponse.rewrite(destination), request);
  }

  if (STATIC_MOBILE_RESOURCE.test(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const destination = request.nextUrl.clone();
  destination.pathname = "/app/index.html";
  return withPreviewCookie(NextResponse.rewrite(destination), request);
}

export const config = {
  matcher: ["/app", "/app/:path*"],
};
