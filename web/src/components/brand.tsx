import {
  ShoppingBasket, Carrot, Milk, Pill, Hammer, Zap, Pencil, Scissors,
  Smartphone, Package,
} from "lucide-react";
import { clsx } from "@/lib/format";
import { categoryMeta } from "@/lib/localmart";

export const CATEGORY_ICONS: Record<string, typeof Package> = {
  kirana: ShoppingBasket,
  vegetables: Carrot,
  dairy: Milk,
  pharmacy: Pill,
  hardware: Hammer,
  electrical: Zap,
  stationery: Pencil,
  tailor: Scissors,
  mobile: Smartphone,
  other: Package,
};

export function CategoryIcon({
  categoryKey,
  size = 44,
  className,
}: {
  categoryKey: string;
  size?: number;
  className?: string;
}) {
  const meta = categoryMeta(categoryKey);
  const Icon = CATEGORY_ICONS[meta.key] ?? Package;
  return (
    <span
      className={clsx("inline-flex items-center justify-center rounded-2xl shrink-0", className)}
      style={{
        width: size,
        height: size,
        background: `${meta.color}1c`,
        color: meta.color,
      }}
    >
      <Icon style={{ width: size * 0.48, height: size * 0.48 }} strokeWidth={2.2} />
    </span>
  );
}

export function Logo({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const box = size === "lg" ? 52 : size === "sm" ? 32 : 40;
  const text =
    size === "lg" ? "text-[30px]" : size === "sm" ? "text-[17px]" : "text-[22px]";
  return (
    <span className="inline-flex items-center gap-2.5 select-none">
      <span
        className="inline-flex items-center justify-center rounded-[28%] bg-brand-green text-brand-cream shadow-sticker-sm border-2 border-brand-ink"
        style={{ width: box, height: box }}
      >
        <ShoppingBasket style={{ width: box * 0.55, height: box * 0.55 }} strokeWidth={2.4} />
      </span>
      <span className={clsx("font-display text-brand-ink tracking-tight leading-none", text)}>
        Local<span className="text-brand-green">Mart</span>
      </span>
    </span>
  );
}

/** Rotated sticker badge — "BEST PRICE", "2 min away", etc. */
export function Sticker({
  children,
  color = "#FEE600",
  rot = -3,
  className,
}: {
  children: React.ReactNode;
  color?: string;
  rot?: number;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-block rounded-full border-2 border-brand-ink px-3 py-1 font-display text-[11px] uppercase tracking-wide text-brand-ink shadow-sticker-sm",
        className,
      )}
      style={{ background: color, transform: `rotate(${rot}deg)` }}
    >
      {children}
    </span>
  );
}

export function SectionHead({
  title,
  sub,
  action,
}: {
  title: string;
  sub?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-end justify-between gap-3 mb-3.5">
      <div>
        <h2 className="font-display text-[19px] leading-tight text-brand-ink">{title}</h2>
        {sub && <p className="text-[13px] font-medium text-muted-foreground mt-0.5">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  sub,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  sub?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-[28px] border-2 border-dashed border-brand-ink/20 bg-card px-6 py-10 text-center">
      <div className="mx-auto w-14 h-14 rounded-2xl bg-brand-yellow/60 flex items-center justify-center text-brand-ink mb-4">
        {icon}
      </div>
      <div className="font-display text-[17px] text-brand-ink">{title}</div>
      {sub && <p className="text-[13.5px] text-muted-foreground font-medium mt-1.5 max-w-xs mx-auto">{sub}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Thinking({ text, dark = false }: { text: string; dark?: boolean }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-2 h-2 rounded-full lm-dot"
            style={{
              background: dark ? "#FFFCF5" : "#009146",
              animationDelay: `${i * 0.18}s`,
            }}
          />
        ))}
      </span>
      <span
        className={clsx(
          "text-[12px] font-bold uppercase tracking-[0.14em]",
          dark ? "text-brand-cream/80" : "text-brand-green",
        )}
      >
        {text}
      </span>
    </div>
  );
}
