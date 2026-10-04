import { useState } from "react";
import { useNavigate } from "react-router";
import { ShoppingBag, Store, BadgeCheck, Plus } from "lucide-react";
import { toast } from "sonner";
import { api as trpc } from "@/lib/api";
import { Logo, CategoryIcon } from "@/components/brand";
import { clsx } from "@/lib/format";
import { CATEGORIES, DEMO_CENTER } from "@/lib/localmart";

type Step = "role" | "shop";

export default function Onboarding() {
  const navigate = useNavigate();
  const utils = trpc.useUtils();
  const [step, setStep] = useState<Step>("role");
  const [busy, setBusy] = useState(false);

  const claimable = trpc.profile.claimableShops.useQuery(undefined, {
    enabled: step === "shop",
  });

  const setRole = trpc.profile.setRole.useMutation();
  const claimShop = trpc.profile.claimShop.useMutation();
  const createShop = trpc.profile.createShop.useMutation();

  const [newShop, setNewShop] = useState({ name: "", categoryKey: "kirana", address: "", phone: "" });
  const [showCreate, setShowCreate] = useState(false);

  const pickCustomer = async () => {
    setBusy(true);
    try {
      await setRole.mutateAsync({ role: "customer" });
      await utils.profile.get.invalidate();
      navigate("/", { replace: true });
    } finally {
      setBusy(false);
    }
  };

  const claim = async (shopId: string) => {
    setBusy(true);
    try {
      await claimShop.mutateAsync({ shopId });
      await utils.invalidate();
      toast.success("Dukaan linked! Inbox is live.");
      navigate("/merchant", { replace: true });
    } catch (e: any) {
      toast.error(e?.message ?? "Could not claim shop");
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (newShop.name.trim().length < 2) {
      toast.error("Dukaan ka naam likho");
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
        lat: DEMO_CENTER.lat + (Math.random() - 0.5) * 0.004,
        lng: DEMO_CENTER.lng + (Math.random() - 0.5) * 0.004,
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
          {step === "role" ? "Kaun ho aap?" : "Apni dukaan chuno"}
        </h1>
        <p className="text-[14px] font-bold text-brand-ink/70 mt-1.5">
          {step === "role"
            ? "Customer ya dukaandaar — dono ka swagat hai."
            : "List mein se apni dukaan claim karo, ya nayi banao."}
        </p>
      </div>

      <div className="flex-1 px-5 py-6 w-full max-w-lg mx-auto">
        {step === "role" ? (
          <div className="grid gap-4">
            <button
              disabled={busy}
              onClick={pickCustomer}
              className="lm-pop text-left rounded-[28px] border-2 border-brand-ink bg-card p-6 shadow-sticker active:translate-y-[3px] active:shadow-none transition-all"
            >
              <span className="w-14 h-14 rounded-2xl bg-brand-yellow grid place-items-center border-2 border-brand-ink">
                <ShoppingBag className="w-7 h-7 text-brand-ink" strokeWidth={2.3} />
              </span>
              <div className="font-display text-[20px] mt-4">Main Customer hoon</div>
              <p className="text-[13.5px] font-semibold text-muted-foreground mt-1">
                Cheezein khojunga, daam compare karunga, mohalle se kharidunga.
              </p>
            </button>
            <button
              disabled={busy}
              onClick={() => setStep("shop")}
              className="lm-pop text-left rounded-[28px] border-2 border-brand-ink bg-brand-ink p-6 shadow-sticker-green active:translate-y-[3px] active:shadow-none transition-all"
              style={{ animationDelay: "0.08s" }}
            >
              <span className="w-14 h-14 rounded-2xl bg-brand-yellow grid place-items-center border-2 border-brand-ink">
                <Store className="w-7 h-7 text-brand-ink" strokeWidth={2.3} />
              </span>
              <div className="font-display text-[20px] mt-4 text-brand-cream">Main Dukaandaar hoon</div>
              <p className="text-[13.5px] font-semibold text-brand-cream/60 mt-1">
                Requests ka jawab dunga, stock aur khata sambhalunga.
              </p>
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {claimable.isLoading && <p className="text-sm font-bold text-muted-foreground">Dukaanein aa rahi hain…</p>}
            {claimable.data?.map((s, i) => (
              <button
                key={s.id}
                disabled={busy}
                onClick={() => claim(s.id)}
                className="lm-pop w-full text-left rounded-3xl border-2 border-brand-ink/15 bg-card p-4 flex items-center gap-3.5 hover:border-brand-ink transition-all active:scale-[0.99]"
                style={{ animationDelay: `${i * 0.05}s` }}
              >
                <CategoryIcon categoryKey={s.categoryKey} />
                <span className="flex-1 min-w-0">
                  <span className="flex items-center gap-1.5">
                    <span className="font-extrabold text-[15.5px] truncate">{s.name}</span>
                    {s.isVerified && <BadgeCheck className="w-4 h-4 text-brand-green shrink-0" />}
                  </span>
                  <span className="block text-[12.5px] font-semibold text-muted-foreground truncate">
                    {s.categoryLabel} · {s.address}
                  </span>
                </span>
              </button>
            ))}

            <button
              onClick={() => setShowCreate((v) => !v)}
              className="w-full rounded-3xl border-2 border-dashed border-brand-ink/30 p-4 flex items-center gap-3 font-extrabold text-[14.5px] text-brand-ink/70"
            >
              <span className="w-11 h-11 rounded-2xl bg-brand-yellow/60 grid place-items-center">
                <Plus className="w-5 h-5" strokeWidth={2.6} />
              </span>
              Meri dukaan list mein nahi hai — nayi banao
            </button>

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

            <button onClick={() => setStep("role")} className="text-[13px] font-extrabold text-muted-foreground pt-2">
              ← Wapas
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
