import { ActivityIndicator, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Thread } from "@/components/assistant-ui/thread";
import { AuthScreen } from "@/components/auth/auth-screen";
import { MobileHeader } from "@/components/shell/mobile-header";
import { useTheme } from "@/hooks/use-theme";
import { useMobileSession } from "@/src/auth/mobile-session";

export default function HomeScreen() {
  const { colors } = useTheme();
  const session = useMobileSession();

  if (session.status === "restoring") {
    return (
      <View
        accessibilityLabel="Восстановление сессии"
        style={[styles.loading, { backgroundColor: colors.background }]}
      >
        <ActivityIndicator color={colors.foreground} />
      </View>
    );
  }

  if (session.status === "signed-out") {
    return <AuthScreen />;
  }

  return (
    <SafeAreaView
      edges={["top", "bottom"]}
      style={[styles.safe, { backgroundColor: colors.background }]}
    >
      <MobileHeader />
      <Thread />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  loading: { alignItems: "center", flex: 1, justifyContent: "center" },
});
