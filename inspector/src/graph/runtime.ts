import type {
  AuditGraph,
  GraphEdge,
  GraphGroup,
  GraphNode,
  NodeExecution,
  NodeStatus,
} from "./model";

type RuntimeStatus = string;

export type RuntimeProjection = {
  protocolVersion: string;
  run: RuntimeRun;
  scopes: RuntimeScope[];
  nodes: RuntimeNode[];
  edges: RuntimeEdge[];
  events: RuntimeEvent[];
  humanRequests: RuntimeHumanRequest[];
  artifacts: RuntimeArtifact[];
};

export type RuntimeViewSnapshot = {
  format: "multiverse-view/v0.1";
  exportedAt: string;
  workflow: { name: string; version: string; runId: string };
  graph: AuditGraph;
  layout: Record<string, { x: number; y: number }>;
  events: RuntimeEvent[];
  humanRequests: RuntimeHumanRequest[];
  artifacts: RuntimeArtifact[];
};

type RuntimeRun = {
  id: string;
  deploymentId: string;
  workflowId: string;
  packageDigest: string;
  bindingDigest: string | null;
  status: RuntimeStatus;
  controlMode: RuntimeStatus;
  currentScopeId: string | null;
  currentNodeId: string | null;
  currentInvocationId: string | null;
  version: number;
  deadlineAt: string;
  createdAt: string;
  updatedAt: string;
  rerunOf: string | null;
  rerunReason: string | null;
};

type RuntimeScope = {
  id: string;
  workflowId: string;
  parentScopeId: string | null;
  parentInvocationId: string | null;
  path: string[];
  inputDigest: string;
  status: RuntimeStatus;
};

type RuntimeInvocation = {
  id: string;
  status: RuntimeStatus;
  inputDigest: string;
  version: number;
  createdAt: string;
  updatedAt: string;
  hasOutput: boolean;
  error: string | null;
};

type RuntimeAttempt = {
  id: string;
  attemptNo: number;
  status: RuntimeStatus;
  version: number;
  inputDigest: string;
  externalRef: string | null;
  createdAt: string;
  updatedAt: string;
  hasOutput: boolean;
  error: string | null;
};

type RuntimeAttemptHistory = {
  id: string;
  attemptNo: number;
  status: RuntimeStatus;
  version: number;
  externalRef: string | null;
  createdAt: string;
  updatedAt: string;
  reconciliation: RuntimeReconciliation | null;
};

type RuntimeReconciliation = {
  conclusion: string | null;
  evidenceRefs: string[];
  reason: string | null;
  actor: string | null;
};

type RuntimeNode = {
  id: string;
  scopeId: string;
  nodeId: string;
  title: string;
  type: string;
  status: RuntimeStatus;
  execution?: NodeExecution | null;
  waitingReason?: string | null;
  inputSummary?: string;
  outputSummary?: string;
  dataSources?: string[];
  dataTargets?: string[];
  invocation: RuntimeInvocation | null;
  latestAttempt: RuntimeAttempt | null;
  attempts: RuntimeAttemptHistory[];
};

type RuntimeEdge = {
  id: string;
  scopeId: string;
  from: string;
  to: string;
  kind: string;
};

type RuntimeEvent = {
  seq: number;
  type: string;
  occurredAt: string;
  scopeId: string | null;
  invocationId: string | null;
  attemptId: string | null;
  payload: Record<string, unknown>;
};

export type RuntimeHumanRequest = {
  id: string;
  scopeId: string;
  invocationId: string;
  requestType: string;
  title: string;
  instructions?: string;
  input?: unknown;
  inputDigest?: string;
  subjectDigest: string;
  choices: string[];
  decisionSchema?: Record<string, unknown>;
  authorizedSubjects?: string[];
  createdAt?: string;
  expiresAt: string;
  version: number;
  status: RuntimeStatus;
  decisionId?: string | null;
  updatedAt?: string | null;
};

export type RuntimeArtifact = {
  id: string;
  invocationId: string | null;
  name: string;
  mediaType: string;
  sizeBytes: number;
  digest: string;
  status: RuntimeStatus;
  createdAt: string;
};

