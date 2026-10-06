import { useState } from "react";
import { MapPin, Search } from "lucide-react";
import { MapContainer, TileLayer, CircleMarker, useMap, useMapEvents } from "react-leaflet";
import { useLocation } from "@/lib/location";

type SearchResult = {
  lat: string;
  lon: string;
  display_name: string;
};

const DEFAULT_CENTER: [number, number] = [24.0732, 75.0698];

function MapControls() {
  const location = useLocation();
  const map = useMap();
  const center: [number, number] =
    location.lat != null && location.lng != null
      ? [location.lat, location.lng]
      : DEFAULT_CENTER;

  useMapEvents({
    click: async (event) => {
      const { lat, lng } = event.latlng;
      location.setManual(lat, lng);
      try {
        const params = new URLSearchParams({
          format: "jsonv2",
          zoom: "10",
          addressdetails: "1",
          lat: String(lat),
          lon: String(lng),
        });
        const response = await fetch(`https://nominatim.openstreetmap.org/reverse?${params}`);
        const data = (await response.json()) as { address?: Record<string, string> };
        const city = data.address?.city ?? data.address?.town ?? data.address?.village;
        if (city) location.setManual(lat, lng, city);
      } catch {
        // The selected coordinates remain usable when reverse geocoding is unavailable.
      }
    },
  });

  map.setView(center);
  return location.lat != null && location.lng != null ? (
    <CircleMarker center={[location.lat, location.lng]} radius={10} pathOptions={{ color: "#141313", fillColor: "#009146", fillOpacity: 1 }} />
  ) : null;
}

export function LocationMapPicker() {
  const location = useLocation();
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  const search = async () => {
    if (query.trim().length < 3) return;
    setSearching(true);
    setError("");
    try {
      const params = new URLSearchParams({
        format: "jsonv2",
        limit: "1",
        q: query.trim(),
      });
      const response = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
      if (!response.ok) throw new Error("Search failed");
      const results = (await response.json()) as SearchResult[];
      const result = results[0];
      if (!result) {
        setError("Place nahi mila — map par pin lagao.");
        return;
      }
      const lat = Number(result.lat);
      const lng = Number(result.lon);
      location.setManual(lat, lng, result.display_name.split(",")[0]);
    } catch {
      setError("Search nahi ho payi. Map par tap karke pin lagao.");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="mt-4">
      <div className="flex items-center gap-2 rounded-2xl border-2 border-brand-ink/15 bg-background px-3">
        <Search className="w-4 h-4 text-brand-ink/45 shrink-0" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && void search()}
          placeholder="Mohalla, city ya landmark search karo"
          className="min-w-0 flex-1 bg-transparent px-1 py-3 text-sm font-bold outline-none"
        />
        <button type="button" onClick={() => void search()} disabled={searching} className="text-xs font-extrabold text-brand-green disabled:opacity-50">
          {searching ? "Dhoondh rahe…" : "Search"}
        </button>
      </div>
      {error && <p className="mt-2 text-xs font-bold text-[#F03749]">{error}</p>}
      <div className="location-map mt-3 overflow-hidden rounded-2xl border-2 border-brand-ink/15">
        <MapContainer center={DEFAULT_CENTER} zoom={13} scrollWheelZoom className="h-64 w-full">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MapControls />
        </MapContainer>
      </div>
      <p className="mt-2 flex items-center gap-1 text-[11px] font-bold text-muted-foreground">
        <MapPin className="h-3.5 w-3.5 text-brand-green" /> Map par tap karke apni exact location pin karo.
      </p>
    </div>
  );
}
