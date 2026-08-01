import type { DocumentPickerAsset } from "expo-document-picker";

import { API_BASE_URL } from "@/src/auth/mobile-session";

const ATTACHMENT_ID = /^attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$/;
const MIME_TYPE =
	/^[a-z0-9][a-z0-9!#$&^_.+-]{0,126}\/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$/;
const CONTENT_PATH =
	/^\/api\/product\/v1\/attachments\/attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}\/content$/;

export type AuthorizedFetch = typeof fetch;

export type MobileAttachmentCapability = {
	readonly projectId: string;
	readonly threadId: string;
	readonly accept: string;
	readonly maxSizeBytes: number;
	readonly maxAttachmentsPerMessage: number;
};

export type UploadedMobileAttachment = {
	readonly attachmentId: string;
	readonly filename: string;
	readonly mimeType: string;
	readonly contentPath: string;
};

const extensionMimeTypes: Readonly<Record<string, string>> = {
	csv: "text/csv",
	docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	gif: "image/gif",
	heic: "image/heic",
	heif: "image/heif",
	jpeg: "image/jpeg",
	jpg: "image/jpeg",
	json: "application/json",
	log: "text/plain",
	markdown: "text/markdown",
	md: "text/markdown",
	pdf: "application/pdf",
	png: "image/png",
	txt: "text/plain",
	webp: "image/webp",
	xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
};

const createAttachmentId = () => {
	const random =
		globalThis.crypto?.randomUUID?.().replaceAll("-", "") ??
		`${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
	return `attachment_${random}`;
};

const readError = async (response: Response) => {
	try {
		const value = (await response.clone().json()) as {
			detail?: { message?: unknown; code?: unknown };
			message?: unknown;
			code?: unknown;
		};
		const error = value.detail ?? value;
		return new Error(
			typeof error.message === "string"
				? error.message
				: `Не удалось загрузить вложение (${response.status}).`,
		);
	} catch {
		return new Error(`Не удалось загрузить вложение (${response.status}).`);
	}
};

const assertMimeType = (value: string) => {
	if (!MIME_TYPE.test(value)) throw new Error("Тип файла не поддерживается.");
	return value;
};

export const inferMimeType = (asset: DocumentPickerAsset) => {
	const declared = asset.mimeType?.split(";", 1)[0]?.trim().toLowerCase();
	if (declared && MIME_TYPE.test(declared)) return declared;
	const extension = asset.name.split(".").pop()?.toLowerCase() ?? "";
	const inferred = extensionMimeTypes[extension];
	if (!inferred) throw new Error("Не удалось определить тип файла.");
	return inferred;
};

const parseCapability = (value: unknown): MobileAttachmentCapability => {
	const record = value as Record<string, unknown>;
	if (
		typeof value !== "object" ||
		value === null ||
		!("enabled" in value) ||
		value.enabled !== true ||
		!("projectId" in value) ||
		typeof value.projectId !== "string" ||
		!("threadId" in value) ||
		typeof value.threadId !== "string" ||
		!("accept" in value) ||
		typeof value.accept !== "string" ||
		!("maxSizeBytes" in value) ||
		!Number.isSafeInteger(value.maxSizeBytes) ||
		!("maxAttachmentsPerMessage" in value) ||
		!Number.isSafeInteger(value.maxAttachmentsPerMessage)
	) {
		throw new Error("Backend не подтвердил загрузку вложений.");
	}
	return {
		projectId: record.projectId as string,
		threadId: record.threadId as string,
		accept: record.accept as string,
		maxSizeBytes: record.maxSizeBytes as number,
		maxAttachmentsPerMessage: record.maxAttachmentsPerMessage as number,
	};
};

const parseUploadedAttachment = (value: unknown): UploadedMobileAttachment => {
	if (
		typeof value !== "object" ||
		value === null ||
		!("attachment_id" in value) ||
		typeof value.attachment_id !== "string" ||
		!ATTACHMENT_ID.test(value.attachment_id) ||
		!("filename" in value) ||
		typeof value.filename !== "string" ||
		!value.filename.trim() ||
		!("mime_type" in value) ||
		typeof value.mime_type !== "string" ||
		!MIME_TYPE.test(value.mime_type) ||
		!("content_path" in value) ||
		typeof value.content_path !== "string" ||
		!CONTENT_PATH.test(value.content_path)
	) {
		throw new Error("Backend вернул некорректные данные вложения.");
	}
	return {
		attachmentId: value.attachment_id,
		filename: value.filename,
		mimeType: value.mime_type,
		contentPath: value.content_path,
	};
};

export class MobileAttachmentClient {
	constructor(private readonly request: AuthorizedFetch) {}

	async capability(projectId: string, threadId: string) {
		const query = new URLSearchParams({ projectId, threadId });
		const response = await this.request(
			`${API_BASE_URL}/v1/attachments/capabilities?${query}`,
			{ headers: { Accept: "application/json" } },
		);
		if (!response.ok) throw await readError(response);
		return parseCapability(await response.json());
	}

	async upload(
		capability: MobileAttachmentCapability,
		asset: DocumentPickerAsset,
	) {
		const mimeType = assertMimeType(inferMimeType(asset));
		if (asset.size !== undefined && asset.size > capability.maxSizeBytes) {
			throw new Error("Размер вложения превышает лимит 10 МиБ.");
		}
		const body = asset.file ?? (await fetch(asset.uri).then((response) => response.blob()));
		const attachmentId = createAttachmentId();
		const response = await this.request(`${API_BASE_URL}/v1/attachments`, {
			method: "POST",
			headers: {
				Accept: "application/json",
				"Content-Type": mimeType,
				"Idempotency-Key": attachmentId,
				"X-Kolibri-Filename": encodeURIComponent(asset.name),
				"X-Kolibri-Project-Id": capability.projectId,
				"X-Kolibri-Thread-Id": capability.threadId,
			},
			body,
		});
		if (!response.ok) throw await readError(response);
		return parseUploadedAttachment(await response.json());
	}
}
