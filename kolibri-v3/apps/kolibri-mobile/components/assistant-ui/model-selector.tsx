import { useCallback, useEffect, useMemo, useState } from "react";
import {
	ActivityIndicator,
	Modal,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";

import { Icon } from "@/components/ui/icon";
import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { API_BASE_URL, useMobileSession } from "@/src/auth/mobile-session";
import {
	effectiveMobileModelName,
	MobileModelClient,
	type MobileModel,
} from "@/src/models/client";

export function ModelSelector() {
	const session = useMobileSession();
	const { colors } = useTheme();
	const [open, setOpen] = useState(false);
	const [catalog, setCatalog] = useState<Awaited<
		ReturnType<MobileModelClient["catalog"]>
	> | null>(null);
	const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
	const [message, setMessage] = useState("");
	const [saving, setSaving] = useState(false);

	// Models and providers are platform-admin concerns. Regular users must not
	// see provider names, model ids or connection state in the mobile UI.
	const client = useMemo(
		() => new MobileModelClient(session.authorizedFetch, API_BASE_URL),
		[session.authorizedFetch],
	);

	const load = useCallback(async () => {
		setStatus("loading");
		setMessage("");
		try {
			setCatalog(await client.catalog());
			setStatus("idle");
		} catch (reason) {
			setMessage(
				reason instanceof Error
					? reason.message
					: "Не удалось загрузить модели.",
			);
			setStatus("error");
		}
	}, [client]);

	useEffect(() => {
		if (open && status === "idle" && !catalog) {
			const timer = setTimeout(() => void load(), 0);
			return () => clearTimeout(timer);
		}
		return undefined;
	}, [catalog, load, open, status]);

	const user = session.user;
	const selectedName = effectiveMobileModelName(
		catalog,
		user?.preferredAgentProfile ?? null,
		user?.preferredModel ?? null,
	);

	const options = useMemo(() => {
		if (!catalog) return [];
		const result: MobileModel[] = [];
		const auto = catalog.models.find((model) => model.id === "auto");
		if (auto) result.push(auto);
		for (const model of catalog.models) {
			if (model.id === "auto") continue;
			if (model.profile === "auto" || model.profile === "mimo-code") {
				// Platform models and unavailable legacy entries surface as a
				// single selectable row; profiles handle the rest below.
				result.push(model);
				continue;
			}
			if (!result.some((entry) => entry.id === model.id)) result.push(model);
		}
		return result;
	}, [catalog]);

	const select = async (model: MobileModel) => {
		if (saving) return;
		haptics.selection();
		setSaving(true);
		setMessage("");
		try {
			await client.saveSettings({
				profile: model.profile === "auto" ? "auto" : model.profile,
				model: model.id === "auto" ? null : model.id,
			});
			await session.refreshProfile();
			setOpen(false);
			haptics.success();
		} catch (reason) {
			setMessage(
				reason instanceof Error ? reason.message : "Не удалось сохранить.",
			);
			haptics.error();
		} finally {
			setSaving(false);
		}
	};

	const currentId = user?.preferredModel ?? "auto";

	// Hooks above keep a stable order for every render; the ownership gate is
	// applied only at the presentation boundary.
	if (session.user?.isPlatformOwner !== true) {
		return null;
	}

	return (
		<>
			<Pressable
				accessibilityHint="Выбор модели для чата"
				accessibilityLabel={`Модель: ${selectedName}`}
				accessibilityRole="button"
				onPress={() => {
					haptics.selection();
					setOpen(true);
				}}
				style={({ pressed }) => [
					styles.pill,
					{ backgroundColor: colors.surface, borderColor: colors.border },
					pressed && styles.pressed,
				]}
			>
				<Icon name="model" size={15} color={colors.mutedForeground} />
				<Text numberOfLines={1} style={[styles.pillText, { color: colors.foreground }]}>
					{selectedName}
				</Text>
				<Icon name="chevron-down" size={14} color={colors.mutedForeground} />
			</Pressable>

			<Modal
				animationType="fade"
				onRequestClose={() => setOpen(false)}
				transparent
				visible={open}
			>
				<View style={styles.backdrop}>
					<Pressable
						accessibilityLabel="Закрыть выбор модели"
						onPress={() => setOpen(false)}
						style={StyleSheet.absoluteFill}
					/>
					<View
						accessibilityViewIsModal
						style={[styles.sheet, { backgroundColor: colors.surfaceRaised }]}
					>
						<View style={styles.sheetHeader}>
							<Text style={[styles.sheetTitle, { color: colors.foreground }]}>
								Модель
							</Text>
							<Text style={[styles.sheetHint, { color: colors.mutedForeground }]}>
								Выбор сохраняется на сервере
							</Text>
						</View>

						{status === "loading" || (open && !catalog) ? (
							<View accessibilityLabel="Загрузка моделей" style={styles.center}>
								<ActivityIndicator color={colors.foreground} />
							</View>
						) : status === "error" ? (
							<View style={styles.center}>
								<Text
									accessibilityRole="alert"
									style={[styles.errorText, { color: colors.destructive }]}
								>
									{message}
								</Text>
								<Pressable
									accessibilityRole="button"
									onPress={() => void load()}
									style={[styles.retry, { backgroundColor: colors.surface }]}
								>
									<Text style={[styles.retryText, { color: colors.foreground }]}>
										Повторить
									</Text>
								</Pressable>
							</View>
						) : (
							<View style={styles.options}>
								{options.map((model) => {
									const selected = model.id === currentId;
									const disabled = !model.available || saving;
									return (
										<Pressable
											key={model.id}
											accessibilityLabel={model.displayName}
											accessibilityRole="button"
											accessibilityState={{ disabled, selected }}
											disabled={disabled}
											onPress={() => void select(model)}
											style={({ pressed }) => [
												styles.option,
												{ borderTopColor: colors.border },
												selected && { backgroundColor: colors.muted },
												pressed && styles.pressed,
												disabled && styles.disabled,
											]}
										>
											<View style={styles.optionCopy}>
												<Text
													numberOfLines={1}
													style={[styles.optionTitle, { color: colors.foreground }]}
												>
													{model.displayName}
												</Text>
												{model.description ? (
													<Text
														numberOfLines={2}
														style={[
															styles.optionDescription,
															{ color: colors.mutedForeground },
														]}
													>
														{model.description}
													</Text>
												) : null}
											</View>
											{selected ? (
												<Icon name="check" size={18} color={colors.foreground} />
											) : null}
										</Pressable>
									);
								})}
								{saving ? (
									<ActivityIndicator
										color={colors.foreground}
										style={styles.saving}
									/>
								) : null}
								{message ? (
									<Text
										accessibilityRole="alert"
										style={[styles.errorText, { color: colors.destructive }]}
									>
										{message}
									</Text>
								) : null}
							</View>
						)}
					</View>
				</View>
			</Modal>
		</>
	);
}

const styles = StyleSheet.create({
	pill: {
		alignItems: "center",
		borderRadius: 999,
		borderWidth: StyleSheet.hairlineWidth,
		flexDirection: "row",
		gap: 6,
		maxWidth: 150,
		minHeight: 34,
		paddingHorizontal: 12,
	},
	pillText: { flexShrink: 1, fontSize: 13, fontWeight: "600" },
	pressed: { opacity: 0.6 },
	disabled: { opacity: 0.45 },
	backdrop: {
		alignItems: "center",
		backgroundColor: "rgba(0, 0, 0, 0.45)",
		flex: 1,
		justifyContent: "center",
		padding: 24,
	},
	sheet: {
		borderRadius: Radius.card,
		maxHeight: 520,
		maxWidth: 460,
		overflow: "hidden",
		width: "100%",
	},
	sheetHeader: {
		paddingHorizontal: 18,
		paddingVertical: 15,
	},
	sheetTitle: { fontSize: 19, fontWeight: "700", letterSpacing: -0.3 },
	sheetHint: { fontSize: 12, marginTop: 3 },
	center: {
		alignItems: "center",
		justifyContent: "center",
		minHeight: 160,
		padding: 20,
	},
	errorText: { fontSize: 13, lineHeight: 18, textAlign: "center" },
	retry: {
		borderRadius: 18,
		marginTop: 14,
		minHeight: 38,
		paddingHorizontal: 18,
		justifyContent: "center",
	},
	retryText: { fontSize: 14, fontWeight: "700" },
	options: { paddingBottom: 8 },
	option: {
		alignItems: "center",
		borderTopWidth: StyleSheet.hairlineWidth,
		flexDirection: "row",
		gap: 12,
		minHeight: 62,
		paddingHorizontal: 18,
		paddingVertical: 10,
	},
	optionCopy: { flex: 1 },
	optionTitle: { fontSize: 16, fontWeight: "600" },
	optionDescription: { fontSize: 12, lineHeight: 16, marginTop: 2 },
	saving: { marginVertical: 10 },
});
