import { useEffect, useState, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  Position,
  MarkerType,
  useNodesState,
  useEdgesState,
  type NodeProps,
  Handle,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Router,
  Server,
  Cpu,
  Zap,
  Circle,
  MessageSquare,
  Brain,
  GitMerge,
  Layers,
} from 'lucide-react';
import clsx from 'clsx';
import type { SSEMessage } from '../hooks/useEventStream';

interface BackendInfo {
  name: string;
  locality: string;
  healthy: boolean;
  default_model: string;
  type: string;
}

interface ModelInfo {
  name: string;
  backend: string;
  size: string;
  quantization: string;
  capabilities: string[];
}

interface RoutingRule {
  preferred_backend: string;
  preferred_model?: string;
  fallback_backends?: string[];
  max_tokens?: number;
  temperature?: number;
}

interface Props {
  ws: {
    connected: boolean;
    on: (fn: (m: SSEMessage) => void) => () => void;
  };
}

/* ── Custom node components ── */

interface NodeData extends Record<string, unknown> {
  label?: string;
  active?: boolean;
  strategy?: string;
  healthy?: boolean;
  locality?: string;
  size?: string;
  quant?: string;
  stepStatus?: string;
}

function RequestNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={clsx(
      'px-3 py-2 rounded-lg border-2 text-center min-w-[120px]',
      data.active
        ? 'border-accent bg-accent/10 shadow-md shadow-accent/20'
        : 'border-border bg-surface',
    )}>
      <div className="flex items-center justify-center gap-1.5 mb-0.5">
        <MessageSquare size={12} className="text-accent" />
        <span className="text-[11px] font-semibold text-accent">REQUEST</span>
      </div>
      <div className="text-[10px] text-stone-500 dark:text-stone-400 font-mono">
        {data.label || 'chat'}
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-accent !border-0" />
    </div>
  );
}

function PlannerNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={clsx(
      'px-3 py-2 rounded-lg border-2 text-center min-w-[130px]',
      data.active
        ? 'border-violet-500 bg-violet-500/10 shadow-md shadow-violet-500/20'
        : 'border-border bg-surface',
    )}>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-violet-500 !border-0" />
      <div className="flex items-center justify-center gap-1.5 mb-0.5">
        <Brain size={12} className="text-violet-500" />
        <span className="text-[11px] font-semibold text-violet-600 dark:text-violet-400">PLANNER</span>
      </div>
      <div className="text-[10px] text-stone-500 dark:text-stone-400">
        decompose & plan
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-violet-500 !border-0" />
    </div>
  );
}

function DispatcherNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={clsx(
      'px-3 py-2 rounded-lg border-2 text-center min-w-[130px]',
      data.active
        ? 'border-amber bg-amber/10 shadow-md shadow-amber/20'
        : 'border-border bg-surface',
    )}>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-amber !border-0" />
      <div className="flex items-center justify-center gap-1.5 mb-0.5">
        <Router size={12} className="text-amber" />
        <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">DISPATCHER</span>
      </div>
      <div className="text-[10px] text-stone-500 dark:text-stone-400">
        {data.strategy || 'route to executors'}
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-amber !border-0" />
    </div>
  );
}

function ExecutorNode({ data }: NodeProps<Node<NodeData>>) {
  const status = data.stepStatus;
  return (
    <div className={clsx(
      'px-3 py-2 rounded-lg border-2 min-w-[140px]',
      status === 'running'
        ? 'border-amber-500 bg-amber-500/10 shadow-md shadow-amber-500/20 animate-pulse'
        : status === 'done'
          ? 'border-green bg-green/10 shadow-md shadow-green/20'
          : data.active
            ? 'border-accent bg-accent/10 shadow-md shadow-accent/20'
            : 'border-border bg-surface',
    )}>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-accent !border-0" />
      <div className="flex items-center gap-1.5 mb-0.5">
        <Cpu size={12} className={status === 'done' ? 'text-green' : 'text-accent'} />
        <span className="text-[11px] font-semibold truncate">{data.label}</span>
      </div>
      <div className="flex items-center gap-1">
        {data.size && (
          <span className="text-[9px] px-1.5 rounded-full bg-surface-strong text-stone-500 dark:text-stone-400">
            {data.size}
          </span>
        )}
        {status && (
          <span className={clsx(
            'text-[9px] px-1.5 rounded-full font-semibold uppercase',
            status === 'running' ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400'
              : status === 'done' ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'
                : 'bg-stone-100 dark:bg-stone-800 text-stone-500',
          )}>
            {status}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-accent !border-0" />
    </div>
  );
}

function ConsolidatorNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={clsx(
      'px-3 py-2 rounded-lg border-2 text-center min-w-[130px]',
      data.active
        ? 'border-emerald-500 bg-emerald-500/10 shadow-md shadow-emerald-500/20'
        : 'border-border bg-surface',
    )}>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-emerald-500 !border-0" />
      <div className="flex items-center justify-center gap-1.5 mb-0.5">
        <GitMerge size={12} className="text-emerald-500" />
        <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">CONSOLIDATOR</span>
      </div>
      <div className="text-[10px] text-stone-500 dark:text-stone-400">merge results</div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-emerald-500 !border-0" />
    </div>
  );
}

function ResponseNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={clsx(
      'px-3 py-2 rounded-lg border-2 text-center min-w-[120px]',
      data.active
        ? 'border-accent bg-accent/10 shadow-md shadow-accent/20'
        : 'border-border bg-surface',
    )}>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-accent !border-0" />
      <div className="flex items-center justify-center gap-1.5 mb-0.5">
        <Layers size={12} className="text-accent" />
        <span className="text-[11px] font-semibold text-accent">RESPONSE</span>
      </div>
    </div>
  );
}

function BackendNode({ data }: NodeProps<Node<NodeData>>) {
  const healthy = !!data.healthy;
  return (
    <div className={clsx(
      'px-3 py-2 rounded-lg border-2 min-w-[130px]',
      data.active
        ? 'border-green bg-green/10 shadow-md shadow-green/20'
        : healthy
          ? 'border-border bg-surface'
          : 'border-red/40 bg-red/5',
    )}>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-green !border-0" />
      <div className="flex items-center gap-1.5 mb-0.5">
        <Server size={12} className={healthy ? 'text-green' : 'text-red'} />
        <span className="text-[11px] font-semibold">{data.label}</span>
        <Circle
          size={6}
          className={clsx('ml-auto', healthy ? 'fill-green text-green' : 'fill-red text-red')}
        />
      </div>
      <div className="flex items-center gap-1 text-[10px] text-stone-500 dark:text-stone-400">
        <span className="px-1.5 py-0 rounded-full bg-surface-strong text-[9px]">
          {data.locality}
        </span>
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-green !border-0" />
    </div>
  );
}

function RuleNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className="px-2.5 py-1.5 rounded-md border border-dashed border-accent/50 bg-accent-soft min-w-[100px] text-center">
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-accent !border-0" />
      <div className="flex items-center justify-center gap-1">
        <Zap size={10} className="text-accent" />
        <span className="text-[10px] font-medium text-accent">{data.label}</span>
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-accent !border-0" />
    </div>
  );
}

const nodeTypes = {
  request: RequestNode,
  planner: PlannerNode,
  dispatcher: DispatcherNode,
  executor: ExecutorNode,
  consolidator: ConsolidatorNode,
  response: ResponseNode,
  backend: BackendNode,
  rule: RuleNode,
};

interface PlanStep {
  index: number;
  description: string;
  task_type: string;
  backend: string;
  model: string;
  status: 'pending' | 'running' | 'done';
}

/* ── Main component ── */

