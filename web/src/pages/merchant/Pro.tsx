import { toast } from "sonner";
import {
  Crown, MapPinned, LineChart, Tag,
  PackageOpen, CalendarDays, ArrowRight, CheckCircle2, AlertTriangle,
  ShoppingCart, Banknote, CreditCard, Flame,
} from "lucide-react";
import { api as trpc } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { EmptyState, Sticker } from "@/components/brand";
import { formatINR, timeAgo } from "@/lib/format";

/**
 * Pro Dashboard — ₹299/month (14-day free trial).
 *
 * Six analytics benefits, all visible in one place so judges can see the full
 * monetisation story in a single screen:
 *
 *   1. Nearby hot products — top-10 SKUs in the shop's pin-code
 *   2. Demand heatmap — visual map of where customers are asking (lazy-loaded)
 *   3. Sales analytics — revenue trends + top sellers + slow movers
 *   4. Smart pricing suggestions — competitor-aware price recommendations
 *   5. Slow-mover alerts — inventory items with rising demand but flat stock
 *   6. Festival readiness — upcoming Indian festival stock-up advice
 *
 * If the user is not yet Pro, show the Subscribe CTA instead.
 */
export default function Pro() {
  const proStatus = trpc.merchant.proStatus.useQuery();
  const subscribe = trpc.merchant.subscribe.useMutation({
    onSuccess: () => {
      toast.success("14-din ka free trial shuru ho gaya! 🎉");
    },
    onError: (e) => toast.error(e.message),
  });
  const utils = trpc.useUtils();

  const isPro = proStatus.data?.isPro ?? false;
  const price = proStatus.data?.priceDisplay ?? "₹299/month";
  const trialDays = proStatus.data?.trialDays ?? 14;
  const expiresAt = proStatus.data?.proExpiresAt;

  const onSubscribe = async () => {
    await subscribe.mutateAsync();
    utils.merchant.proStatus.invalidate();
  };

  return (
    <div>
      <TopBar
        title="Pro Dashboard"
        sub="₹299/month · 6 analytics benefits"
        right={
          <Sticker rot={-3} color={isPro ? "#009146" : "#7C3AED"}>
            {isPro ? "Pro" : "Not Pro"}
          </Sticker>
        }
      />

      {/* ── Subscribe CTA card ── */}
      {!isPro && (
        <SubscribeCard
          price={price}
          trialDays={trialDays}
          isPending={subscribe.isPending}
          onSubscribe={onSubscribe}
        />
      )}

      {/* ── Pro benefits grid ── */}
      {isPro && (
        <>
          {expiresAt && (
            <div className="rounded-2xl border-2 border-brand-ink/15 bg-brand-ink p-4 mb-4">
              <div className="flex items-center gap-2 text-brand-yellow">
                <Crown className="w-4 h-4" />
                <span className="text-[11px] font-extrabold uppercase tracking-wide">
                  Pro active till {new Date(expiresAt).toLocaleDateString("en-IN", {
                    day: "numeric", month: "short", year: "numeric",
                  })}
                </span>
              </div>
              <p className="text-[12px] font-bold text-brand-cream/80 mt-1">
                {subscribe.isPending ? "Extending…" : "All 6 benefits unlocked below."}
              </p>
            </div>
          )}

          <BenefitGrid />
        </>
      )}
    </div>
  );
}

/* --------------------------------------------------------- Subscribe card */

