const ACTIVE_TASK_STATES = new Set(["leased", "running", "review"]);
const QUEUED_TASK_STATES = new Set(["queued", "ready"]);
const KNOWN_TASK_STATES = new Set([
  ...ACTIVE_TASK_STATES,
  ...QUEUED_TASK_STATES,
  "pending",
  "completed",
  "failed",
  "blocked",
  "cancelled",
  "incomplete",
]);
const ONLINE_NODE_STATES = new Set(["online", "ready", "active", "healthy"]);
const KNOWN_NODE_STATES = new Set([
  ...ONLINE_NODE_STATES,
  "offline",
  "stale",
  "inactive",
  "unhealthy",
  "degraded",
  "draining",
]);
const HEALTHY_CONTROL_STATES = new Set(["ok", "completed", "online", "ready", "healthy"]);
const UNHEALTHY_CONTROL_STATES = new Set(["degraded", "failed", "offline", "unhealthy", "unavailable", "blocked"]);

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function loadingMetric(label) {
  return { label, value: "…", hint: "Получение данных", state: "loading" };
}

function unavailableMetric(label, hint = "Источник недоступен") {
  return { label, value: "Нет данных", hint, state: "unavailable" };
}

function liveMetric(label, value, hint) {
  return { label, value, hint, state: "live" };
}

function source(snapshot, key) {
  const section = snapshot?.[key];
  return section?.available ? section : null;
}

function taskState(task) {
  return String(task?.state || task?.status || "").toLowerCase();
}

function nodeState(node) {
  return String(node?.state || node?.status || node?.health || "").toLowerCase();
}

export function buildControlView(snapshot, phase = "ready") {
  if (phase === "loading") {
    return {
      state: "loading",
      stateLabel: "Загрузка",
      intro: "Получаю подтверждённые данные Home…",
      metrics: ["Узлы online", "В очереди", "В работе", "Control Plane"].map(loadingMetric),
      tasks: [],
      tasksState: "loading",
      tasksMessage: "Получаю список задач…",
    };
  }

  const statusSource = source(snapshot, "status");
  const taskSource = source(snapshot, "tasks");
  const nodeSource = source(snapshot, "nodes");
  const status = statusSource?.value && typeof statusSource.value === "object" ? statusSource.value : {};
  const tasks = Array.isArray(taskSource?.value) ? taskSource.value : [];
  const nodes = Array.isArray(nodeSource?.value) ? nodeSource.value : [];
  const tasksHaveKnownStates = tasks.every((task) => KNOWN_TASK_STATES.has(taskState(task)));
  const nodesHaveKnownStates = nodes.every((node) => KNOWN_NODE_STATES.has(nodeState(node)));

  const explicitOnline = finiteNumber(status.online_nodes);
  let onlineMetric;
  if (explicitOnline !== null) {
    const total = finiteNumber(status.total_nodes);
    onlineMetric = liveMetric("Узлы online", explicitOnline, total === null ? "по статусу Home" : `из ${total}`);
  } else if (nodeSource && nodesHaveKnownStates) {
    onlineMetric = liveMetric(
      "Узлы online",
      nodes.filter((node) => ONLINE_NODE_STATES.has(nodeState(node))).length,
      `из ${nodes.length} с явным статусом`,
    );
  } else {
    onlineMetric = unavailableMetric("Узлы online", nodeSource ? "Нет статусов узлов" : "Источник узлов недоступен");
  }

  const explicitQueue = finiteNumber(status.queue_size);
  const queueMetric = explicitQueue !== null
    ? liveMetric("В очереди", explicitQueue, "по статусу Home")
    : taskSource && tasksHaveKnownStates
      ? liveMetric("В очереди", tasks.filter((task) => QUEUED_TASK_STATES.has(taskState(task))).length, "по доступному списку задач")
      : unavailableMetric("В очереди", taskSource ? "Есть задачи с неизвестным статусом" : "Источник задач недоступен");

  const runningMetric = taskSource && tasksHaveKnownStates
    ? liveMetric("В работе", tasks.filter((task) => ACTIVE_TASK_STATES.has(taskState(task))).length, "по доступному списку задач")
    : unavailableMetric("В работе", taskSource ? "Есть задачи с неизвестным статусом" : "Источник задач недоступен");

  const controlStatus = String(status.control_plane?.status || "").toLowerCase();
  const controlMetric = !statusSource
    ? unavailableMetric("Control Plane", "Источник статуса недоступен")
    : !controlStatus
      ? unavailableMetric("Control Plane", "Статус не опубликован")
      : HEALTHY_CONTROL_STATES.has(controlStatus) || UNHEALTHY_CONTROL_STATES.has(controlStatus)
        ? liveMetric(
          "Control Plane",
          HEALTHY_CONTROL_STATES.has(controlStatus) ? "Home" : "Degraded",
          controlStatus,
        )
        : unavailableMetric("Control Plane", "Получен неизвестный статус");

  const anyLiveSource = Boolean(statusSource || taskSource || nodeSource);
  return {
    state: anyLiveSource ? "live" : "unavailable",
    stateLabel: anyLiveSource ? "Live" : "Недоступно",
    intro: anyLiveSource
      ? "Показаны только значения, подтверждённые доступными API Home."
      : "Данные Home сейчас недоступны; нулевые значения не подставляются.",
    metrics: [onlineMetric, queueMetric, runningMetric, controlMetric],
    tasks,
    tasksState: taskSource ? "live" : "unavailable",
    tasksMessage: taskSource ? "Подтверждённых задач в списке нет." : "Список задач сейчас недоступен.",
  };
}
