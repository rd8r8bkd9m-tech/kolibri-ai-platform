import { ComposerPrimitive, useAuiState } from "@assistant-ui/react-native";
import { useEffect, useRef, useState } from "react";
import {
	BackHandler,
	Image,
	Keyboard,
	Platform,
	Pressable,
	ScrollView,
	StyleSheet,
	Text,
	View,
} from "react-native";
import Animated, {
	Easing,
	useAnimatedStyle,
	useReducedMotion,
	useSharedValue,
	withTiming,
} from "react-native-reanimated";

import { PetSprite } from "@/components/pet/pet-sprite";
import { usePetMotion } from "@/components/pet/use-pet-motion";
import { Icon } from "@/src/components/icons/Icon";
import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import {
	DEFAULT_NATIVE_PET,
	NATIVE_PETS,
	type NativePetDefinition,
} from "@/src/pets/registry";
import {
	getNativePet,
	persistNativePetId,
	readNativePetId,
} from "@/src/pets/selection";
import {
	PET_ACTIVITY_COPY_RU,
	type PetActivityState,
} from "@/src/pets/motion";

function PetStatus({ accent, state }: { accent: string; state: PetActivityState }) {
	const { colors } = useTheme();
	const color =
		state === "error"
			? colors.destructive
			: state === "success"
				? colors.success
				: state === "thinking" ||
					  state === "running" ||
					  state === "review"
					? accent
					: colors.mutedForeground;

	return (
		<View accessibilityLiveRegion="polite" style={styles.statusRow}>
			<View
				accessibilityElementsHidden
				style={[styles.statusDot, { backgroundColor: color }]}
			/>
			<Text style={[styles.statusText, { color: colors.mutedForeground }]}>
				{PET_ACTIVITY_COPY_RU[state]}
			</Text>
		</View>
	);
}

function PetPicker({
	selected,
	onSelect,
}: {
	selected: NativePetDefinition;
	onSelect: (pet: NativePetDefinition) => void;
}) {
	const { colors } = useTheme();
	return (
		<ScrollView
			accessibilityLabel="Выбор помощника"
			contentContainerStyle={styles.pickerContent}
			horizontal
			keyboardShouldPersistTaps="handled"
			showsHorizontalScrollIndicator={false}
			style={styles.picker}
		>
			{NATIVE_PETS.map((pet) => {
				const active = selected.id === pet.id;
				return (
					<Pressable
						accessibilityLabel={`${pet.name}, ${pet.role}`}
						accessibilityRole="button"
						accessibilityState={{ selected: active }}
						key={pet.id}
						onPress={() => {
							haptics.selection();
							onSelect(pet);
						}}
						style={({ pressed }) => [
							styles.petChoice,
							{
								backgroundColor: active ? colors.muted : colors.surface,
								borderColor: active ? pet.accent : "transparent",
							},
							pressed && styles.pressed,
						]}
					>
						<Image
							resizeMode="contain"
							source={pet.thumbnail}
							style={styles.petChoiceImage}
						/>
					</Pressable>
				);
			})}
		</ScrollView>
	);
}

function PetComposer({ accent }: { accent: string }) {
	const canSend = useAuiState((state) => state.composer.canSend);
	const running = useAuiState((state) => state.thread.isRunning);
	const { colors } = useTheme();

	return (
		<ComposerPrimitive.Root
			style={[
				styles.composer,
				{ backgroundColor: colors.composer, borderColor: colors.border },
			]}
		>
			<ComposerPrimitive.Input
				accessibilityLabel="Сообщение питомцу в текущий чат"
				autoFocus
				maxLength={65_536}
				multiline
				placeholder="Написать в этот чат…"
				placeholderTextColor={colors.mutedForeground}
				style={[styles.input, { color: colors.foreground }]}
				submitMode="none"
			/>
			{running ? (
				<ComposerPrimitive.Cancel
					accessibilityLabel="Остановить ответ"
					onPressIn={haptics.light}
					style={[styles.send, { backgroundColor: accent }]}
				>
					<Icon name="stop" color="#ffffff" size={14} />
				</ComposerPrimitive.Cancel>
			) : (
				<ComposerPrimitive.Send
					accessibilityLabel="Отправить в текущий чат"
					accessibilityState={{ disabled: !canSend }}
					onPressIn={() => {
						if (!canSend) return;
						haptics.light();
					}}
					style={[
						styles.send,
						{
							backgroundColor: canSend ? accent : colors.muted,
							opacity: canSend ? 1 : 0.72,
						},
					]}
				>
					<Icon
						name="send"
						color={canSend ? "#ffffff" : colors.mutedForeground}
						size={18}
						weight="semibold"
					/>
				</ComposerPrimitive.Send>
			)}
		</ComposerPrimitive.Root>
	);
}