export function parseRuntimeProjection(value: unknown): RuntimeProjection {
  if (!isRuntimeProjection(value)) {
    throw new Error("不是有效的 Runtime 运行快照");
  }
  return value;
}

export function parseRuntimeViewSnapshot(value: unknown): RuntimeViewSnapshot {
  if (!isRuntimeViewSnapshot(value)) {
    throw new Error("不是有效的 Multiverse 运行视图");
  }
  return value;
}

export function mapRuntimeProjection(projection: RuntimeProjection): AuditGraph {
  const scopeGroups = new Map<string, GraphGroup>();
  const nodesByScope = new Map<string, RuntimeNode[]>();

  projection.nodes.forEach((runtimeNode) => {
    const members = nodesByScope.get(runtimeNode.scopeId) ?? [];
    members.push(runtimeNode);
    nodesByScope.set(runtimeNode.scopeId, members);
  });

  let nextScopeY = 132;
  projection.scopes.forEach((scope) => {
    const members = nodesByScope.get(scope.id) ?? [];
    const columnCount = Math.max(1, Math.min(3, members.length));
    const rowCount = Math.max(1, Math.ceil(members.length / columnCount));
    const width = Math.max(420, columnCount * 282 + 40);
    const height = Math.max(194, rowCount * 174 + 70);
    const pathLabel = scope.path.slice(1).join(" / ");
    scopeGroups.set(scope.id, {
      id: scope.id,
      parentId: scope.parentScopeId ?? undefined,
      title: scope.workflowId,
      subtitle: scope.path.length === 1
        ? `流程 ID · 主流程 · ${scope.status}`
        : `流程 ID · 子流程 · ${pathLabel} · ${scope.status}`,
      memberIds: members.map((member) => member.id),
      x: 40,
      y: nextScopeY,
      width,
      height,
    });
    nextScopeY += height + 44;
  });

  const nodes = projection.nodes.map((runtimeNode) =>
    toGraphNode(
      runtimeNode,
      scopeGroups.get(runtimeNode.scopeId),
      nodesByScope.get(runtimeNode.scopeId)?.findIndex(
        (member) => member.id === runtimeNode.id,
      ) ?? 0,
      projection,
    ),
  );
  const edges = projection.edges
    .filter((edge) => projection.nodes.some((node) => node.id === edge.from))
    .filter((edge) => projection.nodes.some((node) => node.id === edge.to))
    .map<GraphEdge>((edge) => ({
      id: edge.id,
      from: edge.from,
      to: edge.to,
      kind: edge.kind === "human" ? "human" : "control",
    }));

  const rootScope = projection.scopes.find((scope) => scope.path.length === 1);
  return {
    packageName: rootScope?.workflowId ?? "运行快照",
    packageVersion: projection.run.packageDigest.slice(0, 16),
    runId: projection.run.id,
    runVersion: projection.run.version,
    currentScopeId: projection.run.currentScopeId,
    currentNodeId:
      projection.run.currentScopeId && projection.run.currentNodeId
        ? `${projection.run.currentScopeId}:${projection.run.currentNodeId}`
        : null,
    controlMode: projection.run.controlMode,
    updatedAt: projection.run.updatedAt,
    runStatus: projection.run.status,
    lastEventSeq: projection.events.at(-1)?.seq ?? 0,
    nodes,
    edges,
    groups: [...scopeGroups.values()],
  };
}

