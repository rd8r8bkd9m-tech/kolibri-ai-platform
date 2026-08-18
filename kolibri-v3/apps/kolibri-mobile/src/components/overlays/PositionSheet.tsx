import { useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Icon } from "@/src/components/icons/Icon";
import { BottomSheet } from "@/src/components/ui/BottomSheet";
import { ChipsRow } from "@/src/components/ui/ChipsRow";
import { CircleButton } from "@/src/components/ui/CircleButton";
import { Field } from "@/src/components/ui/Field";
import { PillButton } from "@/src/components/ui/PillButton";
import { Stepper } from "@/src/components/ui/Stepper";
import { TotalPreview } from "@/src/components/ui/TotalPreview";
import { useDesignTokens } from "@/hooks/use-design-tokens";
import {
	FontSize,
	FontWeight,
	LineHeight,
	Spacing,
} from "@/constants/theme";
import { fmtMoney, fmtQty, lineTotal } from "@/src/utils/format";
import type { NativeEstimateRow } from "@/src/verticals/construction-estimates/contracts";

const DEFAULT_SECTIONS = ["Материалы", "Работы", "Доставка"];
const DEFAULT_UNITS = ["шт", "м²", "м", "ч", "компл."];

const kindForSection = (section: string): NativeEstimateRow["kind"] =>
	section === "Материалы"
		? "material"
		: section === "Работы"
			? "work"
			: "service";

