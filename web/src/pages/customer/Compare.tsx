import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Search, ArrowLeftRight, BadgeCheck } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { useLocation } from "@/lib/location";
import { TopBar } from "@/components/shell";
import { CategoryIcon, EmptyState, Sticker } from "@/components/brand";
import { formatDistance, formatINR, clsx } from "@/lib/format";

const QUICK = ["atta", "doodh", "led bulb", "paracetamol", "notebook", "charger", "pyaz"];

export default function Compare() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [input, setInput] = useState(q);

  const results = trpc.catalog.priceSearch.useQuery(
    { query: q, lat: location.lat, lng: location.lng },
    { enabled: q.length > 1 },
  );

  const search = (term: string) => {
    setInput(term);
    if (term.trim().length > 1) setParams({ q: term.trim() });
  };

  const cheapest = results.data?.filter((r) => r.item.inStock)?.[0];

  return (
    <div>
      <TopBar title="Daam Compare" sub="Kaun sasti, kaun paas" />

      <div className="flex items-center rounded-full border-2 border-brand-ink/15 bg-card px-4 focus-within:border-brand-green transition-colors">
        <Search className="w-5 h-5 text-brand-ink/40 shrink-0" strokeWidth={2.5} />
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search(input)}
          placeholder="jaise: atta, doodh, led bulb…"
          className="flex-1 min-w-0 bg-transparent px-3 py-3.5 text-[14.5px] font-bold outline-none placeholder:text-brand-ink/35"
        />
        <button
          onClick={() => search(input)}
          className="rounded-full bg-brand-ink text-brand-yellow text-[12px] font-extrabold px-4 py-2"
        >
          Go
        </button>
      </div>

      <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-4 sm:-mx-6 px-4 sm:px-6 py-3">
        {QUICK.map((term) => (
          <button
            key={term}
            onClick={() => search(term)}
            className={clsx(
              "shrink-0 rounded-full border-2 px-3.5 py-1.5 text-[12px] font-extrabold transition-all active:scale-95",
              q === term ? "bg-brand-ink text-brand-yellow border-brand-ink" : "bg-card border-brand-ink/12 text-brand-ink/70",
            )}
          >
            {term}
          </button>
        ))}
      </div>

      {q.length <= 1 && (
        <EmptyState
          icon={<ArrowLeftRight className="w-7 h-7" />}
          title="Kya compare karein?"
          sub="Cheez ka naam likho — sabhi dukaanon ke daam side-by-side."
        />
      )}

      {q.length > 1 && results.isLoading && (
        <div className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card h-[76px] animate-pulse" />
          ))}
        </div>
      )}

      {q.length > 1 && results.data?.length === 0 && (
        <EmptyState
          icon={<Search className="w-7 h-7" />}
          title={`"${q}" kisi listed stock mein nahi`}
          sub="Request bhej do — dukaandaar khud daam batayenge."
          action={
            <button
              onClick={() => navigate(`/search?q=${encodeURIComponent(q)}&type=text`)}
              className="rounded-full border-2 border-brand-ink bg-brand-yellow px-6 py-3 font-display text-[14px] shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all"
            >
              Request bhejo →
            </button>
          }
        />
      )}

      {results.data && results.data.length > 0 && (
        <div className="space-y-2.5">
          {results.data.map((r, i) => {
            const isBest = cheapest && r.item.id === cheapest.item.id;
            return (
              <button
                key={r.item.id}
                onClick={() => navigate(`/shop/${r.shop.id}`)}
                className={clsx(
                  "lm-pop w-full text-left rounded-3xl border-2 p-4 transition-all active:scale-[0.99] relative",
                  isBest ? "border-brand-green bg-[#0091460d] shadow-sticker" : "border-brand-ink/10 bg-card",
                )}
                style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
              >
                {isBest && (
                  <span className="absolute -top-3 left-5">
                    <Sticker color="#8ED462" rot={-3}>Sabse sasta</Sticker>
                  </span>
                )}
                <div className="flex items-center gap-3.5">
                  <CategoryIcon categoryKey={r.shop.categoryKey} size={44} />
                  <div className="flex-1 min-w-0">
                    <div className="font-extrabold text-[14.5px] leading-tight truncate">{r.item.name}</div>
                    <div className="flex items-center gap-1.5 text-[11.5px] font-bold text-muted-foreground mt-1">
                      <span className="truncate">{r.shop.name}</span>
                      {r.shop.isVerified && <BadgeCheck className="w-3.5 h-3.5 text-brand-green shrink-0" />}
                      <span>· {formatDistance(r.distanceMeters)}</span>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className={clsx("font-display text-[20px] leading-none", isBest ? "text-brand-green" : "text-brand-ink")}>
                      {formatINR(r.item.price)}
                    </div>
                    <div className="text-[10.5px] font-bold text-muted-foreground mt-1">
                      per {r.item.unit}
                      {!r.item.inStock && <span className="text-[#F03749]"> · out</span>}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
