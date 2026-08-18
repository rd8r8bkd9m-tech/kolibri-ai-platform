import {
	AuiIf,
	ComposerPrimitive,
	useAui,
} from "@assistant-ui/react-native";
import { ScrollView, View } from "react-native";

import { useTheme } from "@/hooks/use-theme";
import { AttachmentButton, ComposerAttachments } from "./attachments";
import {
	MicButton,
	SendButton,
	StopButton,
	VoiceButton,
} from "./controls";
import { useEnterToSend } from "./enter-to-send";
import { styles } from "./styles";

if (typeof globalThis !== "undefined") {
	(globalThis as { __KOLIBRI_MOBILE_ENTER_SEND__?: boolean })
		.__KOLIBRI_MOBILE_ENTER_SEND__ = true;
}

export function Composer() {
	const aui = useAui();
	const { colors } = useTheme();
	const handleKeyPress = useEnterToSend(aui);

	return (
		<View style={styles.outer}>
			<ScrollView
				horizontal
				contentContainerStyle={styles.attachments}
				showsHorizontalScrollIndicator={false}
			>
				<ComposerAttachments />
			</ScrollView>
			<ComposerPrimitive.Root style={styles.root}>
				<AttachmentButton />
				<ComposerPrimitive.Input
					accessibilityLabel="Сообщение"
					maxLength={65_536}
					multiline
					onKeyPress={handleKeyPress}
					placeholder="Спросить КолИ…"
					placeholderTextColor={colors.placeholder}
					style={styles.input}
				/>
				<MicButton />
				<AuiIf condition={(state) => !state.thread.isRunning}>
					<AuiIf condition={(state) => !state.composer.isEmpty}>
						<SendButton />
					</AuiIf>
				</AuiIf>
				<AuiIf condition={(state) => state.thread.isRunning}>
					<StopButton />
				</AuiIf>
				<AuiIf
					condition={(state) =>
						!state.thread.isRunning && state.composer.isEmpty
					}
				>
					<VoiceButton />
				</AuiIf>
			</ComposerPrimitive.Root>
		</View>
	);
}
