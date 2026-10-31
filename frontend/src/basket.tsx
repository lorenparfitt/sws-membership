import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

// What the member intends to buy, kept in this browser until checkout makes
// an order of it. Product ids only; prices are always asked of the API.
const STORAGE_KEY = "sws-basket";

interface BasketState {
  ids: number[];
  has: (id: number) => boolean;
  add: (id: number) => void;
  remove: (id: number) => void;
  clear: () => void;
}

const BasketContext = createContext<BasketState | null>(null);

function stored(): number[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((v): v is number => typeof v === "number") : [];
  } catch {
    return [];
  }
}

export function BasketProvider({ children }: { children: ReactNode }) {
  const [ids, setIds] = useState<number[]>(stored);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
    } catch {
      // Private mode or blocked storage: the basket lives for this page load only.
    }
  }, [ids]);

  const has = useCallback((id: number) => ids.includes(id), [ids]);
  const add = useCallback((id: number) => setIds((current) => (current.includes(id) ? current : [...current, id])), []);
  const remove = useCallback((id: number) => setIds((current) => current.filter((v) => v !== id)), []);
  const clear = useCallback(() => setIds([]), []);

  const value = useMemo(() => ({ ids, has, add, remove, clear }), [ids, has, add, remove, clear]);
  return <BasketContext.Provider value={value}>{children}</BasketContext.Provider>;
}

export function useBasket(): BasketState {
  const state = useContext(BasketContext);
  if (!state) throw new Error("useBasket outside BasketProvider");
  return state;
}
