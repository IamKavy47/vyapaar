import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

interface LocationState {
  lat: number | null;
  lng: number | null;
  label: string;
  locating: boolean;
  locate: () => Promise<boolean>;
  setManual: (lat: number, lng: number, label?: string) => void;
}

const Ctx = createContext<LocationState | null>(null);

async function cityForCoordinates(lat: number, lng: number): Promise<string | null> {
  const params = new URLSearchParams({
    format: "jsonv2",
    zoom: "10",
    addressdetails: "1",
    lat: String(lat),
    lon: String(lng),
  });
  const response = await fetch(`https://nominatim.openstreetmap.org/reverse?${params}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) return null;
  const data = (await response.json()) as { address?: Record<string, string> };
  const address = data.address;
  return address?.city ?? address?.town ?? address?.village ?? address?.municipality ?? null;
}

export function LocationProvider({ children }: { children: ReactNode }) {
  const [loc, setLoc] = useState<{ lat: number | null; lng: number | null; label: string }>({
    lat: null,
    lng: null,
    label: "Location not set",
  });
  const [locating, setLocating] = useState(false);

  const locate = useCallback(() => {
    if (!navigator.geolocation) return Promise.resolve(false);
    setLocating(true);
    return new Promise<boolean>((resolve) => {
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const { latitude, longitude } = pos.coords;
          let city: string | null = null;
          try {
            city = await cityForCoordinates(latitude, longitude);
          } catch {
            // Coordinates are still useful if reverse geocoding is unavailable.
          }
          setLoc({
            lat: latitude,
            lng: longitude,
            label: city ?? "Your location",
          });
          setLocating(false);
          resolve(true);
        },
        () => {
          setLocating(false);
          resolve(false);
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
      );
    });
  }, []);
  const setManual = useCallback((lat: number, lng: number, label = "Manual location") => {
    setLoc({ lat, lng, label });
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
