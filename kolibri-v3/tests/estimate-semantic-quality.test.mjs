import assert from "node:assert/strict";
import test from "node:test";

import {
	analyzeEstimateQuality,
	decimalProductToMoney,
} from "./estimate-semantic-quality.mjs";

const kinds = ["work", "material", "equipment", "service"];

const syntheticPadding = () =>
	Array.from({ length: 12 }, (_, sectionIndex) =>
		Array.from({ length: 100 }, (_, rowIndex) => ({
			id: `row_fixture_${sectionIndex}_${rowIndex}`,
			section: `Раздел ${sectionIndex + 1}`,
			kind: kinds[rowIndex % kinds.length],
			description: `Раздел ${sectionIndex + 1}, ресурсная позиция ${rowIndex + 1}`,
			unit: "шт.",
			quantity: "1",
			unitPrice: "100.00",
			lineTotal: "100.00",
			quantityBasis: "Тестовый проектный объём.",
			priceBasis: "Предварительная тестовая цена.",
			operationId: `operation_fixture_${sectionIndex}_${rowIndex}`,
			technologyCardVersion: "technology_fixture_v1",
			lineConfidence: "preliminary",
		})),
	).flat();

test("semantic gate rejects 1,200 numbered fixture rows despite a passing row count", () => {
	const report = analyzeEstimateQuality(syntheticPadding());
	assert.equal(report.ok, false);
	assert.equal(report.metrics.rowCount, 1_200);
	assert.equal(report.metrics.placeholderCount, 1_200);
	assert.match(report.errors.join("\n"), /placeholder/i);
	assert.match(report.errors.join("\n"), /technology sections/i);
});

test("semantic gate rejects missing linkage, false evidence and model arithmetic", () => {
	const report = analyzeEstimateQuality(
		[
			{
				id: "row_bad_evidence_01",
				section: "Кровля",
				kind: "work",
				description: "Монтаж мембраны с материалами",
				unit: "м²",
				quantity: "2.5",
				unitPrice: "100.00",
				lineTotal: "999.00",
				quantityBasis: "",
				priceBasis: "Модель решила, что цена верна.",
				lineConfidence: "verified",
				enginePriceProvenance: {
					sourceType: "ai_candidate",
					verified: false,
				},
			},
		],
		{
			minimumRows: 1,
			minimumSections: 1,
			requiredKinds: ["work"],
			minimumUniqueDescriptionRatio: 0,
		},
	);
	assert.equal(report.ok, false);
	const diagnostics = report.errors.join("\n");
	assert.match(diagnostics, /quantity basis/i);
	assert.match(diagnostics, /operation\/card linkage/i);
	assert.match(diagnostics, /evidence reference/i);
	assert.match(diagnostics, /AI evidence/i);
	assert.match(diagnostics, /quantity × price/i);
	assert.match(diagnostics, /combining work and materials/i);
});

