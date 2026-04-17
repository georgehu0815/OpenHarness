import type { SessionInfo } from '../types';

type Props = {
  sessions: SessionInfo[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  activeSessions: string[];
};

export function SessionSidebar({ sessions, activeId, onSelect, onNew, activeSessions }: Props) {
  return (
    <nav className="sidebar">
      <div className="sidebar-title">Sessions</div>
      {sessions.map(s => (
        <div
          key={s.id}
          className={`session-item${s.id === activeId ? ' active' : ''}`}
          onClick={() => onSelect(s.id)}
        >
          {activeSessions.includes(s.id) && <span className="dot" />}
          {s.label}
        </div>
      ))}
      <button className="new-chat-btn" onClick={onNew}>+ New chat</button>
    </nav>
  );
}
