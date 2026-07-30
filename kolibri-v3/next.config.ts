import { withAui } from "@assistant-ui/next";
import type { NextConfig } from "next";

const releaseIdPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const configuredReleaseId = process.env.KOLIBRI_RELEASE_ID?.trim();
const publicReleaseId =
  configuredReleaseId && releaseIdPattern.test(configuredReleaseId)
    ? configuredReleaseId
    : "unversioned";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
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
          {
            key: "Permissions-Policy",
            value: "web-share=(self)",
          },
          {
            key: "X-Kolibri-Release",
            value: publicReleaseId,
          },
        ],
      },
    ];
  },
};

export default withAui(nextConfig);
