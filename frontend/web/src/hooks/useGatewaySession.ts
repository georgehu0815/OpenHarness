import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConnectionStatus, GatewayEvent, Message } from '../types';

declare global {
  interface Window { GATEWAY_API_URL?: string; }
}

export type CreateEventSource = (url: string) => EventSource;

const GATEWAY_API_URL: string =
  (typeof window !== 'undefined' && window.GATEWAY_API_URL) ||
  (import.meta.env.VITE_GATEWAY_API_URL as string | undefined) ||
  '';

const FLUSH_INTERVAL_MS = 50;
const FLUSH_CHARS = 384;

function makeId(): string {
  return Math.random().toString(36).slice(2);
}

export type UseGatewaySessionReturn = {
  messages: Message[];
  streamingText: string;
  status: ConnectionStatus;
  send: (text: string) => void;
};

const defaultCreateEs: CreateEventSource = (url) => new EventSource(url);

export function useGatewaySession(
  sessionId: string,
  createEventSource: CreateEventSource = defaultCreateEs,
): UseGatewaySessionReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [status, setStatus] = useState<ConnectionStatus>('connecting');

  const pendingDeltaRef = useRef('');
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushDelta = useCallback(() => {
    const pending = pendingDeltaRef.current;
    if (!pending) return;
    pendingDeltaRef.current = '';
    setStreamingText(prev => prev + pending);
  }, []);

  const commitStreaming = useCallback((finalText: string) => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    pendingDeltaRef.current = '';
    setStreamingText('');
    setMessages(prev => [...prev, { id: makeId(), role: 'assistant', text: finalText }]);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    const url = `${GATEWAY_API_URL}/api/stream?session_id=${encodeURIComponent(sessionId)}`;
    const es = createEventSource(url);

    es.onopen = () => setStatus('connected');
    es.onerror = () => setStatus('disconnected');

    es.onmessage = (evt: MessageEvent) => {
      let event: GatewayEvent;
      try { event = JSON.parse(evt.data as string) as GatewayEvent; } catch { return; }

      if (event.type === 'ping') return;

      if (event.type === 'progress') {
        setStatus('connected');
        return;
      }

      if (event.type === 'delta') {
        pendingDeltaRef.current += event.message ?? '';
        if (pendingDeltaRef.current.length >= FLUSH_CHARS) {
          flushDelta();
          return;
        }
        if (!flushTimerRef.current) {
          flushTimerRef.current = setTimeout(() => {
            flushTimerRef.current = null;
            flushDelta();
          }, FLUSH_INTERVAL_MS);
        }
        return;
      }

      if (event.type === 'final') {
        commitStreaming(event.message ?? '');
        setStatus('connected');
        return;
      }

      if (event.type === 'error') {
        setMessages(prev => [
          ...prev,
          { id: makeId(), role: 'assistant', text: `⚠️ ${event.message ?? 'Unknown error'}` },
        ]);
        setStatus('error');
        setStreamingText('');
      }
    };

    return () => {
      es.close();
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
    };
  }, [sessionId, createEventSource, flushDelta, commitStreaming]);

  const send = useCallback((text: string) => {
    setMessages(prev => [...prev, { id: makeId(), role: 'user', text }]);
    setStatus('connected');
    fetch(`${GATEWAY_API_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    }).catch(() => setStatus('error'));
  }, [sessionId]);

  return { messages, streamingText, status, send };
}
