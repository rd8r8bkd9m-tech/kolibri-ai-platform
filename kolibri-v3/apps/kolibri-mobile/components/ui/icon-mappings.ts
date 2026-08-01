import type { ComponentProps } from "react";
import type MaterialIcons from "@expo/vector-icons/MaterialIcons";
import type { SymbolViewProps, SymbolWeight } from "expo-symbols";

export type IconName =
	| "compose"
	| "bubble"
	| "plus"
	| "send"
	| "stop"
	| "copy"
	| "check"
	| "reload"
	| "chevron-left"
	| "chevron-right"
	| "folder"
	| "library"
	| "settings"
	| "search"
	| "archive"
	| "pin"
	| "document"
	| "person"
	| "appearance"
	| "agent"
	| "model"
	| "shield"
	| "info"
	| "chevron-down"
	| "chevron-up"
	| "save"
	| "close"
	| "logout";

export type IconProps = {
	name: IconName;
	size?: number;
	color: string;
	weight?: SymbolWeight;
};

export const SF_SYMBOLS: Record<IconName, SymbolViewProps["name"]> = {
	compose: "square.and.pencil",
	bubble: "bubble.left",
	plus: "plus",
	send: "arrow.up",
	stop: "stop.fill",
	copy: "doc.on.doc",
	check: "checkmark",
	reload: "arrow.clockwise",
	"chevron-left": "chevron.left",
	"chevron-right": "chevron.right",
	folder: "folder",
	library: "books.vertical",
	settings: "gearshape",
	search: "magnifyingglass",
	archive: "archivebox",
	pin: "pin",
	document: "doc.text",
	person: "person.crop.circle",
	appearance: "circle.lefthalf.filled",
	agent: "sparkles",
	model: "slider.horizontal.3",
	shield: "checkmark.shield",
	info: "info.circle",
	"chevron-down": "chevron.down",
	"chevron-up": "chevron.up",
	save: "checkmark.circle",
	close: "xmark",
	logout: "rectangle.portrait.and.arrow.right",
};

export const MATERIAL_ICONS: Record<
	IconName,
	ComponentProps<typeof MaterialIcons>["name"]
> = {
	compose: "edit",
	bubble: "chat-bubble-outline",
	plus: "add",
	send: "arrow-upward",
	stop: "stop",
	copy: "content-copy",
	check: "check",
	reload: "refresh",
	"chevron-left": "chevron-left",
	"chevron-right": "chevron-right",
	folder: "folder",
	library: "local-library",
	settings: "settings",
	search: "search",
	archive: "archive",
	pin: "push-pin",
	document: "description",
	person: "account-circle",
	appearance: "brightness-6",
	agent: "auto-awesome",
	model: "tune",
	shield: "verified-user",
	info: "info-outline",
	"chevron-down": "keyboard-arrow-down",
	"chevron-up": "keyboard-arrow-up",
	save: "check-circle",
	close: "close",
	logout: "logout",
};
