"use client";

import { makeAssistantToolUI } from "@assistant-ui/react";
import { DownloadIcon, ImageIcon, LoaderCircleIcon } from "lucide-react";

type GeneratedImageProjection = {
  readonly attachmentId: string;
  readonly artifactId: string;
  readonly artifactVersion: number;
  readonly contentHash: string;
  readonly filename: string;
  readonly mimeType: "image/png" | "image/jpeg" | "image/webp";
  readonly sizeBytes: number;
  readonly contentPath: string;
  readonly providerLabel: string;
  readonly revisedPrompt: string | null;
};

const SAFE_ATTACHMENT_PATH =
  /^\/api\/product\/v1\/attachments\/attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}\/content$/;
const SAFE_ATTACHMENT_ID =
  /^attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$/;
const SAFE_ARTIFACT_ID =
  /^artifact_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$/;
const SHA256 = /^sha256:[0-9a-f]{64}$/;
const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const parseResult = (value: unknown): GeneratedImageProjection | null => {
  if (typeof value === "string") {
    try {
      value = JSON.parse(value) as unknown;
    } catch {
      return null;
    }
  }
  if (
    !isRecord(value) ||
    value.$type !== "GeneratedImage" ||
    value.schemaId !== "kolibri.product.attachment" ||
    value.schemaVersion !== "1.0" ||
    typeof value.attachmentId !== "string" ||
    !SAFE_ATTACHMENT_ID.test(value.attachmentId) ||
    typeof value.artifactId !== "string" ||
    !SAFE_ARTIFACT_ID.test(value.artifactId) ||
    typeof value.artifactVersion !== "number" ||
    !Number.isSafeInteger(value.artifactVersion) ||
    value.artifactVersion < 1 ||
    typeof value.contentHash !== "string" ||
    !SHA256.test(value.contentHash) ||
    typeof value.filename !== "string" ||
    value.filename.length < 1 ||
    value.filename.length > 240 ||
    typeof value.mimeType !== "string" ||
    !IMAGE_TYPES.has(value.mimeType) ||
    typeof value.sizeBytes !== "number" ||
    !Number.isSafeInteger(value.sizeBytes) ||
    value.sizeBytes < 1 ||
    value.sizeBytes > 50 * 1_024 * 1_024 ||
    typeof value.contentPath !== "string" ||
    !SAFE_ATTACHMENT_PATH.test(value.contentPath) ||
    value.contentPath !==
      `/api/product/v1/attachments/${value.attachmentId}/content` ||
    value.status !== "available" ||
    typeof value.providerLabel !== "string" ||
    value.providerLabel.length < 1 ||
    value.providerLabel.length > 120 ||
    !(
      value.revisedPrompt === null ||
      (typeof value.revisedPrompt === "string" &&
        value.revisedPrompt.length >= 1 &&
        value.revisedPrompt.length <= 8_000)
    )
  ) {
    return null;
  }
  return {
    attachmentId: value.attachmentId,
    artifactId: value.artifactId,
    artifactVersion: value.artifactVersion,
    contentHash: value.contentHash,
    filename: value.filename,
    mimeType: value.mimeType as GeneratedImageProjection["mimeType"],
    sizeBytes: value.sizeBytes,
    contentPath: value.contentPath,
    providerLabel: value.providerLabel,
    revisedPrompt: value.revisedPrompt,
  };
};

const GeneratedImageCard = ({
  image,
}: {
  readonly image: GeneratedImageProjection;
}) => (
  <figure
    className="border-border/70 bg-card min-w-0 overflow-hidden rounded-[24px] border"
    data-slot="generated-image-artifact"
  >
    {/* The path is an authenticated same-origin BFF route, never a provider URL. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img
      alt={image.revisedPrompt ?? "Изображение, созданное Kolibri"}
      className="bg-muted block aspect-square h-auto max-h-[680px] w-full object-contain"
      decoding="async"
      loading="lazy"
      src={image.contentPath}
    />
    <figcaption className="flex min-w-0 items-center gap-3 px-4 py-3">
      <ImageIcon
        aria-hidden="true"
        className="text-muted-foreground size-4 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{image.filename}</p>
        <p className="text-muted-foreground truncate text-xs">
          {image.providerLabel} · {(image.sizeBytes / 1_024).toFixed(1)} КБ
        </p>
      </div>
      <a
        aria-label={`Скачать ${image.filename}`}
        className="border-border hover:bg-muted focus-visible:ring-ring inline-flex size-9 shrink-0 items-center justify-center rounded-full border transition-colors focus-visible:ring-2 focus-visible:outline-none"
        download={image.filename}
        href={image.contentPath}
      >
        <DownloadIcon aria-hidden="true" className="size-4" />
      </a>
    </figcaption>
  </figure>
);

export const GeneratedImageToolUI = makeAssistantToolUI({
  toolName: "generate_image",
  render: ({ args, result, status }) => {
    if (status.type === "running") {
      return (
        <div
          className="border-border/70 text-muted-foreground flex min-h-36 items-center justify-center gap-2 rounded-[24px] border text-sm"
          role="status"
          aria-live="polite"
        >
          <LoaderCircleIcon
            aria-hidden="true"
            className="size-4 animate-spin"
          />
          Создаю изображение
          {typeof args.prompt === "string" && args.prompt.trim()
            ? " по вашему описанию"
            : ""}
          …
        </div>
      );
    }

    const image = parseResult(result);
    if (image === null) {
      return (
        <div
          className="border-destructive/35 text-destructive rounded-xl border border-dashed px-4 py-3 text-sm"
          role="alert"
        >
          Изображение не прошло проверку формата и не было показано.
        </div>
      );
    }
    return <GeneratedImageCard image={image} />;
  },
});
