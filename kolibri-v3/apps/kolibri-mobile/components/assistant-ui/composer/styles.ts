import { Platform, StyleSheet } from "react-native";

import {
	FontSize,
	FontWeight,
	Layout,
	LineHeight,
	Radius,
	Spacing,
	shadow,
} from "@/constants/theme";

export const styles = StyleSheet.create({
	outer: {
		alignSelf: "center",
		maxWidth: Layout.threadMaxWidth + 24,
		paddingHorizontal: Layout.composerInset,
		paddingTop: Spacing.sm,
		width: "100%",
	},
	attachments: { gap: Spacing.sm, paddingBottom: Spacing.sm },
	attachmentChip: {
		alignItems: "center",
		borderRadius: Radius.md,
		flexDirection: "row",
		gap: Spacing.xs,
		maxWidth: 220,
		paddingHorizontal: Spacing.sm,
		paddingVertical: Spacing.sm,
	},
	attachmentName: {
		flexShrink: 1,
		fontSize: FontSize.footnote,
		fontWeight: FontWeight.semibold,
	},
	attachmentRemove: {
		alignItems: "center",
		height: 22,
		justifyContent: "center",
		width: 22,
	},
	root: {
		alignItems: "center",
		backgroundColor: "transparent",
		borderRadius: Radius.composer,
		borderWidth: 1.5,
		flexDirection: "row",
		gap: Spacing.sm,
		height: 60,
		paddingHorizontal: Spacing.lg,
		position: "relative",
	},
	input: {
		flex: 1,
		fontSize: FontSize.sheet,
		lineHeight: LineHeight.list,
		maxHeight: 96,
		minHeight: 40,
		paddingHorizontal: Spacing.sm,
		paddingVertical: Spacing.md,
		textAlignVertical: "center",
		...Platform.select({
			web: { outlineStyle: "none" } as never,
			default: {},
		}),
	},
	focusedShadow: {
		...Platform.select({
			ios: {
				shadowColor: shadow.shadowColor,
				shadowOffset: shadow.shadowOffset,
				shadowOpacity: 0.18,
				shadowRadius: 22,
			},
			default: {},
		}),
	},
	roundAction: {
		alignItems: "center",
		height: 40,
		justifyContent: "center",
		width: 40,
	},
	outlineAction: { backgroundColor: "transparent" },
	voice: {
		alignItems: "center",
		borderRadius: Radius.control,
		height: 46,
		justifyContent: "center",
		width: 46,
	},
	send: {
		alignItems: "center",
		borderRadius: Radius.control,
		height: 46,
		justifyContent: "center",
		width: 46,
	},
	stopSquare: {
		borderRadius: Radius.dot,
		height: 14,
		width: 14,
	},
	pressed: { opacity: 0.72, transform: [{ scale: 0.92 }] },
	disabled: { opacity: 0.42 },
});
