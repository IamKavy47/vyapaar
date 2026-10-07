import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { api as trpc } from "@/lib/api";
import { Logo } from "@/components/brand";
import { clsx } from "@/lib/format";
import { CATEGORIES } from "@/lib/localmart";
import { useLocation } from "@/lib/location";

export default function Onboarding() {
  const navigate = useNavigate();
  const utils = trpc.useUtils();
  const [busy, setBusy] = useState(false);

  const createShop = trpc.profile.createShop.useMutation();
  const location = useLocation();

  const [newShop, setNewShop] = useState({ name: "", categoryKey: "kirana", address: "", phone: "" });
  const [showCreate] = useState(true);

  const create = async () => {
    if (newShop.name.trim().length < 2) {
      toast.error("Dukaan ka naam likho");
      return;
    }
    if (location.lat == null || location.lng == null) {
      toast.error("Pehle apni dukaan ki location allow karo");
      location.locate();
      return;
    }
    setBusy(true);
    try {
      const cat = CATEGORIES.find((c) => c.key === newShop.categoryKey)!;
      await createShop.mutateAsync({
        name: newShop.name.trim(),
        categoryKey: cat.key,
        categoryLabel: cat.label,
        address: newShop.address.trim() || undefined,
        phone: newShop.phone.trim() || undefined,
        lat: location.lat,
        lng: location.lng,
      });
      await utils.invalidate();
      toast.success("Dukaan ban gayi! Ab stock add karo.");
      navigate("/merchant/inventory", { replace: true });
    } catch (e: any) {
      toast.error(e?.message ?? "Could not create shop");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-dvh bg-background flex flex-col">
      <div className="bg-brand-yellow border-b-2 border-brand-ink/10 px-6 pt-10 pb-8 rounded-b-[36px]">
        <Logo />
        <h1 className="font-display text-[28px] mt-6 text-brand-ink">
          Apni dukaan ki details bharo
        </h1>
        <p className="text-[14px] font-bold text-brand-ink/70 mt-1.5">
          "Apni asli dukaan ki details bharo — yahan koi demo listing nahi hai."
        </p>
      </div>

      <div className="flex-1 px-5 py-6 w-full max-w-lg mx-auto">
        <div className="space-y-3">
            {showCreate && (
              <div className="rounded-3xl border-2 border-brand-ink bg-card p-5 space-y-3 shadow-sticker lm-pop">
                <input
                  value={newShop.name}
                  onChange={(e) => setNewShop({ ...newShop, name: e.target.value })}
                  placeholder="Dukaan ka naam"
                  className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
                />
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
                <input
                  value={newShop.address}
                  onChange={(e) => setNewShop({ ...newShop, address: e.target.value })}
                  placeholder="Address (optional)"
                  className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
                />
                <input
                  value={newShop.phone}
                  onChange={(e) => setNewShop({ ...newShop, phone: e.target.value })}
                  placeholder="Phone (optional)"
                  className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
                />
                <button
                  disabled={busy}
                  onClick={create}
                  className="w-full rounded-full border-2 border-brand-ink bg-brand-green text-brand-cream font-display text-[15px] py-3.5 shadow-sticker active:translate-y-[3px] active:shadow-none transition-all"
                >
                  Dukaan kholo →
                </button>
            </div>
            )}
        </div>
      </div>
    </div>
  );
}
