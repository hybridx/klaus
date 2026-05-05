import { type ReactNode } from 'react';
import type { Page } from '../App';
import {
  GitBranch,
  Layers,
  Route,
  Activity,
  Brain,
  Sun,
  Moon,
  PanelLeftOpen,
  PanelLeftClose,
  BookOpen,
  Zap,
  Server,
  Settings,
  BarChart3,
  ArrowLeft,
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

interface NavGroup {
  label: string;
  icon: typeof Settings;
  items: { id: Page; label: string; icon: typeof GitBranch }[];
}

const MENU_GROUPS: NavGroup[] = [
  {
    label: 'Settings',
    icon: Settings,
    items: [
      { id: 'models', label: 'Models', icon: Layers },
      { id: 'routing', label: 'Routing', icon: Route },
      { id: 'mcp', label: 'MCP Servers', icon: Server },
      { id: 'superpowers', label: 'Superpowers', icon: Zap },
    ],
  },
  {
    label: 'Observability',
    icon: BarChart3,
    items: [
      { id: 'flow', label: 'Pipeline', icon: GitBranch },
      { id: 'activity', label: 'Activity', icon: Activity },
      { id: 'knowledge', label: 'Knowledge', icon: Brain },
    ],
  },
];

const ALL_NAV = MENU_GROUPS.flatMap((g) => g.items);

export { MENU_GROUPS, ALL_NAV };

export default function Layout({
  page, setPage, connected, theme, sidebarOpen, onToggleSidebar, children, sidebar,
}: Props) {
  const current = ALL_NAV.find((n) => n.id === page);
  const isChat = page === 'chat';

  if (isChat) {
    return (
      <div className="flex h-screen">
        {sidebar}
        <div className="flex flex-col flex-1 min-w-0">
          <header className="flex items-center justify-between px-4 h-11 shrink-0
                              border-b border-stone-100 dark:border-stone-800">
            <div className="flex items-center gap-2">
              <button
                onClick={onToggleSidebar}
                className="p-1 rounded-lg text-stone-600 dark:text-stone-400
                           hover:text-stone-900 dark:hover:text-stone-200
                           hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
              </button>
              <span className="text-[14px] font-semibold tracking-tight text-stone-900 dark:text-stone-100">
                Klaus
              </span>
            </div>
            <div className="flex items-center gap-3">
              <a
                href="https://hybridx.github.io/klaus/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[12px] text-stone-600 dark:text-stone-400
                           hover:text-stone-900 dark:hover:text-stone-200 transition-colors
                           flex items-center gap-1"
              >
                <BookOpen size={14} />
                Docs
              </a>

              <div className="w-px h-3.5 bg-stone-200 dark:bg-stone-700" />

              <div className="flex items-center gap-1.5">
                <span className={clsx(
                  'w-2 h-2 rounded-full',
                  connected ? 'bg-emerald-500' : 'bg-red-400',
                )} />
              </div>

              <button
                onClick={theme.toggle}
                className="p-1 rounded-lg text-stone-600 dark:text-stone-400
                           hover:text-stone-900 dark:hover:text-stone-200
                           hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                {theme.isDark ? <Sun size={15} /> : <Moon size={15} />}
              </button>

              <div className="w-px h-3.5 bg-stone-200 dark:bg-stone-700" />

              <button
                onClick={() => setPage('models')}
                className="p-1.5 rounded-lg text-stone-600 dark:text-stone-400
                           hover:text-stone-900 dark:hover:text-stone-200
                           hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                title="Settings"
              >
                <Settings size={16} />
              </button>
            </div>
          </header>

          <main className="flex-1 overflow-hidden">
            {children}
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-stone-50 dark:bg-stone-900">
      {/* Settings sidebar */}
      <aside className="w-56 shrink-0 border-r border-stone-200 dark:border-stone-800
                         bg-white dark:bg-stone-900 flex flex-col">
        <div className="px-4 h-11 flex items-center shrink-0
                        border-b border-stone-100 dark:border-stone-800">
          <button
            onClick={() => setPage('chat')}
            className="flex items-center gap-1.5 text-[13px] font-medium
                       text-stone-600 dark:text-stone-400
                       hover:text-stone-900 dark:hover:text-stone-200 transition-colors"
          >
            <ArrowLeft size={14} />
            Back to Chat
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto py-3 px-2">
          {MENU_GROUPS.map((group) => {
            const GroupIcon = group.icon;
            return (
              <div key={group.label} className="mb-4">
                <div className="flex items-center gap-1.5 px-3 py-1.5 mb-0.5
                                text-[10px] font-semibold uppercase tracking-wider
                                text-stone-500 dark:text-stone-500">
                  <GroupIcon size={12} />
                  {group.label}
                </div>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = page === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() => setPage(item.id)}
                      className={clsx(
                        'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-colors mb-0.5',
                        isActive
                          ? 'bg-stone-100 dark:bg-stone-800 text-stone-900 dark:text-stone-100 font-medium'
                          : 'text-stone-700 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-800/50 hover:text-stone-900 dark:hover:text-stone-200',
                      )}
                    >
                      <Icon size={15} className={isActive ? 'text-stone-700 dark:text-stone-300' : ''} />
                      {item.label}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </nav>

        <div className="px-3 py-3 border-t border-stone-100 dark:border-stone-800 flex flex-col gap-1.5">
          <a
            href="https://hybridx.github.io/klaus/"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px]
                       text-stone-700 dark:text-stone-400
                       hover:bg-stone-50 dark:hover:bg-stone-800/50
                       hover:text-stone-900 dark:hover:text-stone-200 transition-colors"
          >
            <BookOpen size={15} />
            Documentation
          </a>
          <div className="flex items-center justify-between px-3 py-1">
            <div className="flex items-center gap-1.5">
              <span className={clsx(
                'w-2 h-2 rounded-full',
                connected ? 'bg-emerald-500' : 'bg-red-400',
              )} />
              <span className="text-[11px] text-stone-500 dark:text-stone-500">
                {connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            <button
              onClick={theme.toggle}
              className="p-1 rounded-lg text-stone-500 dark:text-stone-500
                         hover:text-stone-900 dark:hover:text-stone-200
                         hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
            >
              {theme.isDark ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-col flex-1 min-w-0">
        <header className="flex items-center gap-2 px-6 h-11 shrink-0
                            border-b border-stone-200 dark:border-stone-800
                            bg-white dark:bg-stone-900">
          <span className="text-[14px] font-semibold text-stone-900 dark:text-stone-100">
            {current?.label}
          </span>
        </header>

        <main className="flex-1 overflow-hidden bg-white dark:bg-stone-900">
          {children}
        </main>
      </div>
    </div>
  );
}
