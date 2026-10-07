import { useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import { ShieldCheck } from "lucide-react";
import type { HeatmapPoint } from "@/lib/api";
import { categoryMeta } from "@/lib/localmart";

interface DemandHeatmapProps {
  points: HeatmapPoint[];
  center: [number, number];
}

/** Fit the map bounds to the points + the merchant's shop, so the heatmap
 * is always in view by default. */
function FitBounds({ points }: { points: HeatmapPoint[] }) {
  const map = useMap();
  useMemo(() => {
    if (points.length === 0) return;
    // Use a small bounds including all points; the merchant's centre is
    // guaranteed by the parent (it passes shop coords as `center`).
    const lats = points.map((p) => p.latitude);
    const lngs = points.map((p) => p.longitude);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLng = Math.min(...lngs);
    const maxLng = Math.max(...lngs);
    // Add some padding so the circles aren't on the edge.
    const pad = 0.005;
    // If only one unique point, just center on it (avoid zero-area bounds).
    if (minLat === maxLat && minLng === maxLng) {
      map.setView([minLat, minLng], 14);
      return;
    }
    map.fitBounds([
      [minLat - pad, minLng - pad],
      [maxLat + pad, maxLng + pad],
    ]);
  }, [points, map]);
  return null;
}

const intensityColor = (unavailableRate: number, uniqueRequests: number): string => {
  // Red intensity for unmet demand, scaled by request volume too.
  const base = unavailableRate;
  if (base >= 0.7) return "#F03749";  // high unmet demand — red
  if (base >= 0.4) return "#E8930C";  // medium — orange
  if (uniqueRequests >= 3) return "#FEE600"; // yellow (popular but available)
  return "#009146";  // green — small/healthy demand
};

const intensityRadius = (uniqueRequests: number): number => {
  // Bigger circle = more demand. Capped to keep things legible.
  return Math.max(10, Math.min(40, 10 + uniqueRequests * 3));
};

/**
 * Privacy-safe demand heatmap. Each circle is a *bucket* of demand (not an
 * individual customer) — the backend snaps demand points to ~300m grid centres
 * before grouping, so individual customer locations are never exposed.
 */
export function DemandHeatmap({ points, center }: DemandHeatmapProps) {
  if (points.length === 0) {
    return (
      <div className="rounded-3xl border-2 border-dashed border-brand-ink/20 bg-card p-6 text-center">
        <ShieldCheck className="w-7 h-7 mx-auto text-muted-foreground" />
        <p className="text-[13px] font-bold text-muted-foreground mt-2">
          Abhi demand map ke liye kafi data nahi hai.
        </p>
        <p className="text-[11px] font-bold text-muted-foreground mt-1">
          Jaise hi mohalle se requests aayengi, yahan demand buckets dikhega.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="location-map overflow-hidden rounded-2xl border-2 border-brand-ink/15">
        <MapContainer center={center} zoom={13} scrollWheelZoom className="h-72 w-full">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {points.map((p, i) => {
            const color = intensityColor(p.unavailableRate, p.uniqueRequests);
            const radius = intensityRadius(p.uniqueRequests);
            const catMeta = categoryMeta(
              // The backend uses backend category keys; the FE has its own taxonomy.
              // Fall back to "other" when the value isn't in the FE map.
              "other",
            );
            return (
              <CircleMarker
                key={`${p.latitude},${p.longitude},${p.product}-${i}`}
                center={[p.latitude, p.longitude]}
                radius={radius}
                pathOptions={{
                  color: "#141313",
                  fillColor: color,
                  fillOpacity: 0.55,
                  weight: 1.5,
                }}
              >
                <Tooltip direction="top" offset={[0, -8]}>
                  <div className="text-[11px] font-bold leading-tight">
                    <div className="text-brand-ink">{p.product}</div>
                    <div className="text-brand-ink/65">
                      {p.uniqueRequests} unique requests
                    </div>
                    <div className="text-brand-ink/65">
                      {p.unavailableRequests} unavailable ({Math.round(p.unavailableRate * 100)}%)
                    </div>
                    {p.category && (
                      <div className="text-brand-ink/45">{catMeta.label}</div>
                    )}
                  </div>
                </Tooltip>
              </CircleMarker>
            );
          })}
          <FitBounds points={points} />
        </MapContainer>
      </div>
      <p className="mt-2 flex items-center gap-1.5 text-[10.5px] font-bold text-muted-foreground">
        <ShieldCheck className="w-3.5 h-3.5 text-brand-green" />
        Demand points ~300m buckets mein aggregated hain — kisi individual customer
        ki location expose nahi hoti.
      </p>
      <div className="mt-2 flex items-center gap-3 flex-wrap text-[10.5px] font-extrabold">
        <Legend color="#F03749" label="High unmet" />
        <Legend color="#E8930C" label="Some unmet" />
        <Legend color="#FEE600" label="Popular" />
        <Legend color="#009146" label="Healthy" />
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-brand-ink/65">
      <span
        className="w-3 h-3 rounded-full border border-brand-ink"
        style={{ background: color }}
      />
      {label}
    </span>
  );
}
