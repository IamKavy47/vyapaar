import { toast } from "sonner";
import {
  Package, CircleCheck, Clock, CreditCard, Banknote, Wrench,
} from "lucide-react";
import { api as trpc } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { EmptyState, Sticker } from "@/components/brand";
import { formatINR, clsx, timeAgo } from "@/lib/format";

export default function Orders() {
  const orders = trpc.merchant.orders.useQuery(undefined, { refetchInterval: 10000 });
  const markPaid = trpc.merchant.markOrderPaid.useMutation({
    onSuccess: () => {
      toast.success("Order paid mark kiya! ✅");
    },
    onError: (e) => toast.error(e.message),
  });
  const utils = trpc.useUtils();
  const invalidateOrders = () => utils.invalidate();

  const list = orders.data?.orders ?? [];
  const pendingCount = list.filter((o) => o.status === "pending").length;
  const paidCount = list.filter((o) => o.status === "paid").length;

  return (
    <div>
      <TopBar
        title="Orders"
        sub={list.length > 0 ? `${pendingCount} pending · ${paidCount} paid` : "Customer orders yahan dikhenge"}
        right={list.length > 0 && <Sticker rot={2}>{list.length} total</Sticker>}
      />

      {orders.isLoading && (
        <div className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card h-[100px] animate-pulse" />
          ))}
        </div>
      )}

      {list.length === 0 && !orders.isLoading && (
        <EmptyState
          icon={<Package className="w-7 h-7" />}
          title="Abhi koi order nahi hai"
          sub="Jab koi customer dukaan select karega aur pay karega, yahan order dikhega."
        />
      )}

      <div className="space-y-2.5">
        {list.map((o, i) => {
          const isPaid = o.status === "paid";
          const isOnline = o.paymentMethod === "online";
          return (
            <div
              key={o.id}
              className={clsx(
                "lm-pop rounded-3xl border-2 p-4 transition-all",
                isPaid
                  ? "border-brand-green/30 bg-[#00914608]"
                  : "border-brand-yellow/40 bg-[#FEE60008]",
              )}
              style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
            >
              <div className="flex items-start gap-3">
                <div className={clsx(
                  "shrink-0 w-11 h-11 rounded-2xl grid place-items-center",
                  isPaid ? "bg-brand-green/10" : "bg-brand-yellow/15",
                )}>
                  {o.isService ? (
                    <Wrench className="w-5 h-5 text-brand-ink" />
                  ) : (
                    <Package className="w-5 h-5 text-brand-ink" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-extrabold text-[14.5px] truncate">{o.product}</span>
                    <span
                      className={clsx(
                        "rounded-full px-2 py-0.5 text-[9.5px] font-extrabold uppercase tracking-wide",
                        isPaid
                          ? "bg-brand-green text-brand-cream"
                          : "bg-brand-yellow text-brand-ink",
                      )}
                    >
                      {isPaid ? (
                        <><CircleCheck className="w-2.5 h-2.5 inline mr-0.5" />Paid</>
                      ) : (
                        <><Clock className="w-2.5 h-2.5 inline mr-0.5" />Pending</>
                      )}
                    </span>
                  </div>
                  <div className="text-[11px] font-bold text-muted-foreground mt-0.5">
                    {o.customerName || "Customer"} · {o.quantity} {o.unit}
                  </div>
                  <div className="text-[10.5px] font-bold text-muted-foreground mt-0.5 flex items-center gap-2 flex-wrap">
                    <span className="inline-flex items-center gap-0.5">
                      {isOnline ? (
                        <><CreditCard className="w-3 h-3" /> Online</>
                      ) : (
                        <><Banknote className="w-3 h-3" /> Cash at shop</>
                      )}
                    </span>
                    <span>· {timeAgo(o.createdAt)}</span>
                    {o.paidAt && <span>· paid {timeAgo(o.paidAt)}</span>}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  {o.price != null ? (
                    <div className="font-display text-[18px] text-brand-ink">{formatINR(o.price)}</div>
                  ) : (
                    <div className="text-[10px] font-extrabold uppercase text-muted-foreground">No price</div>
                  )}
                </div>
              </div>

              {/* Mark paid button for pending cash orders */}
              {!isPaid && !isOnline && (
                <button
                  onClick={async () => {
                    await markPaid.mutateAsync({ orderId: o.id });
                    invalidateOrders();
                  }}
                  disabled={markPaid.isPending}
                  className="mt-3 w-full rounded-full border-2 border-brand-green bg-brand-green text-brand-cream text-[12px] font-extrabold py-2.5 flex items-center justify-center gap-1.5 disabled:opacity-50"
                >
                  <CircleCheck className="w-4 h-4" /> Mark as Paid
                </button>
              )}

              {/* Already paid — show method */}
              {isPaid && (
                <div className="mt-3 text-center text-[10.5px] font-bold text-brand-green flex items-center justify-center gap-1">
                  <CircleCheck className="w-3.5 h-3.5" />
                  {isOnline ? "Online payment received" : "Cash received at shop"}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
