import { useEffect, useState } from 'react';
import { Server, Cpu, Circle } from 'lucide-react';
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

  useEffect(() => {
    Promise.all([
      fetch('/api/routing/backends').then((r) => r.json()),
      fetch('/api/models').then((r) => r.json()),
      fetch('/api/models/health').then((r) => r.json()),
    ]).then(([b, m, h]) => {
      setBackends(b.backends || []);
      setModels(m || {});
      setHealth(h || {});
    }).catch(() => {});
  }, []);

  return (
    <div className="h-full overflow-y-auto p-4 flex flex-col gap-3">
      <p className="text-[11px] text-gray-400 dark:text-gray-600">
        Registered model backends and available models.
      </p>

      {backends.map((b) => {
        const isHealthy = health[b.name] ?? b.healthy;
        const backendModels = models[b.name] || [];

        return (
          <div key={b.name} className="border border-border rounded-lg bg-surface overflow-hidden">
            {/* Backend header */}
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
              <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-surface-strong text-gray-500">
                {b.locality}
              </span>
            </div>

            {/* Models list */}
            {backendModels.length === 0 ? (
              <div className="px-3 py-2 text-[11px] text-gray-400">No models loaded</div>
            ) : (
              <div className="divide-y divide-border">
                {backendModels.map((m) => (
                  <div key={m.name} className="flex items-center gap-2 px-3 py-2">
                    <Cpu size={11} className="text-accent shrink-0" />
                    <span className="text-[12px] font-medium truncate">{m.name}</span>
                    <div className="ml-auto flex items-center gap-1">
                      {m.size && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-surface-strong text-gray-500">
                          {m.size}
                        </span>
                      )}
                      {m.quantization && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-surface-strong text-gray-500">
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
        <div className="text-center text-[12px] text-gray-400 py-8">No backends registered</div>
      )}
    </div>
  );
}
