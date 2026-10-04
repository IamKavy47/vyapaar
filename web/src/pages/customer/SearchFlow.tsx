import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";
import { Phone, Navigation, BadgeCheck, PartyPopper, CircleCheck } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { useLocation } from "@/lib/location";
import { TopBar } from "@/components/shell";
import { CategoryIcon, Thinking } from "@/components/brand";
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
  const [intent, setIntent] = useState<{ product: string; categoryKey: string; confidence: number } | null>(null);
  const [candidates, setCandidates] = useState<any[]>([]);
  const [radiusIdx, setRadiusIdx] = useState(0);
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
  });

  useEffect(() => {
    if (startedRef.current) return;
    // Re-open an existing request (from Activity)
    if (rid) {
      startedRef.current = true;
      setRequestId(rid);
      setPhase("offers");
      return;
    }
    if (!q) return;
    startedRef.current = true;
    (async () => {
      try {
        const res = await createRequest.mutateAsync({
          rawText: q,
          inputType,
          lat: location.lat,
          lng: location.lng,
        });
        setIntent(res.intent);
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

  const offers = detail.data?.offers ?? [];
  const answered = offers.filter((o) => o.status !== "pending");

  // When re-opening an existing request, hydrate intent + candidates from detail
  useEffect(() => {
    if (rid && detail.data && !intent) {
      const r = detail.data.request;
      setIntent({ product: r.product, categoryKey: r.categoryKey, confidence: r.confidence });
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

  const meta = categoryMeta(intent?.categoryKey ?? "other");

  return (
    <div>
      <TopBar title="Khoj" sub={`"${q}"`} back />

      {/* I — intent */}
      <section className="rounded-[28px] bg-brand-ink p-5 sm:p-6 relative overflow-hidden">
        <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full bg-brand-yellow/15" />
        <div className="absolute -bottom-10 -left-6 w-28 h-28 rounded-full bg-brand-green/20" />
        <div className="text-[10.5px] font-extrabold uppercase tracking-[0.18em] text-brand-yellow">
          {inputType === "voice" ? "Awaaz se samjha" : inputType === "image" ? "Photo se pehchana" : "AI Intent"}
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
              <span className={clsx("text-[12px] font-extrabold", (intent?.confidence ?? 0) >= 0.8 ? "text-[#8ED462]" : "text-brand-yellow")}>
                confidence {Math.round((intent?.confidence ?? 0) * 100)}%
              </span>
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

      {/* III — live offers */}
      {phase === "offers" && candidates.length > 0 && (
        <section className="mt-6 lm-enter">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-[19px]">Dukaan ke Jawab</h2>
            {offers.some((o) => o.status === "pending") && (
              <span className="flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-wide text-brand-green">
                <span className="w-2 h-2 rounded-full bg-brand-green lm-pulse-dot" /> live
              </span>
            )}
          </div>

          {offers.length === 0 && (
            <div className="rounded-3xl border-2 border-dashed border-brand-ink/20 bg-card p-6">
              <Thinking text="Dukaandaar se jawab aa raha hai…" />
            </div>
          )}

          <div className="space-y-3">
            {offers.map((o) => (
              <OfferCard
                key={o.id}
                offer={o}
                pending={choose.isPending}
                onChoose={() => choose.mutate({ offerId: o.id })}
                onOpen={() => navigate(`/shop/${o.shopId}`)}
              />
            ))}
          </div>

          {answered.length === 0 && (
            <p className="text-center text-[12px] font-extrabold uppercase tracking-[0.14em] text-muted-foreground py-3">
              Jawab aate hi yahan dikhenge — page khula rakho
            </p>
          )}

          {detail.data?.request.status === "completed" && (
            <div className="lm-pop mt-4 rounded-[28px] border-2 border-brand-ink bg-brand-green p-5 text-center shadow-sticker-green">
              <PartyPopper className="w-7 h-7 mx-auto text-brand-yellow" />
              <div className="font-display text-[19px] text-brand-cream mt-2">Deal pakki!</div>
              <p className="text-[13px] font-bold text-brand-cream/80 mt-1">
                Dukaan pe jaake le lo — ya call karke rakhwa lo.
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

function OfferCard({
  offer,
  pending,
  onChoose,
  onOpen,
}: {
  offer: any;
  pending: boolean;
  onChoose: () => void;
  onOpen: () => void;
}) {
  const ok = offer.status === "accepted";
  const no = offer.status === "declined" || offer.status === "expired";
  const waiting = offer.status === "pending";
  const shop = offer.shop;
  return (
    <div
      className={clsx(
        "lm-pop rounded-[26px] border-2 p-4 relative overflow-hidden transition-all",
        ok && "border-brand-green bg-[#00914610] shadow-sticker",
        waiting && "border-brand-ink/12 bg-card",
        no && "border-brand-ink/10 bg-card opacity-60",
      )}
    >
      <div className="flex items-start gap-3.5">
        <CategoryIcon categoryKey={shop.categoryKey} size={46} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-extrabold text-[15.5px] truncate">{shop.name}</span>
            {shop.isVerified && <BadgeCheck className="w-4 h-4 text-brand-green shrink-0" />}
            <span
              className={clsx(
                "rounded-full px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide",
                ok && "bg-brand-green text-brand-cream",
                waiting && "bg-brand-yellow text-brand-ink",
                no && "bg-brand-ink/10 text-brand-ink/50",
              )}
            >
              {ok ? "Hai!" : waiting ? "soch rahe…" : "Nahi hai"}
            </span>
          </div>
          <div className="text-[12px] font-bold text-muted-foreground mt-1">
            {formatDistance(offer.distanceMeters)} door · {shop.address}
          </div>
        </div>
        {ok && offer.price != null && (
          <div className="text-right shrink-0">
            <div className="font-display text-[24px] leading-none text-brand-ink">{formatINR(offer.price)}</div>
          </div>
        )}
      </div>

      {ok && (
        <div className="grid grid-cols-3 gap-2 mt-4">
          <a
            href={`https://www.google.com/maps/dir/?api=1&destination=${shop.lat},${shop.lng}`}
            target="_blank"
            rel="noreferrer"
            className="rounded-full border-2 border-brand-ink bg-brand-ink text-brand-yellow text-[12px] font-extrabold py-2.5 flex items-center justify-center gap-1.5"
          >
            <Navigation className="w-3.5 h-3.5" /> Route
          </a>
          {shop.phone ? (
            <a
              href={`tel:${shop.phone}`}
              className="rounded-full border-2 border-brand-ink bg-card text-[12px] font-extrabold py-2.5 flex items-center justify-center gap-1.5"
            >
              <Phone className="w-3.5 h-3.5" /> Call
            </a>
          ) : (
            <button onClick={onOpen} className="rounded-full border-2 border-brand-ink bg-card text-[12px] font-extrabold py-2.5">
              Dukaan
            </button>
          )}
          <button
            onClick={onChoose}
            disabled={pending}
            className="rounded-full border-2 border-brand-green bg-brand-green text-brand-cream text-[12px] font-extrabold py-2.5 flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            <CircleCheck className="w-3.5 h-3.5" /> Yahi final
          </button>
        </div>
      )}
      {no && (
        <p className="text-[10.5px] font-extrabold uppercase tracking-[0.12em] mt-2.5 text-muted-foreground">
          Demand note hui · agli baar stock mein hoga
        </p>
      )}
    </div>
  );
}
