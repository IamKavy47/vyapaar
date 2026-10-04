import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { DEMO_CENTER } from "@/lib/localmart";

interface LocationState {
  lat: number;
  lng: number;
  label: string;
  locating: boolean;
  locate: () => void;
}

const Ctx = createContext<LocationState | null>(null);

export function LocationProvider({ children }: { children: ReactNode }) {
  const [loc, setLoc] = useState({ lat: DEMO_CENTER.lat, lng: DEMO_CENTER.lng, label: DEMO_CENTER.label });
  const [locating, setLocating] = useState(false);

  const locate = useCallback(() => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLoc({ lat: pos.coords.latitude, lng: pos.coords.longitude, label: "Your location" });
        setLocating(false);
      },
      () => setLocating(false),
      { timeout: 8000 },
    );
  }, []);

  const value = useMemo(
    () => ({ ...loc, locating, locate }),
    [loc, locating, locate],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLocation(): LocationState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLocation outside provider");
  return v;
}
