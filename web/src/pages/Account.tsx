import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { LogOut, Store, ShoppingBag, Repeat, ChevronRight, BadgeCheck, Send } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { api as trpc, ApiError } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { CategoryIcon } from "@/components/brand";

export default function Account() {
  const { user, logout, refresh } = useAuth();
  const navigate = useNavigate();
  const utils = trpc.useUtils();
  const profile = trpc.profile.get.useQuery();
  const setRole = trpc.profile.setRole.useMutation();
  const telegramLink = trpc.auth.telegramLink.useMutation();
  const [tgBusy, setTgBusy] = useState(false);

  const connectTelegram = async () => {
    setTgBusy(true);
    try {
      const res = await telegramLink.mutateAsync();
      if (res.linked) {
        toast.success("Telegram pehle se connected hai ✅");
      } else if (res.url) {
        window.open(res.url, "_blank", "noopener");
        toast.success("Telegram kholo aur Start dabao — account link ho jayega.");
      }
      await refresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Telegram link nahi ban paya");
    } finally {
      setTgBusy(false);
    }
  };

  const role = profile.data?.appRole ?? "customer";
  const shop = profile.data?.shop;

  const switchRole = async () => {
    const next = role === "customer" ? "shopkeeper" : "customer";
    if (next === "shopkeeper" && !shop) {
      navigate("/onboarding");
      return;
    }
    await setRole.mutateAsync({ role: next });
    await utils.invalidate();
    toast.success(next === "shopkeeper" ? "Dukaandaar mode on" : "Customer mode on");
    navigate(next === "shopkeeper" ? "/merchant" : "/");
  };

  return (
    <div>
      <TopBar title="You" sub="Account aur settings" />

      {/* profile card */}
      <section className="rounded-[28px] border-2 border-brand-ink bg-brand-yellow p-5 shadow-sticker relative overflow-hidden">
        <div className="absolute -bottom-8 -right-8 w-32 h-32 rounded-full bg-brand-cream/40" />
        <div className="flex items-center gap-4 relative">
          <span className="w-16 h-16 rounded-[24px] border-2 border-brand-ink bg-brand-ink text-brand-yellow grid place-items-center font-display text-[24px]">
            {(user?.full_name ?? "L")[0].toUpperCase()}
          </span>
          <div className="min-w-0">
            <div className="font-display text-[20px] leading-tight truncate">{user?.full_name ?? "LocalMart User"}</div>
            <div className="text-[12.5px] font-bold text-brand-ink/60 truncate mt-0.5">{user?.email ?? ""}</div>
            <span className="inline-flex items-center gap-1.5 rounded-full border-2 border-brand-ink bg-brand-cream px-2.5 py-0.5 text-[10.5px] font-extrabold uppercase tracking-wide mt-2">
              {role === "shopkeeper" ? <Store className="w-3 h-3" /> : <ShoppingBag className="w-3 h-3" />}
              {role === "shopkeeper" ? "Dukaandaar" : "Customer"}
            </span>
          </div>
        </div>
      </section>

      {/* my shop */}
      {role === "shopkeeper" && shop && (
        <button
          onClick={() => navigate("/merchant")}
          className="mt-4 w-full text-left rounded-[28px] border-2 border-brand-ink/12 bg-card p-4 flex items-center gap-3.5 hover:border-brand-ink/40 transition-all"
        >
          <CategoryIcon categoryKey={shop.categoryKey} size={48} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-extrabold text-[15.5px] truncate">{shop.name}</span>
              {shop.isVerified && <BadgeCheck className="w-4 h-4 text-brand-green" />}
            </div>
            <div className="text-[12px] font-bold text-muted-foreground mt-0.5 truncate">{shop.address}</div>
          </div>
          <ChevronRight className="w-5 h-5 text-brand-ink/30" />
        </button>
      )}

      {/* actions */}
      <section className="mt-5 rounded-[28px] border-2 border-brand-ink/12 bg-card overflow-hidden divide-y-2 divide-brand-ink/5">
        <button
          onClick={switchRole}
          className="w-full flex items-center gap-3.5 px-5 py-4 text-left hover:bg-brand-yellow/20 transition-colors"
        >
          <span className="w-10 h-10 rounded-2xl bg-brand-yellow/60 grid place-items-center">
            <Repeat className="w-5 h-5 text-brand-ink" />
          </span>
          <span className="flex-1">
            <span className="block font-extrabold text-[14.5px]">
              {role === "customer" ? "Dukaandaar mode" : "Customer mode"}
            </span>
            <span className="block text-[12px] font-semibold text-muted-foreground">
              {role === "customer" ? "Apni dukaan sambhalo" : "Kharidari pe wapas"}
            </span>
          </span>
          <ChevronRight className="w-5 h-5 text-brand-ink/30" />
        </button>
        <button
          onClick={connectTelegram}
          disabled={tgBusy}
          className="w-full flex items-center gap-3.5 px-5 py-4 text-left hover:bg-brand-yellow/20 transition-colors disabled:opacity-60"
        >
          <span className="w-10 h-10 rounded-2xl bg-[#2BA0FF1f] grid place-items-center">
            <Send className="w-5 h-5 text-[#2BA0FF]" />
          </span>
          <span className="flex-1">
            <span className="block font-extrabold text-[14.5px]">
              {user?.telegram_user_id ? "Telegram connected ✅" : "Connect Telegram"}
            </span>
            <span className="block text-[12px] font-semibold text-muted-foreground">
              {user?.telegram_user_id
                ? "Requests aur jawab Telegram par bhi milenge"
                : "Bot par notifications paao — ek tap link"}
            </span>
          </span>
          <ChevronRight className="w-5 h-5 text-brand-ink/30" />
        </button>
        <button
          onClick={() => logout()}
          className="w-full flex items-center gap-3.5 px-5 py-4 text-left hover:bg-[#F037490d] transition-colors"
        >
          <span className="w-10 h-10 rounded-2xl bg-[#F037491a] grid place-items-center">
            <LogOut className="w-5 h-5 text-[#F03749]" />
          </span>
          <span className="flex-1 font-extrabold text-[14.5px] text-[#F03749]">Log out</span>
        </button>
      </section>

      <p className="text-center text-[11.5px] font-bold text-muted-foreground mt-8">
        LocalMart · Mohalle ka apna bazaar · Mandsaur
      </p>
    </div>
  );
}
