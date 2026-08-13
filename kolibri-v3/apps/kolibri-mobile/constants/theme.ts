export type KolibriPalette = {
	background: string;
	settingsBackground: string;
	foreground: string;
	surface: string;
	surfaceRaised: string;
	muted: string;
	mutedForeground: string;
	border: string;
	composer: string;
	userBubble: string;
	send: string;
	primary: string;
	primaryForeground: string;
	destructive: string;
	destructiveSurface: string;
	success: string;
};

export const Colors: {
	light: KolibriPalette;
	dark: KolibriPalette;
} = {
	light: {
		background: "#ffffff",
		settingsBackground: "#ebebf0",
		foreground: "#0d0d0d",
		surface: "#f2f2f2",
		surfaceRaised: "#ffffff",
		muted: "#ececec",
		mutedForeground: "#6f6f6f",
		border: "#d9d9dc",
		composer: "#f2f2f2",
		userBubble: "#cbd4fb",
		send: "#3982f7",
		primary: "#0d0d0d",
		primaryForeground: "#ffffff",
		destructive: "#d92d20",
		destructiveSurface: "rgba(217,45,32,0.1)",
		success: "#18a566",
	},
	dark: {
		background: "#000000",
		settingsBackground: "#000000",
		foreground: "#f5f5f5",
		surface: "#212121",
		surfaceRaised: "#242424",
		muted: "#2f2f2f",
		mutedForeground: "#a5a5a5",
		border: "#3a3a3c",
		composer: "#171717",
		userBubble: "#2e3550",
		send: "#2f7fff",
		primary: "#f5f5f5",
		primaryForeground: "#111111",
		destructive: "#ff6961",
		destructiveSurface: "rgba(255,105,97,0.14)",
		success: "#34c759",
	},
};

export const Radius = {
	sm: 8,
	md: 12,
	card: 18,
	bubble: 20,
	composer: 27,
	circle: 999,
} as const;

export const Layout = {
	edgeInset: 16,
	headerControl: 48,
	drawerFraction: 0.74,
	threadMaxWidth: 768,
} as const;
