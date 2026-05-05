import { useEffect, useState } from 'react';
import { Zap, Wrench, Loader2, Circle } from 'lucide-react';
import clsx from 'clsx';

interface SuperpowerInfo {
  name: string;
  description: string;
  active: boolean;
  version: string;
  tags: string[];
  tools: string[];
}

interface ToolInfo {
  name: string;
  description: string;
}

export default function Superpowers() {
  const [powers, setPowers] = useState<SuperpowerInfo[]>([]);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/superpowers').then((r) => r.json()),
      fetch('/api/superpowers/tools').then((r) => r.json()),
    ]).then(([p, t]) => {
      setPowers(p.superpowers || []);
      setTools(t.tools || []);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-4 flex items-center justify-center">
        <div className="flex items-center gap-2 text-stone-400">
          <Loader2 size={14} className="animate-spin" />
          <span className="text-[11px]">Loading superpowers...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 flex flex-col gap-4">
      <p className="text-[11px] text-stone-400 dark:text-stone-600">
        Active superpowers and tools available to the agent.
      </p>

      <div className="flex flex-col gap-3">
        {powers.map((p) => (
          <div key={p.name} className="border border-border rounded-lg bg-surface overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-surface-alt">
              <Zap size={13} className={p.active ? 'text-amber-500' : 'text-stone-400'} />
              <span className="text-[12px] font-semibold">{p.name}</span>
              <Circle
                size={6}
                className={clsx('ml-1', p.active ? 'fill-green text-green' : 'fill-stone-400 text-stone-400')}
              />
              <span className={clsx(
                'text-[10px]',
                p.active ? 'text-green' : 'text-stone-400',
              )}>
                {p.active ? 'active' : 'inactive'}
              </span>
              {p.version && (
                <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded-full bg-surface-strong text-stone-500">
                  v{p.version}
                </span>
              )}
            </div>
            <div className="px-3 py-2">
              <p className="text-[11px] text-stone-500 dark:text-stone-400">{p.description}</p>
              {p.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {p.tags.map((tag) => (
                    <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded-full
                                               bg-stone-100 dark:bg-stone-800
                                               text-stone-500 dark:text-stone-400">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {tools.length > 0 && (
        <div>
          <h3 className="text-[11px] font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wider mb-2">
            All Agent Tools ({tools.length})
          </h3>
          <div className="border border-border rounded-lg bg-surface divide-y divide-border">
            {tools.map((t) => (
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
        </div>
      )}

      {powers.length === 0 && (
        <div className="text-center text-[12px] text-stone-400 py-8">No superpowers registered</div>
      )}
    </div>
  );
}
