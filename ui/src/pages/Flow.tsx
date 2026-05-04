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
} from 'lucide-react';
import clsx from 'clsx';
import type { WsMessage } from '../hooks/useWebSocket';

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
    send: (d: Record<string, unknown>) => void;
    on: (fn: (m: WsMessage) => void) => () => void;
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
      <div className="text-[10px] text-gray-500 dark:text-gray-400 font-mono">
        {data.label || 'chat'}
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-accent !border-0" />
    </div>
  );
}

function RouterNode({ data }: NodeProps<Node<NodeData>>) {
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
        <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">ROUTER</span>
      </div>
      <div className="text-[10px] text-gray-500 dark:text-gray-400">
        {data.strategy || 'local-first'}
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-amber !border-0" />
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
      <div className="flex items-center gap-1 text-[10px] text-gray-500 dark:text-gray-400">
        <span className="px-1.5 py-0 rounded-full bg-surface-strong text-[9px]">
          {data.locality}
        </span>
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-green !border-0" />
    </div>
  );
}

function ModelNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={clsx(
      'px-3 py-2 rounded-lg border-2 min-w-[140px]',
      data.active
        ? 'border-accent bg-accent/10 shadow-md shadow-accent/20'
        : 'border-border bg-surface',
    )}>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-accent !border-0" />
      <div className="flex items-center gap-1.5 mb-0.5">
        <Cpu size={12} className="text-accent" />
        <span className="text-[11px] font-semibold truncate">{data.label}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {data.size && (
          <span className="text-[9px] px-1.5 rounded-full bg-surface-strong text-gray-500 dark:text-gray-400">
            {data.size}
          </span>
        )}
        {data.quant && (
          <span className="text-[9px] px-1.5 rounded-full bg-surface-strong text-gray-500 dark:text-gray-400">
            {data.quant}
          </span>
        )}
      </div>
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
  router: RouterNode,
  backend: BackendNode,
  model: ModelNode,
  rule: RuleNode,
};

/* ── Main component ── */

export default function Flow({ ws }: Props) {
  const [backends, setBackends] = useState<BackendInfo[]>([]);
  const [models, setModels] = useState<Record<string, ModelInfo[]>>({});
  const [rules, setRules] = useState<Record<string, RoutingRule>>({});
  const [health, setHealth] = useState<Record<string, boolean>>({});
  const [activeBackend, setActiveBackend] = useState<string | null>(null);
  const [activeModel, setActiveModel] = useState<string | null>(null);

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
      }
    });
  }, [ws]);

  const { flowNodes, flowEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    const COL = { request: 0, router: 200, rules: 400, backend: 500, model: 700 };
    const ROW_GAP = 80;

    // Request node
    nodes.push({
      id: 'req',
      type: 'request',
      position: { x: COL.request, y: 100 },
      data: { label: 'chat', active: !!activeBackend },
    });

    // Router node
    nodes.push({
      id: 'router',
      type: 'router',
      position: { x: COL.router, y: 100 },
      data: { strategy: 'local-first', active: !!activeBackend },
    });

    edges.push({
      id: 'req-router',
      source: 'req',
      target: 'router',
      animated: !!activeBackend,
      style: { stroke: 'var(--color-accent)', strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--color-accent)' },
    });

    // Backends + models
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
        source: 'router',
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
          type: 'model',
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

    // Routing rules as nodes
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
        source: 'router',
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

    return { flowNodes: nodes, flowEdges: edges };
  }, [backends, models, rules, health, activeBackend, activeModel]);

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
        minZoom={0.5}
        maxZoom={1.5}
      >
        <Background gap={16} size={1} className="!bg-surface-alt" />
        <Controls
          showInteractive={false}
          className="!bg-surface !border-border !shadow-sm [&>button]:!bg-surface
                     [&>button]:!border-border [&>button]:!text-gray-500
                     [&>button:hover]:!bg-surface-strong"
        />
      </ReactFlow>
    </div>
  );
}
