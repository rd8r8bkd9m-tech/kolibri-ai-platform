import { useRouter } from "expo-router";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import { CircleButton } from "@/components/shell/circle-button";
import { Icon } from "@/components/ui/icon";
import { Radius } from "@/constants/theme";
import { useTheme } from "@/hooks/use-theme";
import { haptics } from "@/lib/haptics";
import {
  MobileApiError,
  useMobileSession,
} from "@/src/auth/mobile-session";
import { constructionEstimateAccess } from "@/src/verticals/construction-estimates/access";
import { ConstructionEstimateClient } from "@/src/verticals/construction-estimates/client";
import {
  isNativeEstimateDraftValid,
  type EstimateDocumentSummary,
  type NativeEstimate,
  type NativeEstimateRow,
} from "@/src/verticals/construction-estimates/contracts";

const formatMoney = (value: string) => {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("ru-RU", {
        currency: "RUB",
        maximumFractionDigits: 2,
        style: "currency",
      }).format(amount)
    : `${value} ₽`;
};

const localLineTotal = (row: NativeEstimateRow) => {
  const total = Number(row.quantity) * Number(row.unitPrice);
  return Number.isFinite(total) ? total.toFixed(2) : row.lineTotal;
};

function ScreenHeader({
  subtitle,
  onBack,
}: {
  subtitle?: string;
  onBack: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.header}>
      <CircleButton
        accessibilityLabel="Вернуться назад"
        accessibilityRole="button"
        onPress={() => {
          haptics.selection();
          onBack();
        }}
      >
        <Icon name="chevron-left" color={colors.foreground} size={28} />
      </CircleButton>
      <View style={styles.headerCopy}>
        <Text
          numberOfLines={1}
          style={[styles.headerTitle, { color: colors.foreground }]}
        >
          Сметы
        </Text>
        {subtitle ? (
          <Text
            numberOfLines={1}
            style={[styles.headerSubtitle, { color: colors.mutedForeground }]}
          >
            {subtitle}
          </Text>
        ) : null}
      </View>
      <View style={styles.headerBalance} />
    </View>
  );
}

function AccessBoundary({ reason }: { reason: string }) {
  const router = useRouter();
  const { colors } = useTheme();
  return (
    <SafeAreaView
      edges={["top", "bottom"]}
      style={[styles.safe, { backgroundColor: colors.background }]}
    >
      <ScreenHeader onBack={() => router.replace("/")} />
      <View style={styles.boundary}>
        <View
          style={[styles.boundaryIcon, { backgroundColor: colors.surface }]}
        >
          <Icon name="document" color={colors.mutedForeground} size={31} />
        </View>
        <Text style={[styles.boundaryTitle, { color: colors.foreground }]}>
          Мобильный редактор выключен сервером
        </Text>
        <Text
          style={[styles.boundaryBody, { color: colors.mutedForeground }]}
        >
          {reason}
        </Text>
        <Text
          accessibilityRole="text"
          style={[styles.boundaryNote, { color: colors.mutedForeground }]}
        >
          Данные и сохранение не подменяются локальным демо.
        </Text>
      </View>
    </SafeAreaView>
  );
}

function EstimateCard({
  document,
  onPress,
}: {
  document: EstimateDocumentSummary;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityHint="Открывает сохранённую серверную смету"
      accessibilityLabel={`${document.name}, ${document.rowCount} позиций`}
      accessibilityRole="button"
      disabled={!document.editable}
      onPress={() => {
        haptics.selection();
        onPress();
      }}
      style={({ pressed }) => [
        styles.documentCard,
        {
          backgroundColor: colors.surface,
          opacity: document.editable ? 1 : 0.55,
        },
        pressed && styles.pressed,
      ]}
    >
      <View style={styles.documentIcon}>
        <Icon name="document" color={colors.foreground} size={25} />
      </View>
      <View style={styles.documentCopy}>
        <Text
          numberOfLines={2}
          style={[styles.documentName, { color: colors.foreground }]}
        >
          {document.name}
        </Text>
        <Text
          numberOfLines={1}
          style={[styles.documentProject, { color: colors.mutedForeground }]}
        >
          {document.projectName} · v{document.version}
        </Text>
        <Text style={[styles.documentMeta, { color: colors.mutedForeground }]}>
          {document.rowCount} позиций · {formatMoney(document.total)}
        </Text>
      </View>
      <Icon
        name="chevron-right"
        color={colors.mutedForeground}
        size={22}
      />
    </Pressable>
  );
}

