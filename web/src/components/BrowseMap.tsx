import { useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import { ShoppingBag } from "lucide-react";
import type { ProductCard } from "@/lib/api";
import { formatINR } from "@/lib/format";

interface BrowseMapProps {
  products: ProductCard[];
  centerLat?: number;
  centerLng?: number;
  onProductClick?: (product: ProductCard) => void;
}

const DEFAULT_CENTER: [number, number] = [24.0732, 75.0698]; // Mandsaur

function FitBounds({ products, centerLat, centerLng }: {
  products: ProductCard[]; centerLat?: number; centerLng?: number;
}) {
  const map = useMap();
  useMemo(() => {
    if (products.length === 0) {
      // Just center on the customer (or default).
      const center: [number, number] =
        centerLat != null && centerLng != null ? [centerLat, centerLng] : DEFAULT_CENTER;
      map.setView(center, 13);
      return;
    }
    // Bounds = all product shop lat/lngs + the customer's own location.
    const lats = products
      .map((p) => p.shop.lat)
      .filter((l): l is number => l != null);
    const lngs = products
      .map((p) => p.shop.lng)
      .filter((l): l is number => l != null);
    if (centerLat != null && centerLng != null) {
      lats.push(centerLat); lngs.push(centerLng);
    }
    if (lats.length === 0) {
      map.setView(DEFAULT_CENTER, 13); return;
    }
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
    if (minLat === maxLat && minLng === maxLng) {
      map.setView([minLat, minLng], 14); return;
    }
    map.fitBounds(
      [[minLat - 0.003, minLng - 0.003], [maxLat + 0.003, maxLng + 0.003]],
      { padding: [20, 20] },
    );
  }, [products, centerLat, centerLng, map]);
  return null;
}

const colourForPrice = (price?: number | null) => {
  if (price == null) return "#8A5A00"; // amber — price not provided
  if (price < 50) return "#009146"; // green — cheap
  if (price < 200) return "#FEE600"; // yellow — moderate
  return "#F03749"; // red — expensive
};

const radiusForDistance = (distanceMeters?: number | null) => {
  if (distanceMeters == null) return 8;
  // Closer shops = bigger circle (more relevant).
  return Math.max(8, Math.min(20, 20 - (distanceMeters / 500)));
};

/**
 * Hyperlocal map view for the Browse page. Shows product pins (one per
 * product-in-stock at a shop), coloured by price band and sized by
 * proximity to the customer. The customer's own location is a green dot.
 */
export function BrowseMap({ products, centerLat, centerLng, onProductClick }: BrowseMapProps) {
  // Group products by shop so we render one CircleMarker per shop with a
  // tooltip listing the available products there.
  const byShop = useMemo(() => {
    const map = new Map<string, { lat?: number | null; lng?: number | null; name: string; products: ProductCard[] }>();
    for (const p of products) {
      if (p.shop.lat == null || p.shop.lng == null) continue;
      const entry = map.get(p.shop.id) ?? {
        lat: p.shop.lat, lng: p.shop.lng, name: p.shop.name, products: [],
      };
      entry.products.push(p);
      map.set(p.shop.id, entry);
    }
    return Array.from(map.values());
  }, [products]);

  const hasCustomerPin = centerLat != null && centerLng != null;

  return (
    <div className="relative">
      <div className="location-map h-80 w-full">
        <MapContainer
          center={
            hasCustomerPin ? [centerLat!, centerLng!] : DEFAULT_CENTER
          }
          zoom={13}
          scrollWheelZoom
          className="h-full w-full"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {byShop.map((shop) => {
            if (shop.lat == null || shop.lng == null) return null;
            // Pick a representative price for colouring — the cheapest at this shop.
            const prices = shop.products
              .map((p) => p.price)
              .filter((p): p is number => p != null);
            const minPrice = prices.length ? Math.min(...prices) : null;
            const minDistance = Math.min(
              ...shop.products
                .map((p) => p.shop.distanceMeters)
                .filter((d): d is number => d != null),
            );
            const colour = colourForPrice(minPrice);
            const radius = radiusForDistance(minDistance);
            return (
              <CircleMarker
                key={shop.name}
                center={[shop.lat, shop.lng]}
                radius={radius}
                pathOptions={{
                  color: "#141313",
                  fillColor: colour,
                  fillOpacity: 0.7,
                  weight: 1.5,
                }}
                eventHandlers={{
                  click: () => onProductClick?.(shop.products[0]),
                }}
              >
                <Tooltip direction="top" offset={[0, -8]}>
                  <div className="text-[11px] font-bold leading-tight">
                    <div className="text-brand-ink">{shop.name}</div>
                    <div className="text-brand-ink/65">
                      {shop.products.length} product{shop.products.length === 1 ? "" : "s"}
                    </div>
                    {minPrice != null && (
                      <div className="text-brand-green">from {formatINR(minPrice)}</div>
                    )}
                    <div className="text-brand-ink/45 text-[10px]">tap to view →</div>
                  </div>
                </Tooltip>
              </CircleMarker>
            );
          })}
          {hasCustomerPin && (
            <CircleMarker
              center={[centerLat!, centerLng!]}
              radius={10}
              pathOptions={{
                color: "#141313",
                fillColor: "#009146",
                fillOpacity: 1,
                weight: 2.5,
              }}
            >
              <Tooltip direction="top" offset={[0, -10]} permanent>
                <div className="text-[11px] font-extrabold text-brand-ink">You</div>
              </Tooltip>
            </CircleMarker>
          )}
          <FitBounds products={products} centerLat={centerLat} centerLng={centerLng} />
        </MapContainer>
      </div>
      {/* legend */}
      <div className="absolute bottom-2 left-2 z-[1000] rounded-xl bg-brand-cream/95 backdrop-blur-sm border-2 border-brand-ink/15 p-2 flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center gap-1 text-[9.5px] font-extrabold text-brand-ink/65">
          <span className="w-2.5 h-2.5 rounded-full border border-brand-ink" style={{ background: "#009146" }} />
          Cheap
        </span>
        <span className="inline-flex items-center gap-1 text-[9.5px] font-extrabold text-brand-ink/65">
          <span className="w-2.5 h-2.5 rounded-full border border-brand-ink" style={{ background: "#FEE600" }} />
          Mid
        </span>
        <span className="inline-flex items-center gap-1 text-[9.5px] font-extrabold text-brand-ink/65">
          <span className="w-2.5 h-2.5 rounded-full border border-brand-ink" style={{ background: "#F03749" }} />
          Premium
        </span>
        <span className="inline-flex items-center gap-1 text-[9.5px] font-extrabold text-brand-ink/65">
          <span className="w-2.5 h-2.5 rounded-full border border-brand-ink" style={{ background: "#8A5A00" }} />
          No price
        </span>
      </div>
      {products.length === 0 && (
        <div className="absolute inset-0 grid place-items-center pointer-events-none">
          <div className="rounded-2xl bg-brand-cream/95 border-2 border-brand-ink/15 p-3 text-center max-w-xs">
            <ShoppingBag className="w-6 h-6 mx-auto text-muted-foreground" />
            <p className="text-[12px] font-bold text-muted-foreground mt-1">
              No listed products nearby yet —
              <br />ask shopkeepers to add inventory.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