function toGraphNode(
  runtimeNode: RuntimeNode,
  group: GraphGroup | undefined,
  memberIndex: number,
  projection: RuntimeProjection,
): GraphNode {
  const status = toNodeStatus(runtimeNode.status);
  const humanRequest = projection.humanRequests.find(
    (request) => request.invocationId === runtimeNode.invocation?.id,
  );
  const artifacts = projection.artifacts.filter(
    (artifact) => artifact.invocationId === runtimeNode.invocation?.id,
  );
  const evidence = [
    runtimeNode.invocation
      ? `Invocation ${runtimeNode.invocation.id} · ${runtimeNode.invocation.status}`
      : "尚未创建 Invocation",
    runtimeNode.latestAttempt
      ? `尝试 ${runtimeNode.latestAttempt.attemptNo} · ${runtimeNode.latestAttempt.status}`
      : "尚未创建 Attempt",
    ...artifacts.map((artifact) => `产物 ${artifact.name} 已登记`),
  ];
  if (humanRequest?.status === "pending") evidence.push("HumanRequest 等待处理");
  if (runtimeNode.invocation?.error) evidence.push(`错误：${runtimeNode.invocation.error}`);

  return {
    id: runtimeNode.id,
    invocationId: runtimeNode.invocation?.id,
    title: runtimeNode.title,
    type: toNodeType(runtimeNode.type),
    status,
    execution: runtimeNode.execution ?? undefined,
    waitingReason: runtimeNode.waitingReason,
    groupId: group?.id,
    x: (group?.x ?? 40) + 20 + (memberIndex % 3) * 282,
    y: (group?.y ?? 132) + 50 + Math.floor(memberIndex / 3) * 174,
    width: 258,
    height: 134,
    subtitle: runtimeNode.nodeId,
    executor: runtimeNode.execution?.target ?? "Binding 未核实",
    detail: humanRequest?.status === "pending"
      ? `${humanRequest.title} · 等待授权处理`
      : "从本地 Runtime 台账导入的只读事实。",
    input: runtimeNode.inputSummary ?? (runtimeNode.invocation ? "查看实际输入" : "尚无输入"),
    output: runtimeNode.outputSummary ?? (runtimeNode.invocation?.hasOutput ? "查看实际输出" : "尚无输出"),
    dataSources: runtimeNode.dataSources ?? [],
    dataTargets: runtimeNode.dataTargets ?? [],
    evidence,
  };
}

function toNodeStatus(status: RuntimeStatus): NodeStatus {
  if (status === "succeeded") return "succeeded";
  if (status === "running" || status === "waiting") return status;
  if (status === "pending" || status === "planned" || status === "ready") return "pending";
  if (
    status === "failed" ||
    status === "unknown" ||
    status === "reconciling" ||
    status === "blocked" ||
    status === "paused" ||
    status === "stopping" ||
    status === "cancelled" ||
    status === "skipped"
  ) {
    return status;
  }
  return "unknown";
}

function toNodeType(type: string): GraphNode["type"] {
  if (type === "input") return "input";
  if (type === "repeat") return "repeat";
  if (type === "parallel") return "parallel";
  if (type === "workflow") return "workflow";
  if (type === "switch") return "switch";
  if (type === "end") return "end";
  return "call";
}

function isRuntimeProjection(value: unknown): value is RuntimeProjection {
  if (!isRecord(value) || typeof value.protocolVersion !== "string") return false;
  if (!isRun(value.run)) return false;
  return (
    Array.isArray(value.scopes) &&
    value.scopes.every(isScope) &&
    Array.isArray(value.nodes) &&
    value.nodes.every(isNode) &&
    Array.isArray(value.edges) &&
    value.edges.every(isEdge) &&
    Array.isArray(value.events) &&
    value.events.every(isEvent) &&
    Array.isArray(value.humanRequests) &&
    value.humanRequests.every(isHumanRequest) &&
    Array.isArray(value.artifacts) &&
    value.artifacts.every(isArtifact)
  );
}

function isRuntimeViewSnapshot(value: unknown): value is RuntimeViewSnapshot {
  if (
    !isRecord(value) ||
    value.format !== "multiverse-view/v0.1" ||
    typeof value.exportedAt !== "string" ||
    !isRecord(value.workflow) ||
    !hasStrings(value.workflow, ["name", "version", "runId"]) ||
    !isAuditGraph(value.graph) ||
    !isRecord(value.layout) ||
    !Array.isArray(value.events) ||
    !value.events.every(isEvent) ||
    !Array.isArray(value.humanRequests) ||
    !value.humanRequests.every(isHumanRequest) ||
    !Array.isArray(value.artifacts) ||
    !value.artifacts.every(isArtifact)
  ) {
    return false;
  }
  return Object.values(value.layout).every(
    (position) =>
      isRecord(position) &&
      typeof position.x === "number" &&
      Number.isFinite(position.x) &&
      typeof position.y === "number" &&
      Number.isFinite(position.y),
  );
}

