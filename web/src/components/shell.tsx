import { useEffect } from "react";
import { NavLink, Outlet, useNavigate, useLocation as useRouteLocation, Link } from "react-router";
import {
  Home, Store, ArrowLeftRight, ClipboardList, UserRound,
  Inbox, Package, BookOpenText, TrendingUp, ArrowLeft, BarChart3, ShieldCheck,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { api as trpc } from "@/lib/api";
import { Logo } from "@/components/brand";
import { clsx } from "@/lib/format";

const CUSTOMER_NAV = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/browse", label: "Shops", icon: Store },
  { to: "/compare", label: "Compare", icon: ArrowLeftRight },
  { to: "/history", label: "Activity", icon: ClipboardList },
  { to: "/account", label: "You", icon: UserRound },
];

const MERCHANT_NAV = [
  { to: "/merchant", label: "Inbox", icon: Inbox, end: true },
  { to: "/merchant/inventory", label: "Stock", icon: Package },
  { to: "/merchant/demand", label: "Demand", icon: TrendingUp },
  { to: "/merchant/impact", label: "Impact", icon: BarChart3 },
  { to: "/merchant/khata", label: "Khata", icon: BookOpenText },
  { to: "/account", label: "You", icon: UserRound },
];

const ADMIN_NAV = [
  { to: "/admin/shops/pending", label: "Verify", icon: ShieldCheck, end: true },
  { to: "/account", label: "You", icon: UserRound },
];

export function AppShell() {
  const { user, isLoading, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const profile = trpc.profile.get.useQuery(undefined, {
    enabled: isAuthenticated,
    retry: false,
  });

  useEffect(() => {
    if (!isLoading && !isAuthenticated) navigate("/login", { replace: true });
  }, [isLoading, isAuthenticated, navigate]);

  useEffect(() => {
    if (profile.data && !profile.data.appRole) navigate("/onboarding", { replace: true });
  }, [profile.data, navigate]);

  if (isLoading || !user || (isAuthenticated && profile.isLoading)) {
    return (
      <div className="min-h-dvh grid place-items-center bg-background">
        <div className="lm-pop"><Logo size="lg" /></div>
      </div>
    );
  }

  const role = profile.data?.appRole
    ?? (user.role === "admin" ? "admin" : "customer");
  const nav = role === "shopkeeper" ? MERCHANT_NAV
    : role === "admin" ? ADMIN_NAV
    : CUSTOMER_NAV;

  return (
    <div className="min-h-dvh bg-background">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-[248px] flex-col border-r-2 border-brand-ink/10 bg-card z-40">
        <div className="px-6 pt-7 pb-6">
          <Link to="/"><Logo /></Link>
        </div>
        <nav className="flex-1 px-4 space-y-1.5">
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-2xl px-4 py-3 text-[14.5px] font-bold transition-all",
                  isActive
                    ? "bg-brand-ink text-brand-yellow shadow-sticker-sm"
                    : "text-brand-ink/70 hover:bg-brand-yellow/40 hover:text-brand-ink",
                )
              }
            >
              <n.icon className="w-[19px] h-[19px]" strokeWidth={2.4} />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-6 pb-7 text-[11px] font-semibold text-muted-foreground leading-relaxed">
          Mohalle ka apna bazaar.
          <br />Mandsaur, MP
        </div>
      </aside>

      {/* Content */}
      <div className="lg:pl-[248px]">
        <main className="mx-auto w-full max-w-3xl px-4 sm:px-6 pb-28 lg:pb-12 lg:max-w-4xl">
          <Outlet context={{ role }} />
        </main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 safe-bottom">
        <div className="mx-auto max-w-3xl px-3 pb-3">
          <div className="rounded-[26px] border-2 border-brand-ink bg-card shadow-sticker px-1.5 py-1.5 flex">
            {nav.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  clsx(
                    "flex-1 flex flex-col items-center gap-0.5 rounded-2xl py-2 transition-all min-h-[48px] justify-center",
                    isActive ? "bg-brand-ink text-brand-yellow" : "text-brand-ink/60",
                  )
                }
              >
                <n.icon className="w-[20px] h-[20px]" strokeWidth={2.4} />
                <span className="text-[10px] font-extrabold tracking-wide">{n.label}</span>
              </NavLink>
            ))}
          </div>
        </div>
      </nav>
    </div>
  );
}

/** Sticky in-page header for sub-screens */
export function TopBar({
  title,
  sub,
  back = false,
  right,
}: {
  title: string;
  sub?: string;
  back?: boolean;
  right?: React.ReactNode;
}) {
  const navigate = useNavigate();
  const loc = useRouteLocation();
  return (
    <div className="sticky top-0 z-30 -mx-4 sm:-mx-6 px-4 sm:px-6 pt-3 pb-3 bg-background/90 backdrop-blur-md">
      <div className="flex items-center gap-3">
        {back && (
          <button
            onClick={() => (loc.key !== "default" ? navigate(-1) : navigate("/"))}
            aria-label="Back"
            className="w-11 h-11 rounded-2xl border-2 border-brand-ink bg-card shadow-sticker-sm grid place-items-center active:translate-y-[2px] active:shadow-none transition-all"
          >
            <ArrowLeft className="w-5 h-5" strokeWidth={2.6} />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[20px] leading-tight truncate">{title}</h1>
          {sub && <p className="text-[12.5px] font-semibold text-muted-foreground truncate">{sub}</p>}
        </div>
        {right}
      </div>
    </div>
  );
}
