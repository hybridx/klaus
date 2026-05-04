import { useState, useCallback } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useTheme } from './hooks/useTheme';
import Layout from './components/Layout';
import Sidebar from './components/Sidebar';
import Chat from './pages/Chat';
import Flow from './pages/Flow';
import Models from './pages/Models';
import Routing from './pages/Routing';
import Activity from './pages/Activity';
import Knowledge from './pages/Knowledge';

export type Page = 'chat' | 'flow' | 'models' | 'routing' | 'activity' | 'knowledge';

function getStoredSession(): string {
  return localStorage.getItem('klaus-session') || Date.now().toString();
}

export default function App() {
  const [page, setPage] = useState<Page>('chat');
  const [sessionId, setSessionId] = useState(getStoredSession);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const ws = useWebSocket();
  const theme = useTheme();

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
      theme={theme}
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
    </Layout>
  );
}
