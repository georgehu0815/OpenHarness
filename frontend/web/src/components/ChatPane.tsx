import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import type { ConnectionStatus, Message } from '../types';
import { MessageBubble } from './MessageBubble';
import { StreamingBubble } from './StreamingBubble';
import { StatusBar } from './StatusBar';

type Props = {
  messages: Message[];
  streamingText: string;
  status: ConnectionStatus;
  onSend: (text: string) => void;
};

export function ChatPane({ messages, streamingText, status, onSend }: Props) {
  const [draft, setDraft] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const busy = status === 'connected' && streamingText.length > 0;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  const submit = useCallback(() => {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft('');
    onSend(text);
  }, [draft, busy, onSend]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }, [submit]);

  return (
    <div className="chat-pane">
      <StatusBar status={status} />
      <div className="messages">
        {messages.map(m => <MessageBubble key={m.id} message={m} />)}
        <StreamingBubble text={streamingText} />
        <div ref={bottomRef} />
      </div>
      <div className="composer">
        <textarea
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          rows={1}
        />
        <button onClick={submit} disabled={!draft.trim() || busy}>
          Send
        </button>
      </div>
    </div>
  );
}
