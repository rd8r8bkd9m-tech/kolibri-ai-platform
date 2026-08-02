import { Platform } from "react-native";

export function releaseWebFocus() {
	if (Platform.OS !== "web") return;
	const activeElement = globalThis.document?.activeElement;
	if (activeElement instanceof globalThis.HTMLElement) {
		activeElement.blur();
	}
}
