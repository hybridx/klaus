import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ReactFlow,
  type Node,
  type Edge,
  useNodesState,
  useEdgesState,
  Background,
  Controls,
  BackgroundVariant,
  type NodeProps,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { X } from 'lucide-react';

interface GraphNode {
  id: string;
  label: string;
  path: string;
  parent: string | null;
  content_preview: string;
  tags: string[];
  branch: string;
  children_count: number;
  access_count: number;
}

interface DetailPanel {
  node: GraphNode;
  fullContent: string;
}

const BRANCH_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  knowledge: { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
  conversations: { bg: '#f3f4f6', border: '#9ca3af', text: '#4b5563' },
  superpowers: { bg: '#ede9fe', border: '#8b5cf6', text: '#5b21b6' },
  root: { bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
};

const DARK_BRANCH_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  knowledge: { bg: '#1e3a5f', border: '#60a5fa', text: '#bfdbfe' },
  conversations: { bg: '#292524', border: '#78716c', text: '#d6d3d1' },
  superpowers: { bg: '#2e1065', border: '#a78bfa', text: '#ddd6fe' },
  root: { bg: '#451a03', border: '#fbbf24', text: '#fef3c7' },
};

function getColors(branch: string, isDark: boolean) {
  const palette = isDark ? DARK_BRANCH_COLORS : BRANCH_COLORS;
  return palette[branch] || palette.knowledge;
}

type KnowledgeNodeData = { label: string; branch: string; childrenCount: number; accessCount: number };

function KnowledgeNode({ data }: NodeProps<Node<KnowledgeNodeData>>) {
  const isDark = document.documentElement.classList.contains('dark');
  const colors = getColors(data.branch, isDark);
  const size = Math.max(40, Math.min(70, 40 + (data.childrenCount ?? 0) * 5));

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div
        className="flex items-center justify-center rounded-full cursor-pointer
                    transition-transform hover:scale-110 shadow-md"
        style={{
          width: size,
          height: size,
          backgroundColor: colors.bg,
          border: `2px solid ${colors.border}`,
        }}
      >
        <span
          className="text-[9px] font-medium leading-tight text-center px-1 truncate"
          style={{ color: colors.text, maxWidth: size - 8 }}
        >
          {data.label}
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </>
  );
}

const nodeTypes = { knowledge: KnowledgeNode };

function layoutTree(graphNodes: GraphNode[]): { nodes: Node[]; edges: Edge[] } {
  const byId = new Map(graphNodes.map((n) => [n.id, n]));
  const childrenMap = new Map<string, GraphNode[]>();

  for (const n of graphNodes) {
    if (n.parent) {
      const siblings = childrenMap.get(n.parent) || [];
      siblings.push(n);
      childrenMap.set(n.parent, siblings);
    }
  }

  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const H_SPACING = 100;
  const V_SPACING = 100;

  let xCounter = 0;

  function place(id: string, depth: number): number {
    const gn = byId.get(id);
    if (!gn) return xCounter;

    const children = childrenMap.get(id) || [];

    if (children.length === 0) {
      const x = xCounter * H_SPACING;
      xCounter++;
      nodes.push({
        id: gn.id,
        type: 'knowledge',
        position: { x, y: depth * V_SPACING },
        data: { label: gn.label, branch: gn.branch, childrenCount: gn.children_count, accessCount: gn.access_count },
      });
      return x;
    }

    const childXValues: number[] = [];
    for (const child of children) {
      const cx = place(child.id, depth + 1);
      childXValues.push(cx);
      edges.push({
        id: `${gn.id}-${child.id}`,
        source: gn.id,
        target: child.id,
        style: { stroke: '#a8a29e', strokeWidth: 1 },
        animated: false,
      });
    }

    const x = (Math.min(...childXValues) + Math.max(...childXValues)) / 2;
    nodes.push({
      id: gn.id,
      type: 'knowledge',
      position: { x, y: depth * V_SPACING },
      data: { label: gn.label, branch: gn.branch, childrenCount: gn.children_count, accessCount: gn.access_count },
    });
    return x;
  }

  const root = graphNodes.find((n) => !n.parent);
  if (root) place(root.id, 0);

  return { nodes, edges };
}

