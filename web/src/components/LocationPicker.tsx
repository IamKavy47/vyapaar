import { MapPin, LocateFixed } from "lucide-react";
import { toast } from "sonner";
import { useLocation } from "@/lib/location";
import { LocationMapPicker } from "@/components/LocationMapPicker";

export function LocationPicker({
  shopMode = false,
  onSave,
}: { shopMode?: boolean; onSave?: (lat: number, lng: number) => Promise<void> }) {
  const location = useLocation();
  const save = () => {
    if (location.lat == null || location.lng == null) {
      toast.error("Map par apni location select karo");
      return;
    }
    if (onSave) {
      void onSave(location.lat, location.lng).catch((error: unknown) => {
        toast.error(error instanceof Error ? error.message : "Location save nahi hui");
      });
      return;
    }
    toast.success("Current location save ho gayi");
  };

  const useGps = async () => {
    const coordinates = await location.locate();
    if (!coordinates) {
      toast.error(
        navigator.geolocation
          ? "Location permission allow karo, aur browser me HTTPS use karo"
          : "Is browser/device par location available nahi hai",
      );
      return;
    }
    if (onSave) {
      try {
        await onSave(coordinates.lat, coordinates.lng);
      } catch {
        // The save handler displays the API error to the user.
      }
    }
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
            Search karo, map par pin lagao, ya GPS use karo.
          </p>
        </div>
      </div>
      <LocationMapPicker />
      <div className="flex gap-2 mt-3">
        <button onClick={useGps} disabled={location.locating} className="flex-1 rounded-full border-2 border-brand-ink bg-background py-2.5 text-xs font-extrabold disabled:opacity-60">
          <LocateFixed className="inline w-4 h-4 mr-1" /> {location.locating ? "Location mil rahi…" : "Fetch location automatically"}
        </button>
        <button onClick={save} className="flex-1 rounded-full border-2 border-brand-green bg-brand-green text-brand-cream py-2.5 text-xs font-extrabold">
          Save location
        </button>
      </div>
      {location.lat != null && location.lng != null && (
        <div className="mt-3 text-center text-xs font-bold text-brand-green">
          {location.label} · {location.lat.toFixed(5)}, {location.lng.toFixed(5)}
          <a className="block underline"
          href={`https://www.openstreetmap.org/?mlat=${location.lat}&mlon=${location.lng}#map=17/${location.lat}/${location.lng}`}
          target="_blank" rel="noreferrer">
            Map par current point dekho
          </a>
        </div>
      )}
    </section>
  );
}
