import { renderHook, act } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/msw-server';
import { useGatewaySession, type CreateEventSource } from './useGatewaySession';
import { describe, it, expect, vi } from 'vitest';

function makeMockEs() {
  const es = {
    onopen: null as ((e: Event) => void) | null,
    onerror: null as ((e: Event) => void) | null,
    onmessage: null as ((e: MessageEvent) => void) | null,
    close: vi.fn(),
    fireOpen() { this.onopen?.(new Event('open')); },
    fireMessage(data: string) {
      this.onmessage?.(new MessageEvent('message', { data }));
    },
    fireError() { this.onerror?.(new Event('error')); },
  };
  return es;
}

describe('useGatewaySession', () => {
  it('starts with empty messages and connecting status', () => {
    const es = makeMockEs();
    const { result } = renderHook(() =>
      useGatewaySession('s1', () => es as unknown as EventSource)
    );
    expect(result.current.messages).toEqual([]);
    expect(result.current.streamingText).toBe('');
    expect(result.current.status).toBe('connecting');
  });

  it('final event commits message to messages array and clears streamingText', () => {
    const es = makeMockEs();
    const { result } = renderHook(() =>
      useGatewaySession('s2', () => es as unknown as EventSource)
    );

    act(() => {
      es.fireOpen();
      es.fireMessage('{"type":"final","message":"Hello agent!"}');
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe('assistant');
    expect(result.current.messages[0].text).toBe('Hello agent!');
    expect(result.current.streamingText).toBe('');
    expect(result.current.status).toBe('connected');
  });

  it('send() adds user message optimistically and POSTs to /api/chat', async () => {
    const postSpy = vi.fn();
    server.use(
      http.post('/api/chat', async ({ request }) => {
        postSpy(await request.json());
        return HttpResponse.json({ status: 'accepted' }, { status: 202 });
      })
    );

    const es = makeMockEs();
    const { result } = renderHook(() =>
      useGatewaySession('s3', () => es as unknown as EventSource)
    );

    await act(async () => {
      result.current.send('hello gateway');
      await new Promise(r => setTimeout(r, 50));
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe('user');
    expect(result.current.messages[0].text).toBe('hello gateway');
    expect(postSpy).toHaveBeenCalledWith({ session_id: 's3', message: 'hello gateway' });
  });

  it('error event sets status to error', () => {
    const es = makeMockEs();
    const { result } = renderHook(() =>
      useGatewaySession('s4', () => es as unknown as EventSource)
    );

    act(() => {
      es.fireMessage('{"type":"error","message":"Auth failed"}');
    });

    expect(result.current.status).toBe('error');
  });
});
