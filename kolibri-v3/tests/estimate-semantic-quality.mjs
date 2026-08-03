const REQUIRED_KINDS = ["work", "material", "equipment", "service"];
const ALLOWED_KINDS = new Set([
	...REQUIRED_KINDS,
	"overhead",
	"tax",
	"contingency",
]);

const asText = (value) => (typeof value === "string" ? value.trim() : "");

const normalizeText = (value) =>
	asText(value)
		.normalize("NFKC")
		.toLocaleLowerCase("ru-RU")
		.replaceAll("ё", "е")
		.replace(/\s+/gu, " ")
		.trim();

const templateFingerprint = (value) =>
	normalizeText(value)
		.replace(/\b(?:row|line|item|resource|operation)[_-]?[a-z0-9._~-]+\b/giu, "#")
		.replace(/\b[0-9a-f]{8,}\b/giu, "#")
		.replace(/\d+(?:[.,]\d+)?/gu, "#")
		.replace(/[№#._,:;()\[\]{}\/\\-]+/gu, " ")
		.replace(/\s+/gu, " ")
		.trim();

const PLACEHOLDER_PATTERNS = [
	/(?:ресурсн\p{L}*\s+)?позици\p{L}*\s*(?:№|#|n[oо]\.?)?\s*\d+/ui,
	/\b(?:item|resource|row|line)\s*(?:№|#|no\.?)?\s*\d+\b/ui,
	/(?:тестов\p{L}*|синтетическ\p{L}*)\s+(?:позици\p{L}*|ресурс\p{L}*)/ui,
];

const SECTION_PLACEHOLDER = /^раздел\s*(?:№|#)?\s*\d+$/ui;
const COMBINED_WORK_MATERIAL =
	/(?:работ\p{L}*\s+(?:и|с)\s+материал\p{L}*|с\s+материал\p{L}*|включая\s+(?:все\s+)?материал\p{L}*|поставк\p{L}*\s+и\s+монтаж\p{L}*|монтаж\p{L}*\s+и\s+поставк\p{L}*)/ui;
const FIXTURE_BASIS =
	/(?:тестов\p{L}*\s+(?:проектн\p{L}*\s+)?(?:объем\p{L}*|количеств\p{L}*)|(?:qa|тестов\p{L}*)[-\s]*(?:цен\p{L}*|оценк\p{L}*))/ui;

const increment = (map, key) => map.set(key, (map.get(key) ?? 0) + 1);

const sampleIds = (rows, indexes, limit = 8) =>
	indexes.slice(0, limit).map((index) => asText(rows[index]?.id) || `row@${index}`);

const parseUnsignedDecimal = (value) => {
	const text = asText(value);
	const match = /^(0|[1-9]\d*)(?:\.(\d+))?$/.exec(text);
	if (!match) return null;
	const fraction = match[2] ?? "";
	return {
		integer: BigInt(`${match[1]}${fraction}`),
		scale: fraction.length,
	};
};

const powerOfTen = (exponent) => 10n ** BigInt(exponent);

export function decimalProductToMoney(quantity, unitPrice) {
	const left = parseUnsignedDecimal(quantity);
	const right = parseUnsignedDecimal(unitPrice);
	if (!left || !right) return null;
	const denominator = powerOfTen(left.scale + right.scale);
	const scaled = left.integer * right.integer * 100n;
	let cents = scaled / denominator;
	const remainder = scaled % denominator;
	if (remainder * 2n >= denominator) cents += 1n;
	return `${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
}

const evidenceReference = (row) => {
	const nested =
		row && typeof row.priceEvidence === "object" && row.priceEvidence !== null
			? row.priceEvidence
			: row &&
				  typeof row.enginePriceProvenance === "object" &&
				  row.enginePriceProvenance !== null
				? row.enginePriceProvenance
				: null;
	const directId = [
		row?.evidenceId,
		row?.priceEvidenceId,
		row?.priceObservationId,
		row?.marketAggregateId,
	].some((value) => asText(value).length > 0);
	const nestedId = nested
		? [
				nested.evidenceId,
				nested.quoteId,
				nested.sourceId,
				nested.sourceReference,
				nested.snapshotHash,
			].some((value) => asText(value).length > 0)
		: false;
	return { nested, present: directId || nestedId };
};

const evidenceLooksAuditable = (evidence) => {
	if (!evidence) return false;
	const source = [
		evidence.sourceUrl,
		evidence.sourceUri,
		evidence.sourceId,
		evidence.sourceReference,
	].some((value) => asText(value).length > 0);
	const observed = [
		evidence.observedAt,
		evidence.priceDate,
		evidence.retrievedAt,
	].some((value) => asText(value).length > 0);
	const snapshot = [evidence.snapshotHash, evidence.evidenceHash].some(
		(value) => asText(value).length > 0,
	);
	return source && observed && asText(evidence.region).length > 0 && snapshot;
};

/**
 * Test-side acceptance oracle. It deliberately uses only the public estimate
 * row contract, so a fixture cannot gain semantic credibility by importing a
 * private backend implementation.
 */
export function analyzeEstimateQuality(rows, options = {}) {
	const settings = {
		minimumRows: options.minimumRows ?? 1_000,
		minimumSections: options.minimumSections ?? 15,
		requiredKinds: options.requiredKinds ?? REQUIRED_KINDS,
		minimumUniqueDescriptionRatio:
			options.minimumUniqueDescriptionRatio ?? 0.3,
		maximumTemplateFamilyRatio: options.maximumTemplateFamilyRatio ?? 0.08,
		minimumTemplateFamilySize: options.minimumTemplateFamilySize ?? 10,
		requireLinkage: options.requireLinkage ?? true,
		requireArithmetic: options.requireArithmetic ?? true,
	};

	if (!Array.isArray(rows)) {
		return {
			ok: false,
			errors: ["Estimate rows must be an array."],
			metrics: { rowCount: 0 },
		};
	}

	const errors = [];
	const sections = new Set();
	const kinds = new Set();
	const descriptions = new Set();
	const exactSignatures = new Map();
	const fingerprints = new Map();
	const placeholderIndexes = [];
	const sectionPlaceholderIndexes = [];
	const missingBasisIndexes = [];
	const missingPriceBasisIndexes = [];
	const fixtureBasisIndexes = [];
	const missingLinkageIndexes = [];
	const missingEvidenceIndexes = [];
	const unauditableEvidenceIndexes = [];
	const invalidConfidenceIndexes = [];
	const dishonestAiEvidenceIndexes = [];
	const invalidUnitIndexes = [];
	const invalidKindIndexes = [];
	const arithmeticIndexes = [];
	const nonAtomicIndexes = [];
	const duplicateIndexes = [];
	const confidenceCounts = new Map();
	let evidenceReferenceCount = 0;

	for (const [index, row] of rows.entries()) {
		if (!row || typeof row !== "object" || Array.isArray(row)) {
			errors.push(`row@${index} is not an object.`);
			continue;
		}
		const section = normalizeText(row.section);
		const kind = normalizeText(row.kind);
		const description = normalizeText(row.description);
		const unit = normalizeText(row.unit);
		if (section) sections.add(section);
		if (kind) kinds.add(kind);
		if (!ALLOWED_KINDS.has(kind)) invalidKindIndexes.push(index);
		if (description) descriptions.add(description);
		if (!unit) invalidUnitIndexes.push(index);

		if (
			PLACEHOLDER_PATTERNS.some((pattern) => pattern.test(description))
		) {
			placeholderIndexes.push(index);
		}
		if (SECTION_PLACEHOLDER.test(section)) sectionPlaceholderIndexes.push(index);
		if (COMBINED_WORK_MATERIAL.test(description)) {
			nonAtomicIndexes.push(index);
		}

		if (!asText(row.quantityBasis)) missingBasisIndexes.push(index);
		if (!asText(row.priceBasis)) missingPriceBasisIndexes.push(index);
		if (
			FIXTURE_BASIS.test(
				`${normalizeText(row.quantityBasis)} ${normalizeText(row.priceBasis)}`,
			)
		) {
			fixtureBasisIndexes.push(index);
		}
		if (
			settings.requireLinkage &&
			(!asText(row.operationId) || !asText(row.technologyCardVersion))
		) {
			missingLinkageIndexes.push(index);
		}

		const confidence = normalizeText(row.lineConfidence);
		if (!["missing", "preliminary", "source_backed", "verified"].includes(confidence)) {
			invalidConfidenceIndexes.push(index);
		} else increment(confidenceCounts, confidence);
		const evidence = evidenceReference(row);
		if (evidence.present) evidenceReferenceCount += 1;
		if (["source_backed", "verified"].includes(confidence)) {
			if (!evidence.present) missingEvidenceIndexes.push(index);
			if (evidence.nested && !evidenceLooksAuditable(evidence.nested)) {
				unauditableEvidenceIndexes.push(index);
			}
		}
		const dishonestEvidence =
			evidence.nested?.sourceType === "ai_candidate" &&
			confidence !== "preliminary";
		const falseVerifiedEvidence =
			confidence === "verified" &&
			Boolean(evidence.nested) &&
			Object.hasOwn(evidence.nested, "verified") &&
			evidence.nested.verified !== true;
		if (dishonestEvidence || falseVerifiedEvidence) {
			dishonestAiEvidenceIndexes.push(index);
		}

		if (settings.requireArithmetic) {
			const expected = decimalProductToMoney(row.quantity, row.unitPrice);
			if (!expected || expected !== asText(row.lineTotal)) {
				arithmeticIndexes.push(index);
			}
		}

		const exactSignature = [
			section,
			kind,
			description,
			unit,
			asText(row.quantity),
			asText(row.unitPrice),
			asText(row.operationId),
			asText(row.technologyCardVersion),
		].join("|");
		if (exactSignatures.has(exactSignature)) duplicateIndexes.push(index);
		else exactSignatures.set(exactSignature, index);

		const fingerprint = templateFingerprint(`${section} ${description}`);
		if (fingerprint) increment(fingerprints, fingerprint);
	}

	if (rows.length < settings.minimumRows) {
		errors.push(
			`Only ${rows.length} rows; ${settings.minimumRows} are required for this reference scope.`,
		);
	}
	if (sections.size < settings.minimumSections) {
		errors.push(
			`Only ${sections.size} sections; ${settings.minimumSections} technology sections are required.`,
		);
	}
	const missingKinds = settings.requiredKinds.filter((kind) => !kinds.has(kind));
	if (missingKinds.length > 0) {
		errors.push(`Missing atomic row kinds: ${missingKinds.join(", ")}.`);
	}
	const uniqueDescriptionRatio = rows.length === 0 ? 0 : descriptions.size / rows.length;
	if (uniqueDescriptionRatio < settings.minimumUniqueDescriptionRatio) {
		errors.push(
			`Description diversity ${uniqueDescriptionRatio.toFixed(3)} is below ${settings.minimumUniqueDescriptionRatio.toFixed(3)}.`,
		);
	}

	const dominantFamilies = [...fingerprints.entries()]
		.filter(
			([, count]) =>
				count >= settings.minimumTemplateFamilySize &&
				rows.length > 0 &&
				count / rows.length > settings.maximumTemplateFamilyRatio,
		)
		.sort((left, right) => right[1] - left[1]);
	if (dominantFamilies.length > 0) {
		const [fingerprint, count] = dominantFamilies[0];
		errors.push(
			`Template family dominates ${count}/${rows.length} rows: ${JSON.stringify(fingerprint.slice(0, 140))}.`,
		);
	}

	const indexedFailures = [
		[placeholderIndexes, "Numbered or synthetic placeholder descriptions"],
		[sectionPlaceholderIndexes, "Numbered placeholder sections"],
		[duplicateIndexes, "Unexplained exact duplicate rows"],
		[missingBasisIndexes, "Rows without quantity basis"],
		[missingPriceBasisIndexes, "Rows without price basis"],
		[fixtureBasisIndexes, "Rows with fixture-only quantity or price basis"],
		[missingLinkageIndexes, "Rows without operation/card linkage"],
		[missingEvidenceIndexes, "Source-backed rows without evidence reference"],
		[unauditableEvidenceIndexes, "Rows with incomplete embedded evidence"],
		[invalidConfidenceIndexes, "Rows with invalid confidence status"],
		[dishonestAiEvidenceIndexes, "Rows with dishonestly promoted AI evidence"],
		[invalidUnitIndexes, "Rows without units"],
		[invalidKindIndexes, "Rows with unsupported cost kinds"],
		[arithmeticIndexes, "Rows whose line total is not deterministic quantity × price"],
		[nonAtomicIndexes, "Rows combining work and materials"],
	];
	for (const [indexes, label] of indexedFailures) {
		if (indexes.length > 0) {
			errors.push(
				`${label}: ${indexes.length}; examples ${sampleIds(rows, indexes).join(", ")}.`,
			);
		}
	}

	const metrics = {
		rowCount: rows.length,
		sectionCount: sections.size,
		kinds: [...kinds].sort(),
		uniqueDescriptionCount: descriptions.size,
		uniqueDescriptionRatio,
		placeholderCount: placeholderIndexes.length,
		exactDuplicateCount: duplicateIndexes.length,
		missingLinkageCount: missingLinkageIndexes.length,
		missingPriceBasisCount: missingPriceBasisIndexes.length,
		missingEvidenceCount: missingEvidenceIndexes.length,
		evidenceReferenceCount,
		confidenceCounts: Object.fromEntries(
			[...confidenceCounts.entries()].sort(([left], [right]) =>
				left.localeCompare(right),
			),
		),
		arithmeticMismatchCount: arithmeticIndexes.length,
		dominantTemplateFamilyCount: dominantFamilies[0]?.[1] ?? 0,
	};
	return { ok: errors.length === 0, errors, metrics };
}

export function formatEstimateQualityReport(report) {
	return JSON.stringify(report, null, 2);
}