function EstimateCatalog({
  client,
  onOpen,
}: {
  client: ConstructionEstimateClient;
  onOpen: (projectId: string) => void;
}) {
  const { colors } = useTheme();
  const [documents, setDocuments] = useState<
    readonly EstimateDocumentSummary[]
  >([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      setDocuments(await client.list());
      setStatus("ready");
    } catch (reason) {
      setMessage(
        reason instanceof Error ? reason.message : "Не удалось загрузить сметы.",
      );
      setStatus("error");
    }
  }, [client]);

  useEffect(() => {
    let active = true;
    void client
      .list()
      .then((next) => {
        if (!active) return;
        setDocuments(next);
        setStatus("ready");
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setMessage(
          reason instanceof Error
            ? reason.message
            : "Не удалось загрузить сметы.",
        );
        setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [client]);

  if (status === "loading") {
    return (
      <View accessibilityLabel="Загрузка смет" style={styles.center}>
        <ActivityIndicator color={colors.foreground} />
      </View>
    );
  }

  if (status === "error") {
    return (
      <View style={styles.center}>
        <Text
          accessibilityRole="alert"
          style={[styles.errorText, { color: colors.destructive }]}
        >
          {message}
        </Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => {
            setStatus("loading");
            setMessage("");
            void load();
          }}
          style={[styles.secondaryButton, { backgroundColor: colors.surface }]}
        >
          <Icon name="reload" color={colors.foreground} size={19} />
          <Text style={[styles.secondaryButtonText, { color: colors.foreground }]}>
            Повторить
          </Text>
        </Pressable>
      </View>
    );
  }

  return (
    <FlatList
      contentContainerStyle={[
        styles.catalog,
        documents.length === 0 && styles.catalogEmpty,
      ]}
      data={documents}
      keyExtractor={(document) => document.id}
      ListEmptyComponent={
        <View style={styles.emptyDocuments}>
          <Icon name="document" color={colors.mutedForeground} size={34} />
          <Text
            style={[styles.emptyTitle, { color: colors.foreground }]}
          >
            Сохранённых смет пока нет
          </Text>
          <Text
            style={[styles.emptyBody, { color: colors.mutedForeground }]}
          >
            Здесь появятся реальные документы V3 после создания в проекте.
          </Text>
        </View>
      }
      renderItem={({ item }) => (
        <EstimateCard document={item} onPress={() => onOpen(item.projectId)} />
      )}
      showsVerticalScrollIndicator={false}
    />
  );
}

function RowEditor({
  row,
  onChange,
}: {
  row: NativeEstimateRow;
  onChange: (
    field: "description" | "unit" | "quantity" | "unitPrice",
    value: string,
  ) => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.rowCard, { backgroundColor: colors.surface }]}>
      <View style={styles.rowHeading}>
        <Text
          numberOfLines={1}
          style={[styles.rowSection, { color: colors.mutedForeground }]}
        >
          {row.section}
        </Text>
        <Text style={[styles.rowTotal, { color: colors.foreground }]}>
          {formatMoney(localLineTotal(row))}
        </Text>
      </View>
      <TextInput
        accessibilityLabel="Наименование позиции"
        maxLength={300}
        multiline
        onChangeText={(value) => onChange("description", value)}
        style={[
          styles.descriptionInput,
          {
            backgroundColor: colors.composer,
            borderColor: colors.border,
            color: colors.foreground,
          },
        ]}
        value={row.description}
      />
      <View style={styles.rowFields}>
        <View style={styles.field}>
          <Text style={[styles.fieldLabel, { color: colors.mutedForeground }]}>
            Количество
          </Text>
          <TextInput
            accessibilityLabel="Количество"
            keyboardType="decimal-pad"
            maxLength={20}
            onChangeText={(value) =>
              onChange("quantity", value.replace(",", "."))
            }
            style={[
              styles.fieldInput,
              {
                backgroundColor: colors.composer,
                borderColor: colors.border,
                color: colors.foreground,
              },
            ]}
            value={row.quantity}
          />
        </View>
        <View style={styles.unitField}>
          <Text style={[styles.fieldLabel, { color: colors.mutedForeground }]}>
            Ед.
          </Text>
          <TextInput
            accessibilityLabel="Единица измерения"
            maxLength={32}
            onChangeText={(value) => onChange("unit", value)}
            style={[
              styles.fieldInput,
              {
                backgroundColor: colors.composer,
                borderColor: colors.border,
                color: colors.foreground,
              },
            ]}
            value={row.unit}
          />
        </View>
        <View style={styles.field}>
          <Text style={[styles.fieldLabel, { color: colors.mutedForeground }]}>
            Цена
          </Text>
          <TextInput
            accessibilityLabel="Цена за единицу"
            keyboardType="decimal-pad"
            maxLength={20}
            onChangeText={(value) =>
              onChange("unitPrice", value.replace(",", "."))
            }
            style={[
              styles.fieldInput,
              {
                backgroundColor: colors.composer,
                borderColor: colors.border,
                color: colors.foreground,
              },
            ]}
            value={row.unitPrice}
          />
        </View>
      </View>
    </View>
  );
}

