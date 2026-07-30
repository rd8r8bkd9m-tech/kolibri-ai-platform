import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useNavigation } from "expo-router";
import type { DrawerNavigationProp } from "expo-router/build/react-navigation/drawer/types";

import { AuthScreen } from "@/components/auth/auth-screen";
import { CircleButton } from "@/components/shell/circle-button";
import { HamburgerMark } from "@/components/shell/hamburger-mark";
import { Icon } from "@/components/ui/icon";
import { Layout, Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { useMobileSession } from "@/src/auth/mobile-session";

const AGENT_PROFILES = [
  { id: "auto", label: "Автоматически", hint: "Kolibri выбирает подходящий runtime" },
  { id: "mimo-code", label: "MiMo Code", hint: "Быстрые рабочие и кодовые задачи" },
  { id: "codex-cli", label: "Codex", hint: "Полноценная агентная разработка" },
] as const;

export default function SettingsScreen() {
  const navigation =
    useNavigation<
      DrawerNavigationProp<{ settings: undefined }, "settings">
    >();
  const session = useMobileSession();
  const { colors } = useTheme();
  const [name, setName] = useState(session.user?.name ?? "");
  const [saving, setSaving] = useState(false);

  if (session.status === "restoring") {
    return (
      <View style={[styles.center, { backgroundColor: colors.background }]}>
        <ActivityIndicator color={colors.foreground} />
      </View>
    );
  }
  if (session.status === "signed-out") return <AuthScreen />;

  const saveName = async () => {
    const normalized = name.trim();
    if (!normalized || normalized === session.user?.name || saving) return;
    setSaving(true);
    try {
      await session.updateProfile({ name: normalized });
      haptics.success();
    } catch {
      haptics.error();
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView
      edges={["top", "bottom"]}
      style={[styles.safe, { backgroundColor: colors.background }]}
    >
      <View style={styles.header}>
        <CircleButton
          accessibilityLabel="Открыть меню"
          accessibilityRole="button"
          onPress={() => {
            haptics.selection();
            navigation.openDrawer();
          }}
        >
          <HamburgerMark />
        </CircleButton>
        <Text style={[styles.headerTitle, { color: colors.foreground }]}>
          Личный кабинет
        </Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.identity}>
          <View style={[styles.avatar, { backgroundColor: colors.foreground }]}>
            <Text style={[styles.avatarText, { color: colors.primaryForeground }]}>
              {session.user?.name.trim().slice(0, 1).toUpperCase() ?? "K"}
            </Text>
          </View>
          <Text style={[styles.identityName, { color: colors.foreground }]}>
            {session.user?.name}
          </Text>
          <Text style={[styles.identityEmail, { color: colors.mutedForeground }]}>
            {session.user?.email}
          </Text>
          {session.user?.isPlatformOwner ? (
            <View style={[styles.ownerBadge, { backgroundColor: colors.muted }]}>
              <Text style={[styles.ownerBadgeText, { color: colors.foreground }]}>
                Владелец платформы
              </Text>
            </View>
          ) : null}
        </View>

        <Text style={[styles.sectionTitle, { color: colors.mutedForeground }]}>
          Профиль
        </Text>
        <View style={[styles.card, { backgroundColor: colors.surface }]}>
          <Text style={[styles.label, { color: colors.mutedForeground }]}>Имя</Text>
          <View style={styles.nameRow}>
            <TextInput
              accessibilityLabel="Имя профиля"
              autoCapitalize="words"
              onChangeText={setName}
              onSubmitEditing={saveName}
              style={[
                styles.nameInput,
                {
                  borderColor: colors.border,
                  color: colors.foreground,
                  backgroundColor: colors.background,
                },
              ]}
              value={name}
            />
            <Pressable
              accessibilityLabel="Сохранить имя"
              accessibilityRole="button"
              disabled={
                saving ||
                !name.trim() ||
                name.trim() === session.user?.name
              }
              onPress={saveName}
              style={({ pressed }) => [
                styles.saveButton,
                { backgroundColor: colors.foreground },
                (saving ||
                  !name.trim() ||
                  name.trim() === session.user?.name) &&
                  styles.disabled,
                pressed && styles.pressed,
              ]}
            >
              {saving ? (
                <ActivityIndicator color={colors.primaryForeground} />
              ) : (
                <Icon name="check" size={20} color={colors.primaryForeground} />
              )}
            </Pressable>
          </View>
        </View>

        <Text style={[styles.sectionTitle, { color: colors.mutedForeground }]}>
          Агент
        </Text>
        <View style={[styles.card, { backgroundColor: colors.surface }]}>
          {AGENT_PROFILES.map((profile, index) => {
            const selected =
              session.user?.preferredAgentProfile === profile.id;
            return (
              <Pressable
                accessibilityLabel={`Профиль агента: ${profile.label}`}
                accessibilityRole="radio"
                accessibilityState={{ checked: selected }}
                key={profile.id}
                onPress={() => {
                  if (selected) return;
                  haptics.selection();
                  void session.updateAgentProfile(profile.id).catch(() => {
                    haptics.error();
                  });
                }}
                style={({ pressed }) => [
                  styles.profileRow,
                  index > 0 && {
                    borderTopColor: colors.border,
                    borderTopWidth: StyleSheet.hairlineWidth,
                  },
                  pressed && styles.pressed,
                ]}
              >
                <View style={styles.profileCopy}>
                  <Text style={[styles.profileLabel, { color: colors.foreground }]}>
                    {profile.label}
                  </Text>
                  <Text
                    style={[styles.profileHint, { color: colors.mutedForeground }]}
                  >
                    {profile.hint}
                  </Text>
                </View>
                {selected ? (
                  <Icon name="check" size={21} color={colors.foreground} />
                ) : null}
              </Pressable>
            );
          })}
        </View>

        {session.error ? (
          <Text style={[styles.error, { color: colors.destructive }]}>
            {session.error}
          </Text>
        ) : null}

        <Pressable
          accessibilityLabel="Выйти из аккаунта"
          accessibilityRole="button"
          onPress={() => void session.logout()}
          style={({ pressed }) => [
            styles.logout,
            { backgroundColor: colors.destructiveSurface },
            pressed && styles.pressed,
          ]}
        >
          <Icon name="logout" size={21} color={colors.destructive} />
          <Text style={[styles.logoutText, { color: colors.destructive }]}>
            Выйти
          </Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { alignItems: "center", flex: 1, justifyContent: "center" },
  header: {
    alignItems: "center",
    flexDirection: "row",
    height: 76,
    justifyContent: "space-between",
    paddingHorizontal: Layout.edgeInset,
  },
  headerTitle: { fontSize: 21, fontWeight: "700", letterSpacing: -0.45 },
  headerSpacer: { height: Layout.headerControl, width: Layout.headerControl },
  content: { paddingBottom: 36, paddingHorizontal: 18 },
  identity: { alignItems: "center", paddingBottom: 28, paddingTop: 12 },
  avatar: {
    alignItems: "center",
    borderRadius: 42,
    height: 84,
    justifyContent: "center",
    width: 84,
  },
  avatarText: { fontSize: 31, fontWeight: "700" },
  identityName: { fontSize: 24, fontWeight: "700", marginTop: 14 },
  identityEmail: { fontSize: 15, marginTop: 4 },
  ownerBadge: { borderRadius: Radius.circle, marginTop: 12, paddingHorizontal: 12, paddingVertical: 6 },
  ownerBadgeText: { fontSize: 12, fontWeight: "700" },
  sectionTitle: { fontSize: 14, fontWeight: "700", marginBottom: 8, marginLeft: 10, marginTop: 18 },
  card: { borderRadius: Radius.card, overflow: "hidden", paddingHorizontal: 14 },
  label: { fontSize: 12, fontWeight: "600", marginBottom: 7, marginTop: 13 },
  nameRow: { alignItems: "center", flexDirection: "row", gap: 10, paddingBottom: 14 },
  nameInput: { borderRadius: Radius.md, borderWidth: StyleSheet.hairlineWidth, flex: 1, fontSize: 16, height: 48, paddingHorizontal: 14 },
  saveButton: { alignItems: "center", borderRadius: 24, height: 48, justifyContent: "center", width: 48 },
  profileRow: { alignItems: "center", flexDirection: "row", minHeight: 72, paddingVertical: 11 },
  profileCopy: { flex: 1, paddingRight: 12 },
  profileLabel: { fontSize: 16, fontWeight: "600" },
  profileHint: { fontSize: 12, lineHeight: 17, marginTop: 3 },
  error: { fontSize: 13, lineHeight: 18, marginHorizontal: 10, marginTop: 12 },
  logout: { alignItems: "center", borderRadius: Radius.card, flexDirection: "row", gap: 10, justifyContent: "center", marginTop: 24, minHeight: 54 },
  logoutText: { fontSize: 16, fontWeight: "700" },
  disabled: { opacity: 0.35 },
  pressed: { opacity: 0.58 },
});
