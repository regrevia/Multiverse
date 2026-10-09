import {
  Activity,
  AlertCircle,
  Box,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Clock3,
  Code2,
  Download,
  Eye,
  FileText,
  GitBranch,
  HelpCircle,
  Layers3,
  Maximize2,
  Minus,
  PauseCircle,
  Play,
  Plus,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  SkipForward,
  Square,
  SquareDashedMousePointer,
  StopCircle,
  Upload,
  UserRound,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  applyAgentPatch,
  artifactsForNode,
  demoGraph,
  type AuditGraph,
  type AgentPatch,
  type GraphNode,
  type NodeExecution,
  type NodeStatus,
  visibleGraph,
} from "./graph/model";
import {
  fitGraphToViewport,
  preserveGraphPositions,
  resolveGraphPosition,
  routeGraphEdge,
  translatePositions,
  type GraphPosition,
} from "./graph/layout";
import {
  mapRuntimeProjection,
  parseRuntimeProjection,
  parseRuntimeViewSnapshot,
  type RuntimeArtifact,
  type RuntimeHumanRequest,
  type RuntimeProjection,
  type RuntimeViewSnapshot,
} from "./graph/runtime";
import {
  RuntimeClient,
  type HumanDecisionPayload,
  type RuntimeCommandReceipt,
  type RuntimeClientConfig,
  type RuntimeEvent,
  type RuntimeInvocationDetail,
  type WatchStatus,
} from "./runtime/client";
import {
  buildHumanInputDecision,
  createHumanDecisionIdempotencyKey,
  getHumanInputFields,
  isArtifactReferenceField,
  type HumanField,
} from "./runtime/human";

type Point = { x: number; y: number };
type PanelMode = "audit" | "agent";
type NodeDrag = {
  ids: string[];
  pointer: Point;
  starts: Record<string, GraphPosition>;
};

const statusLabels: Record<NodeStatus, string> = {
  succeeded: "已完成",
  running: "进行中",
  waiting: "等待处理",
  pending: "待执行",
  failed: "失败",
  unknown: "结果未知",
  reconciling: "核对中",
  blocked: "已阻塞",
  paused: "已暂停",
  stopping: "停止中",
  cancelled: "已取消",
  skipped: "已跳过",
};

const nodeTypeLabels: Record<GraphNode["type"], string> = {
  call: "执行",
  switch: "分支",
  human: "人工",
  end: "结束",
  group: "子流程",
  input: "输入",
  repeat: "循环",
  parallel: "并行",
  workflow: "子流程",
};

const participantLabels: Record<NodeExecution["participantType"], string> = {
  agent: "Agent",
  human: "人工",
  program: "程序",
  external_service: "外部服务",
  process: "本机进程",
  unknown: "执行者未核实",
};

const executionLocationLabels: Record<NodeExecution["location"], string> = {
  runtime: "Runtime",
  local: "本机",
  external: "远程",
  human: "人工入口",
  unknown: "位置未核实",
};

function structureNodeSummary(node: GraphNode): string {
  switch (node.type) {
    case "input":
      return "工作流输入";
    case "switch":
      return `条件分支${node.subtitle ? ` · ${node.subtitle}` : ""}`;
    case "repeat":
      return `循环${node.subtitle ? ` · ${node.subtitle}` : ""}`;
    case "parallel":
      return `并行${node.subtitle ? ` · ${node.subtitle}` : ""}`;
    case "workflow":
      return `子流程${node.subtitle ? ` · ${node.subtitle}` : ""}`;
    case "end":
      return "工作流结束";
    case "group":
      return node.detail;
    case "human":
      return "人工任务";
    case "call":
      return "执行目标未核实";
  }
}

const statusIcons: Record<NodeStatus, typeof Check> = {
  succeeded: Check,
  running: Activity,
  waiting: UserRound,
  pending: CircleDashed,
  failed: AlertCircle,
  unknown: HelpCircle,
  reconciling: Search,
  blocked: ShieldCheck,
  paused: PauseCircle,
  stopping: StopCircle,
  cancelled: Square,
  skipped: SkipForward,
};

type ConnectionState =
  | { kind: "demo"; message: string }
  | { kind: "loading"; message: string }
  | { kind: "live"; message: string }
  | { kind: "reconnecting"; message: string }
  | { kind: "polling"; message: string }
  | { kind: "error"; message: string };

type RuntimeConnectionDraft = {
  baseUrl: string;
  namespace: string;
  runId: string;
  token: string;
};

const RUNTIME_SESSION_KEY = "multiverse.runtime.connection";

type DecisionState = {
  kind: "idle" | "submitting" | "success" | "error";
  message: string;
};

type ControlState = {
  kind: "idle" | "submitting" | "success" | "error";
  message: string;
};

type ArtifactPreviewState = {
  artifactId: string | null;
  kind: "idle" | "loading" | "text" | "binary" | "error";
  mediaType?: string;
  text?: string;
  message?: string;
};

type InvocationDetailState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "loaded"; value: RuntimeInvocationDetail }
  | { kind: "error"; message: string };

function defaultRuntimeConnection(): RuntimeConnectionDraft {
  return {
    baseUrl: import.meta.env.VITE_RUNTIME_BASE_URL ?? "",
    namespace: import.meta.env.VITE_RUNTIME_NAMESPACE ?? "local",
    runId: import.meta.env.VITE_RUNTIME_RUN_ID ?? "",
    token: "",
  };
}

function loadRuntimeConnection(): RuntimeConnectionDraft {
  const fallback = defaultRuntimeConnection();
  try {
    const stored = window.sessionStorage.getItem(RUNTIME_SESSION_KEY);
    if (!stored) return fallback;
    const parsed = JSON.parse(stored) as Partial<RuntimeConnectionDraft>;
    if (
      typeof parsed.baseUrl !== "string" ||
      typeof parsed.namespace !== "string" ||
      typeof parsed.runId !== "string" ||
      typeof parsed.token !== "string"
    ) {
      return fallback;
    }
    return {
      baseUrl: parsed.baseUrl,
      namespace: parsed.namespace,
      runId: parsed.runId,
      token: parsed.token,
    };
  } catch {
    return fallback;
  }
}

function persistRuntimeConnection(connection: RuntimeConnectionDraft) {
  try {
    window.sessionStorage.setItem(RUNTIME_SESSION_KEY, JSON.stringify(connection));
  } catch {
    // Session storage may be disabled by the host; Runtime remains manually connectable.
  }
}

function clearRuntimeConnection() {
  try {
    window.sessionStorage.removeItem(RUNTIME_SESSION_KEY);
  } catch {
    // Ignore storage restrictions when switching to a local snapshot.
  }
}