test("semantic gate accepts a diverse linked preliminary reference estimate", () => {
	const sections = [
		"Подготовка площадки",
		"Земляные работы",
		"Фундаменты",
		"Монолитный каркас",
		"Наружные стены",
		"Фасад",
		"Кровля",
		"Внутренние перегородки",
		"Водоснабжение и канализация",
		"Отопление",
		"Вентиляция",
		"Электроснабжение",
		"Слаботочные системы",
		"Лифтовое оборудование",
		"Отделочные работы",
		"Благоустройство",
	];
	const resources = [
		"геодезическая разбивка",
		"щебёночное основание",
		"бетон класса B25",
		"арматурный каркас A500C",
		"газобетонный блок D500",
		"минераловатная плита",
		"кровельная мембрана",
		"стальной крепёж",
		"трубопровод из полипропилена",
		"радиатор отопления",
		"воздуховод оцинкованный",
		"кабель ВВГнг-LS",
		"пожарный извещатель",
		"лифтовая направляющая",
		"грунтовочный состав",
		"асфальтобетонная смесь",
		"контроль прочности",
		"вывоз строительного грунта",
		"башенный кран",
		"исполнительная документация",
	];
	const verbs = {
		work: "Выполнение операции",
		material: "Поставка материала",
		equipment: "Эксплуатация механизма",
		service: "Оказание услуги",
	};
	const rows = [];
	for (const [sectionIndex, section] of sections.entries()) {
		for (const [kindIndex, kind] of kinds.entries()) {
			for (const [resourceIndex, resource] of resources.entries()) {
				const unitPrice = `${100 + resourceIndex + kindIndex}.00`;
				rows.push({
					id: `row_reference_${sectionIndex}_${kindIndex}_${resourceIndex}`,
					section,
					kind,
					description: `${verbs[kind]} «${resource}» для этапа «${section}»`,
					unit: kind === "equipment" ? "маш.-ч" : "шт.",
					quantity: "1",
					unitPrice,
					lineTotal: unitPrice,
					quantityBasis: `Ресурс операции ${resource} по карте раздела ${section}.`,
					priceBasis: "Предварительная цена; требуется снабженческое подтверждение.",
					operationId: `operation_${sectionIndex}_${kindIndex}_${resourceIndex}`,
					technologyCardVersion: "technology_reference_v1",
					lineConfidence: "preliminary",
				});
			}
		}
	}
	const report = analyzeEstimateQuality(rows);
	assert.equal(report.metrics.rowCount, 1_280);
	assert.deepEqual(report.errors, []);
	assert.equal(report.ok, true);
});

test("decimal product uses fixed precision and half-up money rounding", () => {
	assert.equal(decimalProductToMoney("2.5", "100.00"), "250.00");
	assert.equal(decimalProductToMoney("0.333", "10.00"), "3.33");
	assert.equal(decimalProductToMoney("1.005", "1.00"), "1.01");
	assert.equal(decimalProductToMoney("invalid", "1.00"), null);
});

test("semantic gate accepts explicit overhead, tax and contingency rows", () => {
	const rows = ["overhead", "tax", "contingency"].map((kind, index) => ({
		id: `row_commercial_${kind}`,
		section: "Коммерческие начисления",
		kind,
		description: [
			"Накладные расходы по утверждённому правилу",
			"Налог по выбранному режиму",
			"Резерв на выявленные риски",
		][index],
		unit: "%",
		quantity: "1",
		unitPrice: `${index + 1}.00`,
		lineTotal: `${index + 1}.00`,
		quantityBasis: "Отдельное коммерческое правило версии 1.",
		priceBasis: "Детерминированный расчёт backend.",
		operationId: `operation_commercial_${kind}`,
		technologyCardVersion: "technology_reference_v1",
		lineConfidence: "preliminary",
	}));
	const report = analyzeEstimateQuality(rows, {
		minimumRows: 3,
		minimumSections: 1,
		requiredKinds: ["overhead", "tax", "contingency"],
		minimumUniqueDescriptionRatio: 0,
	});
	assert.deepEqual(report.errors, []);
});

test("source-backed row may reference canonical generation evidence by id", () => {
	const report = analyzeEstimateQuality(
		[
			{
				id: "row_source_backed_01",
				section: "Электроснабжение",
				kind: "material",
				description: "Кабель ВВГнг-LS 3×2,5 мм²",
				unit: "м",
				quantity: "10",
				unitPrice: "125.50",
				lineTotal: "1255.00",
				quantityBasis: "Длина трассы по кабельному журналу.",
				priceBasis: "Коммерческое предложение поставщика.",
				operationId: "operation_electrical_cable_01",
				technologyCardVersion: "technology_reference_v1",
				evidenceId: "estimate_evidence_supplier_01",
				lineConfidence: "source_backed",
			},
		],
		{
			minimumRows: 1,
			minimumSections: 1,
			requiredKinds: ["material"],
			minimumUniqueDescriptionRatio: 0,
		},
	);
	assert.deepEqual(report.errors, []);
	assert.equal(report.metrics.evidenceReferenceCount, 1);
});
