export type NodeStatus =
  | "succeeded"
  | "running"
  | "waiting"
  | "pending"
  | "failed"
  | "unknown"
  | "reconciling"
  | "blocked"
  | "paused"
  | "stopping"
  | "cancelled"
  | "skipped";

export type ParticipantType =
  | "agent"
  | "human"
  | "program"
  | "external_service"
  | "process"
  | "unknown";

export type NodeExecution = {
  participantType: ParticipantType;
  adapter?: string | null;
  executorRef?: string | null;
  location: "runtime" | "local" | "external" | "human" | "unknown";
  target: string;
  model?: string | null;
  workspace?: string | null;
};

export type GraphNode = {
  id: string;
  invocationId?: string;
  title: string;
  type: "call" | "switch" | "human" | "end" | "group" | "input" | "repeat" | "parallel" | "workflow";
  status: NodeStatus;
  waitingReason?: string | null;
  execution?: NodeExecution;
  memberInvocationIds?: string[];
  dataSources?: string[];
  dataTargets?: string[];
  groupId?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  subtitle: string;
  executor: string;
  detail: string;
  input: string;
  output: string;
  evidence: string[];
};

export type GraphEdge = {
  id: string;
  from: string;
  to: string;
  label?: string;
  kind: "data" | "control" | "human";
};

export type GraphGroup = {
  id: string;
  parentId?: string;
  title: string;
  subtitle: string;
  memberIds: string[];
  x: number;
  y: number;
  width: number;
  height: number;
};

export type AuditGraph = {
  packageName: string;
  packageVersion: string;
  runId: string;
  runVersion: number;
  currentScopeId?: string | null;
  currentNodeId?: string | null;
  controlMode: string;
  updatedAt: string;
  runStatus: string;
  lastEventSeq: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  groups: GraphGroup[];
};

export type AgentPatch = {
  nodeId: string;
  title?: string;
  status?: NodeStatus;
  detail?: string;
};

