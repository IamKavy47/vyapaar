import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "@/lib/api";

interface LocationState {
  lat: number | null;
  lng: number | null;
  label: string;
  locating: boolean;
  locate: () => Promise<{ lat: number; lng: number } | null>;
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
  const auth = api.auth.me.useQuery(undefined, { staleTime: 1000 * 60 * 5, retry: false });
  const profile = api.profile.get.useQuery(undefined, {
    enabled: !!auth.data,
    staleTime: 1000 * 60 * 5,
  });
  const [loc, setLoc] = useState<{ lat: number | null; lng: number | null; label: string }>({
    lat: null,
    lng: null,
    label: "Location not set",
  });
  const [locating, setLocating] = useState(false);

  const locate = useCallback(() => {
    if (!navigator.geolocation) return Promise.resolve(null);
    setLocating(true);
    return new Promise<{ lat: number; lng: number } | null>((resolve) => {
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
          resolve({ lat: latitude, lng: longitude });
        },
        () => {
          setLocating(false);
          resolve(null);
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
      );
    });
  }, []);
  const setManual = useCallback((lat: number, lng: number, label = "Manual location") => {
    setLoc({ lat, lng, label });
  }, []);

  const savedLat = profile.data?.location?.lat ?? profile.data?.shop?.lat;
  const savedLng = profile.data?.location?.lng ?? profile.data?.shop?.lng;
  const value = useMemo(
    () => ({
      ...(loc.lat == null && loc.lng == null && savedLat != null && savedLng != null
        ? { lat: savedLat, lng: savedLng, label: "Saved location" }
        : loc),
      locating,
      locate,
      setManual,
    }),
    [loc, locating, locate, savedLat, savedLng, setManual],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLocation(): LocationState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLocation outside provider");
  return v;
}
