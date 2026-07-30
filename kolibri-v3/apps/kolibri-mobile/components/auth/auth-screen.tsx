import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { useMobileSession } from "@/src/auth/mobile-session";

export function AuthScreen() {
  const { colors } = useTheme();
  const session = useMobileSession();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const canSubmit =
    email.trim().length > 0 &&
    password.length >= 8 &&
    (mode === "login" || name.trim().length > 0);

  const submit = async () => {
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    try {
      if (mode === "login") {
        await session.login({ email: email.trim(), password });
      } else {
        await session.register({
          email: email.trim(),
          name: name.trim(),
          password,
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView
      edges={["top", "bottom"]}
      style={[styles.safe, { backgroundColor: colors.background }]}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.keyboard}
      >
        <View style={styles.content}>
          <View style={styles.brand}>
            <View
              style={[styles.mark, { backgroundColor: colors.foreground }]}
            >
              <Text
                style={[styles.markText, { color: colors.primaryForeground }]}
              >
                K
              </Text>
            </View>
            <Text style={[styles.title, { color: colors.foreground }]}>
              Kolibri AI
            </Text>
            <Text style={[styles.subtitle, { color: colors.mutedForeground }]}>
              Проекты, документы и агентная работа
            </Text>
          </View>

          <View style={styles.form}>
            {mode === "register" ? (
              <TextInput
                accessibilityLabel="Имя"
                autoCapitalize="words"
                autoComplete="name"
                onChangeText={setName}
                placeholder="Имя"
                placeholderTextColor={colors.mutedForeground}
                style={[
                  styles.input,
                  {
                    backgroundColor: colors.surface,
                    borderColor: colors.border,
                    color: colors.foreground,
                  },
                ]}
                value={name}
              />
            ) : null}
            <TextInput
              accessibilityLabel="Электронная почта"
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              onChangeText={setEmail}
              placeholder="Электронная почта"
              placeholderTextColor={colors.mutedForeground}
              style={[
                styles.input,
                {
                  backgroundColor: colors.surface,
                  borderColor: colors.border,
                  color: colors.foreground,
                },
              ]}
              value={email}
            />
            <TextInput
              accessibilityLabel="Пароль"
              autoCapitalize="none"
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              onChangeText={setPassword}
              onSubmitEditing={submit}
              placeholder="Пароль"
              placeholderTextColor={colors.mutedForeground}
              secureTextEntry
              style={[
                styles.input,
                {
                  backgroundColor: colors.surface,
                  borderColor: colors.border,
                  color: colors.foreground,
                },
              ]}
              value={password}
            />

            {session.error ? (
              <Text
                accessibilityLiveRegion="polite"
                style={[styles.error, { color: colors.destructive }]}
              >
                {session.error}
              </Text>
            ) : null}

            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: !canSubmit || submitting }}
              disabled={!canSubmit || submitting}
              onPress={submit}
              style={({ pressed }) => [
                styles.primary,
                { backgroundColor: colors.foreground },
                (!canSubmit || submitting) && styles.disabled,
                pressed && styles.pressed,
              ]}
            >
              {submitting ? (
                <ActivityIndicator color={colors.primaryForeground} />
              ) : (
                <Text
                  style={[
                    styles.primaryText,
                    { color: colors.primaryForeground },
                  ]}
                >
                  {mode === "login" ? "Войти" : "Создать аккаунт"}
                </Text>
              )}
            </Pressable>

            <Pressable
              accessibilityRole="button"
              onPress={() =>
                setMode((current) =>
                  current === "login" ? "register" : "login",
                )
              }
              style={({ pressed }) => [
                styles.secondary,
                pressed && styles.pressed,
              ]}
            >
              <Text
                style={[styles.secondaryText, { color: colors.foreground }]}
              >
                {mode === "login"
                  ? "Создать аккаунт"
                  : "У меня уже есть аккаунт"}
              </Text>
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  keyboard: { flex: 1 },
  content: {
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 24,
    paddingBottom: 24,
  },
  brand: { alignItems: "center", marginBottom: 42 },
  mark: {
    alignItems: "center",
    borderRadius: 22,
    height: 64,
    justifyContent: "center",
    marginBottom: 18,
    width: 64,
  },
  markText: { fontSize: 28, fontWeight: "800" },
  title: { fontSize: 32, fontWeight: "700", letterSpacing: -1 },
  subtitle: { fontSize: 15, marginTop: 6, textAlign: "center" },
  form: { gap: 12 },
  input: {
    borderRadius: Radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    fontSize: 16,
    minHeight: 54,
    paddingHorizontal: 16,
  },
  error: { fontSize: 14, lineHeight: 19, paddingHorizontal: 4 },
  primary: {
    alignItems: "center",
    borderRadius: Radius.circle,
    height: 54,
    justifyContent: "center",
    marginTop: 4,
  },
  primaryText: { fontSize: 17, fontWeight: "700" },
  secondary: { alignItems: "center", padding: 12 },
  secondaryText: { fontSize: 15, fontWeight: "600" },
  disabled: { opacity: 0.36 },
  pressed: { opacity: 0.68 },
});
