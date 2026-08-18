import { Radius, shadow, typography } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";

export function useDesignTokens() {
	const { colors } = useTheme();
	return {
		colors: {
			bg: colors.background,
			surface: colors.surfaceRaised,
			surfaceMuted: colors.surfaceMuted,
			card: colors.surface,
			textPrimary: colors.foreground,
			textSecondary: colors.mutedForeground,
			textTertiary: colors.mutedForeground,
			placeholder: colors.placeholder,
			accent: colors.send,
			accentPurple: colors.accentPurple,
			danger: colors.destructive,
			borderDark: colors.foreground,
			borderLight: colors.border,
			overlay: colors.overlay,
			disabled: colors.disabled,
			success: colors.success,
			successBg: colors.successBg,
			infoBg: colors.infoBg,
			draftBg: colors.draftBg,
			grabber: colors.grabber,
			divider: colors.divider,
		},
		radii: Radius,
		shadow,
		typography,
	};
}