function EstimateEditor({
  client,
  initial,
  onClose,
}: {
  client: ConstructionEstimateClient;
  initial: NativeEstimate;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const [estimate, setEstimate] = useState(initial);
  const [title, setTitle] = useState(initial.estimateTitle);
  const [rows, setRows] = useState<readonly NativeEstimateRow[]>(initial.rows);
  const [savedSnapshot, setSavedSnapshot] = useState(() =>
    JSON.stringify({ title: initial.estimateTitle, rows: initial.rows }),
  );
  const [saveState, setSaveState] = useState<
    "idle" | "saving" | "saved" | "error" | "conflict"
  >("idle");
  const [message, setMessage] = useState("");

  const snapshot = JSON.stringify({ title, rows });
  const dirty = snapshot !== savedSnapshot;
  const valid = isNativeEstimateDraftValid(title, rows);
  const total = rows.reduce(
    (sum, row) => sum + Number(localLineTotal(row)),
    0,
  );

  const close = () => {
    if (!dirty) {
      onClose();
      return;
    }
    Alert.alert(
      "Отменить изменения?",
      "Несохранённые правки этой сметы будут потеряны.",
      [
        { text: "Продолжить редактирование", style: "cancel" },
        { text: "Отменить правки", style: "destructive", onPress: onClose },
      ],
    );
  };

  const reload = useCallback(async () => {
    setSaveState("saving");
    setMessage("");
    try {
      const next = await client.open(estimate.projectId);
      setEstimate(next);
      setTitle(next.estimateTitle);
      setRows(next.rows);
      const nextSnapshot = JSON.stringify({
        title: next.estimateTitle,
        rows: next.rows,
      });
      setSavedSnapshot(nextSnapshot);
      setSaveState("idle");
    } catch (reason) {
      setMessage(
        reason instanceof Error ? reason.message : "Не удалось обновить смету.",
      );
      setSaveState("error");
    }
  }, [client, estimate.projectId]);

  const save = async () => {
    if (!dirty || !valid || saveState === "saving") return;
    setSaveState("saving");
    setMessage("");
    try {
      const next = await client.save(estimate, title, rows);
      setEstimate(next);
      setTitle(next.estimateTitle);
      setRows(next.rows);
      setSavedSnapshot(
        JSON.stringify({ title: next.estimateTitle, rows: next.rows }),
      );
      setSaveState("saved");
      haptics.success();
    } catch (reason) {
      if (
        reason instanceof MobileApiError &&
        reason.code === "estimate_version_conflict"
      ) {
        setSaveState("conflict");
        setMessage(reason.message);
      } else {
        setSaveState("error");
        setMessage(
          reason instanceof Error ? reason.message : "Не удалось сохранить.",
        );
      }
      haptics.error();
    }
  };

  const updateRow = (
    id: string,
    field: "description" | "unit" | "quantity" | "unitPrice",
    value: string,
  ) => {
    setRows((current) =>
      current.map((row) =>
        row.id === id
          ? {
              ...row,
              [field]: value,
              ...(field === "quantity"
                ? { quantityBasis: "Введено пользователем" }
                : null),
              ...(field === "description" ||
              field === "unit" ||
              field === "unitPrice"
                ? { priceBasis: "Введено пользователем" }
                : null),
            }
          : row,
      ),
    );
    setSaveState("idle");
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.flex}
    >
      <ScreenHeader subtitle={`Версия ${estimate.version}`} onBack={close} />
      <FlatList
        contentContainerStyle={styles.editorContent}
        data={rows}
        keyExtractor={(row) => row.id}
        keyboardDismissMode="interactive"
        keyboardShouldPersistTaps="handled"
        ListHeaderComponent={
          <View style={styles.editorHeading}>
            <Text style={[styles.fieldLabel, { color: colors.mutedForeground }]}>
              Название сметы
            </Text>
            <TextInput
              accessibilityLabel="Название сметы"
              maxLength={240}
              onChangeText={(value) => {
                setTitle(value);
                setSaveState("idle");
              }}
              style={[
                styles.titleInput,
                {
                  backgroundColor: colors.surface,
                  borderColor: colors.border,
                  color: colors.foreground,
                },
              ]}
              value={title}
            />
            <View style={styles.editorSummary}>
              <Text style={[styles.summaryText, { color: colors.mutedForeground }]}>
                {rows.length} позиций
              </Text>
              <Text style={[styles.summaryTotal, { color: colors.foreground }]}>
                {formatMoney(total.toFixed(2))}
              </Text>
            </View>
          </View>
        }
        renderItem={({ item }) => (
          <RowEditor
            row={item}
            onChange={(field, value) => updateRow(item.id, field, value)}
          />
        )}
        showsVerticalScrollIndicator={false}
      />
      <View
        style={[
          styles.saveBar,
          { backgroundColor: colors.background, borderTopColor: colors.muted },
        ]}
      >
        <View style={styles.saveMessage}>
          <Text
            accessibilityLiveRegion="polite"
            numberOfLines={2}
            style={[
              styles.saveMessageText,
              {
                color:
                  saveState === "error" || saveState === "conflict"
                    ? colors.destructive
                    : colors.mutedForeground,
              },
            ]}
          >
            {saveState === "saving"
              ? "Сохраняю…"
              : saveState === "saved"
                ? "Сохранено на сервере"
                : message || (dirty ? "Есть несохранённые изменения" : "Актуально")}
          </Text>
          {saveState === "conflict" ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => void reload()}
              style={styles.reloadLink}
            >
              <Text style={{ color: colors.foreground, fontWeight: "700" }}>
                Обновить
              </Text>
            </Pressable>
          ) : null}
        </View>
        <Pressable
          accessibilityLabel="Сохранить смету"
          accessibilityRole="button"
          accessibilityState={{
            busy: saveState === "saving",
            disabled: !dirty || !valid || saveState === "saving",
          }}
          disabled={!dirty || !valid || saveState === "saving"}
          onPress={() => void save()}
          style={({ pressed }) => [
            styles.saveButton,
            {
              backgroundColor:
                dirty && valid ? colors.primary : colors.muted,
            },
            pressed && styles.pressed,
          ]}
        >
          {saveState === "saving" ? (
            <ActivityIndicator color={colors.primaryForeground} size="small" />
          ) : (
            <Icon
              name="save"
              color={
                dirty && valid
                  ? colors.primaryForeground
                  : colors.mutedForeground
              }
              size={21}
            />
          )}
          <Text
            style={[
              styles.saveButtonText,
              {
                color:
                  dirty && valid
                    ? colors.primaryForeground
                    : colors.mutedForeground,
              },
            ]}
          >
            Сохранить
          </Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

