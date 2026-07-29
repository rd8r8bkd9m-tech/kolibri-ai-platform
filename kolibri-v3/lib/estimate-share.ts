"use client";

import { announceAuthenticationRequired } from "@/lib/identity/events";

export const ESTIMATE_SHARE_FORMAT = "pdf" as const;
const ESTIMATE_SHARE_MEDIA_TYPE = "application/pdf";

export type PreparedEstimateShare = {
  version: number;
  files: File[];
};

export type EstimateShareResult =
  | { status: "shared"; files: File[] }
  | { status: "cancelled" | "unsupported"; files: [] };

const readResponseError = async (response: Response) => {
  if (response.status === 401) announceAuthenticationRequired();
  try {
    const value = (await response.json()) as unknown;
    if (
      typeof value === "object" &&
      value !== null &&
      "message" in value &&
      typeof value.message === "string"
    ) {
      return value.message;
    }
  } catch {
    // A bounded, user-safe fallback is returned below.
  }
  return "Не удалось подготовить файлы сметы.";
};

const safeExportFilename = (disposition: string, fallback: string) => {
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="([^"]+)"/i)?.[1];
  let candidate = plain ?? fallback;
  if (encoded) {
    try {
      candidate = decodeURIComponent(encoded);
    } catch {
      candidate = plain ?? fallback;
    }
  }
  const sanitized = candidate
    .replaceAll("\\", "_")
    .replaceAll("/", "_")
    .replace(/[\u0000-\u001f\u007f]/g, "")
    .trim();
  return sanitized || fallback;
};

export async function prepareEstimateShareFiles(
  projectId: string,
  requestedVersion: number,
): Promise<PreparedEstimateShare> {
  const response = await fetch(
    `/api/v3/projects/${encodeURIComponent(
      projectId,
    )}/estimate/export/${ESTIMATE_SHARE_FORMAT}`,
    {
      method: "GET",
      headers: { Accept: ESTIMATE_SHARE_MEDIA_TYPE },
      credentials: "same-origin",
      cache: "no-store",
    },
  );
  if (!response.ok) throw new Error(await readResponseError(response));
  const contentType = (response.headers.get("content-type") ?? "")
    .split(";", 1)[0]
    ?.trim()
    .toLowerCase();
  const disposition = response.headers.get("content-disposition") ?? "";
  if (
    contentType !== ESTIMATE_SHARE_MEDIA_TYPE ||
    !/^attachment(?:;|$)/i.test(disposition)
  ) {
    throw new Error(
      "Сервер вернул не комплект сметы. Обновите страницу и повторите.",
    );
  }
  const filename = safeExportFilename(
    disposition,
    `Смета-v${requestedVersion}.pdf`,
  );
  const file = new File([await response.blob()], filename, {
    type: ESTIMATE_SHARE_MEDIA_TYPE,
  });
  return {
    version: requestedVersion,
    files: [file],
  };
}

const systemShareError = (error: unknown) => {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") {
      return new Error(
        "Браузер не разрешил открыть системное меню. Проверьте разрешение на отправку файлов.",
      );
    }
    if (error.name === "InvalidStateError") {
      return new Error(
        "Системное меню уже открыто. Закройте его и повторите.",
      );
    }
  }
  return new Error("Не удалось открыть системное меню отправки файлов.");
};

export async function sharePreparedEstimateFiles(
  prepared: PreparedEstimateShare,
  shareData: Omit<ShareData, "files">,
): Promise<EstimateShareResult> {
  const payload: ShareData = {
    ...shareData,
    files: prepared.files,
  };
  if (
    typeof navigator.share !== "function" ||
    (typeof navigator.canShare === "function" &&
      !navigator.canShare(payload))
  ) {
    return { status: "unsupported", files: [] };
  }
  try {
    await navigator.share(payload);
    return { status: "shared", files: prepared.files };
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return { status: "cancelled", files: [] };
    }
    throw systemShareError(error);
  }
}

export const shareResultMessage = (result: EstimateShareResult) => {
  if (result.status === "cancelled") return "Передача отменена";
  if (result.status === "unsupported") {
    return "Системная отправка файлов недоступна на этом устройстве";
  }
  return "Файлы сметы переданы";
};