export default function Flow({ ws }: Props) {
  const [backends, setBackends] = useState<BackendInfo[]>([]);
  const [models, setModels] = useState<Record<string, ModelInfo[]>>({});
  const [rules, setRules] = useState<Record<string, RoutingRule>>({});
  const [health, setHealth] = useState<Record<string, boolean>>({});
  const [activeBackend, setActiveBackend] = useState<string | null>(null);
  const [activeModel, setActiveModel] = useState<string | null>(null);
  const [planSteps, setPlanSteps] = useState<PlanStep[]>([]);
  const [activePlanPhase, setActivePlanPhase] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch('/api/routing/backends').then((r) => r.json()),
      fetch('/api/models').then((r) => r.json()),
      fetch('/api/routing/rules').then((r) => r.json()),
      fetch('/api/models/health').then((r) => r.json()),
    ]).then(([b, m, r, h]) => {
      setBackends(b.backends || []);
      setModels(m || {});
      setRules(r.rules || {});
      setHealth(h || {});
    }).catch(() => {});
  }, []);

  useEffect(() => {
    return ws.on((msg) => {
      if (msg.type === 'model.routed') {
        setActiveBackend(msg.data?.backend as string);
        setActiveModel((msg.data?.model as string) || null);
        setTimeout(() => { setActiveBackend(null); setActiveModel(null); }, 3000);
      } else if (msg.type === 'plan.created') {
        const plan = (msg.data?.plan as PlanStep[]) || [];
        setPlanSteps(plan.map((s) => ({ ...s, status: 'pending' })));
        setActivePlanPhase('planning');
      } else if (msg.type === 'plan.step_start') {
        const idx = msg.data?.index as number;
        setPlanSteps((prev) => prev.map((s) =>
          s.index === idx ? { ...s, status: 'running' } : s,
        ));
        setActivePlanPhase('executing');
      } else if (msg.type === 'plan.step_done') {
        const idx = msg.data?.index as number;
        setPlanSteps((prev) => prev.map((s) =>
          s.index === idx ? { ...s, status: 'done' } : s,
        ));
      } else if (msg.type === 'plan.consolidated') {
        setActivePlanPhase('consolidated');
        setTimeout(() => { setPlanSteps([]); setActivePlanPhase(null); }, 5000);
      }
    });
  }, [ws]);

  const { flowNodes, flowEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    const hasOrchestration = planSteps.length > 0;

    if (hasOrchestration) {
      const COL = { request: 0, planner: 200, dispatcher: 400, executors: 620, consolidator: 860, response: 1060 };
      const ROW_GAP = 90;
      const centerY = Math.max(100, (planSteps.length * ROW_GAP) / 2);

      nodes.push({
        id: 'req',
        type: 'request',
        position: { x: COL.request, y: centerY },
        data: { label: 'user input', active: true },
      });

      nodes.push({
        id: 'planner',
        type: 'planner',
        position: { x: COL.planner, y: centerY },
        data: { active: activePlanPhase === 'planning' },
      });

      edges.push({
        id: 'req-planner',
        source: 'req',
        target: 'planner',
        animated: true,
        style: { stroke: 'var(--color-accent)', strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--color-accent)' },
      });

      nodes.push({
        id: 'dispatcher',
        type: 'dispatcher',
        position: { x: COL.dispatcher, y: centerY },
        data: { strategy: `${planSteps.length} tasks`, active: activePlanPhase === 'planning' || activePlanPhase === 'executing' },
      });

      edges.push({
        id: 'planner-dispatcher',
        source: 'planner',
        target: 'dispatcher',
        animated: true,
        style: { stroke: 'var(--color-accent)', strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--color-accent)' },
      });

      planSteps.forEach((step, i) => {
        const ey = 40 + i * ROW_GAP;
        const eid = `exec-${step.index}`;

        nodes.push({
          id: eid,
          type: 'executor',
          position: { x: COL.executors, y: ey },
          data: {
            label: `${step.task_type}: ${step.model || 'auto'}`,
            size: step.description.slice(0, 40),
            stepStatus: step.status,
            active: step.status === 'running',
          },
        });

        edges.push({
          id: `dispatch-${eid}`,
          source: 'dispatcher',
          target: eid,
          animated: step.status === 'running',
          style: {
            stroke: step.status === 'done' ? 'var(--color-green)'
              : step.status === 'running' ? '#f59e0b' : 'var(--color-border)',
            strokeWidth: step.status !== 'pending' ? 2 : 1,
          },
          markerEnd: { type: MarkerType.ArrowClosed },
        });

        edges.push({
          id: `${eid}-consolidator`,
          source: eid,
          target: 'consolidator',
          animated: step.status === 'done',
          style: {
            stroke: step.status === 'done' ? 'var(--color-green)' : 'var(--color-border)',
            strokeWidth: step.status === 'done' ? 2 : 1,
          },
          markerEnd: { type: MarkerType.ArrowClosed },
        });
      });

      nodes.push({
        id: 'consolidator',
        type: 'consolidator',
        position: { x: COL.consolidator, y: centerY },
        data: { active: activePlanPhase === 'consolidated' },
      });

      nodes.push({
        id: 'response',
        type: 'response',
        position: { x: COL.response, y: centerY },
        data: { active: activePlanPhase === 'consolidated' },
      });

      edges.push({
        id: 'consolidator-response',
        source: 'consolidator',
        target: 'response',
        animated: activePlanPhase === 'consolidated',
        style: { stroke: 'var(--color-accent)', strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--color-accent)' },
      });
    } else {
      // Standard routing view
      const COL = { request: 0, router: 200, rules: 400, backend: 500, model: 700 };
      const ROW_GAP = 80;

      nodes.push({
        id: 'req',
        type: 'request',
        position: { x: COL.request, y: 100 },
        data: { label: 'chat', active: !!activeBackend },
      });

      nodes.push({
        id: 'dispatcher',
        type: 'dispatcher',
        position: { x: COL.router, y: 100 },
        data: { strategy: 'local-first', active: !!activeBackend },
      });

      edges.push({
        id: 'req-router',
        source: 'req',
        target: 'dispatcher',
        animated: !!activeBackend,
        style: { stroke: 'var(--color-accent)', strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--color-accent)' },
      });

      backends.forEach((b, bi) => {
        const by = 40 + bi * (ROW_GAP * 2);
        const bid = `backend-${b.name}`;
        const isActive = activeBackend === b.name;

        nodes.push({
          id: bid,
          type: 'backend',
          position: { x: COL.backend, y: by },
          data: {
            label: b.name,
            locality: b.locality,
            healthy: health[b.name] ?? b.healthy,
            active: isActive,
          },
        });

        edges.push({
          id: `router-${bid}`,
          source: 'dispatcher',
          target: bid,
          animated: isActive,
          style: {
            stroke: isActive ? 'var(--color-green)' : 'var(--color-border)',
            strokeWidth: isActive ? 2 : 1,
          },
          markerEnd: { type: MarkerType.ArrowClosed, color: isActive ? 'var(--color-green)' : 'var(--color-border)' },
        });

        const backendModels = models[b.name] || [];
        backendModels.forEach((m, mi) => {
          const mid = `model-${b.name}-${m.name}`;
          const modelActive = isActive && (!activeModel || activeModel === m.name);

          nodes.push({
            id: mid,
            type: 'executor',
            position: { x: COL.model, y: by + mi * ROW_GAP },
            data: {
              label: m.name,
              size: m.size,
              quant: m.quantization,
              active: modelActive,
            },
          });

          edges.push({
            id: `${bid}-${mid}`,
            source: bid,
            target: mid,
            animated: modelActive,
            style: {
              stroke: modelActive ? 'var(--color-accent)' : 'var(--color-border)',
              strokeWidth: modelActive ? 2 : 1,
            },
            markerEnd: { type: MarkerType.ArrowClosed, color: modelActive ? 'var(--color-accent)' : 'var(--color-border)' },
          });
        });
      });

      const ruleEntries = Object.entries(rules);
      ruleEntries.forEach(([task, rule], ri) => {
        const rid = `rule-${task}`;
        const ry = 40 + (backends.length * ROW_GAP * 2) + ri * ROW_GAP;

        nodes.push({
          id: rid,
          type: 'rule',
          position: { x: COL.rules, y: ry },
          data: { label: task },
        });

        edges.push({
          id: `router-${rid}`,
          source: 'dispatcher',
          target: rid,
          style: { stroke: 'var(--color-accent)', strokeDasharray: '4 3', strokeWidth: 1 },
        });

        const targetBackend = `backend-${rule.preferred_backend}`;
        if (backends.some((b) => b.name === rule.preferred_backend)) {
          edges.push({
            id: `${rid}-${targetBackend}`,
            source: rid,
            target: targetBackend,
            style: { stroke: 'var(--color-accent)', strokeDasharray: '4 3', strokeWidth: 1 },
            markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--color-accent)' },
          });
        }
      });
    }

    return { flowNodes: nodes, flowEdges: edges };
  }, [backends, models, rules, health, activeBackend, activeModel, planSteps, activePlanPhase]);

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edgesState, setEdges, onEdgesChange] = useEdgesState(flowEdges);

  useEffect(() => {
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [flowNodes, flowEdges, setNodes, setEdges]);

  const proOptions = useMemo(() => ({ hideAttribution: true }), []);

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edgesState}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        proOptions={proOptions}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable
        nodesConnectable={false}
        minZoom={0.3}
        maxZoom={1.5}
      >
        <Background gap={16} size={1} className="!bg-surface-alt" />
        <Controls
          showInteractive={false}
          className="!bg-surface !border-border !shadow-sm [&>button]:!bg-surface
                     [&>button]:!border-border [&>button]:!text-stone-500
                     [&>button:hover]:!bg-surface-strong"
        />
      </ReactFlow>
    </div>
  );
}