export default function Knowledge() {
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [detail, setDetail] = useState<DetailPanel | null>(null);

  useEffect(() => {
    fetch('/api/memory/graph')
      .then((r) => r.json())
      .then((data) => {
        setGraphNodes(data.nodes ?? []);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (graphNodes.length === 0) return;
    const { nodes: n, edges: e } = layoutTree(graphNodes);
    setNodes(n);
    setEdges(e);
  }, [graphNodes]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    const gn = graphNodes.find((g) => g.id === node.id);
    if (!gn) return;

    fetch(`/api/memory/get?path=${encodeURIComponent(gn.path)}`)
      .then((r) => r.json())
      .then((data) => {
        setDetail({ node: gn, fullContent: data.content || '(empty)' });
      })
      .catch(() => {});
  }, [graphNodes]);

  const stats = useMemo(() => {
    const branches: Record<string, number> = {};
    for (const n of graphNodes) {
      branches[n.branch] = (branches[n.branch] || 0) + 1;
    }
    return branches;
  }, [graphNodes]);

  return (
    <div className="h-full flex">
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.2}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
          <Controls />
        </ReactFlow>

        {/* Legend */}
        <div className="absolute top-3 left-3 bg-surface/90 backdrop-blur border border-border
                        rounded-lg px-3 py-2 text-[10px] space-y-1">
          <div className="font-medium text-stone-600 dark:text-stone-300 mb-1">
            {graphNodes.length} nodes
          </div>
          {Object.entries(stats).map(([branch, count]) => {
            const isDark = document.documentElement.classList.contains('dark');
            const colors = getColors(branch, isDark);
            return (
              <div key={branch} className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors.border }} />
                <span className="text-stone-600 dark:text-stone-400">{branch} ({count})</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Detail panel */}
      {detail && (
        <div className="w-72 shrink-0 border-l border-border bg-surface-alt overflow-y-auto">
          <div className="flex items-center justify-between px-3 py-2 border-b border-border">
            <span className="text-[12px] font-medium text-stone-700 dark:text-stone-300 truncate">
              {detail.node.label}
            </span>
            <button onClick={() => setDetail(null)} className="text-stone-400 hover:text-stone-600 dark:hover:text-stone-300">
              <X size={14} />
            </button>
          </div>
          <div className="px-3 py-2 space-y-3 text-[12px]">
            <div>
              <div className="text-[10px] text-stone-400 dark:text-stone-500 uppercase tracking-wider mb-0.5">Path</div>
              <div className="font-mono text-stone-600 dark:text-stone-300 break-all">{detail.node.path}</div>
            </div>
            {detail.node.tags.length > 0 && (
              <div>
                <div className="text-[10px] text-stone-400 dark:text-stone-500 uppercase tracking-wider mb-0.5">Tags</div>
                <div className="flex flex-wrap gap-1">
                  {detail.node.tags.map((t) => (
                    <span key={t} className="px-1.5 py-0.5 rounded bg-stone-100 dark:bg-stone-800
                                              text-[10px] text-stone-600 dark:text-stone-400">{t}</span>
                  ))}
                </div>
              </div>
            )}
            <div>
              <div className="text-[10px] text-stone-400 dark:text-stone-500 uppercase tracking-wider mb-0.5">Content</div>
              <div className="msg-text text-stone-700 dark:text-stone-300 whitespace-pre-wrap break-words leading-relaxed">
                {detail.fullContent}
              </div>
            </div>
            <div className="flex gap-4 text-[10px] text-stone-400 dark:text-stone-500">
              <span>Children: {detail.node.children_count}</span>
              <span>Accessed: {detail.node.access_count}x</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
