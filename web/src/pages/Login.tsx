import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { ShoppingBasket, Mic, Zap, MapPin, Eye, EyeOff, Store, ShoppingBag, Phone, ShieldCheck, Wrench } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/hooks/useAuth";
import { api, ApiError } from "@/lib/api";
import { Sticker } from "@/components/brand";
import { clsx } from "@/lib/format";

const PERKS = [
  { icon: Mic, text: "Bolo ya likho — AI samajh jaata hai" },
  { icon: MapPin, text: "Paas ki dukaanein, real jawab" },
  { icon: Zap, text: "Daam compare karo, phir chuno" },
];

type Mode = "login" | "register";

export default function Login() {
  const { isAuthenticated, isLoading, refresh } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>("login");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  // UI role: customer | shopkeeper | professional
  // Backend role: customer | shopkeeper (professional maps to shopkeeper + shop_type=service)
  const [role, setRole] = useState<"customer" | "shopkeeper" | "professional">("customer");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const login = api.auth.login.useMutation();
  const register = api.auth.register.useMutation();
  const sendOtp = api.auth.sendOtp.useMutation({
    onSuccess: (data) => {
      setOtpSent(true);
      if (data.dev_otp) {
        // Stub mode (hackathon convenience) — paste the OTP from the network response.
        toast(`OTP sent (stub mode): ${data.dev_otp}`, { duration: 8000 });
      } else {
        toast.success("OTP SMS bhej diya. Code dakhil karein.");
      }
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "OTP bhej nahi paaye."),
  });

  useEffect(() => {
    if (!isLoading && isAuthenticated) navigate("/", { replace: true });
  }, [isLoading, isAuthenticated, navigate]);

  const sendOtpNow = async () => {
    if (phone.trim().length < 10) {
      toast.error("Pehle valid phone number likho");
      return;
    }
    try {
      await sendOtp.mutateAsync({ phone: phone.trim() });
    } catch {
      /* onError handles the toast */
    }
  };

  const submit = async () => {
    if (busy) return;
    if (!email.trim() || !password) {
      toast.error("Email aur password bharo");
      return;
    }
    if (mode === "register" && fullName.trim().length < 2) {
      toast.error("Apna naam likho");
      return;
    }
    if (mode === "register" && phone.trim().length < 10) {
      toast.error("Valid phone number bharo");
      return;
    }
    if (mode === "register" && password.length < 8) {
      toast.error("Password kam se kam 8 characters ka ho");
      return;
    }
    if (mode === "register" && otp.trim().length < 4) {
      toast.error("OTP code dakhil karein (Send OTP button se code milega).");
      return;
    }
    setBusy(true);
    try {
      if (mode === "login") {
        await login.mutateAsync({ email: email.trim(), password });
      } else {
        // "professional" is a UI-only role — backend stores it as
        // "shopkeeper" (the Onboarding page then sets shop_type=service).
        const backendRole = role === "professional" ? "shopkeeper" : role;
        await register.mutateAsync({
          fullName: fullName.trim(),
          email: email.trim(),
          phone: phone.trim(),
          password,
          role: backendRole as "customer" | "shopkeeper",
          otp: otp.trim(),
        });
      }
      await refresh();
      toast.success(mode === "login" ? "Namaste! Wapas aa gaye." : "Account ban gaya! Phone verified ✓");
      // Pass the professional hint to the Onboarding page so it pre-selects
      // the right shop type without the user having to pick again.
      const onboardingType = role === "professional" ? "?type=professional"
        : role === "shopkeeper" ? "?type=shop" : "";
      navigate(onboardingType ? `/onboarding${onboardingType}` : "/", { replace: true });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Kuch gadbad ho gayi — phir try karo.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-dvh bg-brand-yellow relative overflow-hidden flex flex-col">
      {/* scattered stickers */}
      <div className="absolute top-[8%] right-[6%] lm-float" style={{ "--sticker-rot": "6deg" } as React.CSSProperties}>
        <Sticker color="#FFFCF5" rot={6}>10 min mein</Sticker>
      </div>
      <div className="absolute top-[34%] left-[4%] lm-float hidden sm:block" style={{ "--sticker-rot": "-8deg", animationDelay: "0.8s" } as React.CSSProperties}>
        <Sticker color="#FF705D" rot={-8}>fresh stock</Sticker>
      </div>
      <div className="absolute bottom-[30%] right-[8%] lm-float hidden sm:block" style={{ "--sticker-rot": "4deg", animationDelay: "1.6s" } as React.CSSProperties}>
        <Sticker color="#8ED462" rot={4}>mohalla first</Sticker>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-6 text-center py-10">
        <div className="lm-pop">
          <span className="inline-flex items-center justify-center w-24 h-24 rounded-[30%] bg-brand-green text-brand-cream border-[3px] border-brand-ink shadow-sticker rotate-[-4deg]">
            <ShoppingBasket className="w-12 h-12" strokeWidth={2.2} />
          </span>
        </div>
        <h1 className="font-display text-[44px] sm:text-[56px] leading-[1.02] mt-7 text-brand-ink lm-pop" style={{ animationDelay: "0.08s" }}>
          Local<span className="text-brand-green">Mart</span>
        </h1>
        <p className="mt-3 text-[16px] sm:text-[17px] font-bold text-brand-ink/75 max-w-sm text-balance lm-pop" style={{ animationDelay: "0.16s" }}>
          Bolo ya likho — paas ki dukaanein jawab dengi. Your neighbourhood, delivered.
        </p>

        <div className="mt-6 space-y-2.5 w-full max-w-xs">
          {PERKS.map((p, i) => (
            <div
              key={p.text}
              className="flex items-center gap-3 rounded-2xl border-2 border-brand-ink bg-brand-cream px-4 py-3 shadow-sticker-sm lm-pop"
              style={{ animationDelay: `${0.22 + i * 0.07}s` }}
            >
              <p.icon className="w-5 h-5 text-brand-green shrink-0" strokeWidth={2.5} />
              <span className="text-[13.5px] font-bold text-brand-ink text-left">{p.text}</span>
            </div>
          ))}
        </div>

        {/* auth card */}
        <div className="mt-7 w-full max-w-xs rounded-[28px] border-2 border-brand-ink bg-brand-cream p-5 shadow-sticker text-left lm-pop" style={{ animationDelay: "0.45s" }}>
          <div className="grid grid-cols-2 gap-1.5 rounded-full border-2 border-brand-ink/15 bg-background p-1">
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setOtpSent(false); setOtp(""); }}
                className={clsx(
                  "rounded-full py-2 text-[12.5px] font-extrabold uppercase tracking-wide transition-all",
                  mode === m ? "bg-brand-ink text-brand-yellow" : "text-brand-ink/60",
                )}
              >
                {m === "login" ? "Login" : "Register"}
              </button>
            ))}
          </div>

          <div className="mt-4 space-y-2.5">
            {mode === "register" && (
              <>
                <input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Poora naam"
                  autoComplete="name"
                  className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
                />
                <div className="flex gap-2">
                  <input
                    value={phone}
                    onChange={(e) => { setPhone(e.target.value); setOtpSent(false); }}
                    placeholder="Phone number"
                    autoComplete="tel"
                    inputMode="tel"
                    className="min-w-0 flex-1 rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
                  />
                  <button
                    type="button"
                    onClick={sendOtpNow}
                    disabled={sendOtp.isPending || phone.trim().length < 10}
                    className="shrink-0 rounded-2xl border-2 border-brand-ink bg-brand-ink text-brand-yellow px-3 text-[11.5px] font-extrabold inline-flex items-center gap-1 disabled:opacity-50"
                  >
                    <Phone className="w-3.5 h-3.5" />
                    {otpSent ? "Resend" : "Send OTP"}
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {([
                    ["customer", "Customer", ShoppingBag],
                    ["shopkeeper", "Dukaandaar", Store],
                    ["professional", "Professional", Wrench],
                  ] as const).map(([value, label, Icon]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setRole(value)}
                      className={clsx(
                        "rounded-2xl border-2 py-2.5 text-[11px] font-extrabold flex flex-col items-center justify-center gap-1",
                        role === value
                          ? "bg-brand-ink text-brand-yellow border-brand-ink"
                          : "bg-background border-brand-ink/15 text-brand-ink/60",
                      )}
                    >
                      <Icon className="w-4 h-4" /> {label}
                    </button>
                  ))}
                </div>
                {otpSent && (
                  <div className="rounded-2xl border-2 border-brand-green/40 bg-brand-green/5 p-2.5 flex items-center gap-2 lm-pop">
                    <ShieldCheck className="w-5 h-5 text-brand-green shrink-0" />
                    <input
                      value={otp}
                      onChange={(e) => setOtp(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && submit()}
                      placeholder="6-digit OTP"
                      inputMode="numeric"
                      maxLength={8}
                      autoComplete="one-time-code"
                      className="min-w-0 flex-1 bg-transparent font-bold text-[16px] tracking-[0.4em] outline-none"
                    />
                  </div>
                )}
              </>
            )}
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              type="email"
              autoComplete="email"
              className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
            />
            <div className="relative">
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder={mode === "register" ? "Password (min 8 characters)" : "Password"}
                type={showPassword ? "text" : "password"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 pr-12 font-bold text-[15px] outline-none focus:border-brand-green"
              />
              <button
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 grid place-items-center text-brand-ink/50"
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>

          <button
            onClick={submit}
            disabled={busy}
            className="mt-4 w-full rounded-full border-2 border-brand-ink bg-brand-ink text-brand-yellow font-display text-[16px] py-4 shadow-sticker active:translate-y-[3px] active:shadow-none transition-all disabled:opacity-60"
          >
            {busy ? "Ek second…" : mode === "login" ? "Login →" : "Account banao →"}
          </button>

          <p className="mt-3 text-center text-[11px] font-bold text-brand-ink/50 leading-relaxed">
            Telegram se judna hai? Account ke baad
            <br />
            <span className="text-brand-green">Account → Connect Telegram</span> dabaiye.
          </p>
          {mode === "register" && (
            <p className="mt-2 text-center text-[10.5px] font-bold text-brand-ink/40 leading-relaxed">
              Phone OTP verifies you're real — scammers ke liye SIM khareedna padta hai.
            </p>
          )}
        </div>
      </div>

      <div className="px-6 pb-8 safe-bottom w-full max-w-sm mx-auto text-center">
        <p className="text-[11.5px] font-bold text-brand-ink/50">
          LocalMart · Mohalle ka apna bazaar · powered by Vyapaar-Mitra
        </p>
      </div>
    </div>
  );
}