export function PetMiniAssistant() {
	const [open, setOpen] = useState(false);
	const [pickerOpen, setPickerOpen] = useState(false);
	const [pet, setPet] = useState<NativePetDefinition>(DEFAULT_NATIVE_PET);
	const { activityState, onTap, state } = usePetMotion();
	const reduceMotion = useReducedMotion();
	const { colors } = useTheme();
	const reveal = useSharedValue(0);
	const longPressConsumedRef = useRef(false);
	const longPressResetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
		null,
	);

	useEffect(() => {
		let active = true;
		void readNativePetId().then((id) => {
			if (active) setPet(getNativePet(id));
		});
		return () => {
			active = false;
		};
	}, []);

	useEffect(() => {
		reveal.value = withTiming(open ? 1 : 0, {
			duration: reduceMotion ? 0 : 180,
			easing: Easing.out(Easing.cubic),
		});
	}, [open, reduceMotion, reveal]);

	useEffect(() => {
		if (!open || Platform.OS !== "android") return;
		const subscription = BackHandler.addEventListener(
			"hardwareBackPress",
			() => {
				Keyboard.dismiss();
				setPickerOpen(false);
				setOpen(false);
				return true;
			},
		);
		return () => subscription.remove();
	}, [open]);

	useEffect(
		() => () => {
			if (longPressResetTimerRef.current) {
				clearTimeout(longPressResetTimerRef.current);
			}
		},
		[],
	);

	const panelStyle = useAnimatedStyle(() => ({
		opacity: reveal.value,
		transform: [
			{ translateY: (1 - reveal.value) * 12 },
			{ scale: 0.98 + reveal.value * 0.02 },
		],
	}));
	return (
		<View
			style={[
				StyleSheet.absoluteFill,
				// react-native-web 0.21.x emits `pointer-events: box-none`,
				// which is invalid CSS and is dropped by the browser, so the
				// full-screen wrapper silently becomes `auto` and swallows
				// every wheel/touch event aimed at the message list below it.
				// On web we use `none`; interactive children (trigger, panel)
				// keep their default `auto` and remain clickable.
				Platform.OS === "web" ? { pointerEvents: "none" } : { pointerEvents: "box-none" },
			]}
		>
			<Pressable
				accessibilityHint="Нажмите для чата; удерживайте для быстрого выбора питомца"
				accessibilityLabel={`${pet.name}, мобильный помощник`}
				accessibilityRole="button"
				accessibilityState={{ expanded: open }}
				accessibilityValue={{ text: PET_ACTIVITY_COPY_RU[activityState] }}
				onPress={() => {
					if (longPressConsumedRef.current) {
						longPressConsumedRef.current = false;
						return;
					}
					haptics.selection();
					onTap();
					setPickerOpen(false);
					setOpen((current) => {
						if (current) Keyboard.dismiss();
						return !current;
					});
				}}
				onLongPress={() => {
					longPressConsumedRef.current = true;
					if (longPressResetTimerRef.current) {
						clearTimeout(longPressResetTimerRef.current);
					}
					longPressResetTimerRef.current = setTimeout(() => {
						longPressConsumedRef.current = false;
						longPressResetTimerRef.current = null;
					}, 800);
					haptics.medium();
					onTap();
					setPickerOpen(true);
					setOpen(true);
				}}
				delayLongPress={380}
				style={[
					styles.trigger,
					{
						backgroundColor: colors.surfaceRaised,
						borderColor: pet.accent,
					},
				]}
			>
				<PetSprite
					pet={pet}
					reducedMotion={reduceMotion}
					state={state}
					testID="mobile-pet-sprite"
					width={56}
				/>
				<View
					accessibilityElementsHidden
					style={[
						styles.triggerStatus,
						{
							backgroundColor:
								activityState === "error"
									? colors.destructive
									: activityState === "thinking" ||
										  activityState === "running" ||
										  activityState === "review"
										? pet.accent
										: activityState === "success"
											? colors.success
											: colors.mutedForeground,
						},
					]}
				/>
			</Pressable>

			<Animated.View
				accessibilityElementsHidden={!open}
				accessibilityViewIsModal={open}
				importantForAccessibility={open ? "yes" : "no-hide-descendants"}
				style={[
					styles.panel,
					{
						backgroundColor: colors.surfaceRaised,
						borderColor: colors.border,
						pointerEvents: open ? "auto" : "none",
					},
					panelStyle,
				]}
			>
				{open ? (
					<>
						<View style={styles.panelHeader}>
							<PetSprite
								pet={pet}
								reducedMotion={reduceMotion}
								state={state}
								width={50}
							/>
							<View style={styles.identity}>
								<Text
									style={[styles.petName, { color: colors.foreground }]}
								>
									{pet.name}
								</Text>
								<Text
									numberOfLines={1}
									style={[
										styles.petRole,
										{ color: colors.mutedForeground },
									]}
								>
									{pet.role} · {pet.personality}
								</Text>
							</View>
							<Pressable
								accessibilityLabel="Закрыть помощника"
								accessibilityRole="button"
								hitSlop={8}
								onPress={() => {
									Keyboard.dismiss();
									haptics.light();
									setPickerOpen(false);
									setOpen(false);
								}}
								style={({ pressed }) => [
									styles.close,
									{ backgroundColor: colors.muted },
									pressed && styles.pressed,
								]}
							>
								<Icon name="close" color={colors.foreground} size={18} />
							</Pressable>
						</View>
						<PetStatus accent={pet.accent} state={activityState} />
						{pickerOpen ? (
							<PetPicker
								selected={pet}
								onSelect={(nextPet) => {
									setPet(nextPet);
									void persistNativePetId(nextPet.id);
									onTap();
								}}
							/>
						) : null}
						<PetComposer accent={pet.accent} />
					</>
				) : null}
			</Animated.View>
		</View>
	);
}

