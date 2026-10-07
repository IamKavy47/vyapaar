import { useState } from "react";
import {
  Phone, Navigation, BadgeCheck, CircleCheck, Clock, Gauge, Info, Sparkles, FlaskConical,
  MessageCircle, Flag, X,
} from "lucide-react";
import { clsx, formatDistance, formatINR, formatScore, formatSeconds } from "@/lib/format";
import type { Offer, FlagReason } from "@/lib/api";
import { CategoryIcon } from "@/components/brand";

export type OfferSortKey =
  | "best"        // best overall — matchScore * trust, then price
  | "nearest"     // distance ascending
  | "cheapest"    // price ascending (accepted only)
  | "reliable"    // reliabilityScore descending
  | "fastest";    // responseSeconds ascending

export const SORT_OPTIONS: { key: OfferSortKey; label: string }[] = [
  { key: "best", label: "Best overall" },
  { key: "nearest", label: "Nearest" },
  { key: "cheapest", label: "Lowest price" },
  { key: "reliable", label: "Most reliable" },
  { key: "fastest", label: "Fastest response" },
];

export function sortOffers(offers: Offer[], key: OfferSortKey): Offer[] {
  const accepted = (o: Offer) => o.status === "accepted";
  const safe = [...offers];
  switch (key) {
    case "nearest":
      safe.sort((a, b) => a.distanceMeters - b.distanceMeters);
      break;
    case "cheapest":
      // Accepted offers first, sorted by price asc; pending/declined at the end.
      safe.sort((a, b) => {
        if (accepted(a) !== accepted(b)) return accepted(a) ? -1 : 1;
        if (!accepted(a) || !accepted(b)) return 0;
        const pa = a.price ?? Number.POSITIVE_INFINITY;
        const pb = b.price ?? Number.POSITIVE_INFINITY;
        return pa - pb;
      });
      break;
    case "reliable":
      safe.sort((a, b) => (b.trust?.reliabilityScore ?? 0) - (a.trust?.reliabilityScore ?? 0));
      break;
    case "fastest":
      // Offers with a measured response time first; pending offers at the end.
      safe.sort((a, b) => {
        const ta = a.responseSeconds ?? Number.POSITIVE_INFINITY;
        const tb = b.responseSeconds ?? Number.POSITIVE_INFINITY;
        return ta - tb;
      });
      break;
    case "best":
    default:
      safe.sort((a, b) => {
        // Accepted first.
        if (accepted(a) !== accepted(b)) return accepted(a) ? -1 : 1;
        // Then by matchScore desc.
        if (b.matchScore !== a.matchScore) return b.matchScore - a.matchScore;
        // Then by reliability desc.
        const ra = a.trust?.reliabilityScore ?? 0;
        const rb = b.trust?.reliabilityScore ?? 0;
        if (rb !== ra) return rb - ra;
        // Then by distance asc.
        return a.distanceMeters - b.distanceMeters;
      });
  }
  return safe;
}

interface OfferCardProps {
  offer: Offer;
  isPending?: boolean;
  isSelected?: boolean;
  showChoose?: boolean;
  onChoose?: () => void;
  onOpen?: () => void;
  onChat?: () => void;
  onFlag?: (reason: FlagReason) => void;
}

/**
 * Enhanced offer card — shows everything the spec asks for on the
 * customer's compare screen: shop name, distance, merchant-confirmed price,
 * response time, reliability/trust indicator, verification status,
 * inventory freshness, match score, short why-recommended explanation,
 * address, phone, map link, and a Choose button.
 *
 * Demo-simulated offers are clearly labelled so customers / judges never
 * confuse them with real merchant activity.
 *
 * Shopfront photo (when present) replaces the abstract CategoryIcon as the
 * shop's visual identity — the strongest trust signal that a real shop
 * exists at the registered location.
 */