const newId = () =>
	`row_local_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;

export type PositionSheetState = {
	mode: "view" | "edit";
	row: NativeEstimateRow | null;
};

type PositionSheetProps = {
	state: PositionSheetState | null;
	extraSections?: readonly string[];
	extraUnits?: readonly string[];
	onClose: () => void;
	onSwitchToEdit: () => void;
	onSave: (row: NativeEstimateRow) => void;
	onDelete: (id: string) => void;
};

function InfoRow({ label, value }: { label: string; value: string }) {
	const { colors } = useDesignTokens();
	const styles = useMemo(() => createInfoStyles(colors), [colors]);
	return (
		<View style={styles.infoRow}>
			<Text style={styles.infoLabel}>{label}</Text>
			<Text style={styles.infoValue}>{value}</Text>
		</View>
	);
}

type InfoRowColors = ReturnType<typeof useDesignTokens>["colors"];

const createInfoStyles = (colors: InfoRowColors) =>
	StyleSheet.create({
		infoRow: {
			alignItems: "center",
			flexDirection: "row",
			justifyContent: "space-between",
		},
		infoLabel: { color: colors.textTertiary, fontSize: FontSize.medium },
		infoValue: {
			color: colors.textPrimary,
			fontSize: FontSize.medium,
			fontWeight: FontWeight.semibold,
		},
	});

export function PositionSheet({
	state,
	extraSections,
	extraUnits,
	onClose,
	onSwitchToEdit,
	onSave,
	onDelete,
}: PositionSheetProps) {
	const { colors, radii, typography } = useDesignTokens();
	const styles = useMemo(() => createStyles(colors, radii, typography), [colors, radii, typography]);
	const base = state?.row ?? null;
	const [name, setName] = useState(base?.description ?? "");
	const [section, setSection] = useState(
		base?.section ?? DEFAULT_SECTIONS[0],
	);
	const [unit, setUnit] = useState(base?.unit ?? DEFAULT_UNITS[0]);
	const [qty, setQty] = useState(base ? Number(base.quantity) || 0 : 1);
	const [price, setPrice] = useState(
		base ? Number(base.unitPrice) || 0 : 0,
	);
	const [note, setNote] = useState(base?.specification ?? "");
	const [confirmDelete, setConfirmDelete] = useState(false);

	useEffect(() => {
		if (!confirmDelete) return;
		const timer = setTimeout(() => setConfirmDelete(false), 3000);
		return () => clearTimeout(timer);
	}, [confirmDelete]);

	const sections = useMemo(() => {
		const list = [...DEFAULT_SECTIONS];
		for (const extra of extraSections ?? []) {
			if (!list.includes(extra)) list.push(extra);
		}
		if (section && !list.includes(section)) list.push(section);
		return list;
	}, [extraSections, section]);

	const units = useMemo(() => {
		const list = [...DEFAULT_UNITS];
		for (const extra of extraUnits ?? []) {
			if (!list.includes(extra)) list.push(extra);
		}
		if (unit && !list.includes(unit)) list.push(unit);
		return list;
	}, [extraUnits, unit]);

	const total = lineTotal(qty, price);
	const valid =
		name.trim().length > 0 && name.length <= 300 && qty > 0 && price >= 0;

	const buildRow = (): NativeEstimateRow => {
		const quantity = String(Number(qty.toFixed(6)));
		const unitPrice = price.toFixed(2);
		const nextTotal = lineTotal(qty, price).toFixed(2);
		if (base) {
			return {
				...base,
				section,
				kind: kindForSection(section),
				description: name.trim(),
				unit,
				quantity,
				unitPrice,
				lineTotal: nextTotal,
				quantityBasis: "Введено пользователем",
				priceBasis: "Введено пользователем",
				specification: note.trim() ? note.trim() : undefined,
				evidenceId: undefined,
				marketAggregateId: undefined,
				priceObservationId: undefined,
				lineConfidence: "preliminary",
			};
		}
		return {
			id: newId(),
			section,
			kind: kindForSection(section),
			description: name.trim(),
			unit,
			quantity,
			unitPrice,
			lineTotal: nextTotal,
			quantityBasis: "Введено пользователем",
			priceBasis: "Введено пользователем",
			specification: note.trim() ? note.trim() : undefined,
			lineConfidence: "preliminary",
		};
	};

	const visible = state !== null;
	const mode = state?.mode ?? "view";

	return (
		<BottomSheet onClose={onClose} snap={mode === "edit" ? "edit" : "view"} visible={visible}>
			{mode === "view" && base ? (
				<View style={styles.block}>
					<View style={styles.viewHeader}>
						<View style={styles.sectionChip}>
							<Text style={styles.sectionChipText}>{base.section}</Text>
						</View>
						<CircleButton
							accessibilityLabel="Закрыть"
							onPress={onClose}
							size={40}
							variant="outline"
						>
							<Icon color={colors.textPrimary} name="close" size={20} />
						</CircleButton>
					</View>
					<Text style={styles.viewTitle}>{base.description}</Text>
					<Text style={styles.viewTotal}>
						{fmtMoney(Number(base.lineTotal) || 0)}
					</Text>
					<View style={styles.infoBox}>
						<InfoRow label="Кол-во" value={fmtQty(Number(base.quantity) || 0)} />
						<InfoRow label="Ед. изм." value={base.unit} />
						<InfoRow label="Цена" value={fmtMoney(Number(base.unitPrice) || 0)} />
						<InfoRow label="Сумма" value={fmtMoney(Number(base.lineTotal) || 0)} />
					</View>
					{base.specification ? (
						<View style={styles.noteBox}>
							<Text style={styles.noteLabel}>Примечание</Text>
							<Text style={styles.noteText}>{base.specification}</Text>
						</View>
					) : null}
					<View style={styles.actions}>
						{confirmDelete ? (
							<Pressable
								accessibilityRole="button"
								onPress={() => base && onDelete(base.id)}
								style={styles.deleteConfirm}
							>
								<Text style={styles.deleteConfirmText}>
									Подтвердить удаление
								</Text>
							</Pressable>
						) : (
							<CircleButton
								accessibilityLabel="Удалить позицию"
								onPress={() => setConfirmDelete(true)}
								size={52}
								variant="outline"
							>
								<Icon color={colors.danger} name="trash" size={22} />
							</CircleButton>
						)}
						<PillButton
							filled
							icon="squarePen"
							onPress={onSwitchToEdit}
							style={styles.editButton}
							title="Изменить"
						/>
					</View>
				</View>
			) : (
				<View style={styles.block}>
					<View style={styles.viewHeader}>
						<Text style={styles.editTitle}>
							{base ? "Позиция" : "Новая позиция"}
						</Text>
						<CircleButton
							accessibilityLabel="Закрыть"
							onPress={onClose}
							size={40}
							variant="outline"
						>
							<Icon color={colors.textPrimary} name="close" size={20} />
						</CircleButton>
					</View>
					<Field
						autoFocus={!base}
						label="Название"
						maxLength={300}
						onChangeText={setName}
						placeholder="Название работы или материала"
						value={name}
					/>
					<View style={styles.fieldGap}>
						<Text style={styles.fieldLabel}>Раздел</Text>
						<ChipsRow onSelect={setSection} options={sections} selected={section} />
					</View>
					<View style={styles.fieldGap}>
						<Text style={styles.fieldLabel}>Ед. изм.</Text>
						<ChipsRow onSelect={setUnit} options={units} selected={unit} />
					</View>
					<View style={styles.qtyPriceRow}>
						<View style={styles.qtyBlock}>
							<Text style={styles.fieldLabel}>Кол-во</Text>
							<Stepper onChange={setQty} value={qty} />
						</View>
						<View style={styles.priceBlock}>
							<Field
								keyboardType="decimal-pad"
								label="Цена"
								onChangeText={(value) =>
									setPrice(Number(value.replace(",", ".")) || 0)
								}
								placeholder="0"
								suffix="₽"
								value={price ? String(price) : ""}
							/>
						</View>
					</View>
					<TotalPreview total={total} />
					<View style={styles.fieldGap}>
						<Field
							label="Примечание"
							multiline
							onChangeText={setNote}
							value={note}
						/>
					</View>
					<PillButton
						disabled={!valid}
						filled
						icon="check"
						onPress={() => onSave(buildRow())}
						style={styles.saveButton}
						title="Сохранить"
					/>
				</View>
			)}
		</BottomSheet>
	);
}

type PositionSheetTokens = ReturnType<typeof useDesignTokens>;

const createStyles = (
	colors: PositionSheetTokens["colors"],
	radii: PositionSheetTokens["radii"],
	typography: PositionSheetTokens["typography"],
) =>
	StyleSheet.create({
		block: { gap: Spacing.lg },
		viewHeader: {
			alignItems: "center",
			flexDirection: "row",
			justifyContent: "space-between",
		},
		sectionChip: {
			backgroundColor: colors.draftBg,
			borderRadius: radii.full,
			paddingHorizontal: Spacing.lg,
			paddingVertical: Spacing.sm,
		},
		sectionChipText: {
			color: colors.textSecondary,
			fontSize: FontSize.footnote,
			fontWeight: FontWeight.semibold,
		},
		viewTitle: { ...typography.hSheet, color: colors.textPrimary },
		viewTotal: { ...typography.amountXL, color: colors.textPrimary },
		infoBox: { gap: Spacing.md },
		infoRow: {
			alignItems: "center",
			flexDirection: "row",
			justifyContent: "space-between",
		},
		infoLabel: { color: colors.textTertiary, fontSize: FontSize.medium },
		infoValue: {
			color: colors.textPrimary,
			fontSize: FontSize.medium,
			fontWeight: FontWeight.semibold,
		},
		noteBox: { gap: Spacing.xs },
		noteLabel: { ...typography.label, color: colors.textTertiary },
		noteText: {
			color: colors.textSecondary,
			fontSize: FontSize.medium,
			lineHeight: LineHeight.base,
		},
		actions: { alignItems: "center", flexDirection: "row", gap: Spacing.md },
		editButton: { flex: 1 },
		deleteConfirm: {
			alignItems: "center",
			backgroundColor: colors.danger,
			borderRadius: radii.full,
			justifyContent: "center",
			minHeight: 52,
			paddingHorizontal: Spacing.xl,
		},
		deleteConfirmText: {
			color: colors.surface,
			fontSize: FontSize.body,
			fontWeight: FontWeight.bold,
		},
		editTitle: { ...typography.hSheet, color: colors.textPrimary },
		fieldGap: { gap: Spacing.sm },
		fieldLabel: { ...typography.label, color: colors.textTertiary },
		qtyPriceRow: { flexDirection: "row", gap: Spacing.lg },
		qtyBlock: { gap: Spacing.sm },
		priceBlock: { flex: 1 },
		saveButton: { marginTop: Spacing.xs },
	});
