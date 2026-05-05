import { useEffect, useState } from 'react';
import { Route, Plus, Trash2, ChevronDown, ChevronRight, Pencil, Check, X, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';

interface RoutingRule {
  preferred_backend: string;
  preferred_model?: string;
  fallback_backends?: string[];
  keywords?: string[];
  description?: string;
  max_tokens?: number;
  temperature?: number;
}

interface ModelInfo {
  name: string;
  backend: string;
}

export default function Routing() {
  const [rules, setRules] = useState<Record<string, RoutingRule>>({});
  const [backends, setBackends] = useState<string[]>([]);
  const [allModels, setAllModels] = useState<ModelInfo[]>([]);

  const [taskMode, setTaskMode] = useState<'select' | 'custom'>('select');
  const [newTask, setNewTask] = useState('');
  const [customTask, setCustomTask] = useState('');
  const [newBackend, setNewBackend] = useState('');
  const [newModel, setNewModel] = useState('');
  const [newKeywords, setNewKeywords] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [addError, setAddError] = useState('');

  const [expanded, setExpanded] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editBackend, setEditBackend] = useState('');
  const [editModel, setEditModel] = useState('');
  const [editKeywords, setEditKeywords] = useState('');
  const [editDescription, setEditDescription] = useState('');

  const effectiveTask = taskMode === 'custom' ? customTask : newTask;

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

  const modelsForBackend = (backend: string) => allModels.filter((m) => m.backend === backend);

  const add = async () => {
    const task = effectiveTask.trim();
    if (!task || !newBackend) return;
    setAddError('');

    const resp = await fetch('/api/routing/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task,
        preferred_backend: newBackend,
        preferred_model: newModel || undefined,
        keywords: newKeywords ? newKeywords.split(',').map((k) => k.trim()).filter(Boolean) : [],
        description: newDescription,
      }),
    });

    if (resp.status === 409) {
      const err = await resp.json();
      setAddError(err.detail || 'Keyword conflict with existing intent');
      return;
    }

    setNewTask('');
    setCustomTask('');
    setTaskMode('select');
    setNewModel('');
    setNewKeywords('');
    setNewDescription('');
    setAddError('');
    load();
  };

  const remove = async (task: string) => {
    await fetch(`/api/routing/rules/${encodeURIComponent(task)}`, { method: 'DELETE' });
    if (expanded === task) setExpanded(null);
    if (editing === task) setEditing(null);
    load();
  };

  const startEdit = (task: string, rule: RoutingRule) => {
    setEditing(task);
    setExpanded(task);
    setEditBackend(rule.preferred_backend || backends[0] || '');
    setEditModel(rule.preferred_model || '');
    setEditKeywords((rule.keywords || []).join(', '));
    setEditDescription(rule.description || '');
  };

  const saveEdit = async (task: string) => {
    const resp = await fetch(`/api/routing/rules/${encodeURIComponent(task)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        preferred_backend: editBackend || undefined,
        preferred_model: editModel || undefined,
        keywords: editKeywords ? editKeywords.split(',').map((k) => k.trim()).filter(Boolean) : [],
        description: editDescription,
      }),
    });

    if (resp.status === 409) {
      const err = await resp.json();
      setAddError(err.detail || 'Keyword conflict');
      return;
    }

    setEditing(null);
    setAddError('');
    load();
  };

  const cancelEdit = () => {
    setEditing(null);
    setAddError('');
  };

  const existingTasks = Object.keys(rules);

  return (
    <div className="h-full overflow-y-auto p-6 flex flex-col gap-4">
      <p className="text-[13px] text-stone-600 dark:text-stone-400">
        Route tasks to specific backends and models. Add keywords for smarter automatic classification.
      </p>

      {/* Add form */}
      <div className="border border-border rounded-lg bg-surface p-3 flex flex-col gap-2.5">
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-stone-400 uppercase tracking-wider font-medium">
              Intent
            </label>
            <select
              value={taskMode === 'custom' ? '_custom' : newTask}
              onChange={(e) => {
                if (e.target.value === '_custom') {
                  setTaskMode('custom');
                  setCustomTask('');
                } else {
                  setTaskMode('select');
                  setNewTask(e.target.value);
                }
              }}
              className="border border-stone-200 dark:border-stone-700 rounded-lg
                         bg-transparent px-2.5 py-1.5 text-[12px] w-[140px]
                         text-stone-800 dark:text-stone-200
                         focus:outline-none focus:ring-1 focus:ring-stone-400"
            >
              <option value="">Select intent...</option>
              {existingTasks.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
              <option value="_custom">Custom...</option>
            </select>
          </div>

          {taskMode === 'custom' && (
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-stone-400 uppercase tracking-wider font-medium">
                Name
              </label>
              <input
                placeholder="e.g. translation"
                value={customTask}
                onChange={(e) => setCustomTask(e.target.value)}
                autoFocus
                className="border border-stone-200 dark:border-stone-700 rounded-lg
                           bg-transparent px-2.5 py-1.5 text-[12px] w-[130px]
                           text-stone-800 dark:text-stone-200
                           focus:outline-none focus:ring-1 focus:ring-stone-400"
              />
            </div>
          )}

          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-stone-400 uppercase tracking-wider font-medium">
              Backend
            </label>
            <select
              value={newBackend}
              onChange={(e) => { setNewBackend(e.target.value); setNewModel(''); }}
              className="border border-stone-200 dark:border-stone-700 rounded-lg
                         bg-transparent px-2.5 py-1.5 text-[12px] w-[120px]
                         text-stone-800 dark:text-stone-200
                         focus:outline-none focus:ring-1 focus:ring-stone-400"
            >
              {backends.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-stone-400 uppercase tracking-wider font-medium">
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
              {modelsForBackend(newBackend).map((m) => (
                <option key={m.name} value={m.name}>{m.name}</option>
              ))}
            </select>
          </div>

          <button
            onClick={add}
            disabled={!effectiveTask.trim() || !newBackend}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium
                       bg-stone-800 dark:bg-stone-200 text-white dark:text-stone-900
                       hover:opacity-80 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Plus size={12} /> Add
          </button>
        </div>

        {/* Keywords + description row */}
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex flex-col gap-1 flex-1 min-w-[200px]">
            <label className="text-[10px] text-stone-400 uppercase tracking-wider font-medium">
              Keywords (comma-separated)
            </label>
            <input
              placeholder="e.g. translate, language, i18n, localize"
              value={newKeywords}
              onChange={(e) => setNewKeywords(e.target.value)}
              className="border border-stone-200 dark:border-stone-700 rounded-lg
                         bg-transparent px-2.5 py-1.5 text-[12px]
                         text-stone-800 dark:text-stone-200
                         focus:outline-none focus:ring-1 focus:ring-stone-400"
            />
          </div>
          <div className="flex flex-col gap-1 flex-1 min-w-[200px]">
            <label className="text-[10px] text-stone-400 uppercase tracking-wider font-medium">
              Description
            </label>
            <input
              placeholder="What this intent is for"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              className="border border-stone-200 dark:border-stone-700 rounded-lg
                         bg-transparent px-2.5 py-1.5 text-[12px]
                         text-stone-800 dark:text-stone-200
                         focus:outline-none focus:ring-1 focus:ring-stone-400"
            />
          </div>
        </div>

        {addError && (
          <div className="flex items-center gap-1.5 text-[11px] text-amber-500">
            <AlertTriangle size={12} /> {addError}
          </div>
        )}
      </div>

      {/* Rules list */}
      <div className="flex flex-col gap-1.5">
        {Object.entries(rules).map(([task, rule]) => {
          const isExpanded = expanded === task;
          const isEditing = editing === task;

          return (
            <div
              key={task}
              className="border border-stone-200 dark:border-stone-700 rounded-lg
                         bg-white dark:bg-stone-800/50 shadow-sm overflow-hidden"
            >
              {/* Header row */}
              <div className="flex items-center gap-3 px-4 py-3">
                <button
                  onClick={() => setExpanded(isExpanded ? null : task)}
                  className="text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300 transition-colors"
                >
                  {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                <Route size={16} className="text-stone-500 dark:text-stone-400 shrink-0" />
                <span className="text-[13px] font-semibold text-stone-800 dark:text-stone-200 min-w-[90px]">
                  {task}
                </span>

                {!isEditing ? (
                  <>
                    <span className="text-[12px] text-stone-600 dark:text-stone-400">
                      &rarr; {rule.preferred_backend}
                      {rule.preferred_model && (
                        <span className="font-medium text-stone-800 dark:text-stone-300">
                          {' / '}{rule.preferred_model}
                        </span>
                      )}
                    </span>
                    {rule.fallback_backends && rule.fallback_backends.length > 0 && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full
                                       bg-stone-200 dark:bg-stone-700
                                       text-stone-600 dark:text-stone-400 font-medium">
                        +{rule.fallback_backends.length} fallback
                      </span>
                    )}
                    {rule.keywords && rule.keywords.length > 0 && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full
                                       bg-blue-100 dark:bg-blue-900/30
                                       text-blue-700 dark:text-blue-400 font-medium">
                        {rule.keywords.length} keywords
                      </span>
                    )}
                  </>
                ) : (
                  <div className="flex items-center gap-2 flex-1">
                    <select
                      value={editBackend}
                      onChange={(e) => { setEditBackend(e.target.value); setEditModel(''); }}
                      className="border border-stone-300 dark:border-stone-600 rounded-lg px-2 py-1
                                 text-[12px] bg-white dark:bg-transparent text-stone-800 dark:text-stone-200"
                    >
                      {backends.map((b) => (
                        <option key={b} value={b}>{b}</option>
                      ))}
                    </select>
                    <select
                      value={editModel}
                      onChange={(e) => setEditModel(e.target.value)}
                      className="border border-stone-300 dark:border-stone-600 rounded-lg px-2 py-1
                                 text-[12px] bg-white dark:bg-transparent text-stone-800 dark:text-stone-200"
                    >
                      <option value="">default</option>
                      {modelsForBackend(editBackend).map((m) => (
                        <option key={m.name} value={m.name}>{m.name}</option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="ml-auto flex items-center gap-1.5">
                  {isEditing ? (
                    <>
                      <button
                        onClick={() => saveEdit(task)}
                        className="p-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-900/20
                                   text-emerald-600 dark:text-emerald-400
                                   hover:bg-emerald-100 dark:hover:bg-emerald-900/40 transition-colors"
                        title="Save"
                      >
                        <Check size={15} />
                      </button>
                      <button
                        onClick={cancelEdit}
                        className="p-1.5 rounded-lg text-stone-500 dark:text-stone-400
                                   hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
                        title="Cancel"
                      >
                        <X size={15} />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => startEdit(task, rule)}
                        className="p-1.5 rounded-lg text-stone-400 dark:text-stone-500
                                   hover:text-stone-700 dark:hover:text-stone-300
                                   hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
                        title="Edit"
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        onClick={() => remove(task)}
                        className="p-1.5 rounded-lg text-stone-400 dark:text-stone-500
                                   hover:text-red-600 dark:hover:text-red-400
                                   hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={15} />
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="px-3 pb-3 pt-0 border-t border-stone-200 dark:border-stone-700">
                  {isEditing ? (
                    <div className="flex flex-col gap-2 pt-2.5">
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] text-stone-400 uppercase tracking-wider font-medium">
                          Keywords
                        </label>
                        <input
                          value={editKeywords}
                          onChange={(e) => setEditKeywords(e.target.value)}
                          placeholder="comma-separated keywords"
                          className="border border-stone-200 dark:border-stone-700 rounded-lg
                                     bg-transparent px-2.5 py-1.5 text-[12px]
                                     text-stone-800 dark:text-stone-200
                                     focus:outline-none focus:ring-1 focus:ring-stone-400"
                        />
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-[10px] text-stone-400 uppercase tracking-wider font-medium">
                          Description
                        </label>
                        <input
                          value={editDescription}
                          onChange={(e) => setEditDescription(e.target.value)}
                          placeholder="What this intent is for"
                          className="border border-stone-200 dark:border-stone-700 rounded-lg
                                     bg-transparent px-2.5 py-1.5 text-[12px]
                                     text-stone-800 dark:text-stone-200
                                     focus:outline-none focus:ring-1 focus:ring-stone-400"
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1.5 pt-2.5">
                      {rule.description && (
                        <p className="text-[11px] text-stone-500 dark:text-stone-400">
                          {rule.description}
                        </p>
                      )}
                      {rule.keywords && rule.keywords.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {rule.keywords.map((kw) => (
                            <span
                              key={kw}
                              className="text-[10px] px-1.5 py-0.5 rounded-md
                                         bg-stone-100 dark:bg-stone-700
                                         text-stone-500 dark:text-stone-400"
                            >
                              {kw}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <p className="text-[10px] text-stone-400 italic">
                          No keywords — this intent is only matched by name.
                          Click edit to add keywords for automatic classification.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {Object.keys(rules).length === 0 && (
        <div className="text-center text-[12px] text-stone-400 dark:text-stone-500 py-8">
          No routing rules configured. Add an intent above to route tasks to specific models.
        </div>
      )}
    </div>
  );
}
