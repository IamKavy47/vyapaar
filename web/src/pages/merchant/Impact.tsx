import { useState, lazy, Suspense } from "react";
import {
  Activity, MapPin, Sparkles, TrendingUp, Users, Store, Gauge, MapPinned,
} from "lucide-react";
import { api as trpc, type HeatmapPoint } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { CategoryIcon, EmptyState, Sticker } from "@/components/brand";
import { clsx, formatDistance } from "@/lib/format";
import { categoryMeta } from "@/lib/localmart";

// Lazy-load to keep the heavy leaflet code split out of the main bundle path.
const DemandHeatmapLazyImpl = lazy(() =>
  import("@/components/DemandHeatmap").then((m) => ({ default: m.DemandHeatmap })),
);

function DemandHeatmapLazy(props: {
  points: HeatmapPoint[];
  center: [number, number];
}) {
  return (
    <Suspense
      fallback={
        <div className="rounded-2xl border-2 border-brand-ink/15 bg-card h-72 animate-pulse" />
      }
    >
      <DemandHeatmapLazyImpl {...props} />
    </Suspense>
  );
}

const PERIODS = [
  { days: 7, label: "7 din" },
  { days: 30, label: "30 din" },
  { days: 90, label: "90 din" },
];

/**
 * Judge-friendly impact dashboard — understood in under 30 seconds.
 * Honest metrics only; demo data is clearly labelled "Demo data" so judges
 * know they're not looking at fake production numbers.
 */
