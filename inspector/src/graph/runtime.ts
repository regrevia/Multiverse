import type {
  AuditGraph,
  GraphEdge,
  GraphGroup,
  GraphNode,
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

type RuntimeArtifact = {
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

export function mapRuntimeProjection(projection: RuntimeProjection): AuditGraph {
  const scopeGroups = new Map<string, GraphGroup>();
  const nodesByScope = new Map<string, RuntimeNode[]>();

  projection.nodes.forEach((runtimeNode) => {
    const members = nodesByScope.get(runtimeNode.scopeId) ?? [];
    members.push(runtimeNode);
    nodesByScope.set(runtimeNode.scopeId, members);
  });

  projection.scopes.forEach((scope, scopeIndex) => {
    const members = nodesByScope.get(scope.id) ?? [];
    const width = Math.max(420, Math.min(760, members.length * 208 + 46));
    const height = 132;
    scopeGroups.set(scope.id, {
      id: scope.id,
      title: scope.path.length === 1 ? "根作用域" : `第 ${scope.path.at(-1)} 轮`,
      subtitle: `${scope.workflowId} · ${scope.status}`,
      memberIds: members.map((member) => member.id),
      x: 40,
      y: 132 + scopeIndex * 178,
      width,
      height,
    });
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
    type: toNodeType(runtimeNode.type, humanRequest),
    status,
    groupId: group?.id,
    x: (group?.x ?? 40) + 22 + memberIndex * 208,
    y: (group?.y ?? 132) + 22,
    width: 190,
    height: 94,
    subtitle: `${runtimeNode.nodeId} · ${runtimeNode.type}`,
    executor: runtimeNode.latestAttempt?.externalRef ?? "Runtime",
    detail: humanRequest?.status === "pending"
      ? `${humanRequest.title} · 等待授权处理`
      : "从本地 Runtime 台账导入的只读事实。",
    input: runtimeNode.invocation?.inputDigest ?? "未创建",
    output: runtimeNode.invocation?.hasOutput ? "已校验输出" : "未产生",
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

function toNodeType(type: string, humanRequest: RuntimeHumanRequest | undefined): GraphNode["type"] {
  if (humanRequest || type === "human") return "human";
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
