"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { AppConfig, Business, getJSON } from "@/lib/api";
import { LiveEvent, useLiveEvents } from "@/lib/live";

type Ctx = {
  businesses: Business[];
  business: Business | null;
  setBusinessId: (id: number) => void;
  config: AppConfig | null;
  connected: boolean;
  error: string | null;
  subscribe: (fn: (e: LiveEvent) => void) => () => void;
};

const BusinessCtx = createContext<Ctx | null>(null);

export function BusinessProvider({ children }: { children: React.ReactNode }) {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [businessId, setId] = useState<number | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [listeners] = useState(() => new Set<(e: LiveEvent) => void>());

  const load = useCallback(async () => {
    try {
      const [list, cfg] = await Promise.all([getJSON<Business[]>("/api/businesses"), getJSON<AppConfig>("/api/config")]);
      setBusinesses(list);
      setConfig(cfg);
      setError(null);
      setId((current) => {
        if (current && list.some((b) => b.id === current)) return current;
        let saved: number | null = null;
        try {
          saved = Number(localStorage.getItem("kasiledger.business")) || null;
        } catch {
          /* storage unavailable */
        }
        return list.find((b) => b.id === saved)?.id ?? list[0]?.id ?? null;
      });
    } catch {
      setError("The KasiLedger API isn't reachable. Start it with: uvicorn app.main:app --reload (in the backend folder).");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const connected = useLiveEvents((e) => {
    if (e.type === "business") load();
    listeners.forEach((fn) => fn(e));
  });

  useEffect(() => {
    if (connected) load();
  }, [connected, load]);

  const setBusinessId = (id: number) => {
    setId(id);
    try {
      localStorage.setItem("kasiledger.business", String(id));
    } catch {
      /* storage unavailable */
    }
  };

  const subscribe = useCallback(
    (fn: (e: LiveEvent) => void) => {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
    [listeners],
  );

  const business = businesses.find((b) => b.id === businessId) ?? null;
  return (
    <BusinessCtx.Provider value={{ businesses, business, setBusinessId, config, connected, error, subscribe }}>
      {children}
    </BusinessCtx.Provider>
  );
}

export function useBusiness() {
  const ctx = useContext(BusinessCtx);
  if (!ctx) throw new Error("useBusiness must be inside BusinessProvider");
  return ctx;
}

export function useLive(fn: (e: LiveEvent) => void) {
  const { subscribe } = useBusiness();
  useEffect(() => subscribe(fn), [subscribe, fn]);
}
