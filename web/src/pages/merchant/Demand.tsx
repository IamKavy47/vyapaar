import { TrendingUp, Flame, Lightbulb } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { CategoryIcon, EmptyState, Sticker } from "@/components/brand";
import { categoryMeta } from "@/lib/localmart";

export default function Demand() {
  const demand = trpc.merchant.demand.useQuery();

  const products = demand.data?.products ?? [];
  const categories = demand.data?.categories ?? [];
  const maxReq = Math.max(1, ...products.map((p) => p.requests));
  const maxCat = Math.max(1, ...categories.map((c) => c.requests));
  const hot = products.filter((p) => p.unavailable >= 3).slice(0, 3);

  return (
    <div>
      <TopBar title="Mohalle ki Demand" sub="Log kya maang rahe hain — aur kahan nahi mil raha" />

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

      {/* opportunity callout */}
      {hot.length > 0 && (
        <section className="rounded-[28px] border-2 border-brand-ink bg-brand-ink p-5 mb-6 relative overflow-hidden">
          <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full bg-brand-yellow/15" />
          <div className="flex items-center gap-2 text-brand-yellow">
            <Lightbulb className="w-5 h-5" />
            <span className="font-display text-[15px]">Mauke ki baat</span>
          </div>
          <p className="text-[13.5px] font-semibold text-brand-cream/80 mt-2.5 leading-relaxed">
            {hot.map((h) => h.product).join(", ")} — yeh cheezein baar-baar maangi ja rahi hain aur
            zyadatar dukaanon pe <b className="text-brand-yellow">nahi milti</b>. Stock kar lo, customers taiyaar hain.
          </p>
        </section>
      )}

      {/* top products */}
      {products.length > 0 && (
        <section className="mb-7">
          <div className="flex items-end justify-between mb-3.5">
            <h2 className="font-display text-[19px]">Sabse zyada maangi gayi</h2>
            <Sticker rot={2}>{demand.data?.total ?? 0} requests</Sticker>
          </div>
          <div className="space-y-2.5">
            {products.map((p, i) => (
              <div
                key={p.product}
                className="lm-pop rounded-3xl border-2 border-brand-ink/10 bg-card p-4"
                style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
              >
                <div className="flex items-center gap-3.5">
                  <CategoryIcon categoryKey={p.categoryKey} size={44} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-[14.5px] truncate">{p.product}</span>
                      {p.unavailable >= 3 && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-[#F0374915] text-[#F03749] px-2 py-0.5 text-[10px] font-extrabold shrink-0">
                          <Flame className="w-3 h-3" /> hot
                        </span>
                      )}
                    </div>
                    <div className="mt-2 h-2.5 rounded-full bg-brand-ink/8 bg-brand-ink/10 overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${(p.requests / maxReq) * 100}%`,
                          background: categoryMeta(p.categoryKey).color,
                        }}
                      />
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-display text-[18px]">{p.requests}</div>
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

      {/* categories */}
      {categories.length > 0 && (
        <section>
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
    </div>
  );
}
