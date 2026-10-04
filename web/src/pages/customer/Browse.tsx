import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { BadgeCheck, Search, Store } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { useLocation } from "@/lib/location";
import { TopBar } from "@/components/shell";
import { CategoryIcon, EmptyState } from "@/components/brand";
import { formatDistance, clsx } from "@/lib/format";
import { CATEGORIES } from "@/lib/localmart";

export default function Browse() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const cat = params.get("cat") ?? "all";
  const [q, setQ] = useState("");

  const shops = trpc.catalog.shops.useQuery({
    lat: location.lat,
    lng: location.lng,
    category: cat,
    query: q || undefined,
  });

  return (
    <div>
      <TopBar title="Saari Dukaanein" sub="Mohalle ka poora bazaar" />

      {/* search */}
      <div className="flex items-center rounded-full border-2 border-brand-ink/15 bg-card px-4 mb-4 focus-within:border-brand-green transition-colors">
        <Search className="w-4.5 h-4.5 w-5 h-5 text-brand-ink/40 shrink-0" strokeWidth={2.5} />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Dukaan ya cheez khojo…"
          className="flex-1 min-w-0 bg-transparent px-3 py-3.5 text-[14.5px] font-bold outline-none placeholder:text-brand-ink/35"
        />
      </div>

      {/* category chips */}
      <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-4 sm:-mx-6 px-4 sm:px-6 pb-1 mb-5">
        {[{ key: "all", label: "Sab", hindi: "सब" }, ...CATEGORIES].map((c) => (
          <button
            key={c.key}
            onClick={() => setParams(c.key === "all" ? {} : { cat: c.key })}
            className={clsx(
              "shrink-0 rounded-full border-2 px-4 py-2 text-[12.5px] font-extrabold transition-all active:scale-95",
              cat === c.key
                ? "bg-brand-ink text-brand-yellow border-brand-ink shadow-sticker-sm"
                : "bg-card border-brand-ink/12 text-brand-ink/70",
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {shops.isLoading && (
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card p-4 h-[96px] animate-pulse" />
          ))}
        </div>
      )}

      {shops.data?.length === 0 && (
        <EmptyState
          icon={<Store className="w-7 h-7" />}
          title="Yahan kuch nahi mila"
          sub="Filter badal ke dekho — ya nayi category try karo."
        />
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {shops.data?.map((s, i) => (
          <button
            key={s.id}
            onClick={() => navigate(`/shop/${s.id}`)}
            className="lm-pop text-left rounded-3xl border-2 border-brand-ink/10 bg-card p-4 hover:border-brand-ink/40 transition-all active:scale-[0.99]"
            style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
          >
            <div className="flex items-start gap-3.5">
              <CategoryIcon categoryKey={s.categoryKey} size={48} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-extrabold text-[15.5px] truncate">{s.name}</span>
                  {s.isVerified && <BadgeCheck className="w-4 h-4 text-brand-green shrink-0" />}
                </div>
                <div className="text-[12px] font-bold text-muted-foreground mt-0.5 truncate">
                  {s.categoryLabel} · {formatDistance(s.distanceMeters)}
                </div>
                {s.description && (
                  <p className="text-[12px] font-semibold text-brand-ink/60 mt-1.5 line-clamp-2">{s.description}</p>
                )}
              </div>
            </div>
            <div className="flex items-center justify-between mt-3 pt-3 border-t-2 border-dashed border-brand-ink/10">
              <span
                className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10.5px] font-extrabold"
                style={
                  s.inventoryCount > 0
                    ? { background: "#0091461a", color: "#009146" }
                    : { background: "#FEE60055", color: "#8A5A00" }
                }
              >
                {s.inventoryCount > 0 ? `${s.inventoryCount} items in stock` : "on request"}
              </span>
              <span className="text-[12px] font-extrabold text-brand-green">Dekho →</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
