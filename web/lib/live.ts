"use client";

import { useEffect, useRef, useState } from "react";
import { API_URL } from "./api";

export type LiveEvent =
  | { type: "message"; message: import("./api").ChatMessage }
  | { type: "transaction" | "transaction_updated"; transaction: import("./api").Transaction }
  | { type: "business"; business: import("./api").Business };

/** Subscribe to live events from the API. Reconnects automatically. */
export function useLiveEvents(onEvent: (e: LiveEvent) => void): boolean {
  const handler = useRef(onEvent);
  handler.current = onEvent;
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let ping: ReturnType<typeof setInterval> | undefined;

    const connect = () => {
      ws = new WebSocket(API_URL.replace(/^http/, "ws") + "/ws");
      ws.onopen = () => {
        setConnected(true);
        ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 20000);
      };
      ws.onmessage = (msg) => {
        try {
          handler.current(JSON.parse(msg.data));
        } catch {
          /* ignore malformed events */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        clearInterval(ping);
        if (!stopped) retry = setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      clearInterval(ping);
      ws?.close();
    };
  }, []);

  return connected;
}
