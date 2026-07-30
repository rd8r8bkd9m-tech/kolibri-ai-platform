import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useNavigation, useRouter } from "expo-router";
import type { DrawerNavigationProp } from "expo-router/build/react-navigation/drawer/types";

import { AuthScreen } from "@/components/auth/auth-screen";
import { CircleButton } from "@/components/shell/circle-button";
import { HamburgerMark } from "@/components/shell/hamburger-mark";
import { Icon } from "@/components/ui/icon";
import { Layout, Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import { useMobileSession } from "@/src/auth/mobile-session";
import { ConstructionEstimateClient } from "@/src/verticals/construction-estimates/client";
import type { EstimateDocumentSummary } from "@/src/verticals/construction-estimates/contracts";

type CatalogMode = "projects" | "library";
type ProjectSummary = {
  id: string;
  name: string;
  documentCount: number;
  updatedAt: string;
};

const dateLabel = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("ru-RU", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(date);
};

export function CatalogScreen({ mode }: { mode: CatalogMode }) {
  const session = useMobileSession();
  const { colors } = useTheme();
  const navigation =
    useNavigation<
      DrawerNavigationProp<
        { projects: undefined; library: undefined },
        CatalogMode
      >
    >();
  const router = useRouter();
  const client = useMemo(
    () => new ConstructionEstimateClient(session.authorizedFetch),
    [session.authorizedFetch],
  );
  const [documents, setDocuments] = useState<
    readonly EstimateDocumentSummary[]
  >([]);
  const [query, setQuery] = useState("");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      setDocuments(await client.list());
      setState("ready");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось загрузить каталог.",
      );
      setState("error");
    }
  }, [client]);

  useEffect(() => {
    let active = true;
    void client
      .list()
      .then((next) => {
        if (!active) return;
        setDocuments(next);
        setState("ready");
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(
          reason instanceof Error
            ? reason.message
            : "Не удалось загрузить каталог.",
        );
        setState("error");
      });
    return () => {
      active = false;
    };
  }, [client]);

  const projects = useMemo(() => {
    const grouped = new Map<string, ProjectSummary>();
    for (const document of documents) {
      const current = grouped.get(document.projectId);
      grouped.set(document.projectId, {
        id: document.projectId,
        name: document.projectName,
        documentCount: (current?.documentCount ?? 0) + 1,
        updatedAt:
          !current || document.updatedAt > current.updatedAt
            ? document.updatedAt
            : current.updatedAt,
      });
    }
    return [...grouped.values()].sort((left, right) =>
      right.updatedAt.localeCompare(left.updatedAt),
    );
  }, [documents]);

  const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");
  const projectRows = projects.filter(
    (project) =>
      !normalizedQuery ||
      project.name.toLocaleLowerCase("ru-RU").includes(normalizedQuery),
  );
  const documentRows = documents.filter(
    (document) =>
      !normalizedQuery ||
      document.name.toLocaleLowerCase("ru-RU").includes(normalizedQuery) ||
      document.projectName.toLocaleLowerCase("ru-RU").includes(normalizedQuery),
  );
  const title = mode === "projects" ? "Проекты" : "Библиотека";

  if (session.status === "restoring") {
    return (
      <View style={[styles.center, { backgroundColor: colors.background }]}>
        <ActivityIndicator color={colors.foreground} />
      </View>
    );
  }
  if (session.status === "signed-out") return <AuthScreen />;

  const data: readonly (ProjectSummary | EstimateDocumentSummary)[] =
    mode === "projects" ? projectRows : documentRows;

  return (
    <SafeAreaView
      edges={["top", "bottom"]}
      style={[styles.safe, { backgroundColor: colors.background }]}
    >
      <View style={styles.header}>
        <CircleButton
          accessibilityLabel="Открыть меню"
          accessibilityRole="button"
          onPress={() => navigation.openDrawer()}
        >
          <HamburgerMark />
        </CircleButton>
        <Text style={[styles.title, { color: colors.foreground }]}>{title}</Text>
        <View style={styles.headerBalance} />
      </View>

      <View
        style={[
          styles.search,
          { backgroundColor: colors.surface, borderColor: colors.border },
        ]}
      >
        <Icon name="search" size={21} color={colors.mutedForeground} />
        <TextInput
          accessibilityLabel={`Поиск: ${title}`}
          onChangeText={setQuery}
          placeholder={
            mode === "projects" ? "Поиск проектов" : "Поиск в библиотеке"
          }
          placeholderTextColor={colors.mutedForeground}
          style={[styles.searchInput, { color: colors.foreground }]}
          value={query}
        />
      </View>

      {state === "loading" ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.foreground} />
        </View>
      ) : state === "error" ? (
        <View style={styles.center}>
          <Text style={[styles.error, { color: colors.destructive }]}>
            {error}
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => void load()}
            style={[styles.retry, { backgroundColor: colors.surface }]}
          >
            <Text style={[styles.retryText, { color: colors.foreground }]}>
              Повторить
            </Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          contentContainerStyle={styles.list}
          data={data}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Icon
                name={mode === "projects" ? "folder" : "library"}
                size={34}
                color={colors.mutedForeground}
              />
              <Text style={[styles.emptyTitle, { color: colors.foreground }]}>
                {query.trim() ? "Ничего не найдено" : `${title} пока пуста`}
              </Text>
              <Text
                style={[styles.emptyBody, { color: colors.mutedForeground }]}
              >
                Данные появятся после сохранения задачи или сметы.
              </Text>
            </View>
          }
          renderItem={({ item }) => {
            const isProject = "documentCount" in item;
            return (
              <Pressable
                accessibilityLabel={
                  isProject
                    ? `Открыть проект ${item.name}`
                    : `Открыть документ ${item.name}`
                }
                accessibilityRole="button"
                onPress={() => {
                  haptics.selection();
                  router.push("/estimates");
                }}
                style={({ pressed }) => [
                  styles.row,
                  { backgroundColor: colors.surface },
                  pressed && styles.pressed,
                ]}
              >
                <View style={[styles.rowIcon, { backgroundColor: colors.muted }]}>
                  <Icon
                    name={isProject ? "folder" : "document"}
                    size={24}
                    color={colors.foreground}
                  />
                </View>
                <View style={styles.rowCopy}>
                  <Text
                    numberOfLines={2}
                    style={[styles.rowTitle, { color: colors.foreground }]}
                  >
                    {item.name}
                  </Text>
                  <Text
                    numberOfLines={1}
                    style={[styles.rowMeta, { color: colors.mutedForeground }]}
                  >
                    {isProject
                      ? `${item.documentCount} док. · ${dateLabel(item.updatedAt)}`
                      : `${item.projectName} · ${item.rowCount} поз.`}
                  </Text>
                </View>
                <Icon
                  name="chevron-right"
                  size={19}
                  color={colors.mutedForeground}
                />
              </Pressable>
            );
          }}
          showsVerticalScrollIndicator={false}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  header: {
    alignItems: "center",
    flexDirection: "row",
    height: 76,
    justifyContent: "space-between",
    paddingHorizontal: Layout.edgeInset,
  },
  title: { fontSize: 22, fontWeight: "700", letterSpacing: -0.5 },
  headerBalance: { height: Layout.headerControl, width: Layout.headerControl },
  search: {
    alignItems: "center",
    borderRadius: Radius.circle,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    marginBottom: 12,
    marginHorizontal: 18,
    minHeight: 48,
    paddingHorizontal: 15,
  },
  searchInput: { flex: 1, fontSize: 16, marginLeft: 9 },
  center: { alignItems: "center", flex: 1, justifyContent: "center", padding: 28 },
  list: { gap: 9, paddingBottom: 32, paddingHorizontal: 16 },
  row: {
    alignItems: "center",
    borderRadius: Radius.card,
    flexDirection: "row",
    minHeight: 72,
    padding: 10,
  },
  rowIcon: {
    alignItems: "center",
    borderRadius: 15,
    height: 50,
    justifyContent: "center",
    width: 50,
  },
  rowCopy: { flex: 1, marginHorizontal: 12 },
  rowTitle: { fontSize: 16, fontWeight: "600", lineHeight: 21 },
  rowMeta: { fontSize: 13, marginTop: 4 },
  empty: { alignItems: "center", paddingHorizontal: 30, paddingTop: 100 },
  emptyTitle: { fontSize: 18, fontWeight: "700", marginTop: 14 },
  emptyBody: { fontSize: 14, lineHeight: 20, marginTop: 5, textAlign: "center" },
  error: { fontSize: 14, lineHeight: 20, textAlign: "center" },
  retry: { borderRadius: Radius.circle, marginTop: 16, paddingHorizontal: 18, paddingVertical: 11 },
  retryText: { fontSize: 15, fontWeight: "700" },
  pressed: { opacity: 0.58 },
});
