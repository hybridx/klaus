import { useEffect, useState, useRef } from 'react';
import { Route, Plus, Trash2 } from 'lucide-react';

interface RoutingRule {
  preferred_backend: string;
  preferred_model?: string;
  fallback_backends?: string[];
  max_tokens?: number;
  temperature?: number;
}

export default function Routing() {
  const [rules, setRules] = useState<Record<string, RoutingRule>>({});
  const [backends, setBackends] = useState<string[]>([]);
  const taskRef = useRef<HTMLInputElement>(null);
  const backendRef = useRef<HTMLSelectElement>(null);
  const modelRef = useRef<HTMLInputElement>(null);

  const load = () => {
    fetch('/api/routing/rules').then((r) => r.json()).then((d) => setRules(d.rules || {})).catch(() => {});
    fetch('/api/models/backends').then((r) => r.json()).then((d) => setBackends(d.backends || [])).catch(() => {});
  };

  useEffect(load, []);

  const add = async () => {
    const task = taskRef.current?.value.trim();
    const backend = backendRef.current?.value;
    if (!task || !backend) return;

    await fetch('/api/routing/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task,
        preferred_backend: backend,
        preferred_model: modelRef.current?.value.trim() || undefined,
      }),
    });
    taskRef.current!.value = '';
    modelRef.current!.value = '';
    load();
  };

  const remove = async (task: string) => {
    await fetch(`/api/routing/rules/${encodeURIComponent(task)}`, { method: 'DELETE' });
    load();
  };

  return (
    <div className="h-full overflow-y-auto p-4 flex flex-col gap-3">
      <p className="text-[11px] text-gray-400 dark:text-gray-600">
        Route tasks to specific backends and models.
      </p>

      {/* Add form */}
      <div className="flex flex-wrap gap-2 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-gray-400 uppercase tracking-wider">Task</label>
          <input
            ref={taskRef}
            placeholder="e.g. code"
            className="border border-border rounded-md bg-surface px-2.5 py-1.5 text-[12px]
                       w-[120px] focus:outline-none focus:border-accent"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-gray-400 uppercase tracking-wider">Backend</label>
          <select
            ref={backendRef}
            className="border border-border rounded-md bg-surface px-2.5 py-1.5 text-[12px]
                       w-[120px] focus:outline-none focus:border-accent"
          >
            {backends.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-gray-400 uppercase tracking-wider">Model (opt)</label>
          <input
            ref={modelRef}
            placeholder="default"
            className="border border-border rounded-md bg-surface px-2.5 py-1.5 text-[12px]
                       w-[120px] focus:outline-none focus:border-accent"
          />
        </div>
        <button
          onClick={add}
          className="flex items-center gap-1 px-3 py-1.5 rounded-md bg-accent text-white text-[11px]
                     font-medium hover:bg-accent/90 transition-colors"
        >
          <Plus size={12} /> Add
        </button>
      </div>

      {/* Rules list */}
      <div className="flex flex-col gap-1">
        {Object.entries(rules).map(([task, rule]) => (
          <div
            key={task}
            className="flex items-center gap-2 px-3 py-2 border border-border rounded-lg bg-surface"
          >
            <Route size={12} className="text-accent shrink-0" />
            <span className="text-[12px] font-semibold min-w-[70px]">{task}</span>
            <span className="text-[11px] text-gray-500 dark:text-gray-400">
              → {rule.preferred_backend}
              {rule.preferred_model && ` / ${rule.preferred_model}`}
            </span>
            {rule.fallback_backends && rule.fallback_backends.length > 0 && (
              <span className="text-[10px] px-1.5 rounded-full bg-surface-strong text-gray-400">
                +{rule.fallback_backends.length} fallback
              </span>
            )}
            <button
              onClick={() => remove(task)}
              className="ml-auto p-1 rounded text-gray-400 hover:text-red transition-colors"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>

      {Object.keys(rules).length === 0 && (
        <div className="text-center text-[12px] text-gray-400 py-8">
          No routing rules configured. The router will use the default strategy.
        </div>
      )}
    </div>
  );
}
