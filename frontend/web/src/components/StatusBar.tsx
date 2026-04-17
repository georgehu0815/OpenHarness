import type { ConnectionStatus } from '../types';

type Props = { status: ConnectionStatus; label?: string };

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connecting: 'Connecting…',
  connected: 'Connected',
  disconnected: 'Disconnected',
  error: 'Connection error',
};

export function StatusBar({ status, label }: Props) {
  return (
    <div className={`status-bar ${status}`}>
      <span className="dot" />
      <span>{label ?? STATUS_LABELS[status]}</span>
    </div>
  );
}
