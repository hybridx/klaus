import { useEffect, useRef, useState, useCallback } from 'react';

export interface WsMessage {
  type: string;
  data?: Record<string, unknown>;
  ts?: number;
  timestamp?: number;
}

type Listener = (msg: WsMessage) => void;

let globalWs: WebSocket | null = null;
let listeners = new Set<Listener>();
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let connectedState = false;

function getWsUrl() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/api/events/ws`;
}

function broadcast(msg: WsMessage) {
  listeners.forEach((fn) => fn(msg));
}

function connect() {
  if (globalWs?.readyState === WebSocket.OPEN) return;
  try {
    globalWs = new WebSocket(getWsUrl());
  } catch {
    scheduleReconnect();
    return;
  }

  globalWs.onopen = () => {
    connectedState = true;
    broadcast({ type: '_connected' });
  };

  globalWs.onclose = () => {
    connectedState = false;
    broadcast({ type: '_disconnected' });
    scheduleReconnect();
  };

  globalWs.onerror = () => {
    globalWs?.close();
  };

  globalWs.onmessage = (ev) => {
    try {
      const msg: WsMessage = JSON.parse(ev.data);
      broadcast(msg);
    } catch { /* ignore non-json */ }
  };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, 2000);
}

function send(data: Record<string, unknown>) {
  if (globalWs?.readyState === WebSocket.OPEN) {
    globalWs.send(JSON.stringify(data));
  }
}

export function useWebSocket() {
  const [connected, setConnected] = useState(connectedState);
  const listenersRef = useRef<Listener[]>([]);

  useEffect(() => {
    const handler: Listener = (msg) => {
      if (msg.type === '_connected') setConnected(true);
      if (msg.type === '_disconnected') setConnected(false);
      listenersRef.current.forEach((fn) => fn(msg));
    };
    listeners.add(handler);
    connect();
    return () => { listeners.delete(handler); };
  }, []);

  const on = useCallback((fn: Listener) => {
    listenersRef.current.push(fn);
    return () => {
      listenersRef.current = listenersRef.current.filter((f) => f !== fn);
    };
  }, []);

  return { connected, send, on };
}
