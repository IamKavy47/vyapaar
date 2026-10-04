import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { Search, Mic, Camera, MapPin, ChevronRight, Flame, BadgeCheck } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { useLocation } from "@/lib/location";
import { useSpeech } from "@/lib/useSpeech";
import { CategoryIcon, SectionHead } from "@/components/brand";
import { formatDistance } from "@/lib/format";
import { CATEGORIES } from "@/lib/localmart";

const SUGGESTIONS = [
  "Teflon tape chahiye",
  "LED bulb 9W",
  "Aashirvaad atta 5kg",
  "Paracetamol hai kya?",
  "Blouse silwana hai",
  "Mobile charger",
];

export default function Home() {
  const navigate = useNavigate();
  const location = useLocation();
  const [q, setQ] = useState("");
  const photoRef = useRef<HTMLInputElement>(null);

  const shops = trpc.catalog.shops.useQuery({ lat: location.lat ?? undefined, lng: location.lng ?? undefined });
  const trending = trpc.catalog.trending.useQuery();

  const speech = useSpeech((text) => {
    navigate(`/search?q=${encodeURIComponent(text)}&type=voice`);
  });

  const go = (type: "text" | "voice" | "image" = "text") => {
    const query = q.trim();
    if (query.length > 1) navigate(`/search?q=${encodeURIComponent(query)}&type=${type}`);
  };

  const onPhoto = (file?: File | null) => {
    if (!file) return;
    navigate(`/search?q=${encodeURIComponent("photo se pehchana gaya item")}&type=image`);
  };

  const topShops = useMemo(() => (shops.data ?? []).slice(0, 6), [shops.data]);
  const ticker = useMemo(
    () => (trending.data ?? []).filter((d) => d.unavailable > 0).slice(0, 8),
    [trending.data],
  );

  return (
    <div>
      {/* Yellow hero */}
      <div className="-mx-4 sm:-mx-6 bg-brand-yellow rounded-b-[36px] border-b-2 border-brand-ink/10 px-4 sm:px-6 pt-5 pb-7 relative overflow-hidden">
        <div className="flex items-center justify-between">
          <button
            onClick={location.locate}
            className="flex items-center gap-1.5 rounded-full border-2 border-brand-ink bg-brand-cream px-3.5 py-2 shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all"
          >
            <MapPin className="w-4 h-4 text-brand-green" strokeWidth={2.6} />
            <span className="text-[12.5px] font-extrabold max-w-[160px] truncate">
              {location.locating ? "Dhundh rahe…" : location.label}
            </span>
          </button>
          <span className="font-display text-[13px] text-brand-ink/70">नमस्ते 🙏</span>
        </div>

        <h1 className="font-display text-[30px] sm:text-[36px] leading-[1.06] mt-6 text-brand-ink">
          Aaj kya <span className="text-brand-green">chahiye</span>?
        </h1>
        <p className="mt-1.5 text-[14.5px] font-bold text-brand-ink/70">
          Bolo ya likho — paas ki dukaanein jawab dengi.
        </p>

        {/* Search */}
        <div className="mt-5 flex items-center rounded-full border-2 border-brand-ink bg-brand-cream shadow-sticker overflow-hidden">
          <Search className="w-5 h-5 ml-4 text-brand-ink/50 shrink-0" strokeWidth={2.6} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && go()}
            placeholder="pipe leak rokne wala safed tape…"
            className="flex-1 min-w-0 bg-transparent px-3 py-4 text-[15.5px] font-bold outline-none placeholder:text-brand-ink/35 placeholder:font-semibold"
          />
          <button
            onClick={() => photoRef.current?.click()}
            aria-label="Photo se khojo"
            className="h-11 w-11 mr-1 rounded-full grid place-items-center text-brand-ink/60 hover:bg-brand-yellow/70 transition-colors"
          >
            <Camera className="w-5 h-5" strokeWidth={2.4} />
          </button>
          <input
            ref={photoRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => onPhoto(e.target.files?.[0])}
          />
          <button
            onClick={() => (speech.listening ? speech.stop() : speech.start())}
            aria-label="Bol kar khojo"
            className="h-11 w-12 mr-1.5 rounded-full grid place-items-center bg-brand-ink text-brand-yellow shrink-0 active:scale-95 transition-transform"
          >
            {speech.listening ? (
              <span className="flex items-end gap-[3px] h-5">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="lm-eq w-[3px] h-5 rounded-full bg-brand-yellow" style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </span>
            ) : (
              <Mic className="w-5 h-5" strokeWidth={2.4} />
            )}
          </button>
        </div>
        {speech.listening && (
          <p className="text-[11.5px] font-extrabold uppercase tracking-[0.14em] mt-2 text-brand-ink">
            Sun raha hoon… boliye
          </p>
        )}

        {/* Suggestion chips */}
        <div className="mt-4 flex gap-2 overflow-x-auto no-scrollbar -mx-4 sm:-mx-6 px-4 sm:px-6">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => navigate(`/search?q=${encodeURIComponent(s)}&type=text`)}
              className="shrink-0 rounded-full border-2 border-brand-ink/25 bg-brand-cream/70 px-3.5 py-2 text-[12.5px] font-bold whitespace-nowrap active:scale-95 transition-transform"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Demand ticker */}
      {ticker.length > 0 && (
        <div className="mt-4 -mx-4 sm:-mx-6 overflow-hidden border-y-2 border-brand-ink/10 bg-brand-ink py-2.5">
          <div className="flex gap-6 whitespace-nowrap lm-marquee w-max">
            {[...ticker, ...ticker].map((d, i) => (
              <button
                key={`${d.product}-${i}`}
                onClick={() => navigate(`/search?q=${encodeURIComponent(d.product)}&type=text`)}
                className="flex items-center gap-2 text-[12px] font-extrabold text-brand-cream/85"
              >
                <Flame className="w-3.5 h-3.5 text-brand-yellow" />
                {d.product}
                <span className="text-brand-cream/40">{d.requests} requests</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Category rail */}
      <section className="mt-7">
        <SectionHead
          title="Categories"
          action={
            <button onClick={() => navigate("/browse")} className="text-[12.5px] font-extrabold text-brand-green flex items-center gap-0.5">
              Sab dekho <ChevronRight className="w-4 h-4" strokeWidth={2.8} />
            </button>
          }
        />
        <div className="grid grid-cols-5 gap-2.5 sm:gap-3">
          {CATEGORIES.slice(0, 10).map((c, i) => (
            <button
              key={c.key}
              onClick={() => navigate(`/browse?cat=${c.key}`)}
              className="lm-pop flex flex-col items-center gap-1.5 active:scale-95 transition-transform"
              style={{ animationDelay: `${i * 0.03}s` }}
            >
              <CategoryIcon categoryKey={c.key} size={52} className="border-2 border-brand-ink/10" />
              <span className="text-[10.5px] font-extrabold text-brand-ink/75 text-center leading-tight line-clamp-1">
                {c.hindi}
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* Trending demand cards */}
      {(trending.data ?? []).length > 0 && (
        <section className="mt-8">
          <SectionHead title="Mohalle ki Demand" sub="Jo log abhi dhoondh rahe hain" />
          <div className="flex gap-3 overflow-x-auto no-scrollbar -mx-4 sm:-mx-6 px-4 sm:px-6 pb-1">
            {(trending.data ?? []).slice(0, 8).map((d, i) => (
              <button
                key={d.product}
                onClick={() => navigate(`/search?q=${encodeURIComponent(d.product)}&type=text`)}
                className="lm-pop shrink-0 w-[148px] text-left rounded-3xl border-2 p-4 transition-all active:scale-[0.97]"
                style={{
                  animationDelay: `${i * 0.05}s`,
                  background: i === 0 ? "#FEE600" : "#FFFCF5",
                  borderColor: i === 0 ? "#141313" : "rgba(20,19,19,0.12)",
                  boxShadow: i === 0 ? "0 3px 0 0 #141313" : undefined,
                }}
              >
                <div className="text-[10px] font-extrabold uppercase tracking-[0.12em] text-brand-ink/50">
                  #{i + 1} · {d.requests} requests
                </div>
                <div className="font-display text-[14.5px] leading-tight mt-2 text-brand-ink line-clamp-2">
                  {d.product}
                </div>
                {d.unavailable > 0 && (
                  <div className="text-[11px] font-extrabold mt-2 text-[#F03749]">
                    {d.unavailable} baar nahi mila
                  </div>
                )}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Nearby shops */}
      <section className="mt-8">
        <SectionHead
          title="Paas ki Dukaanein"
          sub="Distance ke hisaab se"
          action={
            <button onClick={() => navigate("/browse")} className="text-[12.5px] font-extrabold text-brand-green flex items-center gap-0.5">
              Sab dekho <ChevronRight className="w-4 h-4" strokeWidth={2.8} />
            </button>
          }
        />
        <div className="grid gap-3 sm:grid-cols-2">
          {shops.isLoading &&
            [0, 1, 2, 3].map((i) => (
              <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card p-4 h-[92px] animate-pulse" />
            ))}
          {topShops.map((s, i) => (
            <button
              key={s.id}
              onClick={() => navigate(`/shop/${s.id}`)}
              className="lm-pop text-left rounded-3xl border-2 border-brand-ink/10 bg-card p-4 transition-all hover:border-brand-ink/40 active:scale-[0.99]"
              style={{ animationDelay: `${i * 0.05}s` }}
            >
              <div className="flex items-start gap-3.5">
                <CategoryIcon categoryKey={s.categoryKey} size={48} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-extrabold text-[15.5px] truncate">{s.name}</span>
                    {s.isVerified && <BadgeCheck className="w-4 h-4 text-brand-green shrink-0" />}
                  </div>
                  <div className="text-[12px] font-bold text-muted-foreground mt-0.5">
                    {s.categoryLabel} · {formatDistance(s.distanceMeters)}
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {s.capabilities.slice(0, 3).map((c) => (
                      <span key={c} className="rounded-full bg-background px-2 py-0.5 text-[10.5px] font-bold text-brand-ink/60">
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <span
                    className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10.5px] font-extrabold"
                    style={
                      s.inventoryCount > 0
                        ? { background: "#0091461a", color: "#009146" }
                        : { background: "#FEE60055", color: "#8A5A00" }
                    }
                  >
                    <span className={s.inventoryCount > 0 ? "w-1.5 h-1.5 rounded-full bg-brand-green lm-pulse-dot" : "w-1.5 h-1.5 rounded-full bg-[#E8930C]"} />
                    {s.inventoryCount > 0 ? `${s.inventoryCount} items` : "on request"}
                  </span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
