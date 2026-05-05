import { useEffect, useRef, useState, useCallback } from 'react';

export interface SSEMessage {
  type: string;
  data?: Record<string, unknown>;
  ts?: number;
  timestamp?: number;
}

type Listener = (msg: SSEMessage) => void;

let globalSource: EventSource | null = null;
let currentSessionId: string | null = null;
let listeners = new Set<Listener>();
let connectedState = false;

function getStreamUrl(sessionId: string) {
  return `/api/events/stream?session_id=${encodeURIComponent(sessionId)}`;
}

function broadcast(msg: SSEMessage) {
  listeners.forEach((fn) => fn(msg));
}

function connectSSE(sessionId: string) {
  if (globalSource && currentSessionId === sessionId) return;

  if (globalSource) {
    globalSource.close();
    globalSource = null;
  }

  currentSessionId = sessionId;

  try {
    globalSource = new EventSource(getStreamUrl(sessionId));
  } catch {
    connectedState = false;
    broadcast({ type: '_disconnected' });
    return;
  }

  globalSource.onopen = () => {
    connectedState = true;
    broadcast({ type: '_connected' });
  };

  globalSource.onerror = () => {
    connectedState = false;
    broadcast({ type: '_disconnected' });
  };

  globalSource.onmessage = (ev) => {
    try {
      const msg: SSEMessage = JSON.parse(ev.data);
      broadcast(msg);
    } catch { /* ignore non-json (keepalive comments) */ }
  };
}

export async function postChat(payload: {
  messages: Array<{ role: string; content: string }>;
  images?: string[];
  model?: string | null;
  backend?: string | null;
  temperature?: number;
  id: string;
  retry?: boolean;
}): Promise<{ status: string; chat_id: string }> {
  const res = await fetch('/api/events/chat/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Chat send failed: ${res.status}`);
  return res.json();
}

export async function postPlanAction(
  chatId: string,
  action: 'approve' | 'reject' | 'edit',
  opts?: { edits?: Array<Record<string, unknown>>; reason?: string },
): Promise<{ status: string; action: string }> {
  const res = await fetch(`/api/events/chat/${encodeURIComponent(chatId)}/plan-action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, edits: opts?.edits, reason: opts?.reason }),
  });
  if (!res.ok) throw new Error(`Plan action failed: ${res.status}`);
  return res.json();
}

export function useEventStream(sessionId: string) {
  const [connected, setConnected] = useState(connectedState);
  const listenersRef = useRef<Listener[]>([]);

  useEffect(() => {
    const handler: Listener = (msg) => {
      if (msg.type === '_connected') setConnected(true);
      if (msg.type === '_disconnected') setConnected(false);
      listenersRef.current.forEach((fn) => fn(msg));
    };
    listeners.add(handler);
    connectSSE(sessionId);
    return () => { listeners.delete(handler); };
  }, [sessionId]);

  const on = useCallback((fn: Listener) => {
    listenersRef.current.push(fn);
    return () => {
      listenersRef.current = listenersRef.current.filter((f) => f !== fn);
    };
  }, []);

  return { connected, on };
}
