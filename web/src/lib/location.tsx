import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
interface LocationState {
  lat: number | null;
  lng: number | null;
  label: string;
  locating: boolean;
  locate: () => void;
  setManual: (lat: number, lng: number) => void;
}

const Ctx = createContext<LocationState | null>(null);

export function LocationProvider({ children }: { children: ReactNode }) {
  const [loc, setLoc] = useState<{ lat: number | null; lng: number | null; label: string }>({
    lat: null,
    lng: null,
    label: "Location not set",
  });
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
  const setManual = useCallback((lat: number, lng: number) => {
    setLoc({ lat, lng, label: "Manual location" });
  }, []);

  const value = useMemo(
    () => ({ ...loc, locating, locate, setManual }),
    [loc, locating, locate, setManual],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLocation(): LocationState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLocation outside provider");
  return v;
}