const styles = StyleSheet.create({
	trigger: {
		alignItems: "center",
		borderRadius: 31,
		borderWidth: 1.5,
		bottom: 70,
		height: 62,
		justifyContent: "center",
		position: "absolute",
		right: 16,
		boxShadow: "0 5px 12px rgba(0, 0, 0, 0.2)",
		width: 62,
		zIndex: 20,
	},
	triggerStatus: {
		borderColor: "#ffffff",
		borderRadius: 6,
		borderWidth: 1.5,
		bottom: 3,
		height: 11,
		position: "absolute",
		right: 3,
		width: 11,
	},
	panel: {
		borderRadius: Radius.card,
		borderWidth: StyleSheet.hairlineWidth,
		bottom: 68,
		left: 14,
		maxWidth: 430,
		padding: 12,
		position: "absolute",
		right: 14,
		boxShadow: "0 10px 24px rgba(0, 0, 0, 0.28)",
		zIndex: 30,
	},
	panelHeader: {
		alignItems: "center",
		flexDirection: "row",
		minHeight: 54,
	},
	identity: { flex: 1, marginLeft: 8, minWidth: 0 },
	petName: { fontSize: 17, fontWeight: "700", letterSpacing: -0.2 },
	petRole: { fontSize: 12, lineHeight: 16, marginTop: 1 },
	close: {
		alignItems: "center",
		borderRadius: 18,
		height: 36,
		justifyContent: "center",
		marginLeft: 7,
		width: 36,
	},
	statusRow: {
		alignItems: "center",
		flexDirection: "row",
		minHeight: 22,
		paddingHorizontal: 3,
	},
	statusDot: { borderRadius: 4, height: 8, marginRight: 7, width: 8 },
	statusText: { fontSize: 12, fontWeight: "600" },
	picker: { marginHorizontal: -3, marginVertical: 4 },
	pickerContent: { gap: 6, paddingHorizontal: 3 },
	petChoice: {
		alignItems: "center",
		borderRadius: 20,
		borderWidth: 1.5,
		height: 40,
		justifyContent: "center",
		width: 40,
	},
	petChoiceImage: { height: 37, width: 37 },
	composer: {
		alignItems: "flex-end",
		borderRadius: 24,
		borderWidth: StyleSheet.hairlineWidth,
		flexDirection: "row",
		minHeight: 48,
		padding: 4,
	},
	input: {
		flex: 1,
		fontSize: 15,
		lineHeight: 20,
		maxHeight: 92,
		minHeight: 40,
		paddingBottom: 9,
		paddingHorizontal: 10,
		paddingTop: 9,
		...Platform.select({
			web: { outlineStyle: "none" } as never,
			default: {},
		}),
	},
	send: {
		alignItems: "center",
		borderRadius: 20,
		height: 40,
		justifyContent: "center",
		width: 40,
	},
	pressed: { opacity: 0.58 },
});