function SubscribeCard({
  price, trialDays, isPending, onSubscribe,
}: {
  price: string; trialDays: number; isPending: boolean; onSubscribe: () => void;
}) {
  return (
    <div className="rounded-[28px] border-2 border-brand-ink bg-card overflow-hidden relative">
      {/* Hero header band */}
      <div className="bg-brand-ink p-5 relative overflow-hidden">
        <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full bg-brand-yellow/15" />
        <div className="absolute -bottom-12 -left-12 w-40 h-40 rounded-full bg-brand-yellow/10" />
        <div className="relative">
          <div className="flex items-center gap-2 text-brand-yellow">
            <Crown className="w-5 h-5" />
            <span className="text-[11px] font-extrabold uppercase tracking-[0.18em]">
              Vyapaar-Mitra Pro
            </span>
          </div>
          <div className="font-display text-[28px] leading-tight text-brand-cream mt-2">
            Apne mohalle ki demand intelligence unlock karein.
          </div>
          <p className="text-[12.5px] font-semibold text-brand-cream/75 mt-2 leading-relaxed">
            6 analytics benefits — sab ek dashboard mein. {price}. Pehle {trialDays} din free.
          </p>
        </div>
      </div>

      {/* Benefits list */}
      <div className="p-5">
        <ul className="space-y-2.5">
          {[
            { icon: Flame, t: "Nearby hot products", d: "Top-10 most-requested SKUs in your pin-code" },
            { icon: MapPinned, t: "Demand heatmap", d: "Visual map of where customers are asking (~300m buckets)" },
            { icon: LineChart, t: "Sales analytics", d: "Daily revenue trend + top sellers + slow movers" },
            { icon: Tag, t: "Smart pricing", d: "Recommended price vs. competitor offers + demand" },
            { icon: PackageOpen, t: "Slow-mover alerts", d: "Inventory items with rising demand but flat stock" },
            { icon: CalendarDays, t: "Festival readiness", d: "Upcoming festival stock-up advice by category" },
          ].map(({ icon: Icon, t, d }) => (
            <li key={t} className="flex items-start gap-3">
              <div className="shrink-0 w-9 h-9 rounded-2xl bg-brand-yellow/30 grid place-items-center">
                <Icon className="w-4 h-4 text-brand-ink" strokeWidth={2.4} />
              </div>
              <div>
                <div className="font-extrabold text-[13px] text-brand-ink">{t}</div>
                <div className="text-[11px] font-semibold text-muted-foreground">{d}</div>
              </div>
            </li>
          ))}
        </ul>

        {/* Subscribe CTA */}
        <button
          onClick={onSubscribe}
          disabled={isPending}
          className="mt-5 w-full rounded-2xl border-2 border-brand-ink bg-brand-yellow text-brand-ink text-[14px] font-extrabold py-3.5 flex items-center justify-center gap-2 disabled:opacity-60 hover:bg-brand-yellow/80 transition-all active:translate-y-[1px]"
        >
          <Crown className="w-5 h-5" strokeWidth={2.6} />
          {isPending ? "Starting trial…" : `Start ${trialDays}-day free trial`}
          <ArrowRight className="w-4 h-4" strokeWidth={2.6} />
        </button>
        <p className="text-[10.5px] font-bold text-muted-foreground mt-2 text-center">
          No payment for the hackathon demo — just tap and unlock. Production
          wire to Razorpay, same as customer checkout.
        </p>
      </div>
    </div>
  );
}

/* --------------------------------------------------------- Pro benefits grid */

function BenefitGrid() {
  return (
    <div className="space-y-5">
      {/* 1. Nearby hot products */}
      <NearbyHotProducts />

      {/* 2. Demand heatmap (reuse existing endpoint via the Demand page pattern) */}
      <DemandHeatmapEmbed />

      {/* 3. Sales analytics */}
      <SalesAnalyticsCard />

      {/* 4. Smart pricing suggestions */}
      <PricingSuggestionsCard />

      {/* 5. Slow-mover alerts */}
      <SlowMoverAlertsCard />

      {/* 6. Festival readiness */}
      <FestivalReadinessCard />
    </div>
  );
}

/* ── 1. Nearby hot products ── */
function NearbyHotProducts() {
  const q = trpc.merchant.nearbyHotProducts.useQuery({ days: 30, limit: 10 });
  const products = q.data?.products ?? [];
  return (
    <SectionCard
      icon={<Flame className="w-4 h-4" />}
      kicker="#1 · Pro benefit"
      title="Nearby hot products"
      sub="Top-10 most-requested SKUs in your pin-code (last 30 days)"
      isLoading={q.isLoading}
    >
      {products.length === 0 ? (
        <EmptyState
          icon={<Flame className="w-6 h-6" />}
          title="Abhi demand data nahi hai"
          sub="Jaise hi customers requests bhejenge, yahan top products dikhega."
        />
      ) : (
        <ol className="space-y-2">
          {products.map((p, i) => (
            <li key={i} className="flex items-center gap-3 rounded-2xl bg-card p-2.5 border-2 border-brand-ink/8">
              <div className="shrink-0 w-8 h-8 rounded-xl bg-brand-yellow/30 grid place-items-center text-[13px] font-extrabold text-brand-ink">
                {i + 1}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-extrabold text-[13px] truncate">{p.product}</div>
                <div className="text-[10.5px] font-bold text-muted-foreground">
                  {p.uniqueRequests} unique requests · {p.unavailable} unmet ·{" "}
                  {Math.round((p.unavailableRate ?? 0) * 100)}% miss rate
                </div>
              </div>
              {p.unavailableRate >= 0.5 && (
                <Sticker rot={-2} color="#F03749">Hot unmet</Sticker>
              )}
            </li>
          ))}
        </ol>
      )}
    </SectionCard>
  );
}

