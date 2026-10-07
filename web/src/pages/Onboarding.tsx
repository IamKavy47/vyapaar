import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { Store, ShoppingBag, Wrench } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { Logo } from "@/components/brand";
import { clsx } from "@/lib/format";
import { CATEGORIES } from "@/lib/localmart";
import { useLocation } from "@/lib/location";

type ShopType = "shop" | "vendor" | "service";

const SHOP_TYPES: { key: ShopType; label: string; hindi: string; desc: string; icon: typeof Store }[] = [
  { key: "shop", label: "Dukaan", hindi: "दुकान", desc: "Fixed shop with products — kirana, hardware, medical, etc.", icon: Store },
  { key: "vendor", label: "Thela", hindi: "ठेला", desc: "Street vendor — mobile cart, fruits, vegetables, snacks.", icon: ShoppingBag },
  { key: "service", label: "Seva", hindi: "सेवा", desc: "Service provider — plumber, electrician, tailor, repair.", icon: Wrench },
];

const SERVICE_LINES = [
  { key: "plumber", label: "Plumber" },
  { key: "electrician", label: "Electrician" },
  { key: "tailor", label: "Tailor" },
  { key: "carpenter", label: "Carpenter" },
  { key: "painter", label: "Painter" },
  { key: "appliance_repair", label: "Appliance Repair" },
  { key: "mobile_repair", label: "Mobile Repair" },
  { key: "beautician", label: "Beautician" },
  { key: "tutor", label: "Tutor" },
  { key: "other_service", label: "Other Service" },
];

