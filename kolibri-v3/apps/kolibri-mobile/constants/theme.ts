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
	overlay: string;
	// New tokens for design system
	accentPurple: string;
	grabber: string;
	divider: string;
	infoBg: string;
	successBg: string;
	draftBg: string;
	placeholder: string;
	disabled: string;
	surfaceMuted: string;
};

export const Colors: {
	light: KolibriPalette;
	dark: KolibriPalette;
} = {
	light: {
		background: "#fafaf7",
		settingsBackground: "#fafaf7",
		foreground: "#1a1817",
		surface: "#ffffff",
		surfaceRaised: "#f0f0eb",
		muted: "#e5e3dd",
		mutedForeground: "#5f5e5a",
		border: "#d9d6cf",
		composer: "#ffffff",
		userBubble: "#dcece9",
		send: "#0e7a6b",
		primary: "#1a1817",
		primaryForeground: "#fafaf7",
		destructive: "#D93025",
		destructiveSurface: "rgba(217,48,37,0.1)",
		success: "#16A34A",
		overlay: "rgba(0, 0, 0, 0.25)",
		accentPurple: "#6c5ce7",
		grabber: "#b8b5ae",
		divider: "#e8e5df",
		infoBg: "#e5f4f1",
		successBg: "#E8F5EE",
		draftBg: "#eeece7",
		placeholder: "#8a8780",
		disabled: "#b0ada7",
		surfaceMuted: "#d9d6cf",
	},
	dark: {
		background: "#1a1817",
		settingsBackground: "#1a1817",
		foreground: "#fafaf7",
		surface: "#2c2a28",
		surfaceRaised: "#37322d",
		muted: "#242220",
		mutedForeground: "#d2d1cc",
		border: "#3d3936",
		composer: "#242220",
		userBubble: "#2f4d4b",
		send: "#a0d7d1",
		primary: "#fafaf7",
		primaryForeground: "#1a1817",
		destructive: "#ff8b68",
		destructiveSurface: "rgba(255,139,104,0.14)",
		success: "#75e0a7",
		overlay: "rgba(0, 0, 0, 0.55)",
		accentPurple: "#a999ff",
		grabber: "#494642",
		divider: "#37322d",
		infoBg: "#1e3532",
		successBg: "#1d3829",
		draftBg: "#2c2a28",
		placeholder: "#91918d",
		disabled: "#5f5e5a",
		surfaceMuted: "#37322d",
	},
};

export const Radius = {
	xxs: 2,
	tiny: 3,
	xs: 6,
	sm: 8,
	md: 12,
	card: 18,
	bubble: 20,
	composer: 27,
	circle: 999,
	// New tokens
	full: 9999,
	sheet: 40,
	input: 16,
	positionCard: 20,
	controlSmall: 17,
	control: 22,
	dot: 3.5,
	thumb: 10,
	icon: 8,
	badge: 32,
} as const;

export const Layout = {
	edgeInset: 16,
	headerControl: 40,
	composerInset: 18,
	drawerFraction: 0.74,
	threadMaxWidth: 768,
} as const;

export const Spacing = {
	none: 0,
	xs: 4,
	sm: 8,
	md: 12,
	lg: 16,
	xl: 20,
	xxl: 24,
	xxxl: 32,
} as const;

export const FontSize = {
	caption2: 11,
	caption: 12,
	footnote: 13,
	small: 14,
	medium: 15,
	body: 16,
	text: 17,
	title: 18,
	sheet: 19,
	h3: 20,
	h2: 21,
	h1: 22,
	avatar: 23,
	amountXL: 28,
	screen: 30,
} as const;

export const FontWeight = {
	regular: "400",
	medium: "500",
	semibold: "600",
	bold: "700",
} as const;

export const LineHeight = {
	caption2: 14,
	caption: 16,
	footnote: 17,
	compact: 18,
	small: 19,
	normal: 20,
	base: 21,
	body: 22,
	relaxed: 23,
	list: 24,
	text: 25,
	screen: 26,
} as const;

