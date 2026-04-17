import { useCallback, useEffect, useState } from 'react';
import type { SessionInfo } from '../types';
import { useGatewaySession } from '../hooks/useGatewaySession';
import { SessionSidebar } from './SessionSidebar';
import { ChatPane } from './ChatPane';
import './components.css';

const SESSIONS_KEY = 'ohmo_sessions';
const ACTIVE_KEY = 'ohmo_active_session';

function makeId() { return Math.random().toString(36).slice(2); }
function newSession(): SessionInfo {
  return { id: makeId(), label: `Chat ${new Date().toLocaleTimeString()}`, createdAt: Date.now() };
}

function loadSessions(): SessionInfo[] {
  try { return JSON.parse(localStorage.getItem(SESSIONS_KEY) ?? '[]'); } catch { return []; }
}
function saveSessions(s: SessionInfo[]) { localStorage.setItem(SESSIONS_KEY, JSON.stringify(s)); }

export function App() {
  const [sessions, setSessions] = useState<SessionInfo[]>(() => {
    const s = loadSessions();
    return s.length ? s : [newSession()];
  });
  const [activeId, setActiveId] = useState<string>(
    () => localStorage.getItem(ACTIVE_KEY) ?? sessions[0]?.id ?? ''
  );
  const [serverSessions, setServerSessions] = useState<string[]>([]);

  const { messages, streamingText, status, send } = useGatewaySession(activeId);

  useEffect(() => { saveSessions(sessions); }, [sessions]);
  useEffect(() => { localStorage.setItem(ACTIVE_KEY, activeId); }, [activeId]);

  useEffect(() => {
    const poll = () => {
      fetch('/api/sessions')
        .then(r => r.json())
        .then((d: { sessions: string[] }) => setServerSessions(d.sessions))
        .catch(() => {});
    };
    poll();
    const t = setInterval(poll, 10_000);
    return () => clearInterval(t);
  }, []);

  const handleNew = useCallback(() => {
    const s = newSession();
    setSessions(prev => [s, ...prev]);
    setActiveId(s.id);
  }, []);

  return (
    <div className="app">
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={handleNew}
        activeSessions={serverSessions}
      />
      <ChatPane
        messages={messages}
        streamingText={streamingText}
        status={status}
        onSend={send}
      />
    </div>
  );
}
