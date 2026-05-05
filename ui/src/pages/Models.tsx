import { useEffect, useState } from 'react';
import { Server, Cpu, Circle, Loader2 } from 'lucide-react';
import clsx from 'clsx';

interface ModelInfo {
  name: string;
  backend: string;
  size: string;
  quantization: string;
  capabilities: string[];
}

interface BackendInfo {
  name: string;
  locality: string;
  healthy: boolean;
  default_model: string;
  type: string;
}

export default function Models() {
  const [backends, setBackends] = useState<BackendInfo[]>([]);
  const [models, setModels] = useState<Record<string, ModelInfo[]>>({});
  const [health, setHealth] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/routing/backends').then((r) => r.json()),
      fetch('/api/models').then((r) => r.json()),
      fetch('/api/models/health').then((r) => r.json()),
    ]).then(([b, m, h]) => {
      setBackends(b.backends || []);
      setModels(m || {});
      setHealth(h || {});
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-4 flex flex-col gap-3">
        <p className="text-[11px] text-stone-400 dark:text-stone-600">
          Registered model backends and available models.
        </p>
        <div className="flex flex-col gap-3">
          {[1, 2].map((i) => (
            <div key={i} className="border border-border rounded-lg bg-surface overflow-hidden animate-pulse">
              <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-surface-alt">
                <div className="w-3 h-3 rounded bg-stone-200 dark:bg-stone-700" />
                <div className="w-24 h-3 rounded bg-stone-200 dark:bg-stone-700" />
              </div>
              <div className="px-3 py-2 space-y-2">
                {[1, 2, 3].map((j) => (
                  <div key={j} className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded bg-stone-200 dark:bg-stone-700" />
                    <div className="w-40 h-3 rounded bg-stone-200 dark:bg-stone-700" />
                    <div className="ml-auto w-12 h-3 rounded bg-stone-200 dark:bg-stone-700" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-center gap-2 py-4 text-stone-400 dark:text-stone-500">
          <Loader2 size={14} className="animate-spin" />
          <span className="text-[11px]">Loading backends...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 flex flex-col gap-3">
      <p className="text-[11px] text-stone-400 dark:text-stone-600">
        Registered model backends and available models.
      </p>

      {backends.map((b) => {
        const isHealthy = health[b.name] ?? b.healthy;
        const backendModels = models[b.name] || [];

        return (
          <div key={b.name} className="border border-border rounded-lg bg-surface overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-surface-alt">
              <Server size={13} className={isHealthy ? 'text-green' : 'text-red'} />
              <span className="text-[12px] font-semibold">{b.name}</span>
              <Circle
                size={6}
                className={clsx('ml-1', isHealthy ? 'fill-green text-green' : 'fill-red text-red')}
              />
              <span className={clsx(
                'text-[10px]',
                isHealthy ? 'text-green' : 'text-red',
              )}>
                {isHealthy ? 'healthy' : 'offline'}
              </span>
              <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-surface-strong text-stone-500">
                {b.locality}
              </span>
            </div>

            {backendModels.length === 0 ? (
              <div className="px-3 py-2 text-[11px] text-stone-400">No models loaded</div>
            ) : (
              <div className="divide-y divide-border">
                {backendModels.map((m) => (
                  <div key={m.name} className="flex items-center gap-2 px-3 py-2">
                    <Cpu size={11} className="text-accent shrink-0" />
                    <span className="text-[12px] font-medium truncate">{m.name}</span>
                    <div className="ml-auto flex items-center gap-1">
                      {m.capabilities?.includes('tools') && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full
                                         bg-emerald-100 dark:bg-emerald-900/30
                                         text-emerald-600 dark:text-emerald-400">
                          tools
                        </span>
                      )}
                      {m.size && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-surface-strong text-stone-500">
                          {m.size}
                        </span>
                      )}
                      {m.quantization && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-surface-strong text-stone-500">
                          {m.quantization}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {backends.length === 0 && (
        <div className="text-center text-[12px] text-stone-400 py-8">No backends registered</div>
      )}
    </div>
  );
}
