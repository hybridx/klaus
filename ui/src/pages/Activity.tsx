import { useEffect, useState, useRef } from 'react';
import { Zap } from 'lucide-react';
import clsx from 'clsx';
import type { WsMessage } from '../hooks/useWebSocket';

interface EventItem {
  type: string;
  data: Record<string, unknown>;
  ts: number;
}

const TYPE_COLORS: Record<string, string> = {
  'chat.request': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  'chat.response': 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  'chat.error': 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  'model.routed': 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  'mcp.tool_called': 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  'backend.registered': 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

interface Props {
  ws: {
    on: (fn: (m: WsMessage) => void) => () => void;
  };
}

export default function Activity({ ws }: Props) {
  const [events, setEvents] = useState<EventItem[]>([]);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch('/api/events/history')
      .then((r) => r.json())
      .then((d) => {
        const items = (d.events || []).map((e: { type: string; data: Record<string, unknown>; timestamp: number }) => ({
          type: e.type,
          data: e.data,
          ts: e.timestamp,
        }));
        setEvents(items.reverse());
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    return ws.on((msg) => {
      if (msg.type?.startsWith('_')) return;
      setEvents((prev) => [
        { type: msg.type, data: msg.data || {}, ts: msg.ts || Date.now() / 1000 },
        ...prev,
      ].slice(0, 200));
    });
  }, [ws]);

  return (
    <div className="h-full overflow-y-auto p-4 flex flex-col gap-1" ref={listRef}>
      <p className="text-[11px] text-gray-400 dark:text-gray-600 mb-1">
        Real-time event stream from the agent pipeline.
      </p>

      {events.length === 0 && (
        <div className="text-center text-[12px] text-gray-400 py-8">No events yet</div>
      )}

      {events.map((ev, i) => {
        const colorCls = TYPE_COLORS[ev.type] || 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400';
        const summary = Object.entries(ev.data)
          .filter(([, v]) => typeof v === 'string' || typeof v === 'number')
          .map(([k, v]) => `${k}=${v}`)
          .join(' ');

        return (
          <div key={i} className="flex items-start gap-2 py-1.5">
            <Zap size={10} className="text-gray-300 dark:text-gray-600 mt-0.5 shrink-0" />
            <span className={clsx('text-[9px] px-1.5 py-0.5 rounded-full font-medium shrink-0', colorCls)}>
              {ev.type}
            </span>
            <span className="text-[11px] text-gray-500 dark:text-gray-400 truncate flex-1 font-mono">
              {summary || '—'}
            </span>
            <span className="text-[10px] text-gray-300 dark:text-gray-600 shrink-0 font-mono">
              {formatTime(ev.ts)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
