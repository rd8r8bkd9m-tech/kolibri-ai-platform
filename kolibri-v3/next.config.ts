import { withAui } from "@assistant-ui/next";
import type { NextConfig } from "next";

const strictCspDirectives = [
  "default-src 'self'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "object-src 'none'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "connect-src 'self' https: wss:",
  "media-src 'self' blob: https:",
  "worker-src 'self' blob:",
  "manifest-src 'self'",
].join("; ");
const enforceCsp =
  process.env.KOLIBRI_CSP_MODE?.trim().toLowerCase() === "enforce";
const reportOnlyCspDirectives =
  process.env.NODE_ENV === "development"
    ? strictCspDirectives.replace(
        "script-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      )
    : strictCspDirectives;
const enforcedCspDirectives = strictCspDirectives.replace(
  "script-src 'self'",
  // Next emits bounded inline bootstrap scripts. Keep the strict policy in
  // report-only alongside this compatibility policy until nonce propagation
  // is implemented across every dynamic route.
  "script-src 'self' 'unsafe-inline'",
);
const cspHeaders = enforceCsp
  ? [
      { key: "Content-Security-Policy", value: enforcedCspDirectives },
      {
        key: "Content-Security-Policy-Report-Only",
        value: reportOnlyCspDirectives,
      },
    ]
  : [
      {
        key: "Content-Security-Policy-Report-Only",
        value: reportOnlyCspDirectives,
      },
    ];

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "127.0.0.2", "localhost", "dev.kolibriai.ru"],
  devIndicators: false,
  experimental: {
    webpackMemoryOptimizations: true,
  },
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          ...cspHeaders,
          {
            key: "Permissions-Policy",
            value:
              "camera=(), geolocation=(), microphone=(self), payment=(), web-share=(self)",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
        ],
      },
    ];
  },
};

export default withAui(nextConfig);
