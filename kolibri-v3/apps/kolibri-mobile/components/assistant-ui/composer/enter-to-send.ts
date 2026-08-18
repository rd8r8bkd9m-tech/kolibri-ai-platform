import { useCallback } from "react";
import { Platform } from "react-native";

import { useAui } from "@assistant-ui/react-native";

type KeyPressEvent = {
	nativeEvent: { key?: string; shiftKey?: boolean };
	preventDefault: () => void;
};

/**
 * Desktop chat sends on Enter (enterKeyHint="send"); keep the same behavior in
 * the PWA. Shift+Enter still inserts a newline. The native multiline input
 * keeps the send button as the primary action.
 */
export function useEnterToSend(aui: ReturnType<typeof useAui>) {
	return useCallback(
		(event: KeyPressEvent) => {
			if (Platform.OS !== "web") return;
			if (event.nativeEvent.key === "Enter" && !event.nativeEvent.shiftKey) {
				event.preventDefault();
				// The keydown can arrive before the last onChange propagated to
				// the composer store, which would make send() a no-op. Read the
				// value straight from the DOM target and sync it first.
				const target = (
					event as unknown as { target?: { value?: string } }
				).target;
				if (typeof target?.value === "string" && target.value.trim()) {
					aui.composer.setText(target.value);
				}
				aui.composer.send();
			}
		},
		[aui],
	);
}
