import { useState, useCallback, useEffect } from 'react';
import { useEventStream } from './hooks/useEventStream';
import { useTheme } from './hooks/useTheme';
import Layout from './components/Layout';
import Sidebar from './components/Sidebar';
import Chat from './pages/Chat';
import Flow from './pages/Flow';
import Models from './pages/Models';
import Routing from './pages/Routing';
import Activity from './pages/Activity';
import Knowledge from './pages/Knowledge';
import MCP from './pages/MCP';
import Superpowers from './pages/Superpowers';

export type Page = 'chat' | 'flow' | 'models' | 'routing' | 'activity' | 'knowledge' | 'mcp' | 'superpowers';

const VALID_PAGES = new Set<Page>(['chat', 'flow', 'models', 'routing', 'activity', 'knowledge', 'mcp', 'superpowers']);

function getPageFromHash(): Page {
  const hash = window.location.hash.replace('#/', '').replace('#', '');
  return VALID_PAGES.has(hash as Page) ? (hash as Page) : 'chat';
}

function getStoredSession(): string {
  return localStorage.getItem('klaus-session') || Date.now().toString();
}

export default function App() {
  const [page, setPageState] = useState<Page>(getPageFromHash);
  const [sessionId, setSessionId] = useState(getStoredSession);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const ws = useEventStream(sessionId);
  useTheme();

  const setPage = useCallback((p: Page) => {
    setPageState(p);
    window.history.pushState(null, '', p === 'chat' ? '#/' : `#/${p}`);
  }, []);

  useEffect(() => {
    const onHashChange = () => setPageState(getPageFromHash());
    window.addEventListener('hashchange', onHashChange);
    window.addEventListener('popstate', onHashChange);
    return () => {
      window.removeEventListener('hashchange', onHashChange);
      window.removeEventListener('popstate', onHashChange);
    };
  }, []);

  const selectSession = useCallback((id: string) => {
    localStorage.setItem('klaus-session', id);
    setSessionId(id);
  }, []);

  const newChat = useCallback(() => {
    const id = Date.now().toString();
    localStorage.setItem('klaus-session', id);
    setSessionId(id);
  }, []);

  const sidebar = (
    <Sidebar
      currentSession={sessionId}
      onSelectSession={selectSession}
      onNewChat={newChat}
      open={sidebarOpen}
    />
  );

  return (
    <Layout
      page={page}
      setPage={setPage}
      connected={ws.connected}
      sidebarOpen={sidebarOpen}
      onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
      sidebar={sidebar}
    >
      {page === 'chat' && <Chat key={sessionId} ws={ws} setPage={setPage} sessionId={sessionId} />}
      {page === 'flow' && <Flow ws={ws} />}
      {page === 'models' && <Models />}
      {page === 'routing' && <Routing />}
      {page === 'activity' && <Activity ws={ws} />}
      {page === 'knowledge' && <Knowledge />}
      {page === 'mcp' && <MCP />}
      {page === 'superpowers' && <Superpowers />}
    </Layout>
  );
}