export const demoGraph: AuditGraph = {
  packageName: "content-delivery",
  packageVersion: "0.1.0",
  runId: "run_7f4b9d2",
  runVersion: 7,
  controlMode: "run",
  updatedAt: "刚刚",
  runStatus: "running",
  lastEventSeq: 0,
  groups: [
    {
      id: "production",
      title: "生产处理",
      subtitle: "2 次调用 · 确定性交接",
      memberIds: ["produce", "refine"],
      x: 40,
      y: 185,
      width: 604,
      height: 194,
    },
  ],
  nodes: [
    {
      id: "goal",
      title: "请求",
      type: "input",
      status: "succeeded",
      execution: {
        participantType: "program",
        adapter: "builtin",
        executorRef: "runtime.input",
        location: "runtime",
        target: "Runtime 输入",
      },
      x: 40,
      y: 25,
      width: 258,
      height: 134,
      subtitle: "工作流输入",
      executor: "runtime.input",
      detail: "本次运行由这份已冻结的请求发起。",
      input: "request.json",
      output: "goal.constraints",
      evidence: ["输入快照已锁定", "摘要校验通过"],
      dataSources: [],
      dataTargets: ["生成草稿交付物"],
    },
    {
      id: "produce",
      title: "生成草稿交付物",
      type: "call",
      status: "succeeded",
      execution: {
        participantType: "program",
        adapter: "builtin",
        executorRef: "example.content-fixture.v1",
        location: "runtime",
        target: "Multiverse Runtime",
      },
      groupId: "production",
      x: 60,
      y: 235,
      width: 258,
      height: 134,
      subtitle: "content.produce@1",
      executor: "example.content-fixture.v1",
      detail: "根据已冻结的请求创建候选交付物。",
      input: "request.goal",
      output: "deliverable.json",
      evidence: ["尝试 1 已完成", "输出结构校验通过"],
      dataSources: ["工作流输入"],
      dataTargets: ["细化交付物", "校验契约", "人工审核"],
    },
    {
      id: "refine",
      title: "细化交付物",
      type: "call",
      status: "running",
      execution: {
        participantType: "agent",
        adapter: "codex",
        executorRef: "builtin.codex-deliverable.v1",
        location: "local",
        target: "本机 Codex",
        model: "已配置模型",
        workspace: "项目工作区",
      },
      groupId: "production",
      x: 342,
      y: 235,
      width: 258,
      height: 134,
      subtitle: "content.refine@1",
      executor: "agent.preview.v1",
      detail: "智能体正在修改候选交付物，同时保留其契约。",
      input: "deliverable.json",
      output: "deliverable.v2.json",
      evidence: ["尝试 1 进行中", "已选择标准交接"],
      dataSources: ["生成草稿交付物"],
      dataTargets: ["校验契约"],
    },
    {
      id: "verify",
      title: "校验契约",
      type: "call",
      status: "pending",
      execution: {
        participantType: "program",
        adapter: "builtin",
        executorRef: "builtin.nonempty-deliverable.v1",
        location: "runtime",
        target: "Multiverse Runtime",
      },
      x: 390,
      y: 195,
      width: 258,
      height: 134,
      subtitle: "data.validate@1",
      executor: "builtin.nonempty-deliverable.v1",
      detail: "在审核前检查结构和必需材料。",
      input: "deliverable.v2.json",
      output: "verification.json",
      evidence: ["等待上游完成", "无副作用"],
      dataSources: ["生成草稿交付物", "细化交付物"],
      dataTargets: ["人工审核"],
    },
    {
      id: "review",
      title: "人工审核",
      type: "call",
      status: "waiting",
      execution: {
        participantType: "human",
        adapter: "human",
        executorRef: "builtin.human-review.v1",
        location: "human",
        target: "当前页面",
      },
      waitingReason: "等待人工处理",
      x: 670,
      y: 185,
      width: 258,
      height: 134,
      subtitle: "审核请求",
      executor: "builtin.human-review.v1",
      detail: "授权审核人将针对这一确切版本做出决定。",
      input: "deliverable.evidence",
      output: "decision.comment",
      evidence: ["HumanRequest 等待处理", "对象摘要已锁定"],
      dataSources: ["生成草稿交付物", "校验契约"],
      dataTargets: ["交付结果"],
    },
    {
      id: "deliver",
      title: "交付结果",
      type: "end",
      status: "pending",
      x: 670,
      y: 345,
      width: 258,
      height: 134,
      subtitle: "成功边界",
      executor: "runtime.end",
      detail: "获得明确批准后发布工作流结果。",
      input: "approved.review",
      output: "final-output.json",
      evidence: ["尚未到达", "需要批准"],
      dataSources: ["人工审核"],
      dataTargets: [],
    },
  ],
  edges: [
    { id: "e-goal-production", from: "goal", to: "production", kind: "data" },
    { id: "e-produce-refine", from: "produce", to: "refine", kind: "data" },
    { id: "e-production-verify", from: "production", to: "verify", kind: "data" },
    { id: "e-verify-review", from: "verify", to: "review", label: "有效", kind: "control" },
    { id: "e-review-deliver", from: "review", to: "deliver", label: "批准", kind: "human" },
  ],
};

