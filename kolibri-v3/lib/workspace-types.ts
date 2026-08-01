export type WorkspaceProject = {
	id: string;
	name: string;
	updatedAt?: string | null;
};

export type WorkspaceFileKind =
	| "document"
	| "contract"
	| "estimate"
	| "drawing"
	| "attachment";

export type WorkspaceFileCategory =
	| "all"
	| "documents"
	| "contracts"
	| "estimates"
	| "drawings"
	| "attachments";

export type WorkspaceDocumentSlotType =
	| "source-data"
	| "estimate"
	| "commercial-proposal"
	| "contract";

export type WorkspaceFileStatus =
	| "Черновик"
	| "На согласовании"
	| "Подписан"
	| "Проверен"
	| "Устарел"
	| "Отозван"
	| "Вложение";

export type WorkspaceFile = {
	category: Exclude<WorkspaceFileCategory, "all">;
	documentId?: string;
	editable: boolean;
	id: string;
	kind: WorkspaceFileKind;
	modifiedAt: string;
	name: string;
	projectId?: string;
	projectName?: string;
	rowCount?: number;
	size: string;
	slotType?: WorkspaceDocumentSlotType;
	status: WorkspaceFileStatus;
	total?: string;
	version?: number;
};