/* ── 2. Demand heatmap embed (uses existing merchant.heatmap hook) ── */
function DemandHeatmapEmbed() {
  // Heatmap is rendered via the existing DemandHeatmap component, gated by Pro.
  // We lazy-load it to keep the bundle split.
  // For now we show a call-to-action linking to the Demand page (which is
  // Pro-gated on its heatmap section in production). Inline-embedding leaflet
  // here would bloat this single page; the Demand page already does it well.
  return (
    <SectionCard
      icon={<MapPinned className="w-4 h-4" />}
      kicker="#2 · Pro benefit"
      title="Demand heatmap"
      sub="Visual map of where customers are asking (~300m buckets, privacy-safe)"
      isLoading={false}
    >
      <a
        href="/merchant/impact"
        className="block rounded-2xl border-2 border-dashed border-brand-ink/15 bg-card p-4 text-center hover:bg-brand-yellow/20 transition-colors"
      >
        <MapPinned className="w-7 h-7 mx-auto text-brand-ink" />
        <div className="font-extrabold text-[13px] mt-2">Open full-screen demand map →</div>
        <div className="text-[10.5px] font-bold text-muted-foreground mt-0.5">
          Available on the Impact page (Pro-gated)
        </div>
      </a>
    </SectionCard>
  );
}

