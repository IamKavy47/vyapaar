import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { BadgeCheck, MapPin, Phone, Navigation, PackageOpen, CircleCheck } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { useLocation } from "@/lib/location";
import { TopBar } from "@/components/shell";
import { CategoryIcon, EmptyState, Sticker } from "@/components/brand";
import { formatDistance, formatINR } from "@/lib/format";

export default function ShopDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [reservedItem, setReservedItem] = useState<string | null>(null);
  const reserve = trpc.request.reserve.useMutation({
    onSuccess: (_result, variables) => {
      const item = shop.data?.inventory.find((candidate) => candidate.id === variables.itemId);
      setReservedItem(item?.name ?? "Item");
      toast.success("Dukaan ko buy request bhej di. Confirmation ka wait karo.");
    },
    onError: (error) => toast.error(error.message),
  });

  const shop = trpc.catalog.shop.useQuery(
    { id: id ?? "", lat: location.lat ?? undefined, lng: location.lng ?? undefined },
    { enabled: !!id },
  );

  if (shop.isLoading) {
    return (
      <div>
        <TopBar title="Dukaan" back />
        <div className="rounded-[28px] border-2 border-brand-ink/10 bg-card h-40 animate-pulse" />
      </div>
    );
  }
  if (!shop.data) {
    return (
      <div>
        <TopBar title="Dukaan" back />
        <EmptyState icon={<MapPin className="w-7 h-7" />} title="Dukaan nahi mili" />
      </div>
    );
  }

  const s = shop.data;

  return (
    <div>
      <TopBar title={s.categoryLabel} sub={s.address ?? ""} back />

      {/* header card */}
      <section className="rounded-[28px] border-2 border-brand-ink bg-card p-5 shadow-sticker relative overflow-hidden">
        <div className="absolute -top-6 -right-6 w-28 h-28 rounded-full bg-brand-yellow/40" />
        <div className="flex items-start gap-4 relative">
          <CategoryIcon categoryKey={s.categoryKey} size={60} className="border-2 border-brand-ink/10" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="font-display text-[22px] leading-tight">{s.name}</h1>
              {s.isVerified && <BadgeCheck className="w-5 h-5 text-brand-green shrink-0" />}
            </div>
            <div className="text-[13px] font-bold text-muted-foreground mt-1">
              {formatDistance(s.distanceMeters)} door
            </div>
            {s.description && (
              <p className="text-[13.5px] font-semibold text-brand-ink/70 mt-2 leading-relaxed">{s.description}</p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 mt-4">
          {s.capabilities.map((c) => (
            <span key={c} className="rounded-full bg-background px-2.5 py-1 text-[11px] font-bold text-brand-ink/65">
              {c}
            </span>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-2.5 mt-5">
          {s.lat != null && s.lng != null ? (
            <a
              href={`https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lng}`}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border-2 border-brand-ink bg-brand-ink text-brand-yellow text-[13px] font-extrabold py-3 flex items-center justify-center gap-2 active:translate-y-[2px] transition-all"
            >
              <Navigation className="w-4 h-4" /> Route
            </a>
          ) : (
            <span className="rounded-full border-2 border-brand-ink/15 bg-background text-muted-foreground text-[13px] font-extrabold py-3 flex items-center justify-center gap-2">
              <MapPin className="w-4 h-4" /> Location unavailable
            </span>
          )}
          {s.phone && (
            <a
              href={`tel:${s.phone}`}
              className="rounded-full border-2 border-brand-ink bg-brand-yellow text-[13px] font-extrabold py-3 flex items-center justify-center gap-2 shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all"
            >
              <Phone className="w-4 h-4" /> Call karo
            </a>
          )}
        </div>
      </section>

      {reservedItem && s.lat != null && s.lng != null && (
        <section className="mt-4 rounded-[28px] border-2 border-brand-green bg-[#00914612] p-5">
          <div className="flex items-start gap-3">
            <CircleCheck className="mt-0.5 h-6 w-6 shrink-0 text-brand-green" />
            <div>
              <h2 className="font-display text-[17px]">Buy request ready</h2>
              <p className="mt-1 text-[12px] font-bold text-brand-ink/70">
                {reservedItem} ke liye dukaan ko message bhej diya. Confirm hone ke baad yahan se route kholo.
              </p>
            </div>
          </div>
          <a
            href={`https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lng}`}
            target="_blank"
            rel="noreferrer"
            className="mt-4 flex items-center justify-center gap-2 rounded-full border-2 border-brand-ink bg-brand-ink py-3 text-[13px] font-extrabold text-brand-yellow"
          >
            <Navigation className="h-4 w-4" /> Dukaan ka rasta kholo
          </a>
        </section>
      )}

      {/* inventory */}
      <section className="mt-7">
        <div className="flex items-end justify-between mb-3.5">
          <h2 className="font-display text-[19px]">Stock mein kya hai</h2>
          {s.inventory.length > 0 && <Sticker rot={2}>{s.inventory.length} items</Sticker>}
        </div>

        {s.inventory.length === 0 ? (
          <EmptyState
            icon={<PackageOpen className="w-7 h-7" />}
            title="Stock list nahi hai"
            sub="Par dukaan requests ka jawab deti hai — seedha pooch lo."
            action={
              <button
                onClick={() => navigate("/")}
                className="rounded-full border-2 border-brand-ink bg-brand-yellow px-6 py-3 font-display text-[14px] shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all"
              >
                Request bhejo →
              </button>
            }
          />
        ) : (
          <div className="grid gap-2.5 sm:grid-cols-2">
            {s.inventory.map((it, i) => (
              <div
                key={it.id}
                className="lm-pop rounded-3xl border-2 border-brand-ink/10 bg-card p-4 flex items-center gap-3"
                style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
              >
                <div className="flex-1 min-w-0">
                  <div className="font-extrabold text-[14.5px] leading-tight">{it.name}</div>
                  <div className="text-[11.5px] font-bold text-muted-foreground mt-1">
                    per {it.unit} · {it.inStock ? `${it.quantity} available` : "abhi khatam"}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="font-display text-[18px]">{formatINR(it.price)}</div>
                  <span
                    className="inline-block rounded-full px-2 py-0.5 text-[10px] font-extrabold mt-1"
                    style={
                      it.inStock
                        ? { background: "#0091461a", color: "#009146" }
                        : { background: "#F037491a", color: "#F03749" }
                    }
                  >
                    {it.inStock ? "In stock" : "Out"}
                  </span>
                </div>
                {it.inStock && (
                  <button
                    onClick={() => {
                      if (location.lat == null || location.lng == null) {
                        toast.error("Pehle apni location allow karo");
                        void location.locate();
                        return;
                      }
                      reserve.mutate({
                        itemId: it.id,
                        quantity: 1,
                        lat: location.lat,
                        lng: location.lng,
                      });
                    }}
                    disabled={reserve.isPending}
                    className="rounded-full border-2 border-brand-green bg-brand-green px-3 py-2 text-[11px] font-extrabold text-brand-cream disabled:opacity-50"
                  >
                    {reserve.isPending ? "Bhej rahe…" : "Buy / reserve"}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <button
        onClick={() => navigate(`/compare?q=${encodeURIComponent(s.capabilities[0] ?? "")}`)}
        className="mt-6 w-full rounded-full border-2 border-brand-ink bg-card font-display text-[14.5px] py-4 shadow-sticker active:translate-y-[3px] active:shadow-none transition-all"
      >
        Daam compare karo →
      </button>
    </div>
  );
}
