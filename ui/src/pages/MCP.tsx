import { useEffect, useState } from 'react';
import { Server, Wrench, Circle, Loader2, Plus, Trash2 } from 'lucide-react';
import clsx from 'clsx';

interface MCPServer {
  name: string;
  status: string;
  tools: { name: string; description: string }[];
}

export default function MCP() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: '', command: '', args: '' });

  const load = () => {
    fetch('/api/mcp/servers')
      .then((r) => r.json())
      .then((d) => setServers(d.servers || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const addServer = async () => {
    if (!form.name || !form.command) return;
    await fetch('/api/mcp/servers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: form.name,
        command: form.command,
        args: form.args ? form.args.split(' ') : [],
      }),
    });
    setForm({ name: '', command: '', args: '' });
    setShowAdd(false);
    load();
  };

  const removeServer = async (name: string) => {
    await fetch(`/api/mcp/servers/${name}`, { method: 'DELETE' });
    load();
  };

  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-4 flex items-center justify-center">
        <div className="flex items-center gap-2 text-stone-400">
          <Loader2 size={14} className="animate-spin" />
          <span className="text-[11px]">Loading MCP servers...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-stone-400 dark:text-stone-600">
          Model Context Protocol servers and their tools.
        </p>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md
                     bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400
                     hover:bg-stone-200 dark:hover:bg-stone-700 transition-colors"
        >
          <Plus size={12} /> Add Server
        </button>
      </div>

      {showAdd && (
        <div className="border border-border rounded-lg bg-surface p-3 flex flex-col gap-2">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Server name"
            className="text-[12px] px-2 py-1.5 rounded-md border border-border bg-surface
                       text-stone-800 dark:text-stone-200 placeholder:text-stone-400"
          />
          <input
            value={form.command}
            onChange={(e) => setForm({ ...form, command: e.target.value })}
            placeholder="Command (e.g. npx)"
            className="text-[12px] px-2 py-1.5 rounded-md border border-border bg-surface
                       text-stone-800 dark:text-stone-200 placeholder:text-stone-400"
          />
          <input
            value={form.args}
            onChange={(e) => setForm({ ...form, args: e.target.value })}
            placeholder="Arguments (space-separated)"
            className="text-[12px] px-2 py-1.5 rounded-md border border-border bg-surface
                       text-stone-800 dark:text-stone-200 placeholder:text-stone-400"
          />
          <button
            onClick={addServer}
            className="self-end text-[11px] px-3 py-1 rounded-md bg-stone-800 dark:bg-stone-200
                       text-white dark:text-stone-900 hover:opacity-80 transition-opacity"
          >
            Register
          </button>
        </div>
      )}

      {servers.map((s) => (
        <div key={s.name} className="border border-border rounded-lg bg-surface overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-surface-alt">
            <Server size={13} className={s.status === 'connected' ? 'text-green' : 'text-stone-400'} />
            <span className="text-[12px] font-semibold">{s.name}</span>
            <Circle
              size={6}
              className={clsx('ml-1', s.status === 'connected' ? 'fill-green text-green' : 'fill-amber-400 text-amber-400')}
            />
            <span className={clsx(
              'text-[10px]',
              s.status === 'connected' ? 'text-green' : 'text-amber-500',
            )}>
              {s.status}
            </span>
            <button
              onClick={() => removeServer(s.name)}
              className="ml-auto p-1 rounded text-stone-400 hover:text-red-500 transition-colors"
            >
              <Trash2 size={12} />
            </button>
          </div>
          {s.tools.length === 0 ? (
            <div className="px-3 py-2 text-[11px] text-stone-400">No tools discovered</div>
          ) : (
            <div className="divide-y divide-border">
              {s.tools.map((t) => (
                <div key={t.name} className="flex items-start gap-2 px-3 py-2">
                  <Wrench size={11} className="text-stone-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="text-[12px] font-medium text-stone-700 dark:text-stone-300">{t.name}</span>
                    {t.description && (
                      <p className="text-[10px] text-stone-400 dark:text-stone-500 mt-0.5">{t.description}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {servers.length === 0 && (
        <div className="text-center text-[12px] text-stone-400 py-8">
          No MCP servers registered. Add one above or configure in klaus.yaml.
        </div>
      )}
    </div>
  );
}
