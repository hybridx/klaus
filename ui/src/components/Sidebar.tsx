import { useState, useEffect } from 'react';
import { Plus, MessageSquare, Trash2 } from 'lucide-react';
import clsx from 'clsx';

interface Session {
  session_id: string;
  message_count: number;
  last_active: number;
}

interface Props {
  currentSession: string;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  open: boolean;
}

function timeAgo(ts: number): string {
  const diff = Date.now() - ts * 1000;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `${days}d`;
}

export default function Sidebar({ currentSession, onSelectSession, onNewChat, open }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!open) return;
    fetch('/api/conversations/')
      .then((r) => r.json())
      .then((data) => setSessions(data.sessions ?? []))
      .catch(() => {});
  }, [open, currentSession]);

  const deleteAll = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    fetch('/api/conversations/', { method: 'DELETE' })
      .then(() => {
        setSessions([]);
        setConfirmDelete(false);
        onNewChat();
      })
      .catch(() => {});
  };

  if (!open) return null;

  return (
    <div className="w-64 shrink-0 border-r border-border bg-surface-alt h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-3">
        <span className="text-[12px] font-medium text-stone-500 dark:text-stone-400 uppercase tracking-wider">
          Chats
        </span>
        <div className="flex items-center gap-1">
          {sessions.length > 0 && (
            <button
              onClick={deleteAll}
              className={clsx(
                'p-1 rounded-lg transition-colors',
                confirmDelete
                  ? 'text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950'
                  : 'text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800',
              )}
              title={confirmDelete ? 'Click again to confirm' : 'Delete all chats'}
            >
              <Trash2 size={13} />
            </button>
          )}
          <button
            onClick={onNewChat}
            className="p-1 rounded-lg text-stone-400 dark:text-stone-500
                       hover:text-stone-600 dark:hover:text-stone-300
                       hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
            title="New chat"
          >
            <Plus size={15} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {sessions.length === 0 ? (
          <div className="text-[11px] text-stone-400 dark:text-stone-600 text-center py-8">
            No conversations yet
          </div>
        ) : (
          sessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => onSelectSession(s.session_id)}
              className={clsx(
                'w-full text-left px-3 py-2 rounded-lg transition-colors group',
                s.session_id === currentSession
                  ? 'bg-stone-100 dark:bg-stone-800'
                  : 'hover:bg-stone-50 dark:hover:bg-stone-800/50',
              )}
            >
              <div className="flex items-center gap-2">
                <MessageSquare size={12} className="shrink-0 text-stone-400 dark:text-stone-500" />
                <span className="text-[12px] truncate flex-1 text-stone-700 dark:text-stone-300">
                  Chat {s.session_id.slice(0, 8)}
                </span>
                <span className="text-[9px] text-stone-400 dark:text-stone-600 shrink-0">
                  {s.message_count}msg {s.last_active ? timeAgo(s.last_active) : ''}
                </span>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
