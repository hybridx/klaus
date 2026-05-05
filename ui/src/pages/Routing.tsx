import { useEffect, useState } from 'react';
import { Route, Plus, Trash2 } from 'lucide-react';

interface RoutingRule {
  preferred_backend: string;
  preferred_model?: string;
  fallback_backends?: string[];
  max_tokens?: number;
  temperature?: number;
}

interface ModelInfo {
  name: string;
  backend: string;
}

const TASK_OPTIONS = [
  'coding',
  'reasoning',
  'creative',
  'analysis',
  'summarization',
  'chat',
];

export default function Routing() {
  const [rules, setRules] = useState<Record<string, RoutingRule>>({});
  const [backends, setBackends] = useState<string[]>([]);
  const [allModels, setAllModels] = useState<ModelInfo[]>([]);

  const [newTask, setNewTask] = useState('');
  const [newBackend, setNewBackend] = useState('');
  const [newModel, setNewModel] = useState('');

  const load = () => {
    fetch('/api/routing/rules')
      .then((r) => r.json())
      .then((d) => setRules(d.rules || {}))
      .catch(() => {});

    fetch('/api/models')
      .then((r) => r.json())
      .then((data) => {
        const bk: string[] = [];
        const models: ModelInfo[] = [];
        for (const [backend, backendModels] of Object.entries(data)) {
          bk.push(backend);
          for (const m of backendModels as Array<{ name: string }>) {
            models.push({ name: m.name, backend });
          }
        }
        setBackends(bk);
        setAllModels(models);
        if (bk.length > 0 && !newBackend) setNewBackend(bk[0]);
      })
      .catch(() => {});
  };

  useEffect(load, []);

  const modelsForBackend = allModels.filter((m) => m.backend === newBackend);

  const add = async () => {
    if (!newTask || !newBackend) return;

    await fetch('/api/routing/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task: newTask,
        preferred_backend: newBackend,
        preferred_model: newModel || undefined,
      }),
    });
    setNewTask('');
    setNewModel('');
    load();
  };

  const remove = async (task: string) => {
    await fetch(`/api/routing/rules/${encodeURIComponent(task)}`, { method: 'DELETE' });
    load();
  };

  const usedTasks = new Set(Object.keys(rules));
  const availableTasks = TASK_OPTIONS.filter((t) => !usedTasks.has(t));

  return (
    <div className="h-full overflow-y-auto p-4 flex flex-col gap-4">
      <p className="text-[11px] text-stone-400 dark:text-stone-500">
        Route tasks to specific backends and models.
      </p>

      {/* Add form */}
      <div className="flex flex-wrap gap-2 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-stone-400 dark:text-stone-500 uppercase tracking-wider font-medium">
            Task
          </label>
          <select
            value={newTask}
            onChange={(e) => setNewTask(e.target.value)}
            className="border border-stone-200 dark:border-stone-700 rounded-lg
                       bg-transparent px-2.5 py-1.5 text-[12px] w-[140px]
                       text-stone-800 dark:text-stone-200
                       focus:outline-none focus:ring-1 focus:ring-stone-400"
          >
            <option value="">Select task...</option>
            {availableTasks.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
            <option value="_custom">Custom...</option>
          </select>
        </div>

        {newTask === '_custom' && (
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-stone-400 dark:text-stone-500 uppercase tracking-wider font-medium">
              Custom Task
            </label>
            <input
              placeholder="e.g. translation"
              value=""
              onChange={(e) => setNewTask(e.target.value)}
              className="border border-stone-200 dark:border-stone-700 rounded-lg
                         bg-transparent px-2.5 py-1.5 text-[12px] w-[140px]
                         text-stone-800 dark:text-stone-200
                         focus:outline-none focus:ring-1 focus:ring-stone-400"
            />
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-stone-400 dark:text-stone-500 uppercase tracking-wider font-medium">
            Backend
          </label>
          <select
            value={newBackend}
            onChange={(e) => { setNewBackend(e.target.value); setNewModel(''); }}
            className="border border-stone-200 dark:border-stone-700 rounded-lg
                       bg-transparent px-2.5 py-1.5 text-[12px] w-[140px]
                       text-stone-800 dark:text-stone-200
                       focus:outline-none focus:ring-1 focus:ring-stone-400"
          >
            {backends.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-stone-400 dark:text-stone-500 uppercase tracking-wider font-medium">
            Model
          </label>
          <select
            value={newModel}
            onChange={(e) => setNewModel(e.target.value)}
            className="border border-stone-200 dark:border-stone-700 rounded-lg
                       bg-transparent px-2.5 py-1.5 text-[12px] w-[160px]
                       text-stone-800 dark:text-stone-200
                       focus:outline-none focus:ring-1 focus:ring-stone-400"
          >
            <option value="">default</option>
            {modelsForBackend.map((m) => (
              <option key={m.name} value={m.name}>{m.name}</option>
            ))}
          </select>
        </div>

        <button
          onClick={add}
          disabled={!newTask || newTask === '_custom' || !newBackend}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium
                     bg-stone-800 dark:bg-stone-200 text-white dark:text-stone-900
                     hover:opacity-80 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <Plus size={12} /> Add
        </button>
      </div>

      {/* Rules list */}
      <div className="flex flex-col gap-1.5">
        {Object.entries(rules).map(([task, rule]) => (
          <div
            key={task}
            className="flex items-center gap-2.5 px-3 py-2.5
                       border border-stone-200 dark:border-stone-700 rounded-lg
                       bg-stone-50 dark:bg-stone-800/50"
          >
            <Route size={13} className="text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="text-[12px] font-semibold text-stone-800 dark:text-stone-200 min-w-[90px]">
              {task}
            </span>
            <span className="text-[11px] text-stone-500 dark:text-stone-400">
              → {rule.preferred_backend}
              {rule.preferred_model && (
                <span className="font-medium text-stone-700 dark:text-stone-300">
                  {' / '}{rule.preferred_model}
                </span>
              )}
            </span>
            {rule.fallback_backends && rule.fallback_backends.length > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full
                               bg-stone-100 dark:bg-stone-700
                               text-stone-400 dark:text-stone-500">
                +{rule.fallback_backends.length} fallback
              </span>
            )}
            <button
              onClick={() => remove(task)}
              className="ml-auto p-1 rounded-md text-stone-300 dark:text-stone-600
                         hover:text-red-500 dark:hover:text-red-400 transition-colors"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>

      {Object.keys(rules).length === 0 && (
        <div className="text-center text-[12px] text-stone-400 dark:text-stone-500 py-8">
          No routing rules configured. The router will use the default strategy.
        </div>
      )}
    </div>
  );
}
