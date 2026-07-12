const IMAGE_LOCATOR = /^\/v1\/public\/artifacts\/artifact_image_[A-Za-z0-9._:-]+\/content$/;
const IMAGE_MEDIA_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

export function imageArtifactUrl(artifact, { download = false } = {}) {
  if (artifact?.status !== "materialized") return "";
  if (!IMAGE_MEDIA_TYPES.has(String(artifact?.media_type || "").toLowerCase())) return "";
  const locator = artifact?.locator;
  if (typeof locator !== "string" || !IMAGE_LOCATOR.test(locator)) return "";
  return download ? `${locator}?download=true` : locator;
}