export default function Onboarding() {
  const navigate = useNavigate();
  const utils = trpc.useUtils();
  const [busy, setBusy] = useState(false);

  const createShop = trpc.profile.createShop.useMutation();
  const location = useLocation();

  const [shopType, setShopType] = useState<ShopType>("shop");
  const [newShop, setNewShop] = useState({
    name: "", categoryKey: "kirana", address: "", phone: "",
    serviceLine: "plumber",
  });

  const create = async () => {
    if (newShop.name.trim().length < 2) {
      toast.error(shopType === "service" ? "Apna naam ya service ka naam likho" : "Dukaan ka naam likho");
      return;
    }
    if (location.lat == null || location.lng == null) {
      toast.error(shopType === "service" ? "Apna service area allow karo" : "Pehle apni dukaan ki location allow karo");
      location.locate();
      return;
    }
    setBusy(true);
    try {
      const cat = CATEGORIES.find((c) => c.key === newShop.categoryKey) ?? CATEGORIES[0];
      await createShop.mutateAsync({
        name: newShop.name.trim(),
        categoryKey: cat.key,
        categoryLabel: cat.label,
        address: newShop.address.trim() || undefined,
        phone: newShop.phone.trim() || undefined,
        lat: location.lat,
        lng: location.lng,
        shopType,
        serviceLine: shopType === "service" ? newShop.serviceLine : undefined,
      });
      await utils.invalidate();
      toast.success(
        shopType === "service" ? "Service profile ban gaya! Ab requests aayengi."
        : shopType === "vendor" ? "Thela ready! Customers ko turant dikhega."
        : "Dukaan ban gayi! Ab stock add karo.",
      );
      navigate(shopType === "service" ? "/merchant" : "/merchant/inventory", { replace: true });
    } catch (e: any) {
      toast.error(e?.message ?? "Could not create profile");
    } finally {
      setBusy(false);
    }
  };

  const heading = shopType === "service" ? "Apna service details bharo"
    : shopType === "vendor" ? "Apna thela details bharo"
    : "Apni dukaan ki details bharo";

  return (
    <div className="min-h-dvh bg-background flex flex-col">
      <div className="bg-brand-yellow border-b-2 border-brand-ink/10 px-6 pt-10 pb-8 rounded-b-[36px]">
        <Logo />
        <h1 className="font-display text-[26px] mt-6 text-brand-ink">
          {heading}
        </h1>
        <p className="text-[13.5px] font-bold text-brand-ink/70 mt-1.5">
          Pehle batayen aap kya hain — dukaan, thela, ya seva.
        </p>
      </div>

      <div className="flex-1 px-5 py-6 w-full max-w-lg mx-auto">
        {/* Shop type selector */}
        <div className="grid grid-cols-3 gap-2.5 mb-5">
          {SHOP_TYPES.map((t) => (
            <button
              key={t.key}
              onClick={() => setShopType(t.key)}
              className={clsx(
                "rounded-2xl border-2 p-3 text-center transition-all",
                shopType === t.key
                  ? "bg-brand-ink text-brand-yellow border-brand-ink shadow-sticker-sm"
                  : "bg-card border-brand-ink/12 text-brand-ink/70",
              )}
            >
              <t.icon className={clsx("w-6 h-6 mx-auto", shopType === t.key ? "text-brand-yellow" : "text-brand-ink/40")} />
              <div className="font-extrabold text-[12.5px] mt-1.5">{t.label}</div>
              <div className="text-[9px] font-bold opacity-60">{t.hindi}</div>
            </button>
          ))}
        </div>

        <div className="rounded-3xl border-2 border-brand-ink bg-card p-5 space-y-3 shadow-sticker lm-pop">
          {/* Name field — label changes per type */}
          <input
            value={newShop.name}
            onChange={(e) => setNewShop({ ...newShop, name: e.target.value })}
            placeholder={shopType === "service" ? "Naam / service ka naam (e.g. Ramesh Plumber)" : shopType === "vendor" ? "Thela ka naam (e.g. Sharma Fruit Cart)" : "Dukaan ka naam"}
            className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
          />

          {/* Service line selector (only for service type) */}
          {shopType === "service" && (
            <div>
              <div className="text-[10.5px] font-extrabold uppercase tracking-wide text-brand-ink/55 mb-1.5">
                Aap ki seva?
              </div>
              <div className="flex flex-wrap gap-2">
                {SERVICE_LINES.map((s) => (
                  <button
                    key={s.key}
                    onClick={() => setNewShop({ ...newShop, serviceLine: s.key })}
                    className={clsx(
                      "rounded-full px-3 py-1.5 text-[11.5px] font-extrabold border-2 transition-all",
                      newShop.serviceLine === s.key
                        ? "bg-brand-ink text-brand-yellow border-brand-ink"
                        : "border-brand-ink/15 bg-background text-brand-ink/70",
                    )}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Category selector (hidden for services — service_line is the category) */}
          {shopType !== "service" && (
            <div>
              <div className="text-[10.5px] font-extrabold uppercase tracking-wide text-brand-ink/55 mb-1.5">
                Category
              </div>
              <div className="flex flex-wrap gap-2">
                {CATEGORIES.slice(0, 9).map((c) => (
                  <button
                    key={c.key}
                    onClick={() => setNewShop({ ...newShop, categoryKey: c.key })}
                    className={clsx(
                      "rounded-full px-3.5 py-2 text-[12.5px] font-extrabold border-2 transition-all",
                      newShop.categoryKey === c.key
                        ? "bg-brand-ink text-brand-yellow border-brand-ink"
                        : "border-brand-ink/15 bg-background text-brand-ink/70",
                    )}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <input
            value={newShop.address}
            onChange={(e) => setNewShop({ ...newShop, address: e.target.value })}
            placeholder={shopType === "service" ? "Service area / address (optional)" : shopType === "vendor" ? "Typical pitch area (optional)" : "Address (optional)"}
            className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
          />
          <input
            value={newShop.phone}
            onChange={(e) => setNewShop({ ...newShop, phone: e.target.value })}
            placeholder="Phone (optional — customers can call)"
            className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
          />

          <div className="text-[10.5px] font-bold text-brand-ink/45 text-center">
            {shopType === "service" && "Service providers ko bhi phone OTP + verification chahiye — same safety bar as shops."}
            {shopType === "vendor" && "Thela photo (GPS-tagged) baad mein upload karein — Account page se."}
            {shopType === "shop" && "Shopfront photo (GPS-tagged) baad mein upload karein — Account page se."}
          </div>

          <button
            disabled={busy}
            onClick={create}
            className="w-full rounded-full border-2 border-brand-ink bg-brand-green text-brand-cream font-display text-[15px] py-3.5 shadow-sticker active:translate-y-[3px] active:shadow-none transition-all disabled:opacity-60"
          >
            {busy ? "Ban raha hai…" : shopType === "service" ? "Service shuru karo →" : shopType === "vendor" ? "Thela kholo →" : "Dukaan kholo →"}
          </button>
        </div>
      </div>
    </div>
  );
}