function isAuditGraph(value: unknown): value is AuditGraph {
  if (
    !isRecord(value) ||
    !hasStrings(value, [
      "packageName",
      "packageVersion",
      "runId",
      "controlMode",
      "updatedAt",
      "runStatus",
    ]) ||
    typeof value.runVersion !== "number" ||
    typeof value.lastEventSeq !== "number" ||
    !Array.isArray(value.nodes) ||
    !value.nodes.every(isGraphNode) ||
    !Array.isArray(value.groups) ||
    !value.groups.every(isGraphGroup) ||
    !Array.isArray(value.edges) ||
    !value.edges.every(isGraphEdge)
  ) {
    return false;
  }
  return true;
}

function isGraphNode(value: unknown): value is GraphNode {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "id",
      "title",
      "type",
      "status",
      "subtitle",
      "executor",
      "detail",
      "input",
      "output",
    ]) &&
    [
      "call",
      "switch",
      "human",
      "end",
      "group",
      "input",
      "repeat",
      "parallel",
      "workflow",
    ].includes(String(value.type)) &&
    [
      "succeeded",
      "running",
      "waiting",
      "pending",
      "failed",
      "unknown",
      "reconciling",
      "blocked",
      "paused",
      "stopping",
      "cancelled",
      "skipped",
    ].includes(String(value.status)) &&
    (value.invocationId === undefined || typeof value.invocationId === "string") &&
    (value.groupId === undefined || typeof value.groupId === "string") &&
    (value.memberInvocationIds === undefined ||
      (Array.isArray(value.memberInvocationIds) &&
        value.memberInvocationIds.every((id) => typeof id === "string"))) &&
    (value.dataSources === undefined ||
      (Array.isArray(value.dataSources) &&
        value.dataSources.every((name) => typeof name === "string"))) &&
    (value.dataTargets === undefined ||
      (Array.isArray(value.dataTargets) &&
        value.dataTargets.every((name) => typeof name === "string"))) &&
    (value.waitingReason === undefined || value.waitingReason === null || typeof value.waitingReason === "string") &&
    (value.execution === undefined || value.execution === null || isNodeExecution(value.execution)) &&
    typeof value.x === "number" &&
    Number.isFinite(value.x) &&
    typeof value.y === "number" &&
    Number.isFinite(value.y) &&
    typeof value.width === "number" &&
    Number.isFinite(value.width) &&
    typeof value.height === "number" &&
    Number.isFinite(value.height) &&
    Array.isArray(value.evidence) &&
    value.evidence.every((item) => typeof item === "string")
  );
}

function isNodeExecution(value: unknown): value is NodeExecution {
  return (
    isRecord(value) &&
    hasStrings(value, ["participantType", "location", "target"]) &&
    ["agent", "human", "program", "external_service", "process", "unknown"].includes(
      String(value.participantType),
    ) &&
    ["runtime", "local", "external", "human", "unknown"].includes(String(value.location)) &&
    (value.adapter === undefined || value.adapter === null || typeof value.adapter === "string") &&
    (value.executorRef === undefined || value.executorRef === null || typeof value.executorRef === "string") &&
    (value.model === undefined || value.model === null || typeof value.model === "string") &&
    (value.workspace === undefined || value.workspace === null || typeof value.workspace === "string")
  );
}

function isGraphGroup(value: unknown): value is GraphGroup {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "title", "subtitle"]) &&
    (value.parentId === undefined || typeof value.parentId === "string") &&
    Array.isArray(value.memberIds) &&
    value.memberIds.every((id) => typeof id === "string") &&
    typeof value.x === "number" &&
    Number.isFinite(value.x) &&
    typeof value.y === "number" &&
    Number.isFinite(value.y) &&
    typeof value.width === "number" &&
    Number.isFinite(value.width) &&
    typeof value.height === "number" &&
    Number.isFinite(value.height)
  );
}

function isGraphEdge(value: unknown): value is GraphEdge {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "from", "to", "kind"]) &&
    (value.label === undefined || typeof value.label === "string") &&
    ["data", "control", "human"].includes(String(value.kind))
  );
}

