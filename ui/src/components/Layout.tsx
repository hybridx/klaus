import type { ReactNode } from 'react';
import type { Page } from '../App';
import {
  GitBranch,
  Layers,
  Route,
  Activity,
  Brain,
  Sun,
  Moon,
  ChevronLeft,
  PanelLeftOpen,
  PanelLeftClose,
} from 'lucide-react';
import clsx from 'clsx';

interface Props {
  page: Page;
  setPage: (p: Page) => void;
  connected: boolean;
  theme: { isDark: boolean; toggle: () => void };
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  children: ReactNode;
  sidebar: ReactNode;
}

const NAV: { id: Page; label: string; icon: typeof GitBranch }[] = [
  { id: 'knowledge', label: 'Knowledge', icon: Brain },
  { id: 'flow', label: 'Pipeline', icon: GitBranch },
  { id: 'models', label: 'Models', icon: Layers },
  { id: 'routing', label: 'Routing', icon: Route },
  { id: 'activity', label: 'Activity', icon: Activity },
];

export default function Layout({ page, setPage, connected, theme, sidebarOpen, onToggleSidebar, children, sidebar }: Props) {
  const current = NAV.find((n) => n.id === page);

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      {page === 'chat' && sidebar}

      <div className="flex flex-col flex-1 min-w-0">
        {/* Non-chat header */}
        {page !== 'chat' && (
          <header className="flex items-center gap-2 px-4 h-10 shrink-0
                            border-b border-border bg-surface-alt">
            <button
              onClick={() => setPage('chat')}
              className="flex items-center gap-1 text-[12px] text-accent hover:text-stone-700
                         dark:hover:text-stone-200 transition-colors"
            >
              <ChevronLeft size={14} />
              Chat
            </button>
            <span className="text-[12px] font-medium text-stone-500 dark:text-stone-400">
              {current?.label}
            </span>
          </header>
        )}

        {/* Chat header */}
        {page === 'chat' && (
          <header className="flex items-center justify-between px-4 h-11 shrink-0">
            <div className="flex items-center gap-2">
              <button
                onClick={onToggleSidebar}
                className="p-1 rounded-lg text-stone-400 dark:text-stone-500
                           hover:text-stone-600 dark:hover:text-stone-300
                           hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
              </button>
              <span className="text-[14px] font-semibold tracking-tight text-stone-800 dark:text-stone-200">
                Klaus
              </span>
            </div>
            <div className="flex items-center gap-3">
              {NAV.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    onClick={() => setPage(item.id)}
                    className="text-[11px] text-stone-400 dark:text-stone-500
                               hover:text-stone-600 dark:hover:text-stone-300 transition-colors
                               flex items-center gap-1"
                  >
                    <Icon size={12} />
                    {item.label}
                  </button>
                );
              })}

              <div className="w-px h-3 bg-border" />

              <div className="flex items-center gap-1">
                <span className={clsx(
                  'w-1.5 h-1.5 rounded-full',
                  connected ? 'bg-green' : 'bg-red',
                )} />
              </div>

              <button
                onClick={theme.toggle}
                className="text-stone-300 dark:text-stone-600
                           hover:text-stone-500 dark:hover:text-stone-400 transition-colors"
              >
                {theme.isDark ? <Sun size={13} /> : <Moon size={13} />}
              </button>
            </div>
          </header>
        )}

        <main className="flex-1 overflow-hidden">
          {children}
        </main>
      </div>
    </div>
  );
}
