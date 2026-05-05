import { useEffect, useState, useCallback } from 'react';
import {
  Wrench, Loader2, Plus, Trash2, Plug, ChevronDown,
  ChevronRight, Globe, Terminal, AlertCircle, RefreshCw,
  ExternalLink, PlugZap, FileJson,
} from 'lucide-react';
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
  auth_url?: string | null;
}

type TransportType = 'stdio' | 'sse';

export default function MCP() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);

  const [transport, setTransport] = useState<TransportType>('stdio');
  const [form, setForm] = useState({ name: '', command: '', args: '', url: '' });

  const load = useCallback(() => {
    fetch('/api/mcp/servers')
      .then((r) => r.json())
      .then((d) => setServers(d.servers || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const addServer = async () => {
    const payload: Record<string, unknown> = {
      name: form.name,
      auto_connect: true,
    };
    if (transport === 'sse') {
      if (!form.name || !form.url) return;
      payload.url = form.url;
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
    } catch { /* ignore */ }

    setForm({ name: '', command: '', args: '', url: '' });
    setShowAdd(false);
    load();
  };

  const connectServer = async (name: string) => {
    setConnecting(name);
    try {
      const resp = await fetch(`/api/mcp/servers/${name}/connect`, { method: 'POST' });
      const data = await resp.json();

      if (data.auth_url) {
        window.open(data.auth_url, '_blank', 'noopener');

        const poll = setInterval(() => {
          fetch('/api/mcp/servers')
            .then((r) => r.json())
            .then((d) => {
              const updated = (d.servers || []) as MCPServer[];
              const srv = updated.find((s) => s.name === name);
              if (srv && (srv.status === 'connected' || srv.status === 'error')) {
                clearInterval(poll);
                setConnecting(null);
                setServers(updated);
              }
            })
            .catch(() => {});
        }, 2000);

        setTimeout(() => {
          clearInterval(poll);
          setConnecting(null);
          load();
        }, 120_000);
        return;
      }

      load();
    } catch { /* ignore */ }
    setConnecting(null);
  };

  const removeServer = async (name: string) => {
    await fetch(`/api/mcp/servers/${name}`, { method: 'DELETE' });
    load();
  };

  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-6 flex items-center justify-center">
        <div className="flex items-center gap-2 text-stone-400">
          <Loader2 size={16} className="animate-spin" />
          <span className="text-[13px]">Loading MCP servers...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 flex flex-col gap-5 max-w-3xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[13px] text-stone-400 leading-relaxed">
            MCP servers extend Klaus with external tools. Servers are loaded from your{' '}
            <code className="text-[12px] px-1.5 py-0.5 rounded bg-stone-700 text-stone-300 font-mono">
              mcp.json
            </code>{' '}
            config file. OAuth servers will prompt for browser authorization when you click Connect.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={load}
            className="flex items-center gap-1 text-[12px] px-2.5 py-1.5 rounded-lg
                       text-stone-400 hover:bg-stone-800 transition-colors"
          >
            <RefreshCw size={13} /> Refresh
          </button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="flex items-center gap-1 text-[12px] px-3 py-1.5 rounded-lg font-medium
                       text-stone-400 border border-stone-700
                       hover:bg-stone-800 transition-colors"
          >
            <Plus size={13} /> Add Runtime Server
          </button>
        </div>
      </div>

      {/* Empty state */}
      {servers.length === 0 && !showAdd && (
        <div className="border border-dashed border-stone-600 rounded-xl
                        bg-stone-800/40 p-5 text-center">
          <FileJson size={28} className="mx-auto text-stone-500 mb-2" />
          <p className="text-[13px] font-medium text-stone-300 mb-1">
            No MCP servers configured
          </p>
          <p className="text-[12px] text-stone-400 mb-3 max-w-md mx-auto">
            Create an <code className="font-mono px-1 py-0.5 rounded bg-stone-700
                                       text-stone-300">mcp.json</code> file
            in your project root or <code className="font-mono px-1 py-0.5 rounded bg-stone-700
                                       text-stone-300">~/.cursor/mcp.json</code> to auto-load servers.
          </p>
          <pre className="text-left text-[11px] font-mono p-4 rounded-lg bg-stone-700
                          text-stone-300 max-w-md mx-auto mb-3 overflow-x-auto">
{`{
  "mcpServers": {
    "atlassian": {
      "url": "https://mcp.atlassian.com/v1/mcp/authv2"
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  }
}`}
          </pre>
          <button
            onClick={() => setShowAdd(true)}
            className="text-[12px] px-4 py-2 rounded-lg font-medium
                       bg-stone-200 text-stone-900
                       hover:opacity-80 transition-opacity"
          >
            <Plus size={13} className="inline mr-1" />
            Add a server manually
          </button>
        </div>
      )}

      {/* Add form */}
      {showAdd && (
        <div className="border border-stone-700 rounded-xl
                        bg-stone-800/60 shadow-sm p-4 flex flex-col gap-3">
          <div className="text-[13px] font-semibold text-stone-200">
            Add Runtime Server
          </div>

          <div className="flex items-center gap-1 p-0.5 bg-stone-700 rounded-lg w-fit">
            <button
              onClick={() => setTransport('stdio')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors',
                transport === 'stdio'
                  ? 'bg-stone-600 text-stone-100 shadow-sm'
                  : 'text-stone-400',
              )}
            >
              <Terminal size={13} /> Command
            </button>
            <button
              onClick={() => setTransport('sse')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors',
                transport === 'sse'
                  ? 'bg-stone-600 text-stone-100 shadow-sm'
                  : 'text-stone-400',
              )}
            >
              <Globe size={13} /> URL
            </button>
          </div>

          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Server name (e.g. filesystem, github)"
            className="text-[13px] px-3 py-2 rounded-lg border border-stone-600
                       bg-stone-700 text-stone-200
                       placeholder:text-stone-500
                       focus:outline-none focus:ring-2 focus:ring-blue-400/50"
          />

          {transport === 'stdio' ? (
            <>
              <input
                value={form.command}
                onChange={(e) => setForm({ ...form, command: e.target.value })}
                placeholder="Command (e.g. npx, uvx, node)"
                className="text-[13px] px-3 py-2 rounded-lg border border-stone-600
                           bg-stone-700 text-stone-200
                           placeholder:text-stone-500
                           focus:outline-none focus:ring-2 focus:ring-blue-400/50"
              />
              <input
                value={form.args}
                onChange={(e) => setForm({ ...form, args: e.target.value })}
                placeholder="Arguments (space-separated)"
                className="text-[13px] px-3 py-2 rounded-lg border border-stone-600
                           bg-stone-700 text-stone-200
                           placeholder:text-stone-500
                           focus:outline-none focus:ring-2 focus:ring-blue-400/50"
              />
            </>
          ) : (
            <input
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              placeholder="Endpoint URL (e.g. https://mcp.atlassian.com/v1/mcp/authv2)"
              className="text-[13px] px-3 py-2 rounded-lg border border-stone-600
                         bg-stone-700 text-stone-200
                         placeholder:text-stone-500
                         focus:outline-none focus:ring-2 focus:ring-blue-400/50"
            />
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              onClick={() => setShowAdd(false)}
              className="text-[12px] px-3 py-1.5 rounded-lg text-stone-400
                         hover:bg-stone-700 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={addServer}
              disabled={!form.name || (transport === 'stdio' ? !form.command : !form.url)}
              className="text-[12px] px-4 py-1.5 rounded-lg font-medium
                         bg-stone-200 text-stone-900
                         hover:opacity-80 transition-opacity disabled:opacity-30"
            >
              Register & Connect
            </button>
          </div>
        </div>
      )}

      {/* Server list */}
      {servers.length > 0 && (
        <div className="flex flex-col gap-3">
          {servers.map((s) => {
            const isConnected = s.status === 'connected';
            const isError = s.status === 'error';
            const needsAuth = s.status === 'needs_auth';
            const awaitingAuth = s.status === 'awaiting_auth';
            const isExpanded = expanded === s.name;
            const isConnecting = connecting === s.name;
            const showConnect = !isConnected;

            return (
              <div
                key={s.name}
                className={clsx(
                  'border rounded-xl overflow-hidden shadow-sm',
                  isConnected
                    ? 'border-emerald-800 bg-stone-800/60'
                    : needsAuth || awaitingAuth
                      ? 'border-amber-800 bg-stone-800/60'
                      : isError
                        ? 'border-red-800 bg-stone-800/60'
                        : 'border-stone-700 bg-stone-800/60',
                )}
              >
                <div className="flex items-center gap-3 px-4 py-3">
                  <div className={clsx(
                    'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
                    isConnected
                      ? 'bg-emerald-900/30 text-emerald-400'
                      : needsAuth || awaitingAuth
                        ? 'bg-amber-900/30 text-amber-400'
                        : isError
                          ? 'bg-red-900/30 text-red-400'
                          : 'bg-stone-700 text-stone-400',
                  )}>
                    {s.transport === 'sse' ? <Globe size={16} /> : <Terminal size={16} />}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] font-semibold text-stone-200">
                        {s.name}
                      </span>
                      <span className={clsx(
                        'text-[10px] px-1.5 py-0.5 rounded font-medium',
                        s.transport === 'sse'
                          ? 'bg-violet-900/30 text-violet-400'
                          : 'bg-stone-700 text-stone-400',
                      )}>
                        {s.transport === 'sse' ? 'HTTP' : 'stdio'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className={clsx(
                        'w-2 h-2 rounded-full shrink-0',
                        isConnected ? 'bg-emerald-500'
                          : awaitingAuth ? 'bg-amber-400 animate-pulse'
                            : needsAuth ? 'bg-amber-500'
                              : isError ? 'bg-red-500'
                                : 'bg-stone-400',
                      )} />
                      <span className={clsx(
                        'text-[11px]',
                        isConnected ? 'text-emerald-400'
                          : needsAuth || awaitingAuth ? 'text-amber-400'
                            : isError ? 'text-red-400'
                              : 'text-stone-400',
                      )}>
                        {isConnected
                          ? `${s.tools.length} tool${s.tools.length !== 1 ? 's' : ''} available`
                          : awaitingAuth
                            ? 'Waiting for authorization…'
                            : needsAuth
                              ? 'Needs authentication'
                              : isError
                                ? 'Connection error'
                                : s.status}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {showConnect && (
                      <button
                        onClick={() => connectServer(s.name)}
                        disabled={isConnecting}
                        className={clsx(
                          'flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg font-medium',
                          'transition-colors disabled:opacity-50',
                          needsAuth || awaitingAuth
                            ? 'bg-blue-600 text-white hover:bg-blue-700'
                            : 'bg-emerald-600 text-white hover:bg-emerald-700',
                        )}
                      >
                        {isConnecting ? (
                          <Loader2 size={13} className="animate-spin" />
                        ) : needsAuth || awaitingAuth ? (
                          <ExternalLink size={13} />
                        ) : (
                          <Plug size={13} />
                        )}
                        Connect
                      </button>
                    )}
                    {isConnected && (
                      <button
                        onClick={() => connectServer(s.name)}
                        disabled={isConnecting}
                        className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg
                                   text-stone-400 hover:bg-stone-700 transition-colors"
                        title="Reconnect"
                      >
                        <PlugZap size={13} />
                      </button>
                    )}
                    {isConnected && s.tools.length > 0 && (
                      <button
                        onClick={() => setExpanded(isExpanded ? null : s.name)}
                        className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg
                                   text-stone-400 hover:bg-stone-700 transition-colors"
                      >
                        {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                        Tools
                      </button>
                    )}
                    <button
                      onClick={() => removeServer(s.name)}
                      className="p-1.5 rounded-lg text-stone-500
                                 hover:text-red-400 hover:bg-red-900/20 transition-colors"
                      title="Remove"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {(needsAuth || awaitingAuth) && (
                  <div className="px-4 pb-3 flex items-start gap-2">
                    <ExternalLink size={13} className="text-amber-500 shrink-0 mt-0.5" />
                    <span className="text-[11px] text-amber-400">
                      {awaitingAuth
                        ? 'Authorization in progress — complete the consent flow in the browser tab.'
                        : 'Click Connect to open the provider\'s login page.'}
                    </span>
                  </div>
                )}
                {isError && s.error && (
                  <div className="px-4 pb-3 flex items-start gap-2">
                    <AlertCircle size={13} className="text-red-500 shrink-0 mt-0.5" />
                    <span className="text-[11px] text-red-400 break-all">
                      {s.error}
                    </span>
                  </div>
                )}

                {isExpanded && s.tools.length > 0 && (
                  <div className="border-t border-stone-700/60">
                    {s.tools.map((t) => (
                      <div
                        key={t.name}
                        className="flex items-start gap-2.5 px-4 py-2.5
                                   border-b border-stone-700/40 last:border-b-0"
                      >
                        <Wrench size={13} className="text-stone-500 shrink-0 mt-0.5" />
                        <div>
                          <span className="text-[12px] font-medium text-stone-300">
                            {t.name}
                          </span>
                          {t.description && (
                            <p className="text-[11px] text-stone-400 mt-0.5">
                              {t.description}
                            </p>
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
      )}
    </div>
  );
}
