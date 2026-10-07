import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Camera, ShieldCheck, MapPin, RefreshCw } from "lucide-react";
import { api as trpc, ApiError } from "@/lib/api";
import { useLocation } from "@/lib/location";
import { clsx } from "@/lib/format";

interface ShopfrontPhotoCaptureProps {
  shopId: string;
  currentPhotoUrl?: string | null;
  verificationStatus?: string;
  onUploaded?: () => void;
}

/**
 * In-PWA shopfront photo capture — uses <input capture="environment"> so the
 * phone opens the rear camera directly. At the same moment the browser
 * records its current GPS via navigator.geolocation. The photo + browser GPS
 * are uploaded together; the server cross-checks the JPEG's EXIF GPS as a
 * second signal. Both must be within ~200m of the registered shop location.
 */
export function ShopfrontPhotoCapture({
  currentPhotoUrl, verificationStatus, onUploaded,
}: ShopfrontPhotoCaptureProps) {
  const location = useLocation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [capturing, setCapturing] = useState(false);
  const [browserLoc, setBrowserLoc] = useState<{ lat: number; lng: number } | null>(
    location.lat != null && location.lng != null ? { lat: location.lat, lng: location.lng } : null,
  );
  const [preview, setPreview] = useState<string | null>(currentPhotoUrl ?? null);

  useEffect(() => {
    setPreview(currentPhotoUrl ?? null);
  }, [currentPhotoUrl]);

  const upload = trpc.merchant.uploadShopfrontPhoto.useMutation({
    onSuccess: (data) => {
      setPreview(data.shopfrontPhotoUrl);
      toast.success(
        verificationStatus === "verified"
          ? "Photo updated — admin ko dobara approve karna padega."
          : "Photo uploaded — admin approval ka wait karein. Customer turant nahi dikhega.",
      );
      onUploaded?.();
    },
    onError: (e) => {
      toast.error(e instanceof ApiError ? e.message : "Upload nahi ho paaya.");
    },
  });

  const onFile = async (file: File) => {
    if (!file.type.startsWith("image/")) {
      toast.error("Sirf image file upload karein.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error("Photo 5 MB se chhoti honi chahiye.");
      return;
    }
    setCapturing(true);
    try {
      // Capture current browser GPS at the moment of upload.
      let loc = browserLoc;
      if (!loc) {
        try {
          const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
              enableHighAccuracy: true, timeout: 8000, maximumAge: 30000,
            });
          });
          loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
          setBrowserLoc(loc);
        } catch {
          toast.error("Location permission do — photo ka GPS verify karne ke liye.");
          return;
        }
      }
      await upload.mutateAsync({ file, browserLat: loc.lat, browserLng: loc.lng });
    } finally {
      setCapturing(false);
    }
  };

  const captureNow = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="rounded-3xl border-2 border-brand-ink/12 bg-card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Camera className="w-5 h-5 text-brand-green" />
        <div className="flex-1">
          <div className="font-extrabold text-[14.5px]">Shopfront photo</div>
          <div className="text-[10.5px] font-bold text-muted-foreground">
            Dukaan ke bahar se photo lein — yeh customer ko dikhegi aur verification ka hissa hai.
          </div>
        </div>
        {verificationStatus && (
          <StatusBadge status={verificationStatus} />
        )}
      </div>

      {/* Preview / capture target */}
      <div className="flex items-center gap-3">
        <div className="shrink-0">
          {preview ? (
            <img
              src={preview}
              alt="Shopfront"
              className="w-32 h-32 rounded-2xl border-2 border-brand-ink/15 object-cover"
            />
          ) : (
            <button
              type="button"
              onClick={captureNow}
              className="w-32 h-32 rounded-2xl border-2 border-dashed border-brand-ink/20 bg-background grid place-items-center text-[10.5px] font-bold text-muted-foreground text-center p-2 hover:border-brand-green hover:text-brand-green transition-colors"
            >
              <Camera className="w-7 h-7 mb-1" />
              Tap to capture
            </button>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-[11px] font-bold text-brand-green">
            <ShieldCheck className="w-3.5 h-3.5" /> Geo-tagged verification
          </div>
          <p className="text-[11px] font-bold text-muted-foreground mt-1 leading-relaxed">
            Browser location aur JPEG EXIF GPS dono check hote hain — dukaan ke
            registered location ke 200m ke andar hona chahiye. Scammers ke liye
            yeh todna mushkil hai.
          </p>
          {browserLoc && (
            <div className="text-[10.5px] font-bold text-muted-foreground mt-1 flex items-center gap-1">
              <MapPin className="w-3 h-3" />
              Current location: {browserLoc.lat.toFixed(4)}, {browserLoc.lng.toFixed(4)}
            </div>
          )}
          <button
            type="button"
            onClick={captureNow}
            disabled={capturing || upload.isPending}
            className="mt-2 rounded-full border-2 border-brand-ink bg-brand-ink text-brand-yellow text-[11.5px] font-extrabold py-2 px-3 inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            {capturing || upload.isPending ? (
              <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Uploading…</>
            ) : preview ? (
              <><Camera className="w-3.5 h-3.5" /> Retake photo</>
            ) : (
              <><Camera className="w-3.5 h-3.5" /> Capture photo</>
            )}
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void onFile(file);
          e.target.value = "";  // allow re-capture of the same file
        }}
      />
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; color: string }> = {
    pending: { label: "No photo", color: "bg-brand-ink/8 text-brand-ink/55" },
    photo_pending: { label: "Awaiting approval", color: "bg-brand-yellow/30 text-[#8A5A00]" },
    verified: { label: "Verified", color: "bg-brand-green/15 text-brand-green" },
    rejected: { label: "Rejected", color: "bg-[#F03749]/15 text-[#F03749]" },
  };
  const c = config[status] || config.pending;
  return (
    <span className={clsx(
      "rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wide",
      c.color,
    )}>
      {c.label}
    </span>
  );
}
