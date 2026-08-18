import {
	ComposerPrimitive,
	useAui,
	useAuiState,
	useVoiceControls,
	useVoiceState,
} from "@assistant-ui/react-native";
import { Platform, Pressable, View } from "react-native";
import { useCallback, useRef, useState } from "react";

import { Icon } from "@/src/components/icons/Icon";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";

import { styles } from "./styles";

type WebSpeechRecognitionResultEvent = {
	resultIndex: number;
	results: ArrayLike<{
		isFinal: boolean;
		0: { transcript: string };
	}>;
};

type WebSpeechRecognitionHandle = {
	lang: string;
	interimResults: boolean;
	continuous: boolean;
	onresult: ((event: WebSpeechRecognitionResultEvent) => void) | null;
	onend: (() => void) | null;
	onerror: (() => void) | null;
	start(): void;
	stop(): void;
};

type WebSpeechWindow = Window & {
	SpeechRecognition?: new () => WebSpeechRecognitionHandle;
	webkitSpeechRecognition?: new () => WebSpeechRecognitionHandle;
};

export function SendButton() {
	const { colors } = useTheme();
	return (
		<ComposerPrimitive.Send
			accessibilityLabel="Отправить"
			onPressIn={haptics.success}
			style={({ pressed }) => [
				styles.send,
				{ backgroundColor: colors.send },
				pressed && styles.pressed,
			]}
		>
			<Icon name="send" size={22} color={colors.primaryForeground} weight="semibold" />
		</ComposerPrimitive.Send>
	);
}

export function StopButton() {
	const { colors } = useTheme();
	return (
		<ComposerPrimitive.Cancel
			accessibilityLabel="Остановить ответ"
			onPressIn={haptics.light}
			style={({ pressed }) => [
				styles.send,
				{ backgroundColor: colors.send },
				pressed && styles.pressed,
			]}
		>
			<View
				accessibilityElementsHidden
				style={[styles.stopSquare, { backgroundColor: colors.primaryForeground }]}
			/>
		</ComposerPrimitive.Cancel>
	);
}

export function MicButton() {
	const { colors } = useTheme();
	const aui = useAui();
	const recognitionRef = useRef<WebSpeechRecognitionHandle | null>(null);
	const dictationCapable = useAuiState(
		(state) => state.thread.capabilities.dictation,
	);
	const runtimeDictating = useAuiState(
		(state) => state.composer.dictation != null,
	);
	const [localDictating, setLocalDictating] = useState(false);
	const webSpeechSupported =
		Platform.OS === "web" &&
		typeof window !== "undefined" &&
		Boolean(
			(window as WebSpeechWindow).SpeechRecognition ??
				(window as WebSpeechWindow).webkitSpeechRecognition,
		);
	const enabled = dictationCapable || webSpeechSupported;
	const dictating = runtimeDictating || localDictating;

	const startLocal = useCallback(() => {
		const Ctor =
			(window as WebSpeechWindow).SpeechRecognition ??
			(window as WebSpeechWindow).webkitSpeechRecognition;
		if (!Ctor) return;
		const recognition = new Ctor() as unknown as WebSpeechRecognitionHandle;
		recognition.lang = "ru-RU";
		recognition.interimResults = true;
		recognition.continuous = true;
		recognition.onresult = (event) => {
			let finalText = "";
			let interimText = "";
			for (let index = event.resultIndex; index < event.results.length; index += 1) {
				const result = event.results[index];
				if (result.isFinal) {
					finalText += `${result[0].transcript} `;
				} else {
					interimText += result[0].transcript;
				}
			}
			aui.composer.setText(`${finalText}${interimText}`.trim());
		};
		recognition.onend = () => setLocalDictating(false);
		recognition.onerror = () => setLocalDictating(false);
		recognitionRef.current = recognition;
		recognition.start();
		setLocalDictating(true);
	}, [aui]);

	const stopLocal = useCallback(() => {
		recognitionRef.current?.stop();
		recognitionRef.current = null;
		setLocalDictating(false);
	}, []);

	return (
		<Pressable
			accessibilityHint={
				enabled
					? "Голосовой ввод текста"
					: "Диктовка недоступна в этом браузере"
			}
			accessibilityLabel={dictating ? "Остановить диктовку" : "Диктовка"}
			accessibilityRole="button"
			accessibilityState={{ disabled: !enabled, selected: dictating }}
			disabled={!enabled}
			hitSlop={6}
			onPress={() => {
				haptics.selection();
				if (dictating) {
					if (runtimeDictating) aui.composer.stopDictation();
					else stopLocal();
					return;
				}
				if (dictationCapable) aui.composer.startDictation();
				else startLocal();
			}}
			style={({ pressed }) => [
				styles.roundAction,
				styles.outlineAction,
				!enabled && styles.disabled,
				pressed && styles.pressed,
			]}
		>
			<Icon
				name="mic"
				size={26}
				color={dictating ? colors.primaryForeground : colors.foreground}
			/>
		</Pressable>
	);
}

export function VoiceButton() {
	const { colors } = useTheme();
	const voiceControls = useVoiceControls();
	const voiceState = useVoiceState();
	const voiceCapable = useAuiState(
		(state) => state.thread.capabilities.voice,
	);
	const connected = voiceState?.status.type === "running";
	const enabled = voiceCapable;
	return (
		<Pressable
			accessibilityHint={
				enabled ? "Живой голосовой режим" : "Голосовой режим не включён сервером"
			}
			accessibilityLabel={connected ? "Завершить голосовой режим" : "Голосовой режим"}
			accessibilityRole="button"
			accessibilityState={{ disabled: !enabled, selected: connected }}
			disabled={!enabled}
			onPress={() => {
				haptics.light();
				if (connected) voiceControls.disconnect();
				else voiceControls.connect();
			}}
			style={({ pressed }) => [
				styles.voice,
				{ backgroundColor: colors.send },
				!enabled && styles.disabled,
				pressed && styles.pressed,
			]}
		>
			<Icon
				name="audioWaveform"
				size={22}
				color={colors.primaryForeground}
				weight="semibold"
			/>
		</Pressable>
	);
}