export default function EstimatesScreen() {
  const router = useRouter();
  const session = useMobileSession();
  const { colors } = useTheme();
  const access = constructionEstimateAccess(session.user);
  const client = useMemo(
    () => new ConstructionEstimateClient(session.authorizedFetch),
    [session.authorizedFetch],
  );
  const [selected, setSelected] = useState<NativeEstimate | null>(null);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState("");

  if (!access.enabled) return <AccessBoundary reason={access.reason} />;

  const open = async (projectId: string) => {
    setOpening(true);
    setError("");
    try {
      setSelected(await client.open(projectId));
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Не удалось открыть смету.",
      );
      haptics.error();
    } finally {
      setOpening(false);
    }
  };

  return (
    <SafeAreaView
      edges={["top", "bottom"]}
      style={[styles.safe, { backgroundColor: colors.background }]}
    >
      {selected ? (
        <EstimateEditor
          client={client}
          initial={selected}
          onClose={() => setSelected(null)}
        />
      ) : (
        <>
          <ScreenHeader onBack={() => router.replace("/")} />
          {error ? (
            <Text
              accessibilityRole="alert"
              style={[styles.inlineError, { color: colors.destructive }]}
            >
              {error}
            </Text>
          ) : null}
          {opening ? (
            <View accessibilityLabel="Открытие сметы" style={styles.center}>
              <ActivityIndicator color={colors.foreground} />
            </View>
          ) : (
            <EstimateCatalog client={client} onOpen={(id) => void open(id)} />
          )}
        </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  flex: { flex: 1 },
  header: {
    alignItems: "center",
    flexDirection: "row",
    height: 76,
    paddingHorizontal: 16,
  },
  headerCopy: { alignItems: "center", flex: 1, paddingHorizontal: 8 },
  headerTitle: { fontSize: 22, fontWeight: "700", letterSpacing: -0.45 },
  headerSubtitle: { fontSize: 12, marginTop: 2 },
  headerBalance: { height: 48, width: 48 },
  boundary: {
    alignItems: "center",
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 32,
    paddingBottom: 72,
  },
  boundaryIcon: {
    alignItems: "center",
    borderRadius: 34,
    height: 68,
    justifyContent: "center",
    width: 68,
  },
  boundaryTitle: {
    fontSize: 20,
    fontWeight: "700",
    letterSpacing: -0.35,
    marginTop: 18,
    textAlign: "center",
  },
  boundaryBody: {
    fontSize: 15,
    lineHeight: 21,
    marginTop: 9,
    textAlign: "center",
  },
  boundaryNote: {
    fontSize: 12,
    lineHeight: 17,
    marginTop: 12,
    textAlign: "center",
  },
  center: {
    alignItems: "center",
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 28,
  },
  catalog: { gap: 10, padding: 14, paddingBottom: 28 },
  catalogEmpty: { flexGrow: 1 },
  documentCard: {
    alignItems: "center",
    borderRadius: Radius.card,
    flexDirection: "row",
    minHeight: 102,
    paddingHorizontal: 15,
    paddingVertical: 13,
  },
  documentIcon: {
    alignItems: "center",
    height: 45,
    justifyContent: "center",
    width: 45,
  },
  documentCopy: { flex: 1, marginLeft: 7, marginRight: 8 },
  documentName: { fontSize: 17, fontWeight: "700", lineHeight: 21 },
  documentProject: { fontSize: 13, marginTop: 4 },
  documentMeta: { fontSize: 12, marginTop: 3 },
  emptyDocuments: {
    alignItems: "center",
    flex: 1,
    justifyContent: "center",
    paddingBottom: 70,
    paddingHorizontal: 28,
  },
  emptyTitle: { fontSize: 18, fontWeight: "700", marginTop: 14 },
  emptyBody: {
    fontSize: 14,
    lineHeight: 20,
    marginTop: 7,
    textAlign: "center",
  },
  errorText: { fontSize: 14, lineHeight: 20, textAlign: "center" },
  secondaryButton: {
    alignItems: "center",
    borderRadius: 22,
    flexDirection: "row",
    gap: 7,
    marginTop: 15,
    minHeight: 44,
    paddingHorizontal: 18,
  },
  secondaryButtonText: { fontSize: 15, fontWeight: "700" },
  inlineError: {
    fontSize: 13,
    lineHeight: 18,
    paddingHorizontal: 18,
    paddingVertical: 8,
    textAlign: "center",
  },
  editorContent: { gap: 10, padding: 14, paddingBottom: 20 },
  editorHeading: { gap: 7, paddingBottom: 3 },
  titleInput: {
    borderRadius: 13,
    borderWidth: StyleSheet.hairlineWidth,
    fontSize: 17,
    fontWeight: "700",
    minHeight: 50,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  editorSummary: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 30,
    paddingHorizontal: 3,
  },
  summaryText: { fontSize: 13, fontWeight: "600" },
  summaryTotal: { fontSize: 16, fontWeight: "700" },
  rowCard: { borderRadius: Radius.card, padding: 12 },
  rowHeading: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 9,
  },
  rowSection: { flex: 1, fontSize: 12, fontWeight: "700", marginRight: 8 },
  rowTotal: { fontSize: 14, fontWeight: "700" },
  descriptionInput: {
    borderRadius: 11,
    borderWidth: StyleSheet.hairlineWidth,
    fontSize: 15,
    lineHeight: 20,
    minHeight: 58,
    paddingHorizontal: 11,
    paddingVertical: 9,
  },
  rowFields: { flexDirection: "row", gap: 7, marginTop: 9 },
  field: { flex: 1 },
  unitField: { width: 70 },
  fieldLabel: { fontSize: 11, fontWeight: "600", marginBottom: 5 },
  fieldInput: {
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    fontSize: 14,
    minHeight: 43,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  saveBar: {
    alignItems: "center",
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    minHeight: 70,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  saveMessage: { flex: 1, marginRight: 10 },
  saveMessageText: { fontSize: 12, lineHeight: 16 },
  reloadLink: { marginTop: 3, minHeight: 25, justifyContent: "center" },
  saveButton: {
    alignItems: "center",
    borderRadius: 23,
    flexDirection: "row",
    gap: 7,
    height: 46,
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  saveButtonText: { fontSize: 14, fontWeight: "700" },
  pressed: { opacity: 0.58 },
});
