import { lazy, Suspense, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";
import {
  BadgeCheck, Search, Store, Map as MapIcon, LayoutGrid, Sparkles,
  Navigation, ShoppingCart, CircleCheck,
} from "lucide-react";
import { api as trpc, type ProductCard } from "@/lib/api";
import { useLocation } from "@/lib/location";
import { TopBar } from "@/components/shell";
import { CategoryIcon, EmptyState } from "@/components/brand";
import { formatDistance, formatINR, clsx } from "@/lib/format";
import { CATEGORIES } from "@/lib/localmart";

const BrowseMapLazy = lazy(() =>
  import("@/components/BrowseMap").then((m) => ({ default: m.BrowseMap })),
);

type View = "grid" | "map";

export default function Browse() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const cat = params.get("cat") ?? "all";
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"nearest" | "cheapest" | "newest">("nearest");
  const [view, setView] = useState<View>("grid");
  const [page, setPage] = useState(1);

  const lat = location.lat ?? undefined;
  const lng = location.lng ?? undefined;

  const products = trpc.catalog.products.useQuery({
    lat, lng, category: cat, query: q || undefined, sort, page, limit: 30,
  });
  const recommendations = trpc.catalog.recommendations.useQuery({ lat, lng, limit: 6 });

  const productRows = products.data?.products ?? [];
  const recommended = recommendations.data?.recommendations ?? [];

  const reserve = trpc.request.reserve.useMutation({
    onSuccess: () => {
      toast.success("Reserve request bhej diya! Shopkeeper ko YES/NO milega.");
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <div>
      <TopBar
        title="Browse"
        sub="Paas ki dukaano ke products — sabhi verified shops"
        right={
          <div className="flex items-center gap-1 rounded-full border-2 border-brand-ink/15 bg-card p-1">
            <button
              onClick={() => setView("grid")}
              className={clsx(
                "rounded-full p-1.5",
                view === "grid" ? "bg-brand-ink text-brand-yellow" : "text-brand-ink/55",
              )}
              aria-label="Grid view"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("map")}
              className={clsx(
                "rounded-full p-1.5",
                view === "map" ? "bg-brand-ink text-brand-yellow" : "text-brand-ink/55",
              )}
              aria-label="Map view"
            >
              <MapIcon className="w-4 h-4" />
            </button>
          </div>
        }
      />

      {/* search */}
      <div className="flex items-center rounded-full border-2 border-brand-ink/15 bg-card px-4 mb-3 focus-within:border-brand-green transition-colors">
        <Search className="w-5 h-5 text-brand-ink/40 shrink-0" strokeWidth={2.5} />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
          placeholder="Product search — jaise: Teflon Tape, Fevicol, A4 Paper…"
          className="flex-1 min-w-0 bg-transparent px-3 py-3.5 text-[14.5px] font-bold outline-none placeholder:text-brand-ink/35"
        />
      </div>

      {/* sort + category chips */}
      <div className="flex items-center gap-2 overflow-x-auto no-scrollbar -mx-4 sm:-mx-6 px-4 sm:px-6 pb-1 mb-3">
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
          className="shrink-0 rounded-full border-2 border-brand-ink/15 bg-card px-3 py-1.5 text-[11.5px] font-extrabold outline-none"
        >
          <option value="nearest">Nearest</option>
          <option value="cheapest">Lowest price</option>
          <option value="newest">Newest</option>
        </select>
        {[{ key: "all", label: "Sab", hindi: "सब" }, ...CATEGORIES].map((c) => (
          <button
            key={c.key}
            onClick={() => { setParams(c.key === "all" ? {} : { cat: c.key }); setPage(1); }}
            className={clsx(
              "shrink-0 rounded-full border-2 px-3 py-1.5 text-[11.5px] font-extrabold transition-all active:scale-95",
              cat === c.key
                ? "bg-brand-ink text-brand-yellow border-brand-ink shadow-sticker-sm"
                : "bg-card border-brand-ink/12 text-brand-ink/70",
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* recommendations (only on grid view, top of page) */}
      {view === "grid" && recommended.length > 0 && !q && cat === "all" && (
        <section className="mb-5 rounded-3xl border-2 border-brand-ink/12 bg-card p-3">
          <div className="flex items-center gap-2 mb-2 px-1">
            <Sparkles className="w-4 h-4 text-brand-green" />
            <h2 className="font-extrabold text-[12.5px] uppercase tracking-wide text-brand-ink/65">
              Recommended for you
            </h2>
          </div>
          <div className="flex gap-2 overflow-x-auto no-scrollbar">
            {recommended.map((p) => (
              <button
                key={p.id}
                onClick={() => navigate(`/shop/${p.shopId}`)}
                className="lm-pop shrink-0 w-32 text-left rounded-2xl border-2 border-brand-ink/10 bg-background p-2 hover:border-brand-ink/40 transition-all"
              >
                <div className="w-full h-20 rounded-xl overflow-hidden bg-brand-ink/8 mb-1.5">
                  {p.imageUrl ? (
                    <img src={p.imageUrl} alt={p.name} className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full grid place-items-center">
                      <CategoryIcon categoryKey={p.shop.categoryKey} size={28} />
                    </div>
                  )}
                </div>
                <div className="font-extrabold text-[11px] truncate">{p.name}</div>
                <div className="text-[10px] font-bold text-muted-foreground truncate">
                  {formatDistance(p.shop.distanceMeters)} · {p.shop.name}
                </div>
                {p.price != null && (
                  <div className="text-[11.5px] font-display text-brand-ink mt-0.5">
                    {formatINR(p.price)}
                  </div>
                )}
              </button>
            ))}
          </div>
          {recommendations.data?.reason && (
            <p className="text-[10px] font-bold text-muted-foreground mt-1 px-1">
              {recommendations.data.reason}
            </p>
          )}
        </section>
      )}

      {products.isLoading && (
        <div className="grid gap-3 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card p-3 h-[140px] animate-pulse" />
          ))}
        </div>
      )}

      {/* main view */}
      {view === "map" && productRows.length > 0 && (
        <div className="rounded-3xl border-2 border-brand-ink/12 overflow-hidden">
          <Suspense fallback={<div className="h-72 bg-card animate-pulse" />}>
            <BrowseMapLazy
              products={productRows}
              centerLat={lat}
              centerLng={lng}
              onProductClick={(p) => navigate(`/shop/${p.shopId}`)}
            />
          </Suspense>
        </div>
      )}

      {view === "grid" && productRows.length === 0 && !products.isLoading && (
        <EmptyState
          icon={<Store className="w-7 h-7" />}
          title="Koi listed product nahi mila"
          sub="Filter badal ke dekho — ya shopkeepers ko bolo apna inventory add karein."
        />
      )}

      {view === "grid" && productRows.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {productRows.map((p, i) => (
            <ProductCardTile
              key={p.id}
              product={p}
              pending={reserve.isPending}
              onOpen={() => navigate(`/shop/${p.shopId}`)}
              onReserve={async () => {
                if (location.lat == null || location.lng == null) {
                  toast.error("Pehle apni location allow karo");
                  location.locate();
                  return;
                }
                await reserve.mutateAsync({
                  itemId: p.id, lat: location.lat, lng: location.lng,
                });
              }}
              index={i}
            />
          ))}
        </div>
      )}

      {/* load more */}
      {view === "grid" && products.data?.hasMore && (
        <button
          onClick={() => setPage((p) => p + 1)}
          className="mt-5 w-full rounded-full border-2 border-brand-ink bg-card font-extrabold text-[14px] py-3 shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all"
        >
          Aur load karo →
        </button>
      )}
    </div>
  );
}

function ProductCardTile({
  product, pending, onOpen, onReserve, index,
}: {
  product: ProductCard;
  pending: boolean;
  onOpen: () => void;
  onReserve: () => void;
  index: number;
}) {
  const shop = product.shop;
  const aiImage = product.imageSource === "ai_fetched";
  return (
    <div
      className="lm-pop rounded-3xl border-2 border-brand-ink/10 bg-card overflow-hidden hover:border-brand-ink/40 transition-all"
      style={{ animationDelay: `${Math.min(index, 8) * 0.04}s` }}
    >
      {/* image */}
      <button
        onClick={onOpen}
        className="block w-full aspect-[4/3] bg-brand-ink/8 relative overflow-hidden"
      >
        {product.imageUrl ? (
          <img
            src={product.imageUrl}
            alt={product.name}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full grid place-items-center">
            <CategoryIcon categoryKey={shop.categoryKey} size={48} />
          </div>
        )}
        {aiImage && (
          <span className="absolute top-1.5 right-1.5 rounded-full bg-[#7C3AED] text-white text-[8.5px] font-extrabold uppercase tracking-wide px-1.5 py-0.5">
            AI image
          </span>
        )}
        {!product.inStock && (
          <span className="absolute top-1.5 left-1.5 rounded-full bg-[#F03749]/80 text-white text-[8.5px] font-extrabold uppercase tracking-wide px-1.5 py-0.5">
            Out of stock
          </span>
        )}
      </button>

      {/* body */}
      <div className="p-3">
        <button onClick={onOpen} className="block w-full text-left">
          <div className="font-extrabold text-[14px] truncate">{product.name}</div>
          <div className="flex items-center gap-1 text-[10.5px] font-bold text-muted-foreground mt-0.5">
            <Store className="w-3 h-3" />
            <span className="truncate">{shop.name}</span>
            {shop.isVerified && <BadgeCheck className="w-3 h-3 text-brand-green shrink-0" />}
          </div>
          <div className="text-[10.5px] font-bold text-muted-foreground">
            {formatDistance(shop.distanceMeters)} door
          </div>
        </button>

        <div className="flex items-center justify-between mt-2">
          {product.price != null ? (
            <div className="font-display text-[18px] text-brand-ink">{formatINR(product.price)}</div>
          ) : (
            <div className="text-[10.5px] font-extrabold uppercase tracking-wide text-muted-foreground">
              Price not provided
            </div>
          )}
          <button
            onClick={onReserve}
            disabled={pending}
            className="inline-flex items-center gap-1 rounded-full border-2 border-brand-green bg-brand-green text-brand-cream text-[11px] font-extrabold px-2.5 py-1.5 disabled:opacity-50"
          >
            {pending ? <CircleCheck className="w-3.5 h-3.5 animate-spin" /> : <ShoppingCart className="w-3.5 h-3.5" />}
            Reserve
          </button>
        </div>

        <a
          href={`https://www.google.com/maps/dir/?api=1&destination=${shop.lat},${shop.lng}`}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-[10.5px] font-extrabold text-brand-green"
        >
          <Navigation className="w-3 h-3" /> Directions
        </a>
      </div>
    </div>
  );
}
