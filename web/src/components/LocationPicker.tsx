import { useState } from "react";
import { MapPin, LocateFixed } from "lucide-react";
import { toast } from "sonner";
import { useLocation } from "@/lib/location";

export function LocationPicker({
  shopMode = false,
  onSave,
}: { shopMode?: boolean; onSave?: (lat: number, lng: number) => Promise<void> }) {
  const location = useLocation();
  const [lat, setLat] = useState(location.lat == null ? "" : String(location.lat));
  const [lng, setLng] = useState(location.lng == null ? "" : String(location.lng));

  const save = () => {
    const nextLat = Number(lat);
    const nextLng = Number(lng);
    if (!Number.isFinite(nextLat) || nextLat < -90 || nextLat > 90 ||
        !Number.isFinite(nextLng) || nextLng < -180 || nextLng > 180) {
      toast.error("Valid latitude aur longitude daalo");
      return;
    }
    if (onSave) {
      void onSave(nextLat, nextLng).catch((error: unknown) => {
        toast.error(error instanceof Error ? error.message : "Location save nahi hui");
      });
      return;
    }
    location.setManual(nextLat, nextLng);
    toast.success("Current location save ho gayi");
  };

  const useGps = () => {
    location.locate();
    toast("Location permission allow karo");
  };

  return (
    <section className="mt-5 rounded-[28px] border-2 border-brand-ink/12 bg-card p-5">
      <div className="flex items-center gap-3">
        <span className="w-10 h-10 rounded-2xl bg-brand-yellow/60 grid place-items-center">
          <MapPin className="w-5 h-5" />
        </span>
        <div>
          <h2 className="font-display text-[17px]">{shopMode ? "Dukaan ki location" : "Aapki current location"}</h2>
          <p className="text-[11.5px] font-semibold text-muted-foreground">
            GPS use karo ya map se mile coordinates yahan paste karo.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2.5 mt-4">
        <input value={lat} onChange={(e) => setLat(e.target.value)} placeholder="Latitude"
          inputMode="decimal" className="rounded-2xl border-2 border-brand-ink/15 bg-background px-3 py-3 font-bold text-sm outline-none focus:border-brand-green" />
        <input value={lng} onChange={(e) => setLng(e.target.value)} placeholder="Longitude"
          inputMode="decimal" className="rounded-2xl border-2 border-brand-ink/15 bg-background px-3 py-3 font-bold text-sm outline-none focus:border-brand-green" />
      </div>
      <div className="flex gap-2 mt-3">
        <button onClick={useGps} className="flex-1 rounded-full border-2 border-brand-ink bg-background py-2.5 text-xs font-extrabold">
          <LocateFixed className="inline w-4 h-4 mr-1" /> GPS location
        </button>
        <button onClick={save} className="flex-1 rounded-full border-2 border-brand-green bg-brand-green text-brand-cream py-2.5 text-xs font-extrabold">
          Save location
        </button>
      </div>
      {location.lat != null && location.lng != null && (
        <a className="block mt-3 text-center text-xs font-bold text-brand-green underline"
          href={`https://www.openstreetmap.org/?mlat=${location.lat}&mlon=${location.lng}#map=17/${location.lat}/${location.lng}`}
          target="_blank" rel="noreferrer">
          Map par current point dekho
        </a>
      )}
    </section>
  );
}
