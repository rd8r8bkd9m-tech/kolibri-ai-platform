import * as SecureStore from "expo-secure-store";
import {
	createContext,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useState,
	type PropsWithChildren,
} from "react";
import { Platform } from "react-native";

import { Colors, type KolibriPalette } from "@/constants/theme";
import { useColorScheme } from "@/hooks/use-color-scheme";

const THEME_PREFERENCE_KEY = "kolibri.mobile.theme.v1";
export type ThemePreference = "system" | "light" | "dark";

type KolibriThemeValue = {
	colors: KolibriPalette;
	isDark: boolean;
	preference: ThemePreference;
	setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<KolibriThemeValue | null>(null);

const isThemePreference = (value: unknown): value is ThemePreference =>
	value === "system" || value === "light" || value === "dark";

const readStoredPreference = async (): Promise<ThemePreference> => {
	try {
		const value =
			Platform.OS === "web"
				? globalThis.localStorage?.getItem(THEME_PREFERENCE_KEY)
				: await SecureStore.getItemAsync(THEME_PREFERENCE_KEY);
		return isThemePreference(value) ? value : "system";
	} catch {
		return "system";
	}
};

const readStoredPreferenceSync = (): ThemePreference => {
	if (Platform.OS !== "web") return "system";
	try {
		const value = globalThis.localStorage?.getItem(THEME_PREFERENCE_KEY);
		return isThemePreference(value) ? value : "system";
	} catch {
		return "system";
	}
};

const persistPreference = async (preference: ThemePreference) => {
	try {
		if (Platform.OS === "web") {
			globalThis.localStorage?.setItem(THEME_PREFERENCE_KEY, preference);
			return;
		}
		await SecureStore.setItemAsync(THEME_PREFERENCE_KEY, preference, {
			keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
		});
	} catch {
		// Theme remains active in memory when persistence is unavailable.
	}
};

export function KolibriThemeProvider({ children }: PropsWithChildren) {
	const systemScheme = useColorScheme();
	const [preference, setPreferenceState] = useState<ThemePreference>(() =>
		readStoredPreferenceSync(),
	);

	useEffect(() => {
		let active = true;
		void readStoredPreference().then((stored) => {
			if (active) setPreferenceState(stored);
		});
		return () => {
			active = false;
		};
	}, []);

	const setPreference = useCallback((next: ThemePreference) => {
		setPreferenceState(next);
		void persistPreference(next);
	}, []);
	const resolved =
		preference === "system"
			? systemScheme === "dark"
				? "dark"
				: "light"
			: preference;
	const value = useMemo<KolibriThemeValue>(
		() => ({
			colors: Colors[resolved],
			isDark: resolved === "dark",
			preference,
			setPreference,
		}),
		[preference, resolved, setPreference],
	);

	return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useKolibriTheme() {
	const value = useContext(ThemeContext);
	if (!value) throw new Error("useTheme must be used inside KolibriThemeProvider");
	return value;
}