export default function Impact() {
  const [days, setDays] = useState(30);
  const impact = trpc.merchant.impact.useQuery({ days });
  const profile = trpc.profile.get.useQuery();
  const shopLocation = profile.data?.shop?.lat && profile.data?.shop?.lng
    ? [profile.data.shop.lat, profile.data.shop.lng] as [number, number]
    : null;
  // Heatmap shown alongside impact — same period, same shop centre.
  const heatmap = trpc.merchant.heatmap.useQuery({ days, limit: 60 });

  const metrics = impact.data?.metrics;
  const insight = impact.data?.neighborhoodInsight;
  const isDemo = impact.data?.isDemoData ?? false;

  return (
    <div>
      <TopBar
        title="Impact"
        sub="Mohalle ka asar — 30 second mein"
        right={
          <Sticker rot={-3} color={isDemo ? "#7C3AED" : "#009146"}>
            {isDemo ? "Demo data" : "Live"}
          </Sticker>
        }
      />

      {/* Period selector */}
      <div className="flex items-center gap-1.5 rounded-full border-2 border-brand-ink/15 bg-card p-1 mb-5 overflow-x-auto">
        {PERIODS.map((p) => (
          <button
            key={p.days}
            type="button"
            onClick={() => setDays(p.days)}
            className={clsx(
              "rounded-full px-3 py-1 text-[11.5px] font-extrabold whitespace-nowrap",
              days === p.days
                ? "bg-brand-ink text-brand-yellow"
                : "text-brand-ink/60 hover:text-brand-ink",
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      {impact.isLoading && (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card h-[100px] animate-pulse" />
          ))}
        </div>
      )}

      {metrics && (
        <>
          {/* Headline stat block */}
          <div className="rounded-[28px] border-2 border-brand-ink bg-brand-ink p-5 mb-4 relative overflow-hidden">
            <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full bg-brand-green/15" />
            <div className="text-[10.5px] font-extrabold uppercase tracking-[0.18em] text-brand-yellow">
              {days === 30 ? "Is mahine" : days === 7 ? "Is hafte" : "Is quarter"} ka summary
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Headline
                icon={<Users className="w-4 h-4" />}
                value={metrics.uniqueCustomerRequests}
                label="unique customer requests"
              />
              <Headline
                icon={<Store className="w-4 h-4" />}
                value={metrics.requestsMatched}
                label="matched to a nearby shop"
              />
              <Headline
                icon={<Sparkles className="w-4 h-4" />}
                value={metrics.zeroInventoryMatches}
                label="matched without merchant inventory"
              />
              <Headline
                icon={<Gauge className="w-4 h-4" />}
                value={metrics.successfulCustomerSelections}
                label="customer selections completed"
              />
            </div>
          </div>

          {/* Detailed metrics grid */}
          <div className="grid grid-cols-2 gap-3 mb-5">
            <Metric
              icon={<Activity className="w-4 h-4 text-brand-green" />}
              label="Merchant response rate"
              value={`${Math.round(metrics.merchantResponseRate * 100)}%`}
              note={`${metrics.merchantResponseAttempts} attempts`}
            />
            <Metric
              icon={<TrendingUp className="w-4 h-4 text-[#F03749]" />}
              label="Unmet demand discovered"
              value={`${metrics.unavailableResponses}`}
              note="merchants said unavailable"
            />
            <Metric
              icon={<MapPin className="w-4 h-4 text-brand-ink" />}
              label="Average search radius"
              value={formatDistance(metrics.avgSearchDistanceMeters)}
              note="reduced by matching"
            />
            <Metric
              icon={<MapPinned className="w-4 h-4 text-brand-yellow" />}
              label="Search distance saved (est.)"
              value={formatDistance(metrics.estimatedSearchDistanceSavedMeters)}
              note="vs hypothetical 5km city search"
            />
          </div>

          {/* Neighborhood insight: "What would improve this neighborhood most?" */}
          {insight ? (
            <section className="rounded-[28px] border-2 border-brand-ink bg-brand-yellow/40 p-5 mb-5 relative overflow-hidden">
              <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full bg-brand-ink/8" />
              <div className="flex items-center gap-2">
                <CategoryIcon
                  categoryKey={(insight.category ?? "other") as any}
                  size={32}
                />
                <div>
                  <div className="text-[10.5px] font-extrabold uppercase tracking-[0.18em] text-[#8A5A00]">
                    Is mohalle ko sabse zyada kya chahiye?
                  </div>
                  <div className="font-display text-[18px] leading-tight">
                    {insight.product}
                  </div>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <Mini value={insight.uniqueRequests} label="requests" />
                <Mini value={insight.unavailableRequests} label="unavailable" />
                <Mini value={`${Math.round(insight.unavailableRate * 100)}%`} label="unmet" />
              </div>
              <p className="text-[12px] font-semibold text-brand-ink/75 mt-3 leading-relaxed">
                {insight.reason}
              </p>
              <p className="text-[10.5px] font-bold text-brand-ink/55 mt-2">
                Suggested action: nearby {categoryMeta((insight.category ?? "other") as any).label}{" "}
                shops could keep this product in stock.
              </p>
            </section>
          ) : (
            <div className="rounded-3xl border-2 border-dashed border-brand-ink/20 bg-card p-5 mb-5">
              <EmptyState
                icon={<TrendingUp className="w-7 h-7" />}
                title="Insufficient neighborhood data"
                sub="Kuch requests aane ke baad yahan sabse bada unmet demand product dikhega."
              />
            </div>
          )}

          {/* Heatmap */}
          <section className="mb-5">
            <h2 className="font-display text-[18px] mb-3 flex items-center gap-2">
              <MapPinned className="w-5 h-5" /> Demand map
            </h2>
            {shopLocation ? (
              <DemandHeatmapLazy
                points={heatmap.data?.points ?? []}
                center={shopLocation}
              />
            ) : (
              <p className="text-[12px] font-bold text-muted-foreground">
                Apni shop ki location set karo to demand map yahan dikhega.
              </p>
            )}
          </section>
        </>
      )}

      {!impact.isLoading && !metrics && (
        <EmptyState
          icon={<Activity className="w-7 h-7" />}
          title="Abhi impact data nahi hai"
          sub="Jaise hi requests aayengi, yahan metrics dikhega."
        />
      )}

      <p className="text-[11px] font-bold text-muted-foreground mt-4 text-center">
        Saare metrics demand_events aur product_requests collections se computed hain —
        koi fabrication nahi hai.
        {isDemo && (
          <span className="block mt-1 text-[#7C3AED]">
            Demo data: yeh numbers seeded demo activity se aaye hain, real production activity nahi.
          </span>
        )}
      </p>
    </div>
  );
}

function Headline({ icon, value, label }: { icon: React.ReactNode; value: number; label: string }) {
  return (
    <div className="rounded-2xl bg-brand-cream p-3">
      <div className="flex items-center gap-1.5 text-[#8A5A00]">
        {icon}
        <span className="text-[10px] font-extrabold uppercase tracking-wide">{label.split(" ")[0]}</span>
      </div>
      <div className="font-display text-[26px] leading-none mt-1 text-brand-ink">{value}</div>
      <div className="text-[10px] font-bold text-brand-ink/55 mt-0.5">
        {label.split(" ").slice(1).join(" ")}
      </div>
    </div>
  );
}

function Metric({
  icon, label, value, note,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="rounded-3xl border-2 border-brand-ink/10 bg-card p-4">
      <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground">
        {icon} {label}
      </div>
      <div className="font-display text-[20px] mt-1.5">{value}</div>
      {note && (
        <div className="text-[10.5px] font-bold text-muted-foreground mt-0.5">{note}</div>
      )}
    </div>
  );
}

function Mini({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="rounded-xl bg-brand-cream/60 p-2">
      <div className="font-display text-[16px] leading-none">{value}</div>
      <div className="text-[9px] font-extrabold uppercase tracking-wide text-brand-ink/55 mt-1">
        {label}
      </div>
    </div>
  );
}