/* ── 3. Sales analytics ── */
function SalesAnalyticsCard() {
  const q = trpc.merchant.salesAnalytics.useQuery({ days: 30 });
  const data = q.data;
  return (
    <SectionCard
      icon={<LineChart className="w-4 h-4" />}
      kicker="#3 · Pro benefit"
      title="Sales analytics"
      sub="Revenue trend · top sellers · slow movers · online vs cash"
      isLoading={q.isLoading}
    >
      {!data || data.totalOrders === 0 ? (
        <EmptyState
          icon={<LineChart className="w-6 h-6" />}
          title="Abhi koi paid order nahi hai"
          sub="Jab customers pay karenge (online ya cash), yahan revenue trend dikhega."
        />
      ) : (
        <>
          {/* Headline stats */}
          <div className="grid grid-cols-3 gap-2 mb-3">
            <StatBig label="Total revenue" value={formatINR(data.totalRevenue)} />
            <StatBig label="Total orders" value={String(data.totalOrders)} />
            <StatBig label="Avg order value" value={formatINR(data.averageOrderValue)} />
          </div>

          {/* Online vs cash breakdown */}
          <div className="flex items-center gap-2 mb-3 text-[11px] font-bold">
            <span className="inline-flex items-center gap-1 rounded-full bg-card px-2 py-0.5 border border-brand-ink/15">
              <CreditCard className="w-3 h-3" /> Online: {data.onlineVsCash.online}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-card px-2 py-0.5 border border-brand-ink/15">
              <Banknote className="w-3 h-3" /> Cash: {data.onlineVsCash.cash}
            </span>
          </div>

          {/* Mini revenue trend bar chart */}
          {data.revenueTrend.length > 0 && (
            <MiniBarChart
              data={data.revenueTrend.map((d) => ({ x: d.date.slice(5), y: d.revenue }))}
              label="Daily revenue (₹)"
            />
          )}

          {/* Top sellers */}
          {data.topSellers.length > 0 && (
            <div className="mt-3">
              <div className="text-[10.5px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1.5">
                Top sellers
              </div>
              <ul className="space-y-1.5">
                {data.topSellers.map((p, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 text-[12px]">
                    <span className="font-bold truncate">
                      <span className="text-muted-foreground">#{i + 1}</span> {p.product}
                    </span>
                    <span className="font-display text-[13px]">{formatINR(p.revenue)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Slow movers (sales-side, not demand-side) */}
          {data.slowMovers.length > 0 && (
            <div className="mt-3">
              <div className="text-[10.5px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1.5">
                Slow movers (least revenue)
              </div>
              <ul className="space-y-1.5">
                {data.slowMovers.map((p, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 text-[12px]">
                    <span className="font-bold truncate">{p.product}</span>
                    <span className="font-display text-[12.5px] text-muted-foreground">{formatINR(p.revenue)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </SectionCard>
  );
}

/* ── 4. Smart pricing suggestions ── */
function PricingSuggestionsCard() {
  const q = trpc.merchant.pricingSuggestions.useQuery({ limit: 8 });
  const suggestions = q.data?.suggestions ?? [];
  return (
    <SectionCard
      icon={<Tag className="w-4 h-4" />}
      kicker="#4 · Pro benefit"
      title="Smart pricing suggestions"
      sub="Recommended price vs. competitor offers (last 30 days)"
      isLoading={q.isLoading}
    >
      {suggestions.length === 0 ? (
        <EmptyState
          icon={<Tag className="w-6 h-6" />}
          title="Abhi pricing data nahi hai"
          sub="Inventory me price add karein aur competitors se offers aayenge — tab yahan suggestions dikhega."
        />
      ) : (
        <ul className="space-y-2">
          {suggestions.map((s, i) => {
            const recColor =
              s.recommendation === "lower" ? "#F03749"
              : s.recommendation === "raise" ? "#009146"
              : s.recommendation === "set" ? "#7C3AED"
              : "#8A5A00";
            return (
              <li key={i} className="rounded-2xl bg-card border-2 border-brand-ink/8 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-extrabold text-[13px] truncate">{s.product}</div>
                  <Sticker rot={-2} color={recColor}>
                    {s.recommendation.toUpperCase()}
                  </Sticker>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-2 text-[10.5px] font-bold">
                  <div>
                    <div className="text-muted-foreground uppercase tracking-wide">Your price</div>
                    <div className="text-[13px] font-display">
                      {s.yourPrice != null ? formatINR(s.yourPrice) : "—"}
                    </div>
                  </div>
                  <div>
                    <div className="text-muted-foreground uppercase tracking-wide">Market median</div>
                    <div className="text-[13px] font-display">{formatINR(s.medianMarketPrice)}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground uppercase tracking-wide">Recommended</div>
                    <div className="text-[13px] font-display">{formatINR(s.recommendedPrice)}</div>
                  </div>
                </div>
                <p className="text-[11px] font-semibold text-brand-ink/70 mt-2 leading-snug">
                  {s.reason}
                </p>
                <div className="text-[10px] font-bold text-muted-foreground mt-1">
                  Sample: {s.sampleSize} competitor offers · range{" "}
                  {formatINR(s.minMarketPrice)}–{formatINR(s.maxMarketPrice)}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}

/* ── 5. Slow-mover alerts ── */
function SlowMoverAlertsCard() {
  const q = trpc.merchant.slowMoverAlerts.useQuery(undefined, { refetchInterval: 60000 });
  const alerts = q.data?.alerts ?? [];
  return (
    <SectionCard
      icon={<PackageOpen className="w-4 h-4" />}
      kicker="#5 · Pro benefit"
      title="Slow-mover alerts"
      sub="Inventory items with rising demand but no recent restock"
      isLoading={q.isLoading}
    >
      {alerts.length === 0 ? (
        <EmptyState
          icon={<CheckCircle2 className="w-6 h-6" />}
          title="Koi slow-mover alert nahi"
          sub="Sab inventory items recently restocked hain ya demand nahi badh rahi."
        />
      ) : (
        <ul className="space-y-2">
          {alerts.map((a, i) => (
            <li key={i} className="rounded-2xl bg-[#FEE60008] border-2 border-brand-yellow/40 p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-brand-ink mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-extrabold text-[13px] truncate">{a.product}</div>
                    <Sticker rot={-2} color="#F03749">
                      +{Math.round((a.demandRatio - 1) * 100)}% demand
                    </Sticker>
                  </div>
                  <p className="text-[11px] font-semibold text-brand-ink/75 mt-1 leading-snug">
                    {a.reason}
                  </p>
                  <div className="text-[10px] font-bold text-muted-foreground mt-1">
                    Last restock: {timeAgo(a.lastRestockedAt)} · last 7d:{" "}
                    {a.demand7d} reqs · prev 7d: {a.demandPrev7d} reqs
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

/* ── 6. Festival readiness ── */
function FestivalReadinessCard() {
  const q = trpc.merchant.festivalReadiness.useQuery(undefined, { refetchInterval: 300000 });
  const fest = q.data?.nextFestival;
  const stockUp = q.data?.stockUp ?? [];
  return (
    <SectionCard
      icon={<CalendarDays className="w-4 h-4" />}
      kicker="#6 · Pro benefit"
      title="Festival readiness"
      sub="Upcoming Indian festival stock-up advice (filtered by your shop's category)"
      isLoading={q.isLoading}
    >
      {!fest ? (
        <EmptyState
          icon={<CalendarDays className="w-6 h-6" />}
          title="Koi festival nahi aane wala"
          sub={q.data?.reason ?? "Next 21 din mein koi major festival nahi hai."}
        />
      ) : (
        <>
          <div className="rounded-2xl bg-brand-ink p-3 mb-3">
            <div className="flex items-center gap-2 text-brand-yellow">
              <CalendarDays className="w-4 h-4" />
              <span className="text-[10.5px] font-extrabold uppercase tracking-wide">
                {fest.daysUntil === 0 ? "Aaj" : `${fest.daysUntil} din mein`}
              </span>
            </div>
            <div className="font-display text-[18px] text-brand-cream mt-1">{fest.name}</div>
            <div className="text-[10.5px] font-bold text-brand-cream/70 mt-0.5">
              {new Date(fest.date).toLocaleDateString("en-IN", {
                day: "numeric", month: "long", year: "numeric",
              })}
            </div>
            <p className="text-[10.5px] font-semibold text-brand-cream/65 mt-2 leading-snug">
              {fest.note}
            </p>
          </div>

          {stockUp.length === 0 ? (
            <p className="text-[11px] font-bold text-muted-foreground">
              Aapki shop category ({q.data?.shopCategory}) ke liye koi specific
              stock-up recommendation nahi. Generic items: diya, sweets, dry fruits.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {stockUp.map((item, i) => (
                <li key={i} className="rounded-2xl bg-card border-2 border-brand-ink/8 p-2.5 flex items-center gap-3">
                  <div className="shrink-0 w-9 h-9 rounded-xl bg-brand-yellow/30 grid place-items-center">
                    <ShoppingCart className="w-4 h-4 text-brand-ink" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-extrabold text-[12.5px] truncate">{item.product}</span>
                      {item.alreadyInInventory && (
                        <span className="rounded-full bg-brand-green/15 px-1.5 py-0.5 text-[8.5px] font-extrabold text-brand-green">
                          ✓ stocked
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] font-bold text-muted-foreground">
                      {item.reason} · {item.recommendedQuantity} units
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </SectionCard>
  );
}

/* --------------------------------------------------------- shared components */

function SectionCard({
  icon, kicker, title, sub, isLoading, children,
}: {
  icon: React.ReactNode;
  kicker: string;
  title: string;
  sub: string;
  isLoading: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[28px] border-2 border-brand-ink/10 bg-card overflow-hidden">
      <div className="p-4">
        <div className="flex items-start gap-3 mb-3">
          <div className="shrink-0 w-10 h-10 rounded-2xl bg-brand-ink grid place-items-center text-brand-yellow">
            {icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-muted-foreground">
              {kicker}
            </div>
            <div className="font-display text-[18px] leading-tight">{title}</div>
            <div className="text-[10.5px] font-bold text-muted-foreground">{sub}</div>
          </div>
        </div>
        {isLoading ? (
          <div className="space-y-2.5">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-2xl border-2 border-brand-ink/8 bg-card h-[60px] animate-pulse" />
            ))}
          </div>
        ) : children}
      </div>
    </section>
  );
}

function StatBig({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-brand-ink/5 p-2 text-center">
      <div className="text-[9px] font-extrabold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="font-display text-[14px] leading-tight mt-0.5">{value}</div>
    </div>
  );
}

/** Inline mini bar chart — pure SVG, no chart library needed. */
function MiniBarChart({ data, label }: { data: Array<{ x: string; y: number }>; label: string }) {
  if (data.length === 0) return null;
  const max = Math.max(...data.map((d) => d.y), 1);
  const W = 320;
  const H = 90;
  const barW = Math.max(2, (W / data.length) - 2);
  return (
    <div className="mt-3">
      <div className="text-[10.5px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1.5">
        {label}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[90px]" preserveAspectRatio="none">
        {data.map((d, i) => {
          const x = i * (W / data.length);
          const h = (d.y / max) * (H - 14);
          const y = H - h - 12;
          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={h}
                fill="#97781b"
                rx={1.5}
              />
            </g>
          );
        })}
      </svg>
      <div className="flex justify-between text-[8.5px] font-bold text-muted-foreground mt-0.5">
        <span>{data[0]?.x}</span>
        <span>{data[data.length - 1]?.x}</span>
      </div>
    </div>
  );
}
