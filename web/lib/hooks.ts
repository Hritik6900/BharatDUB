"use client";
import { useEffect, useState } from "react";
import { api, type Health } from "./api";

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

export function useHealth(): Health | null | "down" {
  const [h, setH] = useState<Health | null | "down">(null);
  useEffect(() => {
    api<Health>("/health").then(setH).catch(() => setH("down"));
  }, []);
  return h;
}

export function useLocalNumber(key: string, initial: number): [number, (n: number) => void] {
  const [v, setV] = useState(initial);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw != null && !Number.isNaN(Number(raw))) setV(Number(raw));
    } catch {
      /* storage blocked */
    }
  }, [key]);
  const set = (n: number) => {
    setV(n);
    try {
      localStorage.setItem(key, String(n));
    } catch {
      /* storage blocked */
    }
  };
  return [v, set];
}
