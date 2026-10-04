import { useNavigate } from "react-router";
import { ClipboardList, ChevronRight } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { CategoryIcon, EmptyState } from "@/components/brand";
import { timeAgo, clsx } from "@/lib/format";

const STATUS_META: Record<string, { label: string; bg: string; fg: string }> = {
  matching: { label: "Matching", bg: "#FEE600", fg: "#141313" },
  offers: { label: "Jawab aa rahe", bg: "#2BA0FF", fg: "#FFFCF5" },
  completed: { label: "Ho gaya", bg: "#009146", fg: "#FFFCF5" },
  no_match: { label: "Demand noted", bg: "#14131315", fg: "#14131399" },
};

export default function History() {
  const navigate = useNavigate();
  const mine = trpc.request.mine.useQuery();

  return (
    <div>
      <TopBar title="Meri Activity" sub="Saari requests, ek jagah" />

      {mine.isLoading && (
        <div className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card h-[84px] animate-pulse" />
          ))}
        </div>
      )}

      {mine.data?.length === 0 && (
        <EmptyState
          icon={<ClipboardList className="w-7 h-7" />}
          title="Abhi koi request nahi"
          sub="Kuch chahiye toh bolo — mohalla jawab dega."
          action={
            <button
              onClick={() => navigate("/")}
              className="rounded-full border-2 border-brand-ink bg-brand-yellow px-6 py-3 font-display text-[14px] shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all"
            >
              Pehli request →
            </button>
          }
        />
      )}

      <div className="space-y-2.5">
        {mine.data?.map((r, i) => {
          const st = STATUS_META[r.status] ?? STATUS_META.matching;
          return (
            <button
              key={r.id}
              onClick={() => navigate(`/search?q=${encodeURIComponent(r.rawText ?? r.product)}&type=text&rid=${r.id}`)}
              className="lm-pop w-full text-left rounded-3xl border-2 border-brand-ink/10 bg-card p-4 flex items-center gap-3.5 hover:border-brand-ink/40 transition-all active:scale-[0.99]"
              style={{ animationDelay: `${Math.min(i, 8) * 0.04}s` }}
            >
              <CategoryIcon categoryKey={r.categoryKey} size={46} />
              <div className="flex-1 min-w-0">
                <div className="font-extrabold text-[15px] truncate">{r.product}</div>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className="rounded-full px-2.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide"
                    style={{ background: st.bg, color: st.fg }}
                  >
                    {st.label}
                  </span>
                  <span className="text-[11.5px] font-bold text-muted-foreground">{timeAgo(r.createdAt)}</span>
                </div>
              </div>
              <ChevronRight className={clsx("w-5 h-5 shrink-0 text-brand-ink/30")} />
            </button>
          );
        })}
      </div>
    </div>
  );
}
