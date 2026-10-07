import { useState } from "react";
import { toast } from "sonner";
import { Inbox as InboxIcon, PackageCheck, PackageX } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { CategoryIcon, EmptyState } from "@/components/brand";
import { formatDistance, formatINR, timeAgo } from "@/lib/format";

export default function Inbox() {
  const utils = trpc.useUtils();
  const shop = trpc.merchant.myShop.useQuery();
  const inbox = trpc.merchant.inbox.useQuery(undefined, { refetchInterval: 5000 });
  const respond = trpc.merchant.respond.useMutation({
    onSuccess: (_, v) => {
      toast.success(v.accept ? "YES bhej diya!" : "Decline kar diya.");
      utils.merchant.inbox.invalidate();
    },
    onError: (e) => toast.error(e.message),
  });

  const [prices, setPrices] = useState<Record<string, string>>({});

  return (
    <div>
      <TopBar
        title="Requests Inbox"
        sub={shop.data ? `${shop.data.name} · live` : "Dukaan"}
        right={
          inbox.data && inbox.data.length > 0 ? (
            <span className="rounded-full border-2 border-brand-ink bg-brand-yellow px-3 py-1.5 font-display text-[12px] shadow-sticker-sm">
              {inbox.data.length} nayi
            </span>
          ) : undefined
        }
      />

      {inbox.isLoading && (
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <div key={i} className="rounded-[28px] border-2 border-brand-ink/10 bg-card h-36 animate-pulse" />
          ))}
        </div>
      )}

      {inbox.data?.length === 0 && (
        <EmptyState
          icon={<InboxIcon className="w-7 h-7" />}
          title="Abhi sab shaant hai"
          sub="Customer ki request aate hi yahan bajegi. Page khula rakho."
        />
      )}

      <div className="space-y-3.5">
        {inbox.data?.map((o, i) => (
          <div
            key={o.id}
            className="lm-pop rounded-[28px] border-2 border-brand-ink bg-card p-5 shadow-sticker"
            style={{ animationDelay: `${Math.min(i, 6) * 0.06}s` }}
          >
            <div className="flex items-start gap-3.5">
              <CategoryIcon categoryKey={o.request.categoryKey} size={48} />
              <div className="flex-1 min-w-0">
                <div className="font-display text-[17px] leading-tight">{o.request.product}</div>
                <div className="text-[12px] font-bold text-muted-foreground mt-1">
                  {o.request.quantity} {o.request.unit} · {formatDistance(o.distanceMeters)} door · {timeAgo(o.createdAt)}
                </div>
                {o.request.rawText && o.request.rawText !== o.request.product && (
                  <p className="text-[12.5px] font-semibold text-brand-ink/60 mt-1.5 italic">
                    “{o.request.rawText}”
                  </p>
                )}
              </div>
              <span className="shrink-0 rounded-full bg-brand-ink/5 px-2.5 py-1 text-[10.5px] font-extrabold text-brand-ink/60">
                {Math.round(o.matchScore * 100)}% match
              </span>
            </div>

            <div className="mt-4 flex items-center gap-2.5">
              <div className="flex items-center rounded-full border-2 border-brand-ink/15 bg-background px-3.5 flex-1 min-w-0">
                <span className="font-display text-[15px] text-brand-ink/50">₹</span>
                <input
                  value={prices[o.id] ?? (o.price != null ? String(o.price) : "")}
                  onChange={(e) => setPrices((p) => ({ ...p, [o.id]: e.target.value.replace(/[^0-9]/g, "") }))}
                  placeholder="Daam"
                  inputMode="numeric"
                  className="w-full bg-transparent px-2 py-3 text-[15px] font-extrabold outline-none placeholder:text-brand-ink/30"
                />
              </div>
              <button
                disabled={respond.isPending}
                onClick={() =>
                  respond.mutate({
                    offerId: o.id,
                    accept: true,
                    price: prices[o.id] ? Number(prices[o.id]) : undefined,
                  })
                }
                className="h-12 rounded-full border-2 border-brand-ink bg-brand-green text-brand-cream px-5 font-extrabold text-[13.5px] flex items-center gap-1.5 shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all disabled:opacity-50"
              >
                <PackageCheck className="w-4.5 h-4.5 w-5 h-5" /> Hai
              </button>
              <button
                disabled={respond.isPending}
                onClick={() => respond.mutate({ offerId: o.id, accept: false })}
                className="h-12 w-12 rounded-full border-2 border-brand-ink/20 bg-card grid place-items-center text-[#F03749] active:scale-95 transition-all disabled:opacity-50"
                aria-label="Nahi hai"
              >
                <PackageX className="w-5 h-5" />
              </button>
            </div>
            {o.hasInventoryHint && o.price != null && (
              <p className="text-[11px] font-bold text-brand-green mt-2.5">
                Stock mein hai · listed daam {formatINR(o.price)} pehle se bhara hai
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