function isRun(value: unknown): value is RuntimeProjection["run"] {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "id",
      "deploymentId",
      "workflowId",
      "packageDigest",
      "status",
      "controlMode",
      "deadlineAt",
      "createdAt",
      "updatedAt",
    ]) &&
    (value.bindingDigest === null || typeof value.bindingDigest === "string") &&
    (value.currentScopeId === null || typeof value.currentScopeId === "string") &&
    (value.currentNodeId === null || typeof value.currentNodeId === "string") &&
    (value.currentInvocationId === null || typeof value.currentInvocationId === "string") &&
    typeof value.version === "number"
    &&
    (value.rerunOf === null || typeof value.rerunOf === "string") &&
    (value.rerunReason === null || typeof value.rerunReason === "string")
  );
}

function isScope(value: unknown): value is RuntimeScope {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "workflowId", "inputDigest", "status"]) &&
    Array.isArray(value.path) &&
    value.path.every((part) => typeof part === "string")
  );
}

function isNode(value: unknown): value is RuntimeNode {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "scopeId", "nodeId", "title", "type", "status"]) &&
    (value.invocation === null || isInvocation(value.invocation)) &&
    (value.latestAttempt === null || isAttempt(value.latestAttempt)) &&
    Array.isArray(value.attempts) &&
    value.attempts.every(isAttemptHistory)
  );
}

function isInvocation(value: unknown): value is RuntimeInvocation {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "status", "inputDigest", "createdAt", "updatedAt"]) &&
    typeof value.version === "number" &&
    typeof value.hasOutput === "boolean" &&
    (value.error === null || typeof value.error === "string")
  );
}

function isAttempt(value: unknown): value is RuntimeAttempt {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "status", "inputDigest", "createdAt", "updatedAt"]) &&
    typeof value.attemptNo === "number" &&
    typeof value.version === "number" &&
    typeof value.hasOutput === "boolean" &&
    (value.externalRef === null || typeof value.externalRef === "string") &&
    (value.error === null || typeof value.error === "string")
  );
}

function isAttemptHistory(value: unknown): value is RuntimeAttemptHistory {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "status", "createdAt", "updatedAt"]) &&
    typeof value.attemptNo === "number" &&
    typeof value.version === "number" &&
    (value.externalRef === null || typeof value.externalRef === "string") &&
    (value.reconciliation === null || isReconciliation(value.reconciliation))
  );
}

function isReconciliation(value: unknown): value is RuntimeReconciliation {
  return (
    isRecord(value) &&
    (value.conclusion === null || typeof value.conclusion === "string") &&
    Array.isArray(value.evidenceRefs) &&
    value.evidenceRefs.every((item) => typeof item === "string") &&
    (value.reason === null || typeof value.reason === "string") &&
    (value.actor === null || typeof value.actor === "string")
  );
}

function isEdge(value: unknown): value is RuntimeEdge {
  return isRecord(value) && hasStrings(value, ["id", "scopeId", "from", "to", "kind"]);
}

function isEvent(value: unknown): value is RuntimeEvent {
  return (
    isRecord(value) &&
    hasStrings(value, ["type", "occurredAt"]) &&
    typeof value.seq === "number" &&
    (value.scopeId === null || typeof value.scopeId === "string") &&
    (value.invocationId === null || typeof value.invocationId === "string") &&
    (value.attemptId === null || typeof value.attemptId === "string") &&
    isRecord(value.payload)
  );
}

function isHumanRequest(value: unknown): value is RuntimeHumanRequest {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "id",
      "scopeId",
      "invocationId",
      "requestType",
      "title",
      "subjectDigest",
      "expiresAt",
      "status",
    ]) &&
    Array.isArray(value.choices) &&
    value.choices.every((choice) => typeof choice === "string") &&
    typeof value.version === "number"
  );
}

function isArtifact(value: unknown): value is RuntimeArtifact {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "name", "mediaType", "digest", "status", "createdAt"]) &&
    (value.invocationId === null || typeof value.invocationId === "string") &&
    typeof value.sizeBytes === "number"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasStrings(value: Record<string, unknown>, keys: string[]): boolean {
  return keys.every((key) => typeof value[key] === "string");
}
