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

export type GraphNode = {
  id: string;
  invocationId?: string;
  title: string;
  type: "call" | "switch" | "human" | "end" | "group";
  status: NodeStatus;
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
  updatedAt: "刚刚",
  runStatus: "running",
  lastEventSeq: 0,
  groups: [
    {
      id: "production",
      title: "生产处理",
      subtitle: "2 次调用 · 确定性交接",
      memberIds: ["produce", "refine"],
      x: 72,
      y: 150,
      width: 462,
      height: 260,
    },
  ],
  nodes: [
    {
      id: "goal",
      title: "请求",
      type: "call",
      status: "succeeded",
      x: 72,
      y: 34,
      width: 210,
      height: 92,
      subtitle: "输入契约",
      executor: "runtime.input",
      detail: "本次运行由这份已冻结的请求发起。",
      input: "request.json",
      output: "goal.constraints",
      evidence: ["输入快照已锁定", "摘要校验通过"],
    },
    {
      id: "produce",
      title: "生成草稿交付物",
      type: "call",
      status: "succeeded",
      groupId: "production",
      x: 104,
      y: 202,
      width: 198,
      height: 94,
      subtitle: "content.produce@1",
      executor: "example.content-fixture.v1",
      detail: "根据已冻结的请求创建候选交付物。",
      input: "request.goal",
      output: "deliverable.json",
      evidence: ["尝试 1 已完成", "输出结构校验通过"],
    },
    {
      id: "refine",
      title: "细化交付物",
      type: "call",
      status: "running",
      groupId: "production",
      x: 334,
      y: 202,
      width: 174,
      height: 94,
      subtitle: "content.refine@1",
      executor: "agent.preview.v1",
      detail: "智能体正在修改候选交付物，同时保留其契约。",
      input: "deliverable.json",
      output: "deliverable.v2.json",
      evidence: ["尝试 1 进行中", "已选择标准交接"],
    },
    {
      id: "verify",
      title: "校验契约",
      type: "call",
      status: "pending",
      x: 600,
      y: 202,
      width: 204,
      height: 94,
      subtitle: "data.validate@1",
      executor: "builtin.nonempty-deliverable.v1",
      detail: "在审核前检查结构和必需材料。",
      input: "deliverable.v2.json",
      output: "verification.json",
      evidence: ["等待上游完成", "无副作用"],
    },
    {
      id: "review",
      title: "人工审核",
      type: "human",
      status: "waiting",
      x: 600,
      y: 350,
      width: 204,
      height: 94,
      subtitle: "审核请求",
      executor: "builtin.human-review.v1",
      detail: "授权审核人将针对这一确切版本做出决定。",
      input: "deliverable.evidence",
      output: "decision.comment",
      evidence: ["HumanRequest 等待处理", "对象摘要已锁定"],
    },
    {
      id: "deliver",
      title: "交付结果",
      type: "end",
      status: "pending",
      x: 600,
      y: 500,
      width: 204,
      height: 82,
      subtitle: "成功边界",
      executor: "runtime.end",
      detail: "获得明确批准后发布工作流结果。",
      input: "approved.review",
      output: "final-output.json",
      evidence: ["尚未到达", "需要批准"],
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
    nodes.push({
      id: group.id,
      title: group.title,
      type: "group",
      status: running?.status ?? waiting?.status ?? "succeeded",
      x: group.x,
      y: group.y,
      width: group.width,
      height: group.height,
      subtitle: collapsed.has(group.id) ? group.subtitle : "已展开作用域",
      executor: "workflow.scope",
      detail: collapsed.has(group.id)
        ? "作用域已折叠。展开后可查看单个调用。"
        : "作用域已展开。子调用保留稳定的领域 ID。",
      input: "production.request",
      output: "latest.deliverable",
      evidence: members.flatMap((member) => member.evidence).slice(0, 3),
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
