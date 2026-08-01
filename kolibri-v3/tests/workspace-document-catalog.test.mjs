import assert from "node:assert/strict";
import test from "node:test";

import { parseWorkspaceDocuments } from "../lib/workspace-documents.ts";

const identity = {
	projectId: "project_catalog_frontend_01",
	projectName: "Ремонт квартиры",
	updatedAt: "2026-08-01T13:00:00Z",
};

test("workspace catalog maps all persisted document slot types honestly", () => {
	const documents = parseWorkspaceDocuments({
		documents: [
			{
				...identity,
				id: "document_source_frontend_01",
				slotType: "source-data",
				category: "documents",
				kind: "document",
				name: "ТЗ и обмеры",
				status: "ready",
				version: 2,
				editable: false,
			},
			{
				...identity,
				id: "document_estimate_frontend_01",
				slotType: "estimate",
				category: "estimates",
				kind: "estimate",
				name: "Предварительная смета",
				status: "draft",
				version: 3,
				rowCount: 14,
				total: "125000.00",
				currency: "RUB",
				editable: true,
			},
			{
				...identity,
				id: "document_proposal_frontend_01",
				slotType: "commercial-proposal",
				category: "documents",
				kind: "document",
				name: "Коммерческое предложение",
				status: "stale",
				version: 4,
				editable: false,
			},
			{
				...identity,
				id: "document_contract_frontend_01",
				slotType: "contract",
				category: "contracts",
				kind: "contract",
				name: "Договор подряда",
				status: "revoked",
				version: 5,
				editable: false,
			},
		],
	});

	assert.deepEqual(documents, [
		{
			category: "documents",
			documentId: "document_source_frontend_01",
			editable: false,
			id: "document_source_frontend_01",
			kind: "document",
			modifiedAt: "01.08.2026",
			name: "ТЗ и обмеры",
			projectId: identity.projectId,
			projectName: identity.projectName,
			slotType: "source-data",
			size: "Версия 2",
			status: "Проверен",
			version: 2,
		},
		{
			category: "estimates",
			documentId: "document_estimate_frontend_01",
			editable: true,
			id: "document_estimate_frontend_01",
			kind: "estimate",
			modifiedAt: "01.08.2026",
			name: "Предварительная смета",
			projectId: identity.projectId,
			projectName: identity.projectName,
			slotType: "estimate",
			size: "14 поз.",
			status: "Черновик",
			version: 3,
			rowCount: 14,
			total: "125000.00",
		},
		{
			category: "documents",
			documentId: "document_proposal_frontend_01",
			editable: false,
			id: "document_proposal_frontend_01",
			kind: "document",
			modifiedAt: "01.08.2026",
			name: "Коммерческое предложение",
			projectId: identity.projectId,
			projectName: identity.projectName,
			slotType: "commercial-proposal",
			size: "Версия 4",
			status: "Устарел",
			version: 4,
		},
		{
			category: "contracts",
			documentId: "document_contract_frontend_01",
			editable: false,
			id: "document_contract_frontend_01",
			kind: "contract",
			modifiedAt: "01.08.2026",
			name: "Договор подряда",
			projectId: identity.projectId,
			projectName: identity.projectName,
			slotType: "contract",
			size: "Версия 5",
			status: "Отозван",
			version: 5,
		},
	]);
});

test("workspace catalog rejects mismatched slot presentation metadata", () => {
	assert.throws(
		() =>
			parseWorkspaceDocuments({
				documents: [
					{
						...identity,
						id: "document_contract_frontend_02",
						slotType: "contract",
						category: "documents",
						kind: "document",
						name: "Не договор",
						status: "draft",
						version: 1,
						editable: false,
					},
				],
			}),
		/Document catalog has an incompatible shape/,
	);
});
