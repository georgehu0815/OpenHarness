export type GatewayEvent = {
  type: 'progress' | 'delta' | 'final' | 'error' | 'ping';
  message?: string;
};

export type Message = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
};

export type SessionInfo = {
  id: string;
  label: string;
  createdAt: number;
};

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';