export const LetterSpacing = {
	tighter: -1,
	tight: -0.45,
	small: -0.4,
	medium: -0.35,
	base: -0.3,
	relaxed: -0.2,
	none: 0,
} as const;

export const shadow = {
	shadowColor: "#000",
	shadowOffset: { width: 0, height: 8 },
	shadowRadius: 24,
	shadowOpacity: 0.08,
	elevation: 6,
} as const;

export const WebShadow = {
	floating: "0 2px 8px rgba(0, 0, 0, 0.18)",
} as const;

export const Glass = {
	light: {
		fill: "rgba(255, 255, 255, 0.58)",
		filter: "blur(28px) saturate(180%)",
		sheen:
			"linear-gradient(180deg, rgba(255,255,255,0.60), rgba(255,255,255,0) 38%)",
		shadow:
			"inset 0 1px 0 rgba(255,255,255,0.75), inset 0 0 0 0.5px rgba(255,255,255,0.32), 0 2px 10px rgba(0,0,0,0.06), 0 12px 36px -10px rgba(0,0,0,0.16)",
		focusedShadow:
			"inset 0 1px 0 rgba(255,255,255,0.75), inset 0 0 0 0.5px rgba(255,255,255,0.32), 0 16px 40px -24px rgba(0,0,0,0.50), 0 3px 10px -4px rgba(0,0,0,0.14)",
	},
	dark: {
		fill: "rgba(40, 40, 44, 0.62)",
		filter: "blur(28px) saturate(180%)",
		sheen:
			"linear-gradient(180deg, rgba(255,255,255,0.12), rgba(255,255,255,0) 38%)",
		shadow:
			"inset 0 1px 0 rgba(255,255,255,0.18), inset 0 0 0 0.5px rgba(255,255,255,0.10), 0 2px 10px rgba(0,0,0,0.35), 0 12px 36px -10px rgba(0,0,0,0.55)",
		focusedShadow:
			"inset 0 1px 0 rgba(255,255,255,0.18), inset 0 0 0 0.5px rgba(255,255,255,0.10), 0 16px 40px -24px rgba(0,0,0,0.60), 0 3px 10px -4px rgba(0,0,0,0.20)",
	},
} as const;

export const typography = {
	hScreen: { fontSize: FontSize.screen, fontWeight: FontWeight.bold },
	hSheet: { fontSize: FontSize.h1, fontWeight: FontWeight.bold },
	hSection: { fontSize: FontSize.h1, fontWeight: FontWeight.bold },
	listItem: { fontSize: FontSize.h3, fontWeight: FontWeight.semibold },
	suggest: { fontSize: FontSize.h2, fontWeight: FontWeight.semibold },
	pillLabel: { fontSize: FontSize.sheet, fontWeight: FontWeight.bold },
	body: { fontSize: FontSize.text, fontWeight: FontWeight.regular },
	meta: { fontSize: FontSize.small, fontWeight: FontWeight.regular },
	label: { fontSize: FontSize.footnote, fontWeight: FontWeight.semibold },
	amountXL: { fontSize: FontSize.amountXL, fontWeight: FontWeight.bold },
	amountL: { fontSize: FontSize.h3, fontWeight: FontWeight.bold },
	amountM: { fontSize: FontSize.text, fontWeight: FontWeight.bold },
	settingsLabel: {
		fontSize: FontSize.footnote,
		fontWeight: FontWeight.semibold,
	},
	settingsRow: { fontSize: FontSize.body, fontWeight: FontWeight.medium },
	settingsValue: { fontSize: FontSize.small, fontWeight: FontWeight.regular },
	projectName: { fontSize: FontSize.body, fontWeight: FontWeight.bold },
	projectMeta: { fontSize: FontSize.footnote, fontWeight: FontWeight.regular },
	identityName: { fontSize: FontSize.h3, fontWeight: FontWeight.bold },
	identityEmail: { fontSize: FontSize.small, fontWeight: FontWeight.regular },
} as const;
