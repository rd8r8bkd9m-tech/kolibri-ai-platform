import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { useFonts } from "expo-font";
import { Drawer } from "expo-router/drawer";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import {
	DarkTheme,
	DefaultTheme,
	ThemeProvider as NavigationThemeProvider,
	type Theme,
} from "expo-router/react-navigation";
import { Platform, useWindowDimensions } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import "react-native-reanimated";

import { DrawerContent } from "@/components/thread-list/drawer-content";
import { Layout } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { KolibriThemeProvider } from "@/hooks/theme-provider";
import {
	MobileSessionProvider,
	useMobileSession,
} from "@/src/auth/mobile-session";
import { ProductRuntimeProvider } from "@/src/product-chat/runtime-provider";
import { releaseWebFocus } from "@/src/accessibility/release-web-focus";

const DESKTOP_BREAKPOINT_PX = 959;

function hasMobileClientMarker() {
	if (typeof window === "undefined") return false;

	const query = new URLSearchParams(window.location.search);
	if (query.get("client") === "mobile") {
		return true;
	}

	return /(?:^|;\s*)kolibri_ui_client=mobile(?:;|$)/.test(document.cookie);
}

function switchToDesktopClientIfWide() {
	if (typeof window === "undefined") {
		return;
	}
	const url = new URL(window.location.href);
	const query = url.searchParams;

	query.set("client", "desktop");
	window.location.replace(
		query.toString() ? `${url.pathname}?${query.toString()}` : url.pathname,
	);
}

function hasExplicitDesktopClientMarker() {
	if (typeof window === "undefined") return false;
	return new URLSearchParams(window.location.search).get("client") === "desktop";
}

function Navigation() {
	const { width } = useWindowDimensions();
	const session = useMobileSession();
	const { colors, isDark } = useTheme();
	const base = isDark ? DarkTheme : DefaultTheme;
	const theme: Theme = {
		...base,
		colors: {
			...base.colors,
			background: colors.background,
			card: colors.background,
			text: colors.foreground,
			border: colors.border,
			primary: colors.foreground,
		},
	};
	useEffect(() => {
		if (Platform.OS !== "web") return;
		if (hasExplicitDesktopClientMarker()) return;
		if (width <= DESKTOP_BREAKPOINT_PX) return;
		if (!hasMobileClientMarker()) return;
		switchToDesktopClientIfWide();
	}, [width]);

	return (
		<NavigationThemeProvider value={theme}>
			<Drawer
				drawerContent={(props) => <DrawerContent {...props} />}
				screenListeners={{
					blur: releaseWebFocus,
				}}
				screenOptions={{
					drawerStyle: {
						backgroundColor: colors.background,
						borderBottomRightRadius: 28,
						borderTopRightRadius: 28,
						overflow: "hidden",
						width: Math.min(width * Layout.drawerFraction, 340),
					},
					drawerType: "front",
					headerShown: false,
					overlayColor: "transparent",
					swipeEdgeWidth: 34,
					swipeEnabled: session.status === "authenticated",
				}}
			>
				<Drawer.Screen name="index" options={{ title: "Chat" }} />
				<Drawer.Screen
					name="app"
					options={{
						drawerItemStyle: { display: "none" },
						title: "Chat",
					}}
				/>
				<Drawer.Screen
					name="account"
					options={{
						drawerItemStyle: { display: "none" },
						title: "Личный кабинет",
					}}
				/>
				<Drawer.Screen
					name="estimates"
					options={{
						drawerItemStyle: { display: "none" },
						title: "Сметы",
					}}
				/>
			</Drawer>
			<StatusBar style={isDark ? "light" : "dark"} />
		</NavigationThemeProvider>
	);
}

export default function RootLayout() {
	const [fontsLoaded] = useFonts(
		Platform.OS === "ios" ? {} : MaterialIcons.font,
	);
	if (!fontsLoaded) return null;

	return (
		<GestureHandlerRootView style={{ flex: 1 }}>
			<KolibriThemeProvider>
				<MobileSessionProvider>
					<ProductRuntimeProvider>
						<Navigation />
					</ProductRuntimeProvider>
				</MobileSessionProvider>
			</KolibriThemeProvider>
		</GestureHandlerRootView>
	);
}
