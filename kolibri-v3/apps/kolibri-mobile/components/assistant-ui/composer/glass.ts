import { useEffect, useState } from "react";
import { AccessibilityInfo, Platform } from "react-native";

import { Glass, type KolibriPalette } from "@/constants/theme";

import { styles } from "./styles";

/**
 * Reduce Transparency signal. React Native Web does not implement
 * AccessibilityInfo.isReduceTransparencyEnabled and throws on call; web reads
 * the `prefers-reduced-transparency` media query instead, native uses the
 * AccessibilityInfo API.
 */
export function useReduceTransparency(): boolean {
	const [reduceTransparency, setReduceTransparency] = useState(false);
	useEffect(() => {
		if (Platform.OS === "web") {
			const query =
				typeof window !== "undefined"
					? window.matchMedia?.("(prefers-reduced-transparency: reduce)")
					: null;
			const apply = () => setReduceTransparency(Boolean(query?.matches));
			apply();
			query?.addEventListener?.("change", apply);
			return () => query?.removeEventListener?.("change", apply);
		}
		let active = true;
		void AccessibilityInfo.isReduceTransparencyEnabled().then((enabled) => {
			if (active) setReduceTransparency(enabled);
		});
		const subscription = AccessibilityInfo.addEventListener(
			"reduceTransparencyChanged",
			setReduceTransparency,
		);
		return () => {
			active = false;
			subscription.remove();
		};
	}, []);
	return reduceTransparency;
}

/**
 * Liquid Glass (.regular) material. Three layers, per Apple HIG:
 * illumination (translucent fill + blur + saturation), highlight (specular
 * top edge and sheen), shadow (adaptive depth shadow, deeper on focus).
 * Falls back to the solid surface color when the runtime has no
 * backdrop-filter or Reduce Transparency is enabled.
 */
export function useLiquidGlass(isDark: boolean, colors: KolibriPalette) {
	const reduceTransparency = useReduceTransparency();
	const glassTokens = isDark ? Glass.dark : Glass.light;
	const glassMaterial =
		Platform.OS === "web" && !reduceTransparency
			? ({
					backgroundColor: glassTokens.fill,
					backdropFilter: glassTokens.filter,
					WebkitBackdropFilter: glassTokens.filter,
					boxShadow: glassTokens.shadow,
				} as never)
			: { backgroundColor: colors.composer };
	const sheenStyle =
		Platform.OS === "web" && !reduceTransparency
			? {
					backgroundImage: glassTokens.sheen,
				} as never
			: null;
	// On web the focused shadow must keep the inset highlight or the glass
	// material disappears on focus; native uses the iOS shadow props.
	const focusedShadowStyle =
		Platform.OS === "web"
			? ({
					boxShadow: glassTokens.focusedShadow,
				} as never)
			: styles.focusedShadow;
	return { glassMaterial, sheenStyle, focusedShadowStyle };
}
