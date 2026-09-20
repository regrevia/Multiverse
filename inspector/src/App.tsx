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
  FileText,
  GitBranch,
  Layers3,
  Maximize2,
  Minus,
  PanelRight,
  Play,
  Plus,
  Radio,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  UserRound,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import {
  applyAgentPatch,
  demoGraph,
  type AuditGraph,
  type AgentPatch,
  type GraphNode,
  type NodeStatus,
  visibleGraph,
} from "./graph/model";

type Point = { x: number; y: number };
type PanelMode = "audit" | "agent";

const statusLabels: Record<NodeStatus, string> = {
  succeeded: "已完成",
  running: "进行中",
  waiting: "等待处理",
  pending: "待执行",
  failed: "失败",
};

const nodeTypeLabels: Record<GraphNode["type"], string> = {
  call: "调用",
  switch: "分支",
  human: "人工",
  end: "结束",
  group: "作用域",
};

const statusIcons: Record<NodeStatus, typeof Check> = {
  succeeded: Check,
  running: Activity,
  waiting: UserRound,
  pending: CircleDashed,
  failed: AlertCircle,
};

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
  const [agentEvents, setAgentEvents] = useState([
    "智能体已开始一次细化尝试",
    "已为 draft → refine 选择标准交接",
    "运行证据仍绑定在当前作用域",
  ]);
  const viewportRef = useRef<HTMLDivElement>(null);
  const visible = useMemo(
    () => visibleGraph(graph, collapsedGroups),
    [graph, collapsedGroups],
  );
  const selectedNode =
    visible.nodes.find((node) => node.id === selectedId) ??
    graph.nodes.find((node) => node.id === selectedId) ??
    visible.nodes[0];

  function toggleGroup(groupId: string) {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  function focusNode(node: GraphNode) {
    setSelectedId(node.id);
    const centerX = 540 - (node.x + node.width / 2) * zoom;
    const centerY = 320 - (node.y + node.height / 2) * zoom;
    setPan({ x: centerX, y: centerY });
  }

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

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest("button")) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStart({ x: event.clientX - pan.x, y: event.clientY - pan.y });
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragStart) return;
    setPan({ x: event.clientX - dragStart.x, y: event.clientY - dragStart.y });
  }

  function onPointerUp() {
    setDragStart(null);
  }

  function onWheel(event: React.WheelEvent<HTMLDivElement>) {
    setZoom((value) => Math.min(1.24, Math.max(0.58, value - event.deltaY * 0.0008)));
  }

  const nodeMap = new Map(visible.nodes.map((node) => [node.id, node]));

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark"><Workflow size={18} strokeWidth={2.5} /></div>
          <div>
            <strong>Multiverse</strong>
            <span>审计查看器</span>
          </div>
        </div>
        <div className="crumb">
          <span className="crumb-muted">运行</span>
          <ChevronRight size={14} />
          <span>{graph.packageName}</span>
          <span className="version-tag">v{graph.packageVersion}</span>
        </div>
        <div className="topbar-actions">
          <div className="live-state"><span className="live-dot" /> 实时预览</div>
          <button className="icon-button" title="搜索证据"><Search size={17} /></button>
          <button className="icon-button" title="打开面板"><PanelRight size={17} /></button>
          <div className="avatar">R</div>
        </div>
      </header>

      <div className="workspace">
        <aside className="left-rail">
          <div className="rail-section">
            <p className="rail-title">工作区</p>
            <button className="rail-item active"><Activity size={16} /> 当前运行</button>
            <button className="rail-item"><Layers3 size={16} /> 工作流</button>
            <button className="rail-item"><UserRound size={16} /> 人工处理箱 <span className="rail-count">1</span></button>
          </div>
          <div className="rail-section rail-bottom">
            <p className="rail-title">运行</p>
            <div className="run-id">{graph.runId}</div>
            <div className="run-meta"><span className="status-dot running" /> 细化进行中</div>
            <div className="run-meta"><ShieldCheck size={14} /> 摘要已锁定</div>
          </div>
        </aside>

        <section className="main-stage">
          <div className="stage-header">
            <div>
              <div className="eyebrow"><Radio size={13} /> 运行详情</div>
              <h1>内容交付</h1>
              <p>查看工作流状态、运行证据和下一步授权操作。</p>
            </div>
            <div className="stage-actions">
              <button className="quiet-button" onClick={() => setCollapsedGroups(new Set())}>
                <Layers3 size={15} /> 展开作用域
              </button>
              <button className="dark-button" onClick={simulateAgentUpdate}>
                <Zap size={15} /> 模拟智能体更新
              </button>
            </div>
          </div>

          <div className="run-summary">
            <div className="summary-main">
              <div className="summary-icon"><Activity size={18} /></div>
              <div><strong>等待细化完成</strong><span>当前运行仍在进行，并保留上一版本输出。</span></div>
            </div>
            <div className="summary-facts">
              <div><span>进度</span><strong>2 / 6 个节点</strong></div>
              <div><span>作用域</span><strong>root / production</strong></div>
              <div><span>更新时间</span><strong>{graph.updatedAt}</strong></div>
            </div>
          </div>

          <div className="canvas-toolbar">
            <div className="canvas-mode"><button className="mode-button active"><Workflow size={15} /> 流程</button><button className="mode-button"><FileText size={15} /> 证据</button></div>
            <div className="canvas-controls">
              <button className="icon-button small" title="缩小" onClick={() => setZoom((value) => Math.max(0.58, value - 0.1))}><Minus size={15} /></button>
              <span className="zoom-readout">{Math.round(zoom * 100)}%</span>
              <button className="icon-button small" title="放大" onClick={() => setZoom((value) => Math.min(1.24, value + 0.1))}><Plus size={15} /></button>
              <button className="icon-button small" title="适配画布" onClick={() => { setZoom(0.84); setPan({ x: 24, y: 28 }); }}><Maximize2 size={15} /></button>
            </div>
          </div>

          <div
            className={`graph-viewport ${dragStart ? "dragging" : ""}`}
            ref={viewportRef}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onWheel={onWheel}
          >
            <div className="canvas-grid" />
            <div className="graph-world" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
              <svg className="edge-layer" viewBox="0 0 920 650" aria-hidden="true">
                <defs>
                  <marker id="arrow-data" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#9ca39f" /></marker>
                  <marker id="arrow-active" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#36aab0" /></marker>
                </defs>
                {visible.edges.map((edge) => {
                  const from = nodeMap.get(edge.from);
                  const to = nodeMap.get(edge.to);
                  if (!from || !to) return null;
                  const start = { x: from.x + from.width, y: from.y + from.height / 2 };
                  const end = { x: to.x, y: to.y + to.height / 2 };
                  const curve = Math.max(50, Math.abs(end.x - start.x) * 0.48);
                  const active = from.status === "running" || to.status === "running";
                  return (
                    <g key={edge.id} className={`edge-group ${active ? "active" : ""}`}>
                      <path d={`M ${start.x} ${start.y} C ${start.x + curve} ${start.y}, ${end.x - curve} ${end.y}, ${end.x} ${end.y}`} markerEnd={`url(#arrow-${active ? "active" : "data"})`} />
                      {edge.label && <text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - 9}>{edge.label}</text>}
                    </g>
                  );
                })}
              </svg>
              {visible.nodes.filter((node) => node.type === "group").map((node) => {
                const isCollapsed = collapsedGroups.has(node.id);
                return (
                  <button
                    key={node.id}
                    className={`scope-card ${isCollapsed ? "collapsed" : "expanded"}`}
                    style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
                    onClick={() => toggleGroup(node.id)}
                  >
                    <span className="scope-head"><span><Layers3 size={14} /> {node.title}</span>{isCollapsed ? <ChevronRight size={15} /> : <ChevronDown size={15} />}</span>
                    <span className="scope-subtitle">{node.subtitle}</span>
                    {isCollapsed && <span className="scope-state"><StatusIcon status={node.status} /> {statusLabels[node.status]}</span>}
                  </button>
                );
              })}
              {visible.nodes.filter((node) => node.type !== "group").map((node) => (
                <NodeCard
                  key={node.id}
                  node={node}
                  selected={selectedId === node.id}
                  onClick={() => setSelectedId(node.id)}
                />
              ))}
            </div>
            <div className="canvas-hint"><span>拖动平移</span><span>滚轮缩放</span><span>点击节点查看详情</span></div>
          </div>

          <div className="timeline">
            <div className="timeline-heading"><span><Clock3 size={15} /> 证据时间线</span><button className="text-button"><RotateCcw size={14} /> 刷新</button></div>
            <div className="timeline-track">
              <TimelineEvent time="09:42:11" title="草稿交付物已完成" detail="输出结构校验通过" tone="success" />
              <TimelineEvent time="09:42:12" title="细化已开始" detail="尝试 1 进行中" tone="active" />
              <TimelineEvent time="—" title="人工审核" detail="尚未到达" tone="muted" />
            </div>
          </div>
        </section>

        <aside className="inspector-panel">
          <div className="panel-tabs">
            <button className={panelMode === "audit" ? "selected" : ""} onClick={() => setPanelMode("audit")}><ShieldCheck size={15} /> 审计</button>
            <button className={panelMode === "agent" ? "selected" : ""} onClick={() => setPanelMode("agent")}><Code2 size={15} /> 智能体编辑</button>
          </div>
          {panelMode === "audit" ? (
            selectedNode && <AuditPanel node={selectedNode} onFocus={() => focusNode(selectedNode)} />
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
    </main>
  );
}

