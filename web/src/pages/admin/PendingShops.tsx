import { useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, X, Check, MapPin } from "lucide-react";
import { api as trpc, ApiError } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { EmptyState, Sticker } from "@/components/brand";
import { categoryMeta } from "@/lib/localmart";
import { clsx, timeAgo } from "@/lib/format";

/**
 * Admin verification UI — the "verifier" surface. The user (you, for the
 * hackathon) logs in as admin and reviews each pending shopfront photo here.
 * This is the manual step that gates shops from invisible → visible to
 * customers.
 */
export default function AdminPendingShops() {
  const shops = trpc.admin.pendingShops.useQuery(undefined, { refetchInterval: 5000 });
  const approve = trpc.admin.approveShop.useMutation({
    onSuccess: () => {
      toast.success("Shop approved — ab customer searches mein dikhega.");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Approve nahi ho paaya."),
  });
  const reject = trpc.admin.rejectShop.useMutation({
    onSuccess: () => {
      toast.success("Shop reject ho gaya — dobara photo upload kar sakte hain.");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Reject nahi ho paaya."),
  });
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const list = shops.data?.shops ?? [];

  return (
    <div>
      <TopBar
        title="Verification queue"
        sub="Shopfront photos waiting for your approval"
        right={<Sticker rot={-3} color="#7C3AED">{list.length} pending</Sticker>}
      />

      {shops.isLoading && (
        <div className="space-y-3 mt-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card h-[200px] animate-pulse" />
          ))}
        </div>
      )}

      {shops.data && list.length === 0 && (
        <div className="mt-6">
          <EmptyState
            icon={<ShieldCheck className="w-7 h-7" />}
            title="No pending shops"
            sub="Jab koi nayi dukaan photo upload karegi, yahan approve karne ko milegi."
          />
        </div>
      )}

      <div className="mt-5 space-y-4">
        {list.map((shop) => {
          const meta = categoryMeta("other");
          return (
            <div
              key={shop.id}
              className="lm-pop rounded-3xl border-2 border-brand-ink/12 bg-card p-4 overflow-hidden"
            >
              <div className="flex flex-col sm:flex-row gap-4">
                {/* Photo */}
                <div className="shrink-0">
                  {shop.shopfrontPhotoUrl ? (
                    <img
                      src={shop.shopfrontPhotoUrl}
                      alt={shop.shopName}
                      className="w-full sm:w-48 h-44 sm:h-36 rounded-2xl border-2 border-brand-ink/15 object-cover"
                    />
                  ) : (
                    <div className="w-full sm:w-48 h-44 sm:h-36 rounded-2xl border-2 border-dashed border-brand-ink/15 bg-background grid place-items-center text-[11px] font-bold text-muted-foreground">
                      No photo
                    </div>
                  )}
                </div>

                {/* Details */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-extrabold text-[16px] truncate">{shop.shopName}</span>
                    {shop.category && (
                      <span
                        className="rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wide text-brand-cream"
                        style={{ background: meta.color }}
                      >
                        {shop.category}
                      </span>
                    )}
                  </div>
                  <div className="text-[12px] font-bold text-muted-foreground mt-1">
                    📞 {shop.phone || "—"}
                  </div>
                  <div className="text-[12px] font-bold text-muted-foreground mt-0.5">
                    🏠 {shop.address || "—"}
                  </div>
                  {shop.photoUploadedAt && (
                    <div className="text-[10.5px] font-bold text-muted-foreground mt-0.5">
                      Photo uploaded {timeAgo(shop.photoUploadedAt)}
                    </div>
                  )}
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <GpsBlock
                      label="Browser GPS (capture time)"
                      loc={shop.photoBrowserLocation}
                    />
                    <GpsBlock
                      label="JPEG EXIF GPS (cross-check)"
                      loc={shop.photoExifLocation}
                    />
                  </div>
                </div>
              </div>

              {/* Verifier actions */}
              <div className="mt-4 pt-3 border-t-2 border-brand-ink/8 flex items-center gap-2 flex-wrap">
                {rejecting === shop.id ? (
                  <>
                    <input
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      placeholder="Rejection reason (e.g. 'photo location mismatch')"
                      className="min-w-0 flex-1 rounded-full border-2 border-brand-ink/15 bg-background px-3 py-2 text-[12px] font-bold outline-none"
                    />
                    <button
                      onClick={() => { setRejecting(null); setRejectReason(""); }}
                      className="rounded-full border-2 border-brand-ink/15 bg-card px-3 py-2 text-[12px] font-extrabold"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={async () => {
                        await reject.mutateAsync({ shopId: shop.id, reason: rejectReason });
                        setRejecting(null); setRejectReason("");
                      }}
                      className="rounded-full border-2 border-[#F03749] bg-[#F03749] text-brand-cream px-3 py-2 text-[12px] font-extrabold inline-flex items-center gap-1"
                    >
                      <X className="w-3.5 h-3.5" /> Confirm reject
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={async () => { await approve.mutateAsync({ shopId: shop.id }); }}
                      disabled={approve.isPending}
                      className="rounded-full border-2 border-brand-green bg-brand-green text-brand-cream px-4 py-2 text-[12px] font-extrabold inline-flex items-center gap-1.5 disabled:opacity-50"
                    >
                      <Check className="w-4 h-4" /> Approve & make visible
                    </button>
                    <button
                      onClick={() => setRejecting(shop.id)}
                      className="rounded-full border-2 border-[#F03749]/40 bg-card text-[#F03749] px-4 py-2 text-[12px] font-extrabold inline-flex items-center gap-1.5"
                    >
                      <X className="w-4 h-4" /> Reject
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-6 text-[11px] font-bold text-muted-foreground text-center">
        Verified tab tak sirf is page se shops jaate hain. Approve karne ke baad
        woh customer searches aur Browse mein turant dikhega.
      </p>
    </div>
  );
}

function GpsBlock({
  label, loc,
}: {
  label: string;
  loc?: { lat: number; lng: number } | null;
}) {
  return (
    <div className={clsx(
      "rounded-xl p-2",
      loc ? "bg-brand-green/10" : "bg-brand-ink/8",
    )}>
      <div className="text-[9.5px] font-extrabold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      {loc ? (
        <a
          href={`https://www.google.com/maps?q=${loc.lat},${loc.lng}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-[11.5px] font-bold text-brand-green mt-1"
        >
          <MapPin className="w-3 h-3" />
          {loc.lat.toFixed(4)}, {loc.lng.toFixed(4)} →
        </a>
      ) : (
        <div className="text-[11.5px] font-bold text-muted-foreground mt-1">Not available</div>
      )}
    </div>
  );
}