export function OfferCard({
  offer, isPending, isSelected, showChoose = true, onChoose, onOpen, onChat, onFlag,
}: OfferCardProps) {
  const [showWhy, setShowWhy] = useState(false);
  const [showFlagMenu, setShowFlagMenu] = useState(false);
  const ok = offer.status === "accepted";
  const no = offer.status === "declined" || offer.status === "expired";
  const waiting = offer.status === "pending";
  const shop = offer.shop;
  if (!shop) return null;

  const trust = offer.trust;
  const freshness = offer.freshness;
  const why = offer.whyRecommended ?? [];
  const isDemo = offer.isDemoSimulated;

  return (
    <div
      className={clsx(
        "lm-pop rounded-[26px] border-2 p-4 relative overflow-hidden transition-all",
        isSelected && "border-brand-ink bg-brand-ink text-brand-cream shadow-sticker",
        !isSelected && ok && "border-brand-green bg-[#00914610] shadow-sticker",
        !isSelected && waiting && "border-brand-ink/12 bg-card",
        !isSelected && no && "border-brand-ink/10 bg-card opacity-60",
      )}
    >
      {isDemo && (
        <div className="absolute top-0 right-0 bg-[#7C3AED] text-white text-[9px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-bl-xl flex items-center gap-1">
          <FlaskConical className="w-2.5 h-2.5" /> Demo-simulated
        </div>
      )}

      <div className="flex items-start gap-3.5">
        {/* Shopfront photo — replaces CategoryIcon when available.
            This is the strongest visible trust signal. */}
        {shop.shopfrontPhotoUrl ? (
          <img
            src={shop.shopfrontPhotoUrl}
            alt={shop.name}
            className="w-[46px] h-[46px] rounded-2xl border-2 border-brand-ink/15 object-cover shrink-0"
          />
        ) : (
          <CategoryIcon categoryKey={shop.categoryKey} size={46} />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-extrabold text-[15.5px] truncate">{shop.name}</span>
            {shop.isVerified && (
              <BadgeCheck className="w-4 h-4 text-brand-green shrink-0" />
            )}
            <span
              className={clsx(
                "rounded-full px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide",
                isSelected && "bg-brand-yellow text-brand-ink",
                !isSelected && ok && "bg-brand-green text-brand-cream",
                !isSelected && waiting && "bg-brand-yellow text-brand-ink",
                !isSelected && no && "bg-brand-ink/10 text-brand-ink/50",
              )}
            >
              {isSelected ? "Picked" : ok ? "Hai!" : waiting ? "soch rahe…" : "Nahi hai"}
            </span>
          </div>
          <div className="text-[12px] font-bold text-muted-foreground mt-1">
            {formatDistance(offer.distanceMeters)} door · {shop.address}
          </div>
          {/* Freshness label — proves the data shown is current */}
          {freshness && (ok || offer.hasInventoryHint) && (
            <div className="text-[10.5px] font-bold text-brand-ink/55 mt-1 flex items-center gap-1">
              <Clock className="w-3 h-3" /> {freshness.statusLabel} · {freshness.priceLabel}
            </div>
          )}
        </div>
        {ok && offer.price != null && !isSelected && (
          <div className="text-right shrink-0">
            <div className="font-display text-[24px] leading-none text-brand-ink">
              {formatINR(offer.price)}
            </div>
          </div>
        )}
        {ok && offer.price == null && !isSelected && (
          <div className="text-right shrink-0 text-[10.5px] font-extrabold uppercase tracking-wide text-muted-foreground">
            Price not<br />provided
          </div>
        )}
      </div>

      {/* Trust + freshness badges row */}
      {trust && !no && (
        <div className="mt-3 flex items-center gap-1.5 flex-wrap">
          <span
            className={clsx(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-extrabold",
              trust.isNewMerchant
                ? "bg-brand-ink/8 text-brand-ink/65"
                : trust.reliabilityScore >= 80
                  ? "bg-brand-green/15 text-brand-green"
                  : "bg-brand-yellow/30 text-[#8A5A00]",
            )}
          >
            <Gauge className="w-3 h-3" />
            {trust.label} · {formatScore(trust.reliabilityScore)}
          </span>
          {offer.responseSeconds != null && (
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-ink/8 text-brand-ink/65 px-2 py-0.5 text-[10px] font-extrabold">
              <Clock className="w-3 h-3" /> {formatSeconds(offer.responseSeconds)}
            </span>
          )}
          {offer.matchScore > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-ink/8 text-brand-ink/65 px-2 py-0.5 text-[10px] font-extrabold">
              <Sparkles className="w-3 h-3" /> {Math.round(offer.matchScore * 100)}% match
            </span>
          )}
        </div>
      )}

      {/* Why-recommended explanation */}
      {why.length > 0 && !no && (
        <div className="mt-2.5">
          <button
            type="button"
            onClick={() => setShowWhy((s) => !s)}
            className="inline-flex items-center gap-1 text-[10.5px] font-extrabold uppercase tracking-wide text-brand-ink/55 hover:text-brand-ink"
          >
            <Info className="w-3 h-3" />
            {showWhy ? "Hide why" : "Why this shop?"}
          </button>
          {showWhy && (
            <ul className="mt-1.5 space-y-1">
              {why.map((b, i) => (
                <li
                  key={i}
                  className="text-[11.5px] font-bold text-brand-ink/70 flex items-start gap-1.5"
                >
                  <span className="text-brand-green mt-0.5">•</span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Action row — only when accepted and not yet picked */}
      {ok && !isSelected && showChoose && (
        <div className="grid grid-cols-4 gap-1.5 mt-4">
          {onChat && (
            <button
              type="button"
              onClick={onChat}
              className="rounded-full border-2 border-brand-ink bg-card text-[10.5px] font-extrabold py-2.5 flex items-center justify-center gap-1"
            >
              <MessageCircle className="w-3.5 h-3.5" /> Chat
            </button>
          )}
          <a
            href={`https://www.google.com/maps/dir/?api=1&destination=${shop.lat},${shop.lng}`}
            target="_blank"
            rel="noreferrer"
            className="rounded-full border-2 border-brand-ink bg-brand-ink text-brand-yellow text-[10.5px] font-extrabold py-2.5 flex items-center justify-center gap-1"
          >
            <Navigation className="w-3.5 h-3.5" /> Route
          </a>
          {shop.phone ? (
            <a
              href={`tel:${shop.phone}`}
              className="rounded-full border-2 border-brand-ink bg-card text-[10.5px] font-extrabold py-2.5 flex items-center justify-center gap-1"
            >
              <Phone className="w-3.5 h-3.5" /> Call
            </a>
          ) : (
            <button
              type="button"
              onClick={onOpen}
              className="rounded-full border-2 border-brand-ink bg-card text-[10.5px] font-extrabold py-2.5"
            >
              Dukaan
            </button>
          )}
          <button
            type="button"
            onClick={onChoose}
            disabled={isPending}
            className="rounded-full border-2 border-brand-green bg-brand-green text-brand-cream text-[10.5px] font-extrabold py-2.5 flex items-center justify-center gap-1 disabled:opacity-50"
          >
            <CircleCheck className="w-3.5 h-3.5" /> Final
          </button>
        </div>
      )}

      {/* Report button — small, bottom-right, only for declined/expired or
          after a customer has picked (so they can flag the chosen shop). */}
      {(isSelected || no) && onFlag && (
        <div className="mt-3 flex justify-end">
          {showFlagMenu ? (
            <div className="rounded-2xl border-2 border-[#F03749]/30 bg-card p-2 w-full">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10.5px] font-extrabold uppercase tracking-wide text-[#F03749]">
                  <Flag className="w-3.5 h-3.5 inline mr-1" />
                  Report this shop
                </span>
                <button onClick={() => setShowFlagMenu(false)} className="text-brand-ink/50">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="grid grid-cols-1 gap-1">
                {([
                  ["didnt_honor_price", "Didn't honor the price"],
                  ["felt_unsafe", "Felt unsafe"],
                  ["shop_doesnt_exist", "Shop doesn't exist"],
                  ["harassment_in_chat", "Harassment in chat"],
                  ["other", "Other"],
                ] as const).map(([reason, label]) => (
                  <button
                    key={reason}
                    onClick={() => {
                      onFlag(reason);
                      setShowFlagMenu(false);
                    }}
                    className="text-left rounded-xl bg-background px-2.5 py-1.5 text-[11.5px] font-bold hover:bg-[#F037490d]"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowFlagMenu(true)}
              className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wide text-brand-ink/40 hover:text-[#F03749]"
            >
              <Flag className="w-3 h-3" /> Report
            </button>
          )}
        </div>
      )}

      {isSelected && (
        <p className="text-[11px] font-extrabold uppercase tracking-wide text-brand-yellow mt-3">
          ✓ Aapne is dukaan ko chuna
        </p>
      )}

      {no && (
        <p className="text-[10.5px] font-extrabold uppercase tracking-[0.12em] mt-2.5 text-muted-foreground">
          Demand note hui · agli baar stock mein hoga
        </p>
      )}
    </div>
  );
}