function NodeCard({ node, selected, onClick }: { node: GraphNode; selected: boolean; onClick: () => void }) {
  const Icon = node.type === "human" ? UserRound : node.type === "end" ? Check : node.type === "switch" ? GitBranch : Box;
  return (
    <button className={`node-card ${selected ? "selected" : ""} status-${node.status}`} style={{ left: node.x, top: node.y, width: node.width, height: node.height }} onClick={onClick}>
      <span className="node-topline"><span className="node-type"><Icon size={14} /> {nodeTypeLabels[node.type]}</span><StatusIcon status={node.status} /></span>
      <strong>{node.title}</strong>
      <span className="node-subtitle">{node.subtitle}</span>
      <span className="node-footer"><span className="node-executor">{node.executor}</span><ChevronRight size={14} /></span>
    </button>
  );
}

function AuditPanel({ node, onFocus }: { node: GraphNode; onFocus: () => void }) {
  return (
    <div className="panel-content">
      <div className="panel-heading">
        <div><span className="panel-kicker"><ShieldCheck size={13} /> 已验证证据</span><h2>{node.title}</h2><p>{node.detail}</p></div>
        <button className="icon-button small" title="聚焦节点" onClick={onFocus}><Maximize2 size={15} /></button>
      </div>
      <div className="audit-status"><StatusIcon status={node.status} /><div><span>当前状态</span><strong>{statusLabels[node.status]}</strong></div></div>
      <div className="detail-block"><span className="detail-label">执行器</span><strong>{node.executor}</strong></div>
      <div className="contract-grid"><div><span className="detail-label">输入</span><strong>{node.input}</strong></div><div><span className="detail-label">输出</span><strong>{node.output}</strong></div></div>
      <div className="evidence-list"><div className="detail-label">证据</div>{node.evidence.map((item) => <div className="evidence-row" key={item}><Check size={14} /> {item}</div>)}</div>
      <div className="panel-callout"><ShieldCheck size={16} /><span>身份、版本和输出均绑定到此节点 ID。</span></div>
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
      <div className="panel-heading"><div><span className="panel-kicker"><Zap size={13} /> 实时编排</span><h2>智能体编辑流</h2><p>在作用域变更成为新版本之前，先查看预览结果。</p></div></div>
      <label className="field-label" htmlFor="patch">作用域补丁</label>
      <textarea id="patch" value={patchText} onChange={(event) => setPatchText(event.target.value)} spellCheck={false} />
      <div className={`patch-state ${patchState.kind}`}><span className="state-indicator" /> {patchState.message}</div>
      <button className="apply-button" onClick={onApply}><Send size={15} /> 应用预览</button>
      <button className="quiet-button full" onClick={onSimulate}><Play size={15} /> 模拟下一条智能体事件</button>
      <div className="agent-events"><div className="detail-label">最近智能体活动</div>{events.map((event) => <div className="agent-event" key={event}><span />{event}</div>)}</div>
      <div className="panel-callout warning"><AlertCircle size={16} /><span>预览变更只会更新图，不会发布。正式发布仍需要校验、差异确认和授权决策。</span></div>
    </div>
  );
}

function TimelineEvent({ time, title, detail, tone }: { time: string; title: string; detail: string; tone: "success" | "active" | "muted" }) {
  return <div className={`timeline-event ${tone}`}><span className="timeline-time">{time}</span><span className="timeline-marker" /><div><strong>{title}</strong><span>{detail}</span></div></div>;
}

function StatusIcon({ status }: { status: NodeStatus }) {
  const Icon = statusIcons[status];
  return <Icon className={`status-icon ${status}`} size={15} />;
}

export default App;
