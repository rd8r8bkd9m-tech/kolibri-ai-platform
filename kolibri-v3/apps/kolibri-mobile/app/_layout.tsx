import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { useFonts } from "expo-font";
import { Drawer } from "expo-router/drawer";
import { StatusBar } from "expo-status-bar";
import {
  DarkTheme,
  DefaultTheme,
  ThemeProvider,
  type Theme,
} from "expo-router/react-navigation";
import { Platform, useWindowDimensions } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import "react-native-reanimated";

import { DrawerContent } from "@/components/thread-list/drawer-content";
import { Layout } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { MobileSessionProvider, useMobileSession } from "@/src/auth/mobile-session";
import { ProductRuntimeProvider } from "@/src/product-chat/runtime-provider";

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

  return (
    <ThemeProvider value={theme}>
      <Drawer
        drawerContent={(props) => <DrawerContent {...props} />}
        screenOptions={{
          drawerStyle: {
            backgroundColor: colors.background,
            width: Math.min(width * Layout.drawerFraction, 340),
          },
          drawerType: "front",
          headerShown: false,
          overlayColor: "rgba(0,0,0,0.58)",
          swipeEdgeWidth: 34,
          swipeEnabled: session.status === "authenticated",
        }}
      >
        <Drawer.Screen name="index" options={{ title: "Chat" }} />
        <Drawer.Screen
          name="estimates"
          options={{
            drawerItemStyle: { display: "none" },
            title: "Сметы",
          }}
        />
      </Drawer>
      <StatusBar style="auto" />
    </ThemeProvider>
  );
}

export default function RootLayout() {
  const [fontsLoaded] = useFonts(
    Platform.OS === "ios" ? {} : MaterialIcons.font,
  );
  if (!fontsLoaded) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <MobileSessionProvider>
        <ProductRuntimeProvider>
          <Navigation />
        </ProductRuntimeProvider>
      </MobileSessionProvider>
    </GestureHandlerRootView>
  );
}