function App() {
  const [graph, setGraph] = useState<AuditGraph>(demoGraph);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set(["production"]),
  );
  const [selectedId, setSelectedId] = useState("refine");
  const [panelMode, setPanelMode] = useState<PanelMode>("audit");
  const [patchText, setPatchText] = useState(
    JSON.stringify(
      {
        nodeId: "refine",
        title: "细化交付物",
        status: "running",
      },
      null,
      2,
    ),
  );
  const [patchState, setPatchState] = useState<
    { kind: "idle" | "success" | "error"; message: string }
  >({ kind: "idle", message: "等待智能体修改" });
  const [zoom, setZoom] = useState(0.84);
  const [pan, setPan] = useState<Point>({ x: 24, y: 28 });
  const [dragStart, setDragStart] = useState<Point | null>(null);
  const [nodePositions, setNodePositions] = useState<Record<string, GraphPosition>>({});
  const [nodeDrag, setNodeDrag] = useState<NodeDrag | null>(null);
  const nodeMovedRef = useRef(false);
  const [agentEvents, setAgentEvents] = useState([
    "智能体已开始一次细化尝试",
    "已为 draft → refine 选择标准交接",
    "运行证据仍绑定在当前作用域",
  ]);
  const [importState, setImportState] = useState<
    { kind: "demo" | "reading" | "success" | "error"; message: string }
  >({ kind: "demo", message: "演示数据" });
  const [sourceLabel, setSourceLabel] = useState("演示数据");
  const [connection, setConnection] = useState<RuntimeConnectionDraft>(loadRuntimeConnection);
  const [connectionDraft, setConnectionDraft] = useState(connection);
  const [showConnection, setShowConnection] = useState(false);
  const [connectionEnabled, setConnectionEnabled] = useState(true);
  const [connectionState, setConnectionState] = useState<ConnectionState>(
    connection.baseUrl && connection.runId && connection.token
      ? { kind: "loading", message: "正在连接 Runtime" }
      : { kind: "demo", message: "演示数据" },
  );
  const [runtimeEvents, setRuntimeEvents] = useState<RuntimeEvent[]>([]);
  const [humanRequests, setHumanRequests] = useState<RuntimeHumanRequest[]>([]);
  const [artifacts, setArtifacts] = useState<RuntimeArtifact[]>([]);
  const [decisionComment, setDecisionComment] = useState("");
  const [decisionValues, setDecisionValues] = useState<Record<string, string>>({});
  const [decisionState, setDecisionState] = useState<DecisionState>({
    kind: "idle",
    message: "",
  });
  const [controlState, setControlState] = useState<ControlState>({
    kind: "idle",
    message: "",
  });
  const [artifactPreview, setArtifactPreview] = useState<ArtifactPreviewState>({
    artifactId: null,
    kind: "idle",
  });
  const [invocationDetail, setInvocationDetail] = useState<InvocationDetailState>({
    kind: "idle",
  });
  const [lastEventSeq, setLastEventSeq] = useState(0);
  const viewportRef = useRef<HTMLDivElement>(null);
  const snapshotInputRef = useRef<HTMLInputElement>(null);
  const runtimeControllerRef = useRef<AbortController | null>(null);
  const fitCanvasRequestedRef = useRef(true);
  const fitCanvasRef = useRef<() => void>(() => undefined);
  const nodePositionsRef = useRef(nodePositions);
  nodePositionsRef.current = nodePositions;
  const visible = useMemo(
    () => visibleGraph(graph, collapsedGroups),
    [graph, collapsedGroups],
  );
  const renderedNodes = useMemo(
    () =>
      visible.nodes.map((node) => ({
        ...node,
        ...(nodePositions[node.id] ?? {}),
      })),
    [nodePositions, visible.nodes],
  );
  const selectedNode =
    renderedNodes.find((node) => node.id === selectedId) ??
    graph.nodes.find((node) => node.id === selectedId) ??
    renderedNodes[0];
  const selectedHumanRequest = humanRequests.find(
    (request) => request.invocationId === selectedNode?.invocationId,
  );
  const pendingHumanRequestCount = humanRequests.filter(
    (request) => request.status === "pending",
  ).length;

  useEffect(() => {
    setDecisionComment("");
    setDecisionValues({});
    setDecisionState({ kind: "idle", message: "" });
  }, [selectedHumanRequest?.id]);

  useEffect(() => {
    const invocationId = selectedNode?.invocationId;
    if (
      !invocationId ||
      !connectionEnabled ||
      !connection.baseUrl ||
      !connection.namespace ||
      !connection.runId ||
      !connection.token
    ) {
      setInvocationDetail({ kind: "idle" });
      return;
    }
    const controller = new AbortController();
    setInvocationDetail({ kind: "loading" });
    new RuntimeClient(connection).getInvocation(invocationId, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setInvocationDetail({ kind: "loaded", value });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setInvocationDetail({
          kind: "error",
          message: error instanceof Error ? error.message : "节点详情读取失败",
        });
      });
    return () => controller.abort();
  }, [
    selectedNode?.invocationId,
    selectedNode?.status,
    connectionEnabled,
    connection.baseUrl,
    connection.namespace,
    connection.runId,
    connection.token,
  ]);

  useEffect(() => {
    if (
      !connectionEnabled ||
      !connection.baseUrl ||
      !connection.namespace ||
      !connection.runId ||
      !connection.token
    ) {
      return;
    }
    const client = new RuntimeClient(connection as RuntimeClientConfig);
    const controller = new AbortController();
    runtimeControllerRef.current = controller;
    setConnectionState({ kind: "loading", message: "正在读取 Runtime 快照" });
    client
      .getGraph(controller.signal)
      .then((projection) => {
        if (controller.signal.aborted) return;
        const nextGraph = mapRuntimeProjection(projection);
        const projectionCursor = projection.events.at(-1)?.seq ?? 0;
        fitCanvasRequestedRef.current = true;
        setGraph(nextGraph);
        setSourceLabel(`Runtime · ${projection.run.workflowId}`);
        setRuntimeEvents(projection.events);
        setHumanRequests(projection.humanRequests);
        setArtifacts(projection.artifacts);
        setLastEventSeq(projectionCursor);
        setCollapsedGroups(new Set(nextGraph.groups.map((group) => group.id)));
        setSelectedId(nextGraph.nodes[0]?.id ?? nextGraph.groups[0]?.id ?? "");
        setImportState({ kind: "success", message: "Runtime 快照" });
        return client
          .listHumanRequests(controller.signal)
          .then((result) => {
            setHumanRequests((current) => mergeHumanRequests(current, result.requests));
            return projectionCursor;
          })
          .catch(() => projectionCursor);
      })
      .then((projectionCursor) =>
        projectionCursor === undefined || controller.signal.aborted
          ? undefined
          : client.watchRun({
          after: projectionCursor,
          signal: controller.signal,
          onSnapshot: (projection) => {
            if (controller.signal.aborted) return;
            const nextGraph = mapRuntimeProjection(projection);
            setGraph((current) => ({
              ...nextGraph,
              ...preserveGraphPositions(current, nextGraph, nodePositionsRef.current),
            }));
            setHumanRequests((current) =>
              mergeHumanRequests(current, projection.humanRequests),
            );
            setArtifacts(projection.artifacts);
            setLastEventSeq(projection.events.at(-1)?.seq ?? 0);
          },
          onEvent: (event) => {
            if (controller.signal.aborted) return;
            setRuntimeEvents((current) => mergeEvents(current, event));
            setLastEventSeq((current) => Math.max(current, event.seq));
          },
          onStatus: (status) => {
            if (!controller.signal.aborted) setConnectionState(connectionStateFor(status));
          },
        }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setConnectionState({
          kind: "error",
          message: error instanceof Error ? error.message : "Runtime 连接失败",
        });
      });
    return () => {
      controller.abort();
      if (runtimeControllerRef.current === controller) runtimeControllerRef.current = null;
    };
  }, [
    connectionEnabled,
    connection.baseUrl,
    connection.namespace,
    connection.runId,
    connection.token,
  ]);

  function toggleGroup(groupId: string) {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  function connectRuntime(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setConnectionEnabled(true);
    setConnection(connectionDraft);
    persistRuntimeConnection(connectionDraft);
    setShowConnection(false);
  }

  function openWorkflow(scopeId?: string) {
    const target = scopeId
      ? renderedNodes.find((node) => node.id === scopeId)
      : renderedNodes.find((node) => node.id === graph.groups[0]?.id);
    if (!target) return;
    setPanelMode("audit");
    setSelectedId(target.id);
    if (target.type === "group") setCollapsedGroups((current) => {
      const next = new Set(current);
      next.delete(target.id);
      return next;
    });
  }

  function openCurrentRun() {
    const activeNode = graph.nodes.find((node) => node.id === graph.currentNodeId) ??
      graph.nodes.find(
      (node) => node.status === "running" || node.status === "waiting",
    );
    if (!activeNode) {
      openWorkflow();
      return;
    }
    setPanelMode("audit");
    expandGroupPath(activeNode.groupId);
    focusNode(activeNode);
  }

  function openHumanInbox() {
    const request = humanRequests.find((item) => item.status === "pending");
    const node = request
      ? graph.nodes.find((item) => item.invocationId === request.invocationId)
      : graph.nodes.find(
        (item) => item.execution?.participantType === "human",
      );
    if (!node) return;
    setPanelMode("audit");
    expandGroupPath(node.groupId);
    focusNode(node);
  }

  function expandGroupPath(groupId?: string) {
    if (!groupId) return;
    const ancestorIds = new Set<string>();
    let current = graph.groups.find((group) => group.id === groupId);
    while (current) {
      ancestorIds.add(current.id);
      current = current.parentId
        ? graph.groups.find((group) => group.id === current?.parentId)
        : undefined;
    }
    setCollapsedGroups((currentGroups) =>
      new Set([...currentGroups].filter((id) => !ancestorIds.has(id))),
    );
  }

  async function submitHumanDecision(choice?: string) {
    if (
      !selectedHumanRequest ||
      selectedHumanRequest.status !== "pending" ||
      !connection.baseUrl ||
      !connection.namespace ||
      !connection.runId ||
      !connection.token
    ) {
      return;
    }
    let payload: HumanDecisionPayload;
    if (selectedHumanRequest.requestType === "input") {
      const fields = getHumanInputFields(selectedHumanRequest.decisionSchema);
      if (!fields) {
        setDecisionState({
          kind: "error",
          message: "当前结果 Schema 暂不支持表单填写，已阻止提交",
        });
        return;
      }
      const allowedValues = Object.fromEntries(
        fields
          .filter(isArtifactReferenceField)
          .map((field) => [
            field.name,
            artifacts
              .filter((artifact) => artifact.status === "ready")
              .map((artifact) => artifact.id),
          ]),
      );
      const result = buildHumanInputDecision(fields, decisionValues, { allowedValues });
      if (!result.decision) {
        setDecisionState({
          kind: "error",
          message: result.errors.join("；"),
        });
        return;
      }
      payload = {
        expectedVersion: selectedHumanRequest.version,
        subjectDigest: selectedHumanRequest.subjectDigest,
        decision: result.decision,
        comment: decisionComment,
      };
    } else {
      if (!choice) return;
      payload = {
        expectedVersion: selectedHumanRequest.version,
        subjectDigest: selectedHumanRequest.subjectDigest,
        choice,
        comment: decisionComment,
      };
    }
    const idempotencyKey = createHumanDecisionIdempotencyKey(
      selectedHumanRequest.id,
      selectedHumanRequest.version,
      payload,
    );
    setDecisionState({ kind: "submitting", message: "正在提交人工决定" });
    try {
      const client = new RuntimeClient(connection);
      const receipt: RuntimeCommandReceipt = await client.submitHumanDecision(
        selectedHumanRequest.id,
        payload,
        idempotencyKey,
      );
      setDecisionState({
        kind: "success",
        message: `已提交，等待 Runtime 确认（${receipt.status}）`,
      });
    } catch (error) {
      setDecisionState({
        kind: "error",
        message: error instanceof Error ? error.message : "人工决定提交失败",
      });
    }
  }

  async function submitControl(operation: "pause" | "resume" | "cancel") {
    if (
      controlState.kind === "submitting" ||
      !connection.baseUrl ||
      !connection.namespace ||
      !connection.runId ||
      !connection.token
    ) {
      return;
    }
    const labels = { pause: "暂停派发", resume: "恢复派发", cancel: "停止运行" };
    const reason = `从 Inspector 请求${labels[operation]}。`;
    setControlState({ kind: "submitting", message: "命令已提交，等待 Runtime 确认" });
    try {
      const client = new RuntimeClient(connection);
      const receipt = await client.controlRun(
        operation,
        { expectedVersion: graph.runVersion, reason },
        `inspector-run-${operation}-${graph.runVersion}`,
      );
      setControlState({
        kind: "success",
        message: `已请求${labels[operation]}，等待事实状态更新（${receipt.status}）`,
      });
    } catch (error) {
      setControlState({
        kind: "error",
        message: error instanceof Error ? error.message : "运行控制提交失败",
      });
    }
  }

  async function previewArtifact(artifact: RuntimeArtifact) {
    if (
      !connection.baseUrl ||
      !connection.namespace ||
      !connection.runId ||
      !connection.token
    ) {
      return;
    }
    setArtifactPreview({ artifactId: artifact.id, kind: "loading" });
    try {
      const response = await new RuntimeClient(connection).getArtifactContent(artifact.id);
      const mediaType = response.headers.get("content-type")?.split(";")[0] ?? artifact.mediaType;
      const previewable =
        mediaType.startsWith("text/") ||
        mediaType === "application/json" ||
        mediaType === "application/xml" ||
        mediaType === "application/yaml";
      if (!previewable) {
        await response.arrayBuffer();
        setArtifactPreview({
          artifactId: artifact.id,
          kind: "binary",
          mediaType,
          message: "该产物是二进制内容，Inspector 不直接执行或内嵌展示。",
        });
        return;
      }
      setArtifactPreview({
        artifactId: artifact.id,
        kind: "text",
        mediaType,
        text: await response.text(),
      });
    } catch (error) {
      setArtifactPreview({
        artifactId: artifact.id,
        kind: "error",
        message: error instanceof Error ? error.message : "产物读取失败",
      });
    }
  }

  function focusNode(node: GraphNode) {
    setSelectedId(node.id);
    const viewport = viewportRef.current;
    if (!viewport) return;
    const position = resolveGraphPosition(node, nodePositionsRef.current);
    const centerX = viewport.clientWidth / 2 - (position.x + node.width / 2) * zoom;
    const centerY = viewport.clientHeight / 2 - (position.y + node.height / 2) * zoom;
    setPan({ x: centerX, y: centerY });
  }

  function fitCanvas() {
    const viewport = viewportRef.current;
    if (!viewport) return;
    if (viewport.clientWidth <= 760) {
      const focus =
        graph.nodes.find((node) => node.id === graph.currentNodeId) ??
        graph.nodes.find((node) => node.id === selectedId) ??
        renderedNodes[0];
      if (!focus) return;
      if (focus.groupId) {
        setCollapsedGroups((current) => {
          if (!current.has(focus.groupId!)) return current;
          const next = new Set(current);
          next.delete(focus.groupId!);
          return next;
        });
      }
      const position = resolveGraphPosition(focus, nodePositionsRef.current);
      const mobileZoom = 0.72;
      setZoom(mobileZoom);
      setPan({
        x: Math.round(viewport.clientWidth / 2 - (position.x + focus.width / 2) * mobileZoom),
        y: Math.round(viewport.clientHeight / 2 - (position.y + focus.height / 2) * mobileZoom),
      });
      return;
    }
    const fit = fitGraphToViewport(renderedNodes, {
      width: viewport.clientWidth,
      height: viewport.clientHeight,
    });
    if (!fit) return;
    setZoom(fit.zoom);
    setPan(fit.pan);
  }

  function fitCanvasToViewport() {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const fit = fitGraphToViewport(
      renderedNodes,
      { width: viewport.clientWidth, height: viewport.clientHeight },
      24,
    );
    if (!fit) return;
    setZoom(fit.zoom);
    setPan(fit.pan);
  }

  fitCanvasRef.current = fitCanvas;

  useEffect(() => {
    if (!fitCanvasRequestedRef.current) return;
    fitCanvasRequestedRef.current = false;
    fitCanvas();
  }, [renderedNodes]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => fitCanvasRef.current());
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  function applyPatchText(nextText = patchText) {
    try {
      const patch = JSON.parse(nextText) as AgentPatch;
      const result = applyAgentPatch(graph, patch);
      if (!result.ok) {
        setPatchState({ kind: "error", message: result.error });
        return;
      }
      setGraph(result.graph);
      setSelectedId(patch.nodeId);
      setPatchState({ kind: "success", message: "预览已根据智能体补丁更新" });
      setAgentEvents((events) => [
        `已将作用域补丁应用到 ${patch.nodeId}`,
        ...events,
      ]);
    } catch {
      setPatchState({ kind: "error", message: "补丁必须是有效 JSON" });
    }
  }

  function simulateAgentUpdate() {
    const patch: AgentPatch = {
      nodeId: "refine",
      title: "细化交付物",
      status: graph.nodes.find((node) => node.id === "refine")?.status === "running"
        ? "succeeded"
        : "running",
      detail: "智能体预览已修改此节点，但没有改变其领域身份。",
    };
    const nextText = JSON.stringify(patch, null, 2);
    setPatchText(nextText);
    applyPatchText(nextText);
  }

  async function importSnapshot(event: React.ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;

    setImportState({ kind: "reading", message: "读取中" });
    try {
      const raw = JSON.parse(await file.text()) as unknown;
      let viewSnapshot: RuntimeViewSnapshot | undefined;
      let projection: RuntimeProjection | undefined;
      if (
        typeof raw === "object" &&
        raw !== null &&
        !Array.isArray(raw) &&
        "format" in raw &&
        raw.format === "multiverse-view/v0.1"
      ) {
        viewSnapshot = parseRuntimeViewSnapshot(raw);
      } else {
        projection = parseRuntimeProjection(raw);
      }
      const nextGraph = viewSnapshot?.graph ?? mapRuntimeProjection(projection!);
      runtimeControllerRef.current?.abort();
      runtimeControllerRef.current = null;
      setConnectionEnabled(false);
      setConnectionState({ kind: "demo", message: "本地快照" });
      clearRuntimeConnection();
      fitCanvasRequestedRef.current = true;
      setGraph(nextGraph);
      const events = viewSnapshot?.events ?? projection!.events;
      setRuntimeEvents(events);
      setHumanRequests(viewSnapshot?.humanRequests ?? projection!.humanRequests);
      setArtifacts(viewSnapshot?.artifacts ?? projection!.artifacts);
      setLastEventSeq(events.at(-1)?.seq ?? 0);
      setCollapsedGroups(new Set(nextGraph.groups.map((group) => group.id)));
      setSelectedId(nextGraph.groups[0]?.id ?? nextGraph.nodes[0]?.id ?? "");
      setPanelMode("audit");
      setZoom(0.84);
      setPan({ x: 24, y: 28 });
      setNodePositions(viewSnapshot?.layout ?? {});
      setNodeDrag(null);
      setImportState({ kind: "success", message: file.name });
      setSourceLabel(file.name);
    } catch (error) {
      setImportState({
        kind: "error",
        message: error instanceof Error ? error.message : "快照读取失败",
      });
    } finally {
      input.value = "";
    }
  }

  function exportCurrentView() {
    const payload = {
      format: "multiverse-view/v0.1",
      exportedAt: new Date().toISOString(),
      workflow: {
        name: graph.packageName,
        version: graph.packageVersion,
        runId: graph.runId,
      },
      graph,
      layout: nodePositions,
      events: runtimeEvents,
      humanRequests,
      artifacts,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${graph.packageName || "workflow"}-view.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setImportState({ kind: "success", message: "当前工作流视图已导出" });
  }

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest("button")) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStart({ x: event.clientX - pan.x, y: event.clientY - pan.y });
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (nodeDrag) {
      const delta = {
        x: (event.clientX - nodeDrag.pointer.x) / zoom,
        y: (event.clientY - nodeDrag.pointer.y) / zoom,
      };
      if (Math.abs(delta.x) > 2 || Math.abs(delta.y) > 2) {
        nodeMovedRef.current = true;
      }
      setNodePositions((current) => ({
        ...current,
        ...translatePositions(nodeDrag.starts, nodeDrag.ids, delta),
      }));
      return;
    }
    if (!dragStart) return;
    setPan({ x: event.clientX - dragStart.x, y: event.clientY - dragStart.y });
  }

  function onPointerUp() {
    setDragStart(null);
    setNodeDrag(null);
  }

  function positionFor(id: string): GraphPosition {
    const stored = nodePositions[id];
    if (stored) return stored;
    const graphItem =
      graph.nodes.find((node) => node.id === id) ??
      graph.groups.find((group) => group.id === id);
    return graphItem ? { x: graphItem.x, y: graphItem.y } : { x: 0, y: 0 };
  }

  function startNodeDrag(
    event: React.PointerEvent<HTMLButtonElement>,
    node: GraphNode,
  ) {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    nodeMovedRef.current = false;
    const memberIds = graph.groups.find((group) => group.id === node.id)?.memberIds ?? [];
    const ids = node.type === "group" ? [node.id, ...memberIds] : [node.id];
    setNodeDrag({
      ids,
      pointer: { x: event.clientX, y: event.clientY },
      starts: Object.fromEntries(ids.map((id) => [id, positionFor(id)])),
    });
  }

  function onWheel(event: React.WheelEvent<HTMLDivElement>) {
    setZoom((value) => Math.min(1.24, Math.max(0.05, value - event.deltaY * 0.0008)));
  }

  const nodeMap = new Map(renderedNodes.map((node) => [node.id, node]));
  const canvasWidth = Math.max(920, ...renderedNodes.map((node) => node.x + node.width + 80));
  const canvasHeight = Math.max(650, ...renderedNodes.map((node) => node.y + node.height + 80));

  return (
    <main className="app-shell">
      <header className="topbar">
        <input
          ref={snapshotInputRef}
          className="visually-hidden"
          type="file"
          accept=".json,application/json"
          onChange={importSnapshot}
        />
        <div className="brand-lockup">
          <div className="brand-mark"><Workflow size={18} strokeWidth={2.5} /></div>
          <div>
            <strong>Multiverse</strong>
            <span>工作流工作台</span>
          </div>
        </div>
        <div className="workflow-identity">
          <div className="workflow-title">
            <strong>{graph.packageName}</strong>
            <span>v{graph.packageVersion}</span>
          </div>
          <span className="workflow-source">{sourceLabel}</span>
        </div>
        <div className="topbar-actions">
          <div className="live-state">
            <span className={`live-dot ${connectionState.kind}`} /> {connectionState.message}
          </div>
          <button
            className="topbar-button"
            onClick={() => snapshotInputRef.current?.click()}
            title="导入 Runtime 运行快照 JSON"
          >
            <Upload size={15} /> 导入快照
          </button>
          <button className="topbar-button" onClick={exportCurrentView}>
            <Download size={15} /> 导出视图
          </button>
          <button
            className="icon-button"
            title="连接 Runtime"
            aria-label="连接 Runtime"
            onClick={() => {
              setConnectionDraft(connection);
              setShowConnection(true);
            }}
          >
            <SquareDashedMousePointer size={17} />
          </button>
        </div>
      </header>

      <div className="workspace">
        <section className="main-stage">
          <div className="stage-header">
            <div>
              <div className="stage-kicker">当前工作流</div>
              <h1>{graph.packageName}</h1>
              <p className="stage-description">查看流程结构、运行证据、人工任务与交付结果。</p>
              <div className="run-summary">
                <span><StatusIcon status={statusForRun(graph.runStatus)} />{statusLabels[statusForRun(graph.runStatus)]}</span>
                <code>{graph.runId}</code>
                <span>事件 {lastEventSeq || graph.lastEventSeq}</span>
                {pendingHumanRequestCount > 0 && (
                  <span className="pending-count"><UserRound size={13} />待处理 {pendingHumanRequestCount}</span>
                )}
              </div>
            </div>
            <div className="stage-actions">
              {pendingHumanRequestCount > 0 && (
                <button className="text-action review-action" onClick={openHumanInbox}>
                  <UserRound size={15} /> 处理人工任务 <span>{pendingHumanRequestCount}</span>
                </button>
              )}
              {connectionState.kind !== "demo" && graph.controlMode === "pause" && (
                <button
                  aria-label="恢复派发"
                  className="text-action"
                  title="恢复派发"
                  onClick={() => submitControl("resume")}
                  disabled={controlState.kind === "submitting"}
                >
                  <Play size={15} /> 恢复
                </button>
              )}
              {connectionState.kind !== "demo" &&
                graph.controlMode === "run" &&
                !["succeeded", "failed", "cancelled"].includes(graph.runStatus) && (
                  <button
                    aria-label="暂停派发"
                  className="text-action"
                    title="暂停派发"
                    onClick={() => submitControl("pause")}
                    disabled={controlState.kind === "submitting"}
                  >
                    <PauseCircle size={15} /> 暂停
                  </button>
                )}
              {connectionState.kind !== "demo" &&
                graph.controlMode !== "cancel" &&
                !["succeeded", "failed", "cancelled"].includes(graph.runStatus) && (
                  <button
                    aria-label="停止运行"
                    className="text-action danger-action"
                    title="停止运行"
                    onClick={() => submitControl("cancel")}
                    disabled={controlState.kind === "submitting"}
                  >
                    <Square size={15} /> 停止
                  </button>
                )}
              <button
                aria-label={collapsedGroups.size ? "展开全部作用域" : "折叠全部作用域"}
                className="icon-button action-button"
                title={collapsedGroups.size ? "展开全部作用域" : "折叠全部作用域"}
                onClick={() =>
                  setCollapsedGroups(
                    collapsedGroups.size ? new Set() : new Set(graph.groups.map((group) => group.id)),
                  )
                }
              >
                <Layers3 size={16} />
              </button>
            </div>
          </div>
          {importState.kind === "error" && (
            <div className="snapshot-error" role="alert">
              <AlertCircle size={15} /> {importState.message}
            </div>
          )}
          {controlState.message && (
            <div className={`control-state ${controlState.kind}`} role="status">
              <span className="state-indicator" /> {controlState.message}
            </div>
          )}

          <div className="canvas-toolbar">
            <div className="canvas-controls">
              <button className="icon-button small" title="缩小" onClick={() => setZoom((value) => Math.max(0.05, value - 0.1))}><Minus size={15} /></button>
              <span className="zoom-readout">{Math.round(zoom * 100)}%</span>
              <button className="icon-button small" title="放大" onClick={() => setZoom((value) => Math.min(1.24, value + 0.1))}><Plus size={15} /></button>
              <button className="icon-button small" title="适配全图" aria-label="适配全图" onClick={fitCanvasToViewport}><Maximize2 size={15} /></button>
              <button className="icon-button small" title="恢复自动布局" onClick={() => setNodePositions({})}><RotateCcw size={14} /></button>
            </div>
          </div>

          <div
            className={`graph-viewport ${dragStart ? "dragging" : ""} ${nodeDrag ? "node-moving" : ""}`}
            ref={viewportRef}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onWheel={onWheel}
          >
            <div
              className="graph-world"
              style={{
                width: canvasWidth,
                height: canvasHeight,
                transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              }}
            >
              <svg
                className="edge-layer"
                viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
                style={{ width: canvasWidth, height: canvasHeight }}
                aria-hidden="true"
              >
                <defs>
                  <marker id="arrow-data" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#9ca39f" /></marker>
                  <marker id="arrow-active" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#36aab0" /></marker>
                </defs>
                {visible.edges.map((edge) => {
                  const from = nodeMap.get(edge.from);
                  const to = nodeMap.get(edge.to);
                  if (!from || !to) return null;
                  const route = routeGraphEdge(from, to);
                  const active = from.status === "running" || to.status === "running";
                  const related = edge.from === selectedId || edge.to === selectedId;
                  return (
                    <g key={edge.id} className={`edge-group ${route.direction} ${active ? "active" : ""} ${related ? "related" : ""}`}>
                      <path d={route.path} markerEnd={`url(#arrow-${active ? "active" : "data"})`} />
                      {edge.label && <text x={(from.x + from.width / 2 + to.x + to.width / 2) / 2} y={(from.y + from.height / 2 + to.y + to.height / 2) / 2 - 9}>{edge.label}</text>}
                    </g>
                  );
                })}
              </svg>
              {renderedNodes.filter((node) => node.type === "group").map((node) => {
                const isCollapsed = collapsedGroups.has(node.id);
                return (
                  <button
                    key={node.id}
                    className={`scope-card ${isCollapsed ? "collapsed" : "expanded"}`}
                    style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
                    onPointerDown={(event) => startNodeDrag(event, node)}
                    onClick={() => {
                      if (nodeMovedRef.current) {
                        nodeMovedRef.current = false;
                        return;
                      }
                      toggleGroup(node.id);
                    }}
                  >
                    <span className="scope-head"><span><Layers3 size={14} /> {node.title}</span>{isCollapsed ? <ChevronRight size={15} /> : <ChevronDown size={15} />}</span>
                    <span className="scope-subtitle">{node.subtitle}</span>
                    {isCollapsed && <span className="scope-state"><StatusIcon status={node.status} /> {statusLabels[node.status]}</span>}
                  </button>
                );
              })}
              {renderedNodes.filter((node) => node.type !== "group").map((node) => (
                <NodeCard
                  key={node.id}
                  node={node}
                  selected={selectedId === node.id}
                  hasIncoming={visible.edges.some((edge) => edge.to === node.id)}
                  hasOutgoing={visible.edges.some((edge) => edge.from === node.id)}
                  verticalIncoming={visible.edges.some((edge) => {
                    const from = nodeMap.get(edge.from);
                    return edge.to === node.id && !!from && routeGraphEdge(from, node).direction === "vertical";
                  })}
                  verticalOutgoing={visible.edges.some((edge) => {
                    const to = nodeMap.get(edge.to);
                    return edge.from === node.id && !!to && routeGraphEdge(node, to).direction === "vertical";
                  })}
                  onClick={() => setSelectedId(node.id)}
                  onPointerDown={(event) => startNodeDrag(event, node)}
                />
              ))}
            </div>
          </div>

          <div className="timeline">
            <div className="timeline-heading">
              <span><Clock3 size={15} /> 最近证据</span>
              <button className="timeline-link" onClick={openCurrentRun}>查看当前运行</button>
            </div>
            <div className="timeline-track">
              {(runtimeEvents.length ? runtimeEvents.slice(-3) : demoTimeline).map((event) => (
                <TimelineEvent
                  key={typeof event === "string" ? event : event.seq}
                  time={typeof event === "string" ? "—" : formatEventTime(event.occurredAt)}
                  title={typeof event === "string" ? event : event.type}
                  tone={typeof event === "string" ? "muted" : eventTone(event.type)}
                />
              ))}
            </div>
          </div>
        </section>

        <aside className="inspector-panel">
          <div className="panel-tabs">
            <button className={panelMode === "audit" ? "selected" : ""} onClick={() => setPanelMode("audit")}><ShieldCheck size={15} /> 审计</button>
            <button className={panelMode === "agent" ? "selected" : ""} onClick={() => setPanelMode("agent")}><Code2 size={15} /> 智能体编辑</button>
          </div>
          {panelMode === "audit" ? (
            selectedNode && (
              <AuditPanel
                node={selectedNode}
                humanRequest={selectedHumanRequest}
                invocationDetail={invocationDetail}
                decisionComment={decisionComment}
                setDecisionComment={setDecisionComment}
                decisionValues={decisionValues}
                setDecisionValue={(name, value) =>
                  setDecisionValues((current) => ({ ...current, [name]: value }))
                }
                artifacts={artifacts}
                artifactPreview={artifactPreview}
                onPreviewArtifact={previewArtifact}
                decisionState={decisionState}
                onDecision={submitHumanDecision}
                onFocus={() => focusNode(selectedNode)}
              />
            )
          ) : (
            <AgentPanel
              patchText={patchText}
              setPatchText={setPatchText}
              patchState={patchState}
              onApply={() => applyPatchText()}
              onSimulate={simulateAgentUpdate}
              events={agentEvents}
            />
          )}
        </aside>
      </div>
      {showConnection && (
        <div className="connection-backdrop" role="presentation" onMouseDown={() => setShowConnection(false)}>
          <form className="connection-dialog" onSubmit={connectRuntime} onMouseDown={(event) => event.stopPropagation()}>
            <div className="panel-heading">
              <div>
                <h2>连接 Runtime</h2>
              <p>令牌只保留在当前浏览器会话内，不写入 URL 或持久本地存储。</p>
              </div>
              <button type="button" className="icon-button small" title="关闭" onClick={() => setShowConnection(false)}>×</button>
            </div>
            <label className="field-label" htmlFor="runtime-base-url">服务地址</label>
            <input id="runtime-base-url" value={connectionDraft.baseUrl} onChange={(event) => setConnectionDraft({ ...connectionDraft, baseUrl: event.target.value })} placeholder="http://127.0.0.1:8080" />
            <div className="connection-grid">
              <div>
                <label className="field-label" htmlFor="runtime-namespace">命名空间</label>
                <input id="runtime-namespace" value={connectionDraft.namespace} onChange={(event) => setConnectionDraft({ ...connectionDraft, namespace: event.target.value })} />
              </div>
              <div>
                <label className="field-label" htmlFor="runtime-run-id">运行 ID</label>
                <input id="runtime-run-id" value={connectionDraft.runId} onChange={(event) => setConnectionDraft({ ...connectionDraft, runId: event.target.value })} />
              </div>
            </div>
            <label className="field-label" htmlFor="runtime-token">Bearer 令牌</label>
            <input id="runtime-token" type="password" value={connectionDraft.token} onChange={(event) => setConnectionDraft({ ...connectionDraft, token: event.target.value })} autoComplete="off" />
            <div className="connection-actions">
              <button type="button" className="icon-button" title="取消" onClick={() => setShowConnection(false)}>×</button>
              <button type="submit" className="apply-button">连接并查看</button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}

function NodeCard({
  node,
  selected,
  hasIncoming,
  hasOutgoing,
  verticalIncoming,
  verticalOutgoing,
  onClick,
  onPointerDown,
}: {
  node: GraphNode;
  selected: boolean;
  hasIncoming: boolean;
  hasOutgoing: boolean;
  verticalIncoming: boolean;
  verticalOutgoing: boolean;
  onClick: () => void;
  onPointerDown: (event: React.PointerEvent<HTMLButtonElement>) => void;
}) {
  const execution = node.execution;
  const category = execution
    ? participantLabels[execution.participantType]
    : nodeTypeLabels[node.type];
  const Icon = execution?.participantType === "human"
    ? UserRound
    : execution?.participantType === "agent"
      ? Activity
      : execution?.participantType === "external_service"
        ? SquareDashedMousePointer
        : node.type === "input"
          ? FileText
          : node.type === "end"
            ? Check
            : node.type === "switch"
              ? GitBranch
              : node.type === "repeat"
                ? RotateCcw
                : node.type === "parallel"
                  ? Layers3
                  : node.type === "workflow"
                    ? Workflow
                    : Code2;
  return (
    <button
      className={`node-card ${selected ? "selected" : ""} status-${node.status} ${hasIncoming ? "has-incoming" : ""} ${hasOutgoing ? "has-outgoing" : ""} ${verticalIncoming ? "has-incoming-vertical" : ""} ${verticalOutgoing ? "has-outgoing-vertical" : ""}`}
      style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
      onClick={onClick}
      onPointerDown={onPointerDown}
    >
      <span className="node-topline">
        <span className={`node-type participant-${execution?.participantType ?? node.type}`}>
          <Icon size={14} /> {category}
        </span>
        <span className={`node-state-text ${node.status}`}>
          <StatusIcon status={node.status} />
          {statusLabels[node.status]}
        </span>
      </span>
      <strong>{node.title}</strong>
      <span className="node-target">
        {execution
          ? `${executionLocationLabels[execution.location]} · ${execution.target}`
          : node.type === "call"
            ? "Binding 未核实"
            : structureNodeSummary(node)}
      </span>
      <span className="node-io-summary">
        <span><small>入</small>{node.input}</span>
        <span><small>出</small>{node.output}</span>
      </span>
    </button>
  );
}

function AuditPanel({
  node,
  humanRequest,
  invocationDetail,
  decisionComment,
  setDecisionComment,
  decisionValues,
  setDecisionValue,
  artifacts,
  artifactPreview,
  onPreviewArtifact,
  decisionState,
  onDecision,
  onFocus,
}: {
  node: GraphNode;
  humanRequest?: RuntimeHumanRequest;
  invocationDetail: InvocationDetailState;
  decisionComment: string;
  setDecisionComment: (value: string) => void;
  decisionValues: Record<string, string>;
  setDecisionValue: (name: string, value: string) => void;
  artifacts: RuntimeArtifact[];
  artifactPreview: ArtifactPreviewState;
  onPreviewArtifact: (artifact: RuntimeArtifact) => void;
  decisionState: DecisionState;
  onDecision: (choice?: string) => void;
  onFocus: () => void;
}) {
  const execution = node.execution;
  const detail = invocationDetail.kind === "loaded" ? invocationDetail.value : undefined;
  const actor = execution
    ? `${participantLabels[execution.participantType]} · ${executionLocationLabels[execution.location]}`
    : nodeTypeLabels[node.type];
  return (
    <div className="panel-content">
      <div className="panel-heading">
        <div><h2>{node.title}</h2><p>{node.detail}</p></div>
        <button className="icon-button small" title="聚焦节点" onClick={onFocus}><Maximize2 size={15} /></button>
      </div>
      <div className="audit-status">
        <StatusIcon status={node.status} />
        <div>
          <span>{actor}</span>
          <strong>{node.waitingReason ?? statusLabels[node.status]}</strong>
        </div>
      </div>
      {node.type !== "group" && (
      <details className="info-disclosure" open>
        <summary>本次输入与输出</summary>
        {invocationDetail.kind === "loading" && <p className="detail-load-state">正在读取节点执行详情</p>}
        {invocationDetail.kind === "error" && (
          <div className="detail-load-error" role="alert">{invocationDetail.message}</div>
        )}
        <div className="invocation-io">
          <div>
            <span className="detail-label">输入</span>
            <strong>{node.input}</strong>
            {detail && <details className="payload-disclosure"><summary>查看实际输入</summary><pre>{formatJson(detail.input)}</pre></details>}
          </div>
          <div>
            <span className="detail-label">输出</span>
            <strong>{node.output}</strong>
            {detail && <details className="payload-disclosure"><summary>查看实际输出</summary><pre>{formatJson(detail.output)}</pre></details>}
          </div>
        </div>
      </details>
      )}
      {(node.dataSources?.length || node.dataTargets?.length) ? (
        <details className="info-disclosure">
          <summary>数据交接</summary>
          <div className="data-flow-facts">
            <div>
              <span className="detail-label">数据来源</span>
              <span>{node.dataSources?.length ? node.dataSources.join(" · ") : "无显式上游引用"}</span>
            </div>
            <div>
              <span className="detail-label">下游使用</span>
              <span>{node.dataTargets?.length ? node.dataTargets.join(" · ") : "暂无显式下游引用"}</span>
            </div>
          </div>
        </details>
      ) : null}
      {execution && (
        <details className="info-disclosure">
          <summary>执行信息</summary>
          <div className="execution-facts">
            <div><span className="detail-label">执行器</span><strong>{execution.executorRef ?? "未核实"}</strong></div>
            <div><span className="detail-label">接入方式</span><strong>{execution.adapter ?? "未核实"}</strong></div>
            {execution.model && <div><span className="detail-label">模型</span><strong>{execution.model}</strong></div>}
            {execution.workspace && <div><span className="detail-label">工作区</span><strong>{execution.workspace}</strong></div>}
            {detail && <div><span className="detail-label">Invocation</span><code>{detail.id}</code></div>}
          </div>
          {detail && detail.attempts.length > 0 && (
            <div className="attempt-list">
              <span className="detail-label">尝试记录</span>
              {detail.attempts.map((attempt) => (
                <details className="attempt-row" key={attempt.id}>
                  <summary>
                    第 {attempt.attemptNo} 次 · {statusLabels[statusForRun(attempt.status)]}
                  </summary>
                  <div className="attempt-facts">
                    <span>{formatEventTime(attempt.createdAt)}</span>
                    {attempt.externalRef && <code>外部引用：{attempt.externalRef}</code>}
                    {attempt.error != null && <pre>{formatJson(attempt.error)}</pre>}
                  </div>
                </details>
              ))}
            </div>
          )}
          {detail?.error != null && (
            <div className="detail-load-error">错误：{formatJson(detail.error)}</div>
          )}
        </details>
      )}
      {node.evidence.length > 0 && (
        <details className="info-disclosure">
          <summary>审计证据 · {node.evidence.length}</summary>
          <div className="evidence-list">
            {node.evidence.map((item) => <div className="evidence-row" key={item}><Check size={14} /> {item}</div>)}
          </div>
        </details>
      )}
      <ArtifactList
        artifacts={artifactsForNode(node, artifacts)}
        preview={artifactPreview}
        onPreview={onPreviewArtifact}
      />
      {humanRequest && (
        <HumanRequestPanel
          request={humanRequest}
          comment={decisionComment}
          setComment={setDecisionComment}
          values={decisionValues}
          setValue={setDecisionValue}
          artifacts={artifacts}
          state={decisionState}
          onDecision={onDecision}
        />
      )}
    </div>
  );
}

function ArtifactList({
  artifacts,
  preview,
  onPreview,
}: {
  artifacts: RuntimeArtifact[];
  preview: ArtifactPreviewState;
  onPreview: (artifact: RuntimeArtifact) => void;
}) {
  if (artifacts.length === 0) return null;
  const selected = artifacts.find((artifact) => artifact.id === preview.artifactId);
  return (
    <section className="artifact-list">
      <div className="detail-label">已登记产物</div>
      {artifacts.map((artifact) => (
        <div className="artifact-row" key={artifact.id}>
          <FileText size={14} />
          <div className="artifact-row-copy">
            <strong>{artifact.name}</strong>
            <code>{artifact.mediaType} · {formatBytes(artifact.sizeBytes)}</code>
          </div>
          <button
            className="icon-button small"
            title="查看产物"
            aria-label={`查看产物 ${artifact.name}`}
            onClick={() => onPreview(artifact)}
            disabled={artifact.status !== "ready" || preview.kind === "loading"}
          >
            <Eye size={13} />
          </button>
        </div>
      ))}
      {selected && preview.artifactId === selected.id && preview.kind !== "idle" && (
        <div className={`artifact-preview ${preview.kind}`}>
          <div className="artifact-preview-heading">
            <span>{selected.name}</span>
            <code>{preview.mediaType ?? selected.mediaType}</code>
          </div>
          {preview.kind === "loading" && <p>正在读取产物</p>}
          {preview.kind === "error" && <p>{preview.message}</p>}
          {preview.kind === "binary" && <p>{preview.message}</p>}
          {preview.kind === "text" && <pre>{preview.text}</pre>}
        </div>
      )}
    </section>
  );
}

function HumanRequestPanel({
  request,
  comment,
  setComment,
  values,
  setValue,
  artifacts,
  state,
  onDecision,
}: {
  request: RuntimeHumanRequest;
  comment: string;
  setComment: (value: string) => void;
  values: Record<string, string>;
  setValue: (name: string, value: string) => void;
  artifacts: RuntimeArtifact[];
  state: DecisionState;
  onDecision: (choice?: string) => void;
}) {
  const pending = request.status === "pending";
  const submitting = state.kind === "submitting";
  const inputFields =
    request.requestType === "input" ? getHumanInputFields(request.decisionSchema) : null;
  const unsupportedInputSchema = request.requestType === "input" && inputFields === null;
  return (
    <section className="human-request-panel" aria-label="人工请求">
      <div className="detail-label">人工请求</div>
      <div className="request-meta">
        <span>{request.requestType}</span>
        <code>v{request.version}</code>
      </div>
      {request.instructions && <p className="request-instructions">{request.instructions}</p>}
      <details className="info-disclosure audit-material-disclosure">
        <summary>审计材料</summary>
        {request.input !== undefined && (
          <div className="request-material">
            <span className="detail-label">冻结材料</span>
            <pre>{formatJson(request.input)}</pre>
          </div>
        )}
        <div className="request-subject">
          <span className="detail-label">主题摘要</span>
          <code>{request.subjectDigest}</code>
        </div>
        {request.authorizedSubjects && (
          <div className="request-subject">
            <span className="detail-label">授权处理人</span>
            <span>{request.authorizedSubjects.join(" · ")}</span>
          </div>
        )}
        {request.expiresAt && (
          <div className="request-subject">
            <span className="detail-label">截止时间</span>
            <span>{new Date(request.expiresAt).toLocaleString("zh-CN")}</span>
          </div>
        )}
      </details>
      {pending ? (
        <>
          {request.requestType === "input" ? (
            <>
              {unsupportedInputSchema ? (
                <div className="panel-callout warning">
                  <AlertCircle size={15} />
                  <span>当前结果契约包含暂不支持的字段类型，不能安全提交。</span>
                </div>
              ) : (
                <div className="human-input-fields">
                  <div className="detail-label">提交结果</div>
                  {inputFields?.map((field) => (
                    <HumanInputField
                      key={field.name}
                      field={field}
                      value={values[field.name] ?? ""}
                      onChange={(value) => setValue(field.name, value)}
                      disabled={submitting}
                      artifacts={artifacts}
                    />
                  ))}
                </div>
              )}
              <label className="field-label" htmlFor="decision-comment">审计备注</label>
              <textarea
                id="decision-comment"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                placeholder="仅用于审计记录，可选"
                disabled={submitting}
              />
              <button
                className="decision-button approve input-submit"
                onClick={() => onDecision()}
                disabled={submitting || unsupportedInputSchema}
              >
                <Send size={15} />
                提交结果
              </button>
            </>
          ) : (
            <>
              <label className="field-label" htmlFor="decision-comment">审计备注</label>
              <textarea
                id="decision-comment"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                placeholder="可选"
                disabled={submitting}
              />
              <div className="decision-actions">
                {request.choices.map((choice) => (
                  <button
                    key={choice}
                    className={`decision-button ${choice === "approve" ? "approve" : "reject"}`}
                    onClick={() => onDecision(choice)}
                    disabled={submitting}
                  >
                    {choice === "approve" ? <Check size={15} /> : <AlertCircle size={15} />}
                    {choice === "approve" ? "批准" : choice === "reject" ? "拒绝" : choice}
                  </button>
                ))}
              </div>
            </>
          )}
        </>
      ) : (
        <div className="patch-state success"><span className="state-indicator" /> 请求已{request.status === "decided" ? "完成" : request.status}</div>
      )}
      {state.message && <div className={`patch-state ${state.kind}`}>{state.message}</div>}
    </section>
  );
}

function HumanInputField({
  field,
  value,
  onChange,
  disabled,
  artifacts,
}: {
  field: HumanField;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  artifacts: RuntimeArtifact[];
}) {
  const inputId = `human-input-${field.name}`;
  const hint = field.description
    ? field.description
    : field.type === "array"
      ? "每行填写一项"
      : undefined;
  return (
    <div className="human-input-field">
      <label className="field-label" htmlFor={inputId}>
        {field.title}
        {field.required && <span className="required-mark"> *</span>}
      </label>
      {field.type === "boolean" ? (
        <select
          id={inputId}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
        >
          <option value="">请选择</option>
          <option value="true">是</option>
          <option value="false">否</option>
        </select>
      ) : isArtifactReferenceField(field) ? (
        <ArtifactReferencePicker
          field={field}
          value={value}
          artifacts={artifacts}
          onChange={onChange}
          disabled={disabled}
        />
      ) : field.type === "array" || field.type === "string" ? (
        <textarea
          id={inputId}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={hint}
          disabled={disabled}
          rows={field.type === "array" ? 3 : 2}
        />
      ) : (
        <input
          id={inputId}
          type="number"
          step={field.type === "integer" ? 1 : "any"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={hint}
          disabled={disabled}
        />
      )}
      {field.description && <p className="human-input-hint">{field.description}</p>}
    </div>
  );
}

function ArtifactReferencePicker({
  field,
  value,
  artifacts,
  onChange,
  disabled,
}: {
  field: HumanField;
  value: string;
  artifacts: RuntimeArtifact[];
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const selected = new Set(
    value
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean),
  );
  const readyArtifacts = artifacts.filter((artifact) => artifact.status === "ready");
  function toggle(artifactId: string) {
    const next = new Set(selected);
    if (next.has(artifactId)) next.delete(artifactId);
    else next.add(artifactId);
    onChange([...next].join("\n"));
  }
  if (readyArtifacts.length === 0) {
    return (
      <div className="artifact-picker-empty">
        <AlertCircle size={14} />
        <span>当前运行还没有可引用的已登记产物。</span>
      </div>
    );
  }
  return (
    <div className="artifact-picker" aria-label={`${field.title}可选产物`}>
      {readyArtifacts.map((artifact) => (
        <label className="artifact-option" key={artifact.id}>
          <input
            type="checkbox"
            checked={selected.has(artifact.id)}
            onChange={() => toggle(artifact.id)}
            disabled={disabled}
          />
          <span>
            <strong>{artifact.name}</strong>
            <code>{artifact.id}</code>
          </span>
        </label>
      ))}
    </div>
  );
}

function AgentPanel({
  patchText,
  setPatchText,
  patchState,
  onApply,
  onSimulate,
  events,
}: {
  patchText: string;
  setPatchText: (value: string) => void;
  patchState: { kind: "idle" | "success" | "error"; message: string };
  onApply: () => void;
  onSimulate: () => void;
  events: string[];
}) {
  return (
    <div className="panel-content agent-panel">
      <div className="panel-heading"><div><h2>智能体编辑流</h2></div></div>
      <label className="field-label" htmlFor="patch">作用域补丁</label>
      <textarea id="patch" value={patchText} onChange={(event) => setPatchText(event.target.value)} spellCheck={false} />
      <div className={`patch-state ${patchState.kind}`}><span className="state-indicator" /> {patchState.message}</div>
      <button className="apply-button" onClick={onApply}><Send size={15} /> 应用预览</button>
      <button
        aria-label="模拟下一条智能体事件"
        className="apply-button simulate-button"
        title="演示下一条智能体事件"
        onClick={onSimulate}
      >
        <Play size={15} /> 演示下一条事件
      </button>
      <div className="agent-events"><div className="detail-label">最近智能体活动</div>{events.map((event) => <div className="agent-event" key={event}><span />{event}</div>)}</div>
      <div className="panel-callout warning"><AlertCircle size={16} /><span>预览不会发布。</span></div>
    </div>
  );
}

function TimelineEvent({ time, title, tone }: { time: string; title: string; tone: "success" | "active" | "muted" }) {
  return <div className={`timeline-event ${tone}`}><span className="timeline-time">{time}</span><span className="timeline-marker" /><strong>{title}</strong></div>;
}

function StatusIcon({ status }: { status: NodeStatus }) {
  const Icon = statusIcons[status];
  return <Icon className={`status-icon ${status}`} size={15} />;
}

function mergeEvents(current: RuntimeEvent[], incoming: RuntimeEvent): RuntimeEvent[] {
  const bySeq = new Map(current.map((event) => [event.seq, event]));
  bySeq.set(incoming.seq, incoming);
  return [...bySeq.values()].sort((left, right) => left.seq - right.seq);
}

function connectionStateFor(status: WatchStatus): ConnectionState {
  if (status === "live") return { kind: "live", message: "Runtime 实时连接" };
  if (status === "reconnecting") return { kind: "reconnecting", message: "正在重连 Runtime" };
  if (status === "polling") return { kind: "polling", message: "轮询 Runtime 事件" };
  return { kind: "loading", message: "正在连接 Runtime" };
}

function statusForRun(status: string): NodeStatus {
  return status in statusLabels ? (status as NodeStatus) : "unknown";
}

function formatEventTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : date.toLocaleTimeString("zh-CN", { hour12: false });
}

function eventTone(type: string): "success" | "active" | "muted" {
  if (type.includes("succeeded") || type.includes("completed")) return "success";
  if (type.includes("running") || type.includes("created") || type.includes("waiting")) return "active";
  return "muted";
}

function mergeHumanRequests(
  current: RuntimeHumanRequest[],
  incoming: RuntimeHumanRequest[],
): RuntimeHumanRequest[] {
  const byId = new Map(current.map((request) => [request.id, request]));
  incoming.forEach((request) => {
    byId.set(request.id, { ...byId.get(request.id), ...request });
  });
  return [...byId.values()];
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

const demoTimeline = ["演示数据：草稿交付物已完成", "演示数据：细化已开始", "演示数据：人工审核"];

export default App;
