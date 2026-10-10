import { useEffect, useState, useRef } from "react";
import { useNavigate, useSearchParams, Link } from "react-router";
import { Mail, ShieldCheck, AlertTriangle, Clock, ArrowRight, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { Sticker } from "@/components/brand";

/**
 * VerifyEmail — landing page for the email verification link.
 *
 * Mounted at `/verify-email?token=...`. On mount:
 *   1. Reads the raw token from the URL.
 *   2. POSTs to /auth/verify-email (single-use, hashed-at-rest, expiring).
 *   3. Shows loading → success / expired / invalid / consumed.
 *
 * Does NOT auto-log the user in — they must type their password to log in.
 * This is deliberate: the link-click itself doesn't grant a session.
 */
type Status = "loading" | "success" | "expired" | "consumed" | "invalid" | "error";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status>("loading");
  const [verifiedEmail, setVerifiedEmail] = useState<string | null>(null);
  const [resendEmail, setResendEmail] = useState("");
  const verifyMutation = api.auth.verifyEmail.useMutation({
    onSuccess: (data) => {
      setStatus("success");
      setVerifiedEmail(data.email);
      toast.success("Email verified! Ab aap login kar sakte hain.");
    },
    onError: (e) => {
      if (e instanceof ApiError) {
        // Map HTTP status to a specific status for tailored UI
        if (e.status === 410) {
          // 410 Gone — expired OR consumed. Backend differentiates via message.
          if (e.message.toLowerCase().includes("expire")) {
            setStatus("expired");
          } else if (e.message.toLowerCase().includes("pehle hi use")) {
            setStatus("consumed");
          } else {
            setStatus("expired");
          }
        } else if (e.status === 400) {
          setStatus("invalid");
        } else {
          setStatus("error");
        }
      } else {
        setStatus("error");
      }
    },
  });
  const resend = api.auth.resendVerification.useMutation({
    onSuccess: (data) => {
      if (data.sent) {
        toast.success("Naya verification link bhej diya! Check your inbox.");
        setStatus("loading");  // reset so user can click the new link from email
      } else {
        toast(data.reason, { duration: 6000 });
      }
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Resend fail ho gaya."),
  });
  // useRef to avoid double-firing the verify in StrictMode dev mode
  const firedRef = useRef(false);

  useEffect(() => {
    if (firedRef.current) return;
    if (!token || token.length < 16) {
      setStatus("invalid");
      return;
    }
    firedRef.current = true;
    verifyMutation.mutate({ token });
  }, [token, verifyMutation]);

  return (
    <div className="min-h-dvh bg-brand-yellow grid place-items-center p-4">
      <div className="w-full max-w-md">
        {/* ── Loading ── */}
        {status === "loading" && (
          <div className="lm-pop rounded-3xl border-2 border-brand-ink bg-card p-8 text-center">
            <div className="w-16 h-16 rounded-2xl bg-brand-yellow/40 grid place-items-center mx-auto mb-4 animate-pulse">
              <Mail className="w-7 h-7 text-brand-ink" />
            </div>
            <h1 className="font-display text-[22px] mb-1">Verifying your email…</h1>
            <p className="text-[12.5px] font-bold text-muted-foreground">
              Ek second — token validate ho raha hai.
            </p>
          </div>
        )}

        {/* ── Success ── */}
        {status === "success" && (
          <div className="lm-pop rounded-3xl border-2 border-brand-ink bg-card p-8 text-center">
            <div className="w-16 h-16 rounded-2xl bg-brand-green/15 grid place-items-center mx-auto mb-4">
              <ShieldCheck className="w-7 h-7 text-brand-green" />
            </div>
            <Sticker rot={-3} color="#009146">Verified ✓</Sticker>
            <h1 className="font-display text-[22px] mt-4 mb-1">Email verified!</h1>
            <p className="text-[12.5px] font-bold text-muted-foreground mb-1">
              {verifiedEmail ?? "Your email"} ab verified hai.
            </p>
            <p className="text-[11px] font-bold text-muted-foreground mb-5">
              Ab aap apna password type karke login kar sakte hain.
            </p>
            <button
              onClick={() => navigate("/login")}
              className="w-full rounded-2xl border-2 border-brand-ink bg-brand-ink text-brand-yellow text-[13px] font-extrabold py-3 flex items-center justify-center gap-2 active:translate-y-[1px] transition-all"
            >
              Go to login <ArrowRight className="w-4 h-4" strokeWidth={2.6} />
            </button>
          </div>
        )}

        {/* ── Expired ── */}
        {status === "expired" && (
          <ResendCard
            icon={<Clock className="w-7 h-7 text-brand-ink" />}
            title="Link expire ho gaya"
            sub="Yeh verification link ki time-limit khatam ho gayi (24 hours). Naya link mangaiye."
            resendEmail={resendEmail}
            setResendEmail={setResendEmail}
            onResend={async () => { await resend.mutateAsync({ email: resendEmail }); }}
            isPending={resend.isPending}
          />
        )}

        {/* ── Consumed (already used) ── */}
        {status === "consumed" && (
          <div className="lm-pop rounded-3xl border-2 border-brand-ink bg-card p-8 text-center">
            <div className="w-16 h-16 rounded-2xl bg-brand-yellow/30 grid place-items-center mx-auto mb-4">
              <ShieldCheck className="w-7 h-7 text-brand-ink" />
            </div>
            <h1 className="font-display text-[22px] mb-1">Pehle hi verified</h1>
            <p className="text-[12.5px] font-bold text-muted-foreground mb-5">
              Yeh link pehle hi use ho chuka hai. Aapka email verified hai — ab seedha login karein.
            </p>
            <button
              onClick={() => navigate("/login")}
              className="w-full rounded-2xl border-2 border-brand-ink bg-brand-ink text-brand-yellow text-[13px] font-extrabold py-3 flex items-center justify-center gap-2 active:translate-y-[1px] transition-all"
            >
              Go to login <ArrowRight className="w-4 h-4" strokeWidth={2.6} />
            </button>
          </div>
        )}

        {/* ── Invalid (bad token / no token) ── */}
        {status === "invalid" && (
          <ResendCard
            icon={<AlertTriangle className="w-7 h-7 text-brand-ink" />}
            title="Link invalid"
            sub="Yeh verification link sahi nahi hai. Email mein jo link bheja gaya, usi par click karein — ya naya link mangaiye."
            resendEmail={resendEmail}
            setResendEmail={setResendEmail}
            onResend={async () => { await resend.mutateAsync({ email: resendEmail }); }}
            isPending={resend.isPending}
          />
        )}

        {/* ── Generic error ── */}
        {status === "error" && (
          <div className="lm-pop rounded-3xl border-2 border-brand-ink bg-card p-8 text-center">
            <div className="w-16 h-16 rounded-2xl bg-[#F03749]/10 grid place-items-center mx-auto mb-4">
              <AlertTriangle className="w-7 h-7 text-[#F03749]" />
            </div>
            <h1 className="font-display text-[22px] mb-1">Kuch gadbad ho gayi</h1>
            <p className="text-[12.5px] font-bold text-muted-foreground mb-5">
              Verification fail ho gayi. Thodi der baad phir try karein, ya naya link mangaiye.
            </p>
            <Link
              to="/login"
              className="block w-full rounded-2xl border-2 border-brand-ink bg-brand-ink text-brand-yellow text-[13px] font-extrabold py-3 text-center"
            >
              Back to login
            </Link>
          </div>
        )}

        <p className="text-center mt-4">
          <Link to="/login" className="text-[12px] font-extrabold text-brand-ink underline">
            Back to login
          </Link>
        </p>
      </div>
    </div>
  );
}

/* ── Reusable resend-card for the expired + invalid states ── */
function ResendCard({
  icon, title, sub, resendEmail, setResendEmail, onResend, isPending,
}: {
  icon: React.ReactNode;
  title: string;
  sub: string;
  resendEmail: string;
  setResendEmail: (v: string) => void;
  onResend: () => Promise<void>;
  isPending: boolean;
}) {
  return (
    <div className="lm-pop rounded-3xl border-2 border-brand-ink bg-card p-8 text-center">
      <div className="w-16 h-16 rounded-2xl bg-brand-yellow/30 grid place-items-center mx-auto mb-4">
        {icon}
      </div>
      <h1 className="font-display text-[22px] mb-1">{title}</h1>
      <p className="text-[12.5px] font-bold text-muted-foreground mb-5">{sub}</p>

      <div className="text-left">
        <label className="block text-[10.5px] font-extrabold uppercase tracking-wide text-muted-foreground mb-1">
          Apna email
        </label>
        <input
          type="email"
          value={resendEmail}
          onChange={(e) => setResendEmail(e.target.value)}
          placeholder="you@example.com"
          className="w-full rounded-2xl border-2 border-brand-ink/20 bg-brand-cream px-4 py-3 text-[14px] font-bold focus:outline-none focus:border-brand-ink"
        />
      </div>
      <button
        onClick={onResend}
        disabled={isPending || !resendEmail.trim()}
        className="mt-3 w-full rounded-2xl border-2 border-brand-ink bg-brand-yellow text-brand-ink text-[13px] font-extrabold py-3 flex items-center justify-center gap-2 disabled:opacity-50 active:translate-y-[1px] transition-all"
      >
        <RefreshCw className={`w-4 h-4 ${isPending ? "animate-spin" : ""}`} strokeWidth={2.6} />
        {isPending ? "Bhej rahe hain…" : "Send new verification link"}
      </button>
    </div>
  );
}
