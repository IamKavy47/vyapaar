import { useState } from "react";
import { toast } from "sonner";
import {
  TrendingUp, Flame, Lightbulb, ShieldCheck, ArrowRight, Package,
} from "lucide-react";
import { useNavigate } from "react-router";
import { api as trpc } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { CategoryIcon, EmptyState, Sticker } from "@/components/brand";
import { categoryMeta } from "@/lib/localmart";
import { clsx } from "@/lib/format";

const PERIODS = [
  { days: 7, label: "7 din" },
  { days: 30, label: "30 din" },
  { days: 90, label: "90 din" },
];

/**
 * Merchant demand dashboard — the "neighborhood demand intelligence" surface.
 *
 * Sections (top to bottom):
 *   1. Honest stats callout: "X unique customer requests · Y merchant responses"
 *   2. Stock opportunities (Priority 2) — explainable opportunity scoring,
 *      with an "Add to inventory plan" button per product (does NOT auto-add
 *      stock without merchant confirmation).
 *   3. Top unique requested products
 *   4. Category breakdown
 *
 * Demo data is clearly labelled so judges never confuse it with production.
 */
export default function Demand() {
  const [days, setDays] = useState(30);
  const navigate = useNavigate();

  const demand = trpc.merchant.demand.useQuery({ days });
  const opportunities = trpc.merchant.opportunities.useQuery({ days, limit: 8 });
  const planFromOpp = trpc.merchant.planFromOpportunity.useMutation({
    onSuccess: () => {
      toast.success("Inventory plan mein add ho gaya. Confirm karne ke liye Stock kholiye.");
    },
    onError: (e) => toast.error(e.message),
  });

  const products = demand.data?.products ?? [];
  const categories = demand.data?.categories ?? [];
  const honestStats = demand.data?.honestStats;
  const maxReq = Math.max(1, ...products.map((p) => p.uniqueRequests));
  const maxCat = Math.max(1, ...categories.map((c) => c.requests));
  const isDemo = demand.data?.isDemoData ?? false;

  const oppList = opportunities.data?.opportunities ?? [];

  return (
    <div>
      <TopBar
        title="Mohalle ki Demand"
        sub="Log kya maang rahe hain — aur kahan nahi mil raha"
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

      {demand.isLoading && (
        <div className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card h-[80px] animate-pulse" />
          ))}
        </div>
      )}

      {demand.data && demand.data.total === 0 && (
        <EmptyState
          icon={<TrendingUp className="w-7 h-7" />}
          title="Abhi data jama ho raha hai"
          sub="Jaise hi mohalla requests bhejega, yahan demand dikhegi."
        />
      )}

      {/* Honest demand metrics (Priority 4) */}
      {honestStats && honestStats.uniqueCustomerRequests > 0 && (
        <section className="rounded-[28px] border-2 border-brand-ink/12 bg-card p-4 mb-5 lm-enter">
          <div className="flex items-center gap-2 text-[10.5px] font-extrabold uppercase tracking-[0.18em] text-brand-ink/55">
            <ShieldCheck className="w-4 h-4 text-brand-green" />
            Honest demand metrics
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <Stat
              value={honestStats.uniqueCustomerRequests}
              label="unique customers asked"
            />
            <Stat
              value={honestStats.merchantResponseAttempts}
              label="merchant responses collected"
            />
            <Stat
              value={honestStats.availableResponses}
              label="merchants said available"
              tone="green"
            />
            <Stat
              value={honestStats.unavailableResponses}
              label="merchants said unavailable"
              tone="red"
            />
          </div>
          <p className="text-[10.5px] font-bold text-muted-foreground mt-3">
            Ek customer request kaai merchants ko bheji jaati hai — isliye merchant responses
            unique customer requests se zyada hoti hain. Yahan dono alag-alag dikhaye gaye hain.
          </p>
        </section>
      )}

      {/* Stock opportunities (Priority 2) */}
      <section className="mb-7">
        <h2 className="font-display text-[19px] mb-3.5 flex items-center gap-2">
          <Lightbulb className="w-5 h-5 text-brand-yellow" />
          Stock Opportunities
        </h2>
        {opportunities.isLoading && (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card h-[140px] animate-pulse" />
            ))}
          </div>
        )}
        {oppList.length === 0 && !opportunities.isLoading && (
          <div className="rounded-3xl border-2 border-dashed border-brand-ink/20 bg-card p-5">
            <EmptyState
              icon={<Lightbulb className="w-7 h-7" />}
              title="Abhi koi mauka nahi dikha"
              sub="Jaise hi demand data jama hoga, yahan stock opportunities dikhega."
            />
          </div>
        )}
        <div className="space-y-3">
          {oppList.map((opp) => (
            <OpportunityCard
              key={opp.product}
              opp={opp}
              pending={planFromOpp.isPending}
              onPlan={() => {
                planFromOpp.mutate({
                  product: opp.product,
                  quantity: opp.recommendedQuantity,
                  unit: "piece",
                  price: undefined,
                });
              }}
            />
          ))}
        </div>
      </section>

      {/* Top products */}
      {products.length > 0 && (
        <section className="mb-7">
          <div className="flex items-end justify-between mb-3.5">
            <h2 className="font-display text-[19px]">Sabse zyada maangi gayi</h2>
            <Sticker rot={2}>{demand.data?.total ?? 0} unique</Sticker>
          </div>
          <div className="space-y-2.5">
            {products.map((p, i) => (
              <div
                key={p.product}
                className="lm-pop rounded-3xl border-2 border-brand-ink/10 bg-card p-4"
                style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
              >
                <div className="flex items-center gap-3.5">
                  <CategoryIcon categoryKey={categoryKey(p.category)} size={44} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-[14.5px] truncate">{p.product}</span>
                      {p.unavailable >= 3 && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-[#F0374915] text-[#F03749] px-2 py-0.5 text-[10px] font-extrabold shrink-0">
                          <Flame className="w-3 h-3" /> hot
                        </span>
                      )}
                    </div>
                    <div className="mt-2 h-2.5 rounded-full bg-brand-ink/10 overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${(p.uniqueRequests / maxReq) * 100}%`,
                          background: categoryMeta(categoryKey(p.category)).color,
                        }}
                      />
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-display text-[18px]">{p.uniqueRequests}</div>
                    <div className="text-[10px] font-extrabold text-muted-foreground uppercase">
                      {p.unavailable > 0 ? `${p.unavailable} nahi mile` : "sab mile"}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Categories */}
      {categories.length > 0 && (
        <section className="mb-7">
          <h2 className="font-display text-[19px] mb-3.5">Category-wise</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            {categories.map((c, i) => {
              const meta = categoryMeta(c.categoryKey);
              return (
                <div
                  key={c.categoryKey}
                  className="lm-pop rounded-3xl border-2 border-brand-ink/10 bg-card p-4"
                  style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
                >
                  <CategoryIcon categoryKey={c.categoryKey} size={38} />
                  <div className="font-display text-[20px] mt-2.5">{c.requests}</div>
                  <div className="text-[11px] font-extrabold text-muted-foreground uppercase tracking-wide mt-0.5">
                    {meta.label}
                  </div>
                  <div className="mt-2 h-1.5 rounded-full bg-brand-ink/10 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${(c.requests / maxCat) * 100}%`, background: meta.color }} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Heatmap deep-link */}
      <button
        type="button"
        onClick={() => navigate("/merchant/impact")}
        className="w-full rounded-full border-2 border-brand-ink bg-card font-display text-[14px] py-3.5 shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all flex items-center justify-center gap-2"
      >
        Demand map dekhiye <ArrowRight className="w-4 h-4" />
      </button>
    </div>
  );
}

function categoryKey(backendCategory?: string | null): string {
  // The demand backend emits "hardware", "plumbing", "kirana", etc. The web
  // FE_CATEGORY map collapses plumbing→hardware. Mirror that mapping here.
  if (!backendCategory) return "other";
  const map: Record<string, string> = {
    kirana: "kirana",
    hardware: "hardware",
    plumbing: "hardware",
    electrical: "electrical",
    medical: "pharmacy",
    clothing: "tailor",
    stationery: "stationery",
    mobile_electronics: "mobile",
    repair: "mobile",
    bakery_food: "dairy",
    cosmetics: "other",
    general_store: "kirana",
    other: "other",
  };
  return map[backendCategory] ?? "other";
}

function Stat({
  value, label, tone = "default",
}: {
  value: number;
  label: string;
  tone?: "default" | "green" | "red";
}) {
  return (
    <div className="rounded-2xl bg-background p-3">
      <div
        className={clsx(
          "font-display text-[22px] leading-none",
          tone === "green" && "text-brand-green",
          tone === "red" && "text-[#F03749]",
          tone === "default" && "text-brand-ink",
        )}
      >
        {value}
      </div>
      <div className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground mt-1.5">
        {label}
      </div>
    </div>
  );
}

function OpportunityCard({
  opp, pending, onPlan,
}: {
  opp: import("@/lib/api").StockOpportunity;
  pending: boolean;
  onPlan: () => void;
}) {
  const score = opp.opportunityScore;
  const scoreColor = score >= 70 ? "text-brand-green" : score >= 50 ? "text-[#8A5A00]" : "text-muted-foreground";
  return (
    <div className="lm-pop rounded-3xl border-2 border-brand-ink/12 bg-card p-4">
      <div className="flex items-start gap-3">
        <CategoryIcon categoryKey={categoryKey(opp.category)} size={46} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-extrabold text-[14.5px] truncate">{opp.product}</span>
            {opp.trend === "rising" && (
              <span className="inline-flex items-center gap-1 rounded-full bg-brand-green/15 text-brand-green px-2 py-0.5 text-[10px] font-extrabold">
                <TrendingUp className="w-3 h-3" /> rising
              </span>
            )}
          </div>
          <div className="mt-1 grid grid-cols-3 gap-2 text-center">
            <Mini value={opp.uniqueRequests} label="requests" />
            <Mini value={`${Math.round(opp.unavailableRate * 100)}%`} label="unmet" />
            <Mini value={opp.recommendedQuantity} label="suggested qty" />
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={clsx("font-display text-[22px] leading-none", scoreColor)}>
            {score}
          </div>
          <div className="text-[9px] font-extrabold uppercase tracking-wide text-muted-foreground mt-1">
            /100
          </div>
        </div>
      </div>

      <p className="text-[11.5px] font-bold text-brand-ink/70 mt-3 leading-relaxed">
        {opp.reason}
      </p>

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={onPlan}
          disabled={pending}
          className="rounded-full border-2 border-brand-green bg-brand-green text-brand-cream text-[11.5px] font-extrabold py-2 px-3 inline-flex items-center gap-1.5 disabled:opacity-50"
        >
          <Package className="w-3.5 h-3.5" /> Add to inventory plan
        </button>
        <span className="text-[10px] font-bold text-muted-foreground">
          Auto-stock nahi hota — pehle confirm karna padega
        </span>
      </div>
    </div>
  );
}

function Mini({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="rounded-xl bg-background/60 p-1.5">
      <div className="font-display text-[14px] leading-none">{value}</div>
      <div className="text-[9px] font-extrabold uppercase tracking-wide text-muted-foreground mt-1">
        {label}
      </div>
    </div>
  );
}
