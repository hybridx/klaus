import { useEffect, useState } from 'react';
import { Server, Wrench, Loader2, Plus, Trash2, Plug, ChevronDown, ChevronRight, Globe, Terminal, AlertCircle, RefreshCw } from 'lucide-react';
import clsx from 'clsx';

interface MCPTool {
  name: string;
  description: string;
}

interface MCPServer {
  name: string;
  status: string;
  transport: string;
  command?: string;
  url?: string;
  tools: MCPTool[];
  error?: string | null;
}

type TransportType = 'stdio' | 'sse';

export default function MCP() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);

  const [transport, setTransport] = useState<TransportType>('stdio');
  const [form, setForm] = useState({
    name: '', command: '', args: '', url: '', headerKey: '', headerVal: '',
  });
  const [headers, setHeaders] = useState<Record<string, string>>({});

  const load = () => {
    fetch('/api/mcp/servers')
      .then((r) => r.json())
      .then((d) => setServers(d.servers || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const addServer = async () => {
    const payload: Record<string, unknown> = {
      name: form.name,
      auto_connect: true,
    };
    if (transport === 'sse') {
      if (!form.name || !form.url) return;
      payload.url = form.url;
      if (Object.keys(headers).length > 0) payload.headers = headers;
    } else {
      if (!form.name || !form.command) return;
      payload.command = form.command;
      payload.args = form.args ? form.args.split(' ').filter(Boolean) : [];
    }

    try {
      const resp = await fetch('/api/mcp/servers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
        alert(err.detail || 'Failed to register server');
        return;
      }
    } catch { /* */ }

    setForm({ name: '', command: '', args: '', url: '', headerKey: '', headerVal: '' });
    setHeaders({});
    setShowAdd(false);
    load();
  };

  const connectServer = async (name: string) => {
    setConnecting(name);
    try {
      const resp = await fetch(`/api/mcp/servers/${name}/connect`, { method: 'POST' });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Connection failed' }));
        alert(err.detail || 'Connection failed');
      }
      load();
    } catch { /* */ }
    setConnecting(null);
  };

  const removeServer = async (name: string) => {
    await fetch(`/api/mcp/servers/${name}`, { method: 'DELETE' });
    load();
  };

  const addHeader = () => {
    if (!form.headerKey) return;
    setHeaders((prev) => ({ ...prev, [form.headerKey]: form.headerVal }));
    setForm((f) => ({ ...f, headerKey: '', headerVal: '' }));
  };

  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-6 flex items-center justify-center">
        <div className="flex items-center gap-2 text-stone-500 dark:text-stone-400">
          <Loader2 size={16} className="animate-spin" />
          <span className="text-[13px]">Loading MCP servers...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 flex flex-col gap-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <p className="text-[13px] text-stone-600 dark:text-stone-400">
          Manage MCP servers — connect via command (stdio) or URL (SSE/HTTP).
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1 text-[12px] px-2.5 py-1.5 rounded-lg
                       text-stone-600 dark:text-stone-400
                       hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
          >
            <RefreshCw size={13} /> Refresh
          </button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="flex items-center gap-1 text-[12px] px-3 py-1.5 rounded-lg font-medium
                       bg-stone-800 dark:bg-stone-200 text-white dark:text-stone-900
                       hover:opacity-80 transition-opacity"
          >
            <Plus size={13} /> Add Server
          </button>
        </div>
      </div>

      {/* Add server form */}
      {showAdd && (
        <div className="border border-stone-200 dark:border-stone-700 rounded-xl
                        bg-white dark:bg-stone-800/60 shadow-sm p-4 flex flex-col gap-3">
          <div className="text-[13px] font-semibold text-stone-800 dark:text-stone-200">
            New MCP Server
          </div>

          {/* Transport toggle */}
          <div className="flex items-center gap-1 p-0.5 bg-stone-100 dark:bg-stone-700 rounded-lg w-fit">
            <button
              onClick={() => setTransport('stdio')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors',
                transport === 'stdio'
                  ? 'bg-white dark:bg-stone-600 text-stone-800 dark:text-stone-100 shadow-sm'
                  : 'text-stone-500 dark:text-stone-400',
              )}
            >
              <Terminal size={13} /> Command (stdio)
            </button>
            <button
              onClick={() => setTransport('sse')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors',
                transport === 'sse'
                  ? 'bg-white dark:bg-stone-600 text-stone-800 dark:text-stone-100 shadow-sm'
                  : 'text-stone-500 dark:text-stone-400',
              )}
            >
              <Globe size={13} /> URL (SSE/HTTP)
            </button>
          </div>

          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Server name (e.g. filesystem, github)"
            className="text-[13px] px-3 py-2 rounded-lg border border-stone-200 dark:border-stone-600
                       bg-white dark:bg-stone-700 text-stone-800 dark:text-stone-200
                       placeholder:text-stone-400 dark:placeholder:text-stone-500
                       focus:outline-none focus:ring-2 focus:ring-blue-400/50"
          />

          {transport === 'stdio' ? (
            <>
              <input
                value={form.command}
                onChange={(e) => setForm({ ...form, command: e.target.value })}
                placeholder="Command (e.g. npx, uvx, node)"
                className="text-[13px] px-3 py-2 rounded-lg border border-stone-200 dark:border-stone-600
                           bg-white dark:bg-stone-700 text-stone-800 dark:text-stone-200
                           placeholder:text-stone-400 dark:placeholder:text-stone-500
                           focus:outline-none focus:ring-2 focus:ring-blue-400/50"
              />
              <input
                value={form.args}
                onChange={(e) => setForm({ ...form, args: e.target.value })}
                placeholder="Arguments (space-separated, e.g. -y @modelcontextprotocol/server-filesystem /tmp)"
                className="text-[13px] px-3 py-2 rounded-lg border border-stone-200 dark:border-stone-600
                           bg-white dark:bg-stone-700 text-stone-800 dark:text-stone-200
                           placeholder:text-stone-400 dark:placeholder:text-stone-500
                           focus:outline-none focus:ring-2 focus:ring-blue-400/50"
              />
            </>
          ) : (
            <>
              <input
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="SSE endpoint URL (e.g. https://mcp.atlassian.com/v1/mcp/authv2)"
                className="text-[13px] px-3 py-2 rounded-lg border border-stone-200 dark:border-stone-600
                           bg-white dark:bg-stone-700 text-stone-800 dark:text-stone-200
                           placeholder:text-stone-400 dark:placeholder:text-stone-500
                           focus:outline-none focus:ring-2 focus:ring-blue-400/50"
              />
              <div className="flex flex-col gap-2">
                <span className="text-[11px] font-medium text-stone-500 dark:text-stone-400 uppercase tracking-wider">
                  Headers (for authentication)
                </span>
                {Object.entries(headers).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2 text-[12px]">
                    <span className="font-mono text-stone-600 dark:text-stone-300 bg-stone-100 dark:bg-stone-700 px-2 py-0.5 rounded">{k}</span>
                    <span className="text-stone-400">:</span>
                    <span className="font-mono text-stone-500 dark:text-stone-400 truncate flex-1">{v.substring(0, 20)}...</span>
                    <button
                      onClick={() => setHeaders((prev) => { const copy = { ...prev }; delete copy[k]; return copy; })}
                      className="text-stone-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
                <div className="flex items-center gap-2">
                  <input
                    value={form.headerKey}
                    onChange={(e) => setForm({ ...form, headerKey: e.target.value })}
                    placeholder="Header name"
                    className="text-[12px] px-2 py-1.5 rounded-lg border border-stone-200 dark:border-stone-600
                               bg-white dark:bg-stone-700 text-stone-800 dark:text-stone-200
                               placeholder:text-stone-400 w-[140px]
                               focus:outline-none focus:ring-1 focus:ring-blue-400/50"
                  />
                  <input
                    value={form.headerVal}
                    onChange={(e) => setForm({ ...form, headerVal: e.target.value })}
                    placeholder="Header value"
                    className="text-[12px] px-2 py-1.5 rounded-lg border border-stone-200 dark:border-stone-600
                               bg-white dark:bg-stone-700 text-stone-800 dark:text-stone-200
                               placeholder:text-stone-400 flex-1
                               focus:outline-none focus:ring-1 focus:ring-blue-400/50"
                  />
                  <button
                    onClick={addHeader}
                    className="text-[11px] px-2 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-700
                               text-stone-600 dark:text-stone-300
                               hover:bg-stone-200 dark:hover:bg-stone-600 transition-colors"
                  >
                    Add
                  </button>
                </div>
              </div>
            </>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              onClick={() => setShowAdd(false)}
              className="text-[12px] px-3 py-1.5 rounded-lg text-stone-600 dark:text-stone-400
                         hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={addServer}
              disabled={!form.name || (transport === 'stdio' ? !form.command : !form.url)}
              className="text-[12px] px-4 py-1.5 rounded-lg font-medium
                         bg-stone-800 dark:bg-stone-200 text-white dark:text-stone-900
                         hover:opacity-80 transition-opacity disabled:opacity-30"
            >
              Register & Connect
            </button>
          </div>
        </div>
      )}

      {/* Server list */}
      <div className="flex flex-col gap-3">
        {servers.map((s) => {
          const isConnected = s.status === 'connected';
          const isError = s.status === 'error';
          const isExpanded = expanded === s.name;

          return (
            <div
              key={s.name}
              className={clsx(
                'border rounded-xl overflow-hidden shadow-sm',
                isConnected
                  ? 'border-emerald-200 dark:border-emerald-800 bg-white dark:bg-stone-800/60'
                  : isError
                    ? 'border-red-200 dark:border-red-800 bg-white dark:bg-stone-800/60'
                    : 'border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800/60',
              )}
            >
              <div className="flex items-center gap-3 px-4 py-3">
                <div className={clsx(
                  'w-8 h-8 rounded-lg flex items-center justify-center text-[13px] font-bold shrink-0',
                  isConnected
                    ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'
                    : isError
                      ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                      : 'bg-stone-100 dark:bg-stone-700 text-stone-500 dark:text-stone-400',
                )}>
                  {s.name[0].toUpperCase()}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-semibold text-stone-800 dark:text-stone-200">
                      {s.name}
                    </span>
                    <span className={clsx(
                      'text-[10px] px-1.5 py-0.5 rounded font-medium',
                      s.transport === 'sse'
                        ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                        : 'bg-stone-100 dark:bg-stone-700 text-stone-500 dark:text-stone-400',
                    )}>
                      {s.transport === 'sse' ? 'SSE' : 'stdio'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={clsx(
                      'w-2 h-2 rounded-full',
                      isConnected ? 'bg-emerald-500' : isError ? 'bg-red-500' : 'bg-amber-400',
                    )} />
                    <span className={clsx(
                      'text-[11px]',
                      isConnected ? 'text-emerald-600 dark:text-emerald-400'
                        : isError ? 'text-red-600 dark:text-red-400'
                          : 'text-stone-500 dark:text-stone-400',
                    )}>
                      {isConnected
                        ? `${s.tools.length} tool${s.tools.length !== 1 ? 's' : ''} enabled`
                        : isError
                          ? 'Connection error'
                          : s.status}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {!isConnected && (
                    <button
                      onClick={() => connectServer(s.name)}
                      disabled={connecting === s.name}
                      className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg font-medium
                                 bg-emerald-600 text-white hover:bg-emerald-700 transition-colors
                                 disabled:opacity-50"
                    >
                      {connecting === s.name ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Plug size={13} />
                      )}
                      Connect
                    </button>
                  )}
                  {isConnected && s.tools.length > 0 && (
                    <button
                      onClick={() => setExpanded(isExpanded ? null : s.name)}
                      className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg
                                 text-stone-500 dark:text-stone-400
                                 hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
                    >
                      {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      Tools
                    </button>
                  )}
                  <button
                    onClick={() => removeServer(s.name)}
                    className="p-1.5 rounded-lg text-stone-400 dark:text-stone-500
                               hover:text-red-600 dark:hover:text-red-400
                               hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                    title="Remove"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {/* Error detail */}
              {isError && s.error && (
                <div className="px-4 pb-3 flex items-start gap-2">
                  <AlertCircle size={13} className="text-red-500 shrink-0 mt-0.5" />
                  <span className="text-[11px] text-red-600 dark:text-red-400 break-all">
                    {s.error}
                  </span>
                </div>
              )}

              {/* Tools list (expanded) */}
              {isExpanded && s.tools.length > 0 && (
                <div className="border-t border-stone-100 dark:border-stone-700/60">
                  {s.tools.map((t) => (
                    <div key={t.name} className="flex items-start gap-2.5 px-4 py-2.5
                                                  border-b border-stone-50 dark:border-stone-700/40 last:border-b-0">
                      <Wrench size={13} className="text-stone-400 dark:text-stone-500 shrink-0 mt-0.5" />
                      <div>
                        <span className="text-[12px] font-medium text-stone-700 dark:text-stone-300">{t.name}</span>
                        {t.description && (
                          <p className="text-[11px] text-stone-500 dark:text-stone-400 mt-0.5">{t.description}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {servers.length === 0 && (
        <div className="text-center py-12">
          <Server size={32} className="mx-auto text-stone-300 dark:text-stone-600 mb-3" />
          <p className="text-[14px] font-medium text-stone-600 dark:text-stone-400 mb-1">
            No MCP servers registered
          </p>
          <p className="text-[12px] text-stone-400 dark:text-stone-500 mb-4">
            Add a server to extend Klaus with external tools and capabilities.
          </p>
          <button
            onClick={() => setShowAdd(true)}
            className="text-[12px] px-4 py-2 rounded-lg font-medium
                       bg-stone-800 dark:bg-stone-200 text-white dark:text-stone-900
                       hover:opacity-80 transition-opacity"
          >
            <Plus size={13} className="inline mr-1" />
            Add your first server
          </button>
        </div>
      )}
    </div>
  );
}