export function visibleGraph(graph: AuditGraph, collapsedGroups: Set<string>) {
  const collapsed = new Set(collapsedGroups);
  const memberToGroup = new Map<string, string>();
  graph.groups.forEach((group) => {
    if (collapsed.has(group.id)) {
      group.memberIds.forEach((memberId) => memberToGroup.set(memberId, group.id));
    }
  });

  const nodes = graph.nodes.filter((node) => !memberToGroup.has(node.id));
  graph.groups.forEach((group) => {
    const members = graph.nodes.filter((node) => group.memberIds.includes(node.id));
    const running = members.find((node) => node.status === "running");
    const waiting = members.find((node) => node.status === "waiting");
    const participantCounts = new Map<string, number>();
    members.forEach((member) => {
      const participant = member.execution?.participantType;
      if (participant) participantCounts.set(participant, (participantCounts.get(participant) ?? 0) + 1);
    });
    const participantSummary = [...participantCounts]
      .map(([participant, count]) => `${count} ${participantLabel(participant)}`)
      .join(" · ");
    const failedCount = members.filter((member) => member.status === "failed").length;
    const blockedCount = members.filter((member) =>
      ["blocked", "unknown", "reconciling"].includes(member.status),
    ).length;
    const groupStatus: NodeStatus = failedCount > 0
      ? "failed"
      : blockedCount > 0
        ? "blocked"
        : waiting?.status ?? running?.status ?? (
          members.length > 0 && members.every((member) => member.status === "pending")
            ? "pending"
            : "succeeded"
        );
    const issueSummary = [
      failedCount > 0 ? `${failedCount} 个节点失败` : "",
      blockedCount > 0 ? `${blockedCount} 个节点需核对` : "",
    ].filter(Boolean).join(" · ");
    const stateSummary = issueSummary
      ? issueSummary
      : waiting
        ? `${waiting.title} · ${waiting.waitingReason ?? statusLabel(waiting.status)}`
        : running
          ? `${running.title} · 进行中`
          : "当前分组";
    nodes.push({
      id: group.id,
      title: group.title,
      type: "group",
      status: groupStatus,
      x: group.x,
      y: group.y,
      width: collapsed.has(group.id) ? 304 : group.width,
      height: collapsed.has(group.id) ? 116 : group.height,
      subtitle: collapsed.has(group.id)
        ? `${members.length} 个节点${participantSummary ? ` · ${participantSummary}` : ""}`
        : "内部节点",
      executor: "workflow.scope",
      detail: collapsed.has(group.id)
        ? [participantSummary, stateSummary].filter(Boolean).join(" · ")
        : `${members.length} 个节点${participantSummary ? ` · ${participantSummary}` : ""}`,
      input: "接口未投影",
      output: "接口未投影",
      evidence: members.flatMap((member) => member.evidence).slice(0, 3),
      memberInvocationIds: members.flatMap((member) =>
        member.invocationId ? [member.invocationId] : [],
      ),
      dataSources: [...new Set(members.flatMap((member) => member.dataSources ?? []))],
      dataTargets: [...new Set(members.flatMap((member) => member.dataTargets ?? []))],
    });
  });

  const edgeKeys = new Set<string>();
  const edges = graph.edges.flatMap((edge) => {
    const from = memberToGroup.get(edge.from) ?? edge.from;
    const to = memberToGroup.get(edge.to) ?? edge.to;
    if (from === to) return [];
    const id = `${from}->${to}`;
    if (edgeKeys.has(id)) return [];
    edgeKeys.add(id);
    return [{ ...edge, id: `${edge.id}:${from}:${to}`, from, to }];
  });

  return { nodes, edges };
}

export function artifactsForNode<T extends { invocationId: string | null }>(
  node: GraphNode,
  artifacts: T[],
): T[] {
  const invocationIds = node.type === "group"
    ? new Set(node.memberInvocationIds ?? [])
    : node.invocationId
      ? new Set([node.invocationId])
      : new Set<string>();
  return artifacts.filter(
    (artifact) => artifact.invocationId !== null && invocationIds.has(artifact.invocationId),
  );
}

function participantLabel(participant: string): string {
  const labels: Record<string, string> = {
    agent: "Agent",
    human: "人工",
    program: "程序",
    external_service: "外部服务",
    process: "本机进程",
    unknown: "未核实",
  };
  return labels[participant] ?? "执行者";
}

function statusLabel(status: NodeStatus): string {
  return status === "pending" ? "待执行" : status === "waiting" ? "等待处理" : status;
}

export function applyAgentPatch(graph: AuditGraph, patch: AgentPatch) {
  const index = graph.nodes.findIndex((node) => node.id === patch.nodeId);
  if (index === -1) return { ok: false as const, error: "找不到对应节点" };
  const next = structuredClone(graph);
  const node = next.nodes[index];
  if (patch.title !== undefined) node.title = patch.title.slice(0, 80);
  if (patch.status !== undefined) node.status = patch.status;
  if (patch.detail !== undefined) node.detail = patch.detail.slice(0, 240);
  next.updatedAt = "刚刚";
  return { ok: true as const, graph: next };
}
