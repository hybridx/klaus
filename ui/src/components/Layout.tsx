import { type ReactNode, useState, useRef, useEffect } from 'react';
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
  BookOpen,
  Menu,
  X,
  Zap,
  Server,
  Settings,
  BarChart3,
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

export default function Layout({ page, setPage, connected, theme, sidebarOpen, onToggleSidebar, children, sidebar }: Props) {
  const current = ALL_NAV.find((n) => n.id === page);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

  const navigate = (p: Page) => {
    setPage(p);
    setMenuOpen(false);
  };

  return (
    <div className="flex h-screen">
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
            <div className="ml-auto flex items-center gap-2">
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
              <a
                href="https://hybridx.github.io/klaus/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] text-stone-400 dark:text-stone-500
                           hover:text-stone-600 dark:hover:text-stone-300 transition-colors
                           flex items-center gap-1"
              >
                <BookOpen size={12} />
                Docs
              </a>

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

              <div className="w-px h-3 bg-border" />

              {/* Hamburger menu */}
              <div className="relative" ref={menuRef}>
                <button
                  onClick={() => setMenuOpen(!menuOpen)}
                  className="p-1 rounded-lg text-stone-400 dark:text-stone-500
                             hover:text-stone-600 dark:hover:text-stone-300
                             hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                >
                  {menuOpen ? <X size={16} /> : <Menu size={16} />}
                </button>

                {menuOpen && (
                  <div className="absolute right-0 top-full mt-1 w-56 rounded-xl border border-border
                                  bg-surface shadow-lg z-50 py-1 overflow-hidden">
                    {MENU_GROUPS.map((group) => {
                      const GroupIcon = group.icon;
                      return (
                        <div key={group.label}>
                          <div className="flex items-center gap-1.5 px-3 py-1.5 text-[10px]
                                          font-semibold uppercase tracking-wider
                                          text-stone-400 dark:text-stone-500">
                            <GroupIcon size={10} />
                            {group.label}
                          </div>
                          {group.items.map((item) => {
                            const Icon = item.icon;
                            return (
                              <button
                                key={item.id}
                                onClick={() => navigate(item.id)}
                                className={clsx(
                                  'w-full flex items-center gap-2 px-3 py-2 text-[12px] transition-colors',
                                  page === item.id
                                    ? 'bg-stone-100 dark:bg-stone-800 text-stone-900 dark:text-stone-100 font-medium'
                                    : 'text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-800/50',
                                )}
                              >
                                <Icon size={13} />
                                {item.label}
                              </button>
                            );
                          })}
                          <div className="my-1 h-px bg-border" />
                        </div>
                      );
                    })}
                    <a
                      href="https://hybridx.github.io/klaus/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 px-3 py-2 text-[12px]
                                 text-stone-600 dark:text-stone-400
                                 hover:bg-stone-50 dark:hover:bg-stone-800/50 transition-colors"
                    >
                      <BookOpen size={13} />
                      Documentation
                    </a>
                  </div>
                )}
              </div>
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
