import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";
import {
  Phone, Navigation, PartyPopper, Filter, Siren, Share2,
} from "lucide-react";
import { api as trpc, type FlagReason } from "@/lib/api";
import { useLocation } from "@/lib/location";
import { TopBar } from "@/components/shell";
import { CategoryIcon, Thinking } from "@/components/brand";
import {
  OfferCard, SORT_OPTIONS, sortOffers, type OfferSortKey,
} from "@/components/OfferCard";
import { ChatDrawer } from "@/components/ChatDrawer";
import { formatDistance, formatINR, clsx } from "@/lib/format";
import { categoryMeta } from "@/lib/localmart";

type Phase = "intent" | "matching" | "offers";

const tick = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function SearchFlow() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const q = params.get("q") ?? "";
  const rid = params.get("rid");
  const inputType = (params.get("type") ?? "text") as "text" | "voice" | "image";

  const [phase, setPhase] = useState<Phase>("intent");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [intent, setIntent] = useState<{
    product: string;
    categoryKey: string;
    confidence: number;
    provider?: string;
    isRuleBased?: boolean;
  } | null>(null);
  const [candidates, setCandidates] = useState<any[]>([]);
  const [radiusIdx, setRadiusIdx] = useState(0);
  const [sortKey, setSortKey] = useState<OfferSortKey>("best");
  const [hideDeclined, setHideDeclined] = useState(true);
  const startedRef = useRef(false);
  const RADII = [500, 1000, 2000, 5000];

  const createRequest = trpc.request.create.useMutation();
  const detail = trpc.request.detail.useQuery(
    { id: requestId ?? "" },
    { enabled: requestId != null, refetchInterval: 4000 },
  );
  const choose = trpc.request.choose.useMutation({
    onSuccess: () => {
      toast.success("Pakka! Dukaan ko bata diya.");
      detail.refetch();
    },
    onError: (e) => toast.error(e.message),
  });
  const flagShop = trpc.request.flag.useMutation({
    onSuccess: (data) => {
      toast.success(
        data.auto_suspended
          ? "Reported — shop abhi turant suspend ho gaya hai (safety reason)."
          : "Reported — admin review ke liye bhej diya.",
      );
    },
    onError: (e) => toast.error(e.message),
  });
  const panic = trpc.request.panic.useMutation({
    onSuccess: (data) => {
      toast(data.message ?? "Panic alert recorded.", { duration: 6000 });
    },
    onError: (e) => toast.error(e.message),
  });

  // Chat drawer state — opens when customer taps Chat on the chosen offer.
  const [chatOpen, setChatOpen] = useState(false);

  const triggerPanic = async () => {
    if (location.lat == null || location.lng == null) {
      toast.error("Panic ke liye location permission do.");
      location.locate();
      return;
    }
    if (!confirm("Panic button dabana hai? Aapke trusted contact ko alert jaayegi.")) return;
    await panic.mutateAsync({
      requestId: requestId ?? undefined,
      latitude: location.lat,
      longitude: location.lng,
    });
  };

  const shareTrip = () => {
    // Open Google Maps so the customer can start live-trip sharing with their family.
    // (Google Maps' trip-share UI is a manual start — we just deep-link them there.)
    if (selectedOffer?.shop?.lat && selectedOffer?.shop?.lng) {
      const url = `https://www.google.com/maps/dir/?api=1&destination=${selectedOffer.shop.lat},${selectedOffer.shop.lng}`;
      window.open(url, "_blank", "noopener");
      toast.success("Maps khul gaya. Top-right → 'Share trip' → family ko bhej do.");
    }
  };

  useEffect(() => {
    if (startedRef.current) return;
    if (rid) {
      startedRef.current = true;
      setRequestId(rid);
      setPhase("offers");
      return;
    }
    if (!q) return;
    if (location.lat == null || location.lng == null) {
      toast.error("Pehle apni location allow karo");
      location.locate();
      return;
    }
    const requestLat = location.lat;
    const requestLng = location.lng;
    startedRef.current = true;
    (async () => {
      try {
        const res = await createRequest.mutateAsync({
          rawText: q,
          inputType,
          lat: requestLat,
          lng: requestLng,
        });
        setIntent({
          product: res.intent.product,
          categoryKey: res.intent.categoryKey,
          confidence: res.intent.confidence,
          provider: res.intent.provider,
          isRuleBased: res.intent.isRuleBased,
        });
        setRequestId(res.requestId);
        await tick(1000);
        setPhase("matching");
        for (let i = 0; i < RADII.length; i++) {
          setRadiusIdx(i);
          await tick(620);
        }
        setCandidates(res.candidates);
        await tick(650);
        setPhase("offers");
        if (res.candidates.length === 0) {
          toast("Koi dukaan match nahi hui — demand note kar li hai.");
        }
      } catch {
        toast.error("Kuch gadbad ho gayi — phir try karo.");
        navigate("/");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  // Live-pulled offers from the detail endpoint.
  const offers = detail.data?.offers ?? [];
  const request = detail.data?.request;
  const selectedMatchId = request?.selectedMatchId ?? null;
  const acceptedCount = offers.filter((o) => o.status === "accepted").length;

  // Apply sort + filter to the offer list.
  const visibleOffers = useMemo(() => {
    const filtered = hideDeclined
      ? offers.filter((o) => o.status !== "declined" && o.status !== "expired")
      : offers;
    return sortOffers(filtered, sortKey);
  }, [offers, sortKey, hideDeclined]);

  // When re-opening an existing request, hydrate intent + candidates from detail
  useEffect(() => {
    if (rid && detail.data && !intent) {
      const r = detail.data.request;
      setIntent({
        product: r.product,
        categoryKey: r.categoryKey,
        confidence: r.confidence,
      });
      setCandidates(
        detail.data.offers.map((o) => ({
          shopId: o.shopId,
          shop: o.shop,
          distanceMeters: o.distanceMeters,
          matchScore: o.matchScore,
          hasInventoryHint: o.hasInventoryHint,
        })),
      );
    }
  }, [rid, detail.data, intent]);

  // Selected shop (for the "Deal pakki!" panel) — find the accepted offer that
  // matches the request's selectedMatchId.
  const selectedOffer = useMemo(
    () => offers.find((o) => o.id === selectedMatchId) ?? null,
    [offers, selectedMatchId],
  );

  const meta = categoryMeta(intent?.categoryKey ?? "other");

  return (
    <div>
      <TopBar title="Khoj" sub={`"${q}"`} back />

      {/* I — intent */}
      <section className="rounded-[28px] bg-brand-ink p-5 sm:p-6 relative overflow-hidden">
        <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full bg-brand-yellow/15" />
        <div className="absolute -bottom-10 -left-6 w-28 h-28 rounded-full bg-brand-green/20" />
        <div className="text-[10.5px] font-extrabold uppercase tracking-[0.18em] text-brand-yellow">
          {inputType === "voice"
            ? "Awaaz se samjha"
            : inputType === "image"
              ? "Photo se pehchana"
              : "AI Intent"}
        </div>
        {phase === "intent" || !intent ? (
          <div className="mt-4"><Thinking dark text="Samajh raha hoon…" /></div>
        ) : (
          <div className="lm-pop mt-2">
            <div className="font-display text-[26px] sm:text-[30px] leading-tight text-brand-cream">
              {intent?.product}
            </div>
            <div className="flex items-center gap-2.5 mt-3 flex-wrap">
              <span
                className="rounded-full px-3 py-1 text-[11px] font-extrabold uppercase tracking-wide text-brand-cream"
                style={{ background: meta.color }}
              >
                {meta.label}
              </span>
              <span className={clsx(
                "text-[12px] font-extrabold",
                (intent?.confidence ?? 0) >= 0.8 ? "text-[#8ED462]" : "text-brand-yellow",
              )}>
                confidence {Math.round((intent?.confidence ?? 0) * 100)}%
              </span>
              {intent?.isRuleBased && (
                <span className="rounded-full bg-[#7C3AED]/30 text-brand-yellow px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wide">
                  Rule-based fallback
                </span>
              )}
              {intent?.provider && !intent?.isRuleBased && (
                <span className="text-[11px] font-bold text-brand-yellow/70 uppercase tracking-wide">
                  via {intent.provider}
                </span>
              )}
            </div>
          </div>
        )}
      </section>

      {/* II — radar matching */}
      {(phase === "matching" || phase === "offers") && (
        <section className="mt-4 rounded-[28px] border-2 border-brand-ink/12 bg-card p-5 lm-enter">
          <div className="flex items-center gap-5">
            <Radar active={phase === "matching"} found={candidates.length > 0} />
            <div className="flex-1">
              {phase === "matching" ? (
                <>
                  <div className="font-display text-[17px]">Dukaanein dhundh raha hoon…</div>
                  <div className="text-[11.5px] font-extrabold uppercase tracking-[0.12em] mt-1.5 text-[#8A5A00]">
                    radius {RADII[radiusIdx]}m {radiusIdx < RADII.length - 1 ? "→ badh raha hai" : ""}
                  </div>
                </>
              ) : (
                <>
                  <div className="font-display text-[17px]">
                    {candidates.length > 0
                      ? candidates.length === 1
                        ? "1 dukaan mili"
                        : `${candidates.length} dukaanein mili`
                      : "Koi match nahi mila"}
                  </div>
                  <div className="text-[11.5px] font-extrabold uppercase tracking-[0.12em] mt-1.5 text-brand-green">
                    {candidates.length > 0 ? "score se sort · request bhej di" : "demand note ho gayi"}
                  </div>
                </>
              )}
            </div>
          </div>

          {candidates.length > 0 && (
            <div className="mt-4 space-y-2">
              {candidates.map((c, i) => (
                <div
                  key={c.shopId}
                  className="lm-pop flex items-center gap-3 rounded-2xl border-2 border-brand-ink/10 bg-background p-3"
                  style={{ animationDelay: `${i * 0.08}s` }}
                >
                  <span
                    className={clsx(
                      "w-8 h-8 rounded-xl grid place-items-center font-display text-[13px] shrink-0",
                      i === 0 ? "bg-brand-ink text-brand-yellow" : "bg-brand-ink/10 text-brand-ink",
                    )}
                  >
                    {i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="font-extrabold text-[14.5px] truncate">{c.shop.name}</div>
                    <div className="text-[11px] font-bold text-muted-foreground">
                      {c.shop.categoryLabel} · {formatDistance(c.distanceMeters)}
                      {c.hasInventoryHint && <span className="text-brand-green"> · stock hint ✓</span>}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-display text-[14px]">{Math.round(c.matchScore * 100)}%</div>
                    <div className="w-14 h-1.5 rounded-full bg-brand-ink/10 mt-1 overflow-hidden">
                      <div className="h-full rounded-full bg-brand-green" style={{ width: `${c.matchScore * 100}%` }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* III — live offers + sort + filter */}
      {phase === "offers" && candidates.length > 0 && (
        <section className="mt-6 lm-enter">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-[19px]">Dukaan ke Jawab</h2>
              {acceptedCount > 0 && (
                <span className="rounded-full bg-brand-green text-brand-cream px-2 py-0.5 text-[10.5px] font-extrabold">
                  {acceptedCount} offer{acceptedCount === 1 ? "" : "s"} ready
                </span>
              )}
            </div>
            {offers.some((o) => o.status === "pending") && (
              <span className="flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-wide text-brand-green">
                <span className="w-2 h-2 rounded-full bg-brand-green lm-pulse-dot" /> live
              </span>
            )}
          </div>

          {/* Sort + filter controls */}
          {offers.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap mb-3">
              <div className="flex items-center gap-1.5 rounded-full border-2 border-brand-ink/15 bg-card p-1 overflow-x-auto">
                {SORT_OPTIONS.map((opt) => (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => setSortKey(opt.key)}
                    className={clsx(
                      "rounded-full px-3 py-1 text-[11px] font-extrabold whitespace-nowrap",
                      sortKey === opt.key
                        ? "bg-brand-ink text-brand-yellow"
                        : "text-brand-ink/60 hover:text-brand-ink",
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setHideDeclined((v) => !v)}
                className={clsx(
                  "rounded-full border-2 px-3 py-1 text-[11px] font-extrabold inline-flex items-center gap-1",
                  hideDeclined
                    ? "border-brand-ink/15 bg-card text-brand-ink/60"
                    : "border-brand-ink bg-brand-ink text-brand-yellow",
                )}
              >
                <Filter className="w-3 h-3" /> {hideDeclined ? "Sabhi" : "Sirf 'Hai!'"}
              </button>
            </div>
          )}

          {offers.length === 0 && (
            <div className="rounded-3xl border-2 border-dashed border-brand-ink/20 bg-card p-6">
              <Thinking text="Dukaandaar se jawab aa raha hai…" />
              <p className="text-[11.5px] font-extrabold uppercase tracking-[0.14em] text-muted-foreground text-center mt-2">
                Page khula rakho — jaise hi koi dukaan haan bolega, yahan dikh jayega
              </p>
            </div>
          )}

          {visibleOffers.length > 0 && (
            <div className="space-y-3">
              {visibleOffers.map((o) => (
                <OfferCard
                  key={o.id}
                  offer={o}
                  isPending={choose.isPending}
                  isSelected={o.id === selectedMatchId}
                  onChoose={() => choose.mutate({ offerId: o.id })}
                  onOpen={() => navigate(`/shop/${o.shopId}`)}
                  onChat={o.status === "accepted" ? () => setChatOpen(true) : undefined}
                  onFlag={(reason: FlagReason) =>
                    flagShop.mutate({ requestId: o.requestId, reason })
                  }
                />
              ))}
            </div>
          )}

          {request?.status === "completed" && selectedOffer && (
            <div className="lm-pop mt-4 rounded-[28px] border-2 border-brand-ink bg-brand-green p-5 shadow-sticker-green">
              <div className="flex items-center gap-2 text-brand-yellow">
                <PartyPopper className="w-7 h-7" />
                <div className="font-display text-[19px] text-brand-cream">Deal pakki!</div>
              </div>
              <div className="mt-3 rounded-2xl bg-brand-cream p-4">
                <div className="flex items-start gap-3">
                  <CategoryIcon categoryKey={selectedOffer.shop?.categoryKey ?? "other"} size={44} />
                  <div className="flex-1 min-w-0">
                    <div className="font-extrabold text-[15px]">
                      {selectedOffer.shop?.name}
                    </div>
                    <div className="text-[12px] font-bold text-brand-ink/60 mt-0.5">
                      {formatDistance(selectedOffer.distanceMeters)} door · {selectedOffer.shop?.address}
                    </div>
                    {selectedOffer.price != null && (
                      <div className="font-display text-[22px] mt-1 text-brand-green">
                        {formatINR(selectedOffer.price)}
                      </div>
                    )}
                    {selectedOffer.freshness && (
                      <div className="text-[10.5px] font-bold text-brand-ink/55 mt-1">
                        {selectedOffer.freshness.statusLabel}
                      </div>
                    )}
                  </div>
                </div>
                {selectedOffer.shop && (
                  <div className="grid grid-cols-2 gap-2 mt-4">
                    <a
                      href={`https://www.google.com/maps/dir/?api=1&destination=${selectedOffer.shop.lat},${selectedOffer.shop.lng}`}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-full border-2 border-brand-ink bg-brand-ink text-brand-yellow text-[12px] font-extrabold py-2.5 flex items-center justify-center gap-1.5"
                    >
                      <Navigation className="w-3.5 h-3.5" /> Route
                    </a>
                    {selectedOffer.shop.phone && (
                      <a
                        href={`tel:${selectedOffer.shop.phone}`}
                        className="rounded-full border-2 border-brand-ink bg-card text-[12px] font-extrabold py-2.5 flex items-center justify-center gap-1.5"
                      >
                        <Phone className="w-3.5 h-3.5" /> Call
                      </a>
                    )}
                  </div>
                )}

                {/* Safety row — Share trip + Panic */}
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={shareTrip}
                    className="rounded-full border-2 border-brand-ink/30 bg-card text-brand-ink text-[11px] font-extrabold py-2 flex items-center justify-center gap-1.5"
                  >
                    <Share2 className="w-3.5 h-3.5" /> Share trip
                  </button>
                  <button
                    type="button"
                    onClick={triggerPanic}
                    disabled={panic.isPending}
                    className="rounded-full border-2 border-[#F03749] bg-[#F03749] text-brand-cream text-[11px] font-extrabold py-2 flex items-center justify-center gap-1.5 disabled:opacity-50"
                  >
                    <Siren className="w-3.5 h-3.5" /> Panic
                  </button>
                </div>

                <p className="text-[10.5px] font-bold text-brand-ink/55 mt-2 text-center">
                  Dukaan pe jaake le lo — ya call karke rakhwa lo.
                </p>
              </div>
            </div>
          )}

          {request?.status === "no_match" && (
            <div className="mt-4 rounded-[28px] border-2 border-dashed border-brand-ink/20 bg-card p-5">
              <div className="font-display text-[17px]">Demand note ho gayi</div>
              <p className="text-[12px] font-bold text-muted-foreground mt-1">
                Aapki request demand data mein save ho gayi hai — nearby shops ko
                pata chalega ki is mohalle ko yeh product chahiye.
              </p>
            </div>
          )}
        </section>
      )}

      <button
        onClick={() => navigate("/")}
        className="mt-8 w-full rounded-full border-2 border-brand-ink bg-card font-display text-[15px] py-4 shadow-sticker active:translate-y-[3px] active:shadow-none transition-all"
      >
        Nayi khoj →
      </button>

      {/* Chat drawer — opens when customer taps Chat on the chosen offer */}
      {chatOpen && selectedOffer && (
        <ChatDrawer
          requestId={selectedOffer.requestId}
          shopName={selectedOffer.shop?.name}
          shopfrontPhotoUrl={selectedOffer.shop?.shopfrontPhotoUrl}
          shopAddress={selectedOffer.shop?.address}
          side="customer"
          onClose={() => setChatOpen(false)}
        />
      )}
    </div>
  );
}

function Radar({ active, found }: { active: boolean; found: boolean }) {
  return (
    <div className="relative w-[84px] h-[84px] shrink-0">
      <svg viewBox="0 0 84 84" className="w-full h-full">
        <circle cx="42" cy="42" r="40" fill="none" stroke="#141313" strokeOpacity="0.15" strokeWidth="2" />
        <circle cx="42" cy="42" r="27" fill="none" stroke="#141313" strokeOpacity="0.15" strokeWidth="2" />
        <circle cx="42" cy="42" r="14" fill="none" stroke="#141313" strokeOpacity="0.15" strokeWidth="2" />
        <g className={active ? "lm-radar" : ""} style={{ transformOrigin: "42px 42px" }}>
          <path d="M42 42 L42 2 A40 40 0 0 1 70 13 Z" fill={found ? "#009146" : "#FEE600"} fillOpacity="0.45" />
          <line x1="42" y1="42" x2="42" y2="2" stroke={found ? "#009146" : "#E8930C"} strokeWidth="2.5" strokeLinecap="round" />
        </g>
        <circle cx="42" cy="42" r="4.5" fill="#F03749" stroke="#FFFCF5" strokeWidth="2" />
      </svg>
    </div>
  );
}
