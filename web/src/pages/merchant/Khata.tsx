import { useState } from "react";
import { toast } from "sonner";
import { BookOpenText, Plus } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { EmptyState } from "@/components/brand";
import { formatINR, timeAgo, clsx } from "@/lib/format";

export default function Khata() {
  const utils = trpc.useUtils();
  const khata = trpc.merchant.khata.useQuery();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ customerName: "", amount: "", direction: "udhaar" as "udhaar" | "jama", note: "" });

  const add = trpc.merchant.addKhata.useMutation({
    onSuccess: () => {
      toast.success("Entry likh di!");
      setForm({ customerName: "", amount: "", direction: "udhaar", note: "" });
      setShowAdd(false);
      utils.merchant.khata.invalidate();
    },
    onError: (e) => toast.error(e.message),
  });

  const submit = () => {
    const amount = Number(form.amount);
    if (form.customerName.trim().length < 2 || !amount) {
      toast.error("Naam aur amount bharo");
      return;
    }
    add.mutate({
      customerName: form.customerName.trim(),
      amount,
      direction: form.direction,
      note: form.note.trim() || undefined,
    });
  };

  const data = khata.data;

  return (
    <div>
      <TopBar
        title="Digital Khata"
        sub="Udhaar-jama ka hisaab"
        right={
          <button
            onClick={() => setShowAdd((v) => !v)}
            className="h-11 rounded-full border-2 border-brand-ink bg-brand-yellow px-4 font-extrabold text-[13px] flex items-center gap-1.5 shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all"
          >
            <Plus className="w-4 h-4" strokeWidth={2.8} /> Entry
          </button>
        }
      />

      {/* summary */}
      {data && (
        <div className="grid grid-cols-3 gap-2.5 mb-5">
          <div className="rounded-3xl border-2 border-brand-ink bg-[#F03749] p-4 text-center shadow-sticker">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-brand-cream/80">Udhaar</div>
            <div className="font-display text-[19px] text-brand-cream mt-1">{formatINR(data.udhaar)}</div>
          </div>
          <div className="rounded-3xl border-2 border-brand-ink bg-brand-green p-4 text-center shadow-sticker">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-brand-cream/80">Jama</div>
            <div className="font-display text-[19px] text-brand-cream mt-1">{formatINR(data.jama)}</div>
          </div>
          <div className="rounded-3xl border-2 border-brand-ink bg-brand-yellow p-4 text-center shadow-sticker">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-brand-ink/60">Baaki</div>
            <div className="font-display text-[19px] text-brand-ink mt-1">
              {data.outstanding < 0 ? `Advance ${formatINR(Math.abs(data.outstanding))}` : formatINR(data.outstanding)}
            </div>
          </div>
        </div>
      )}

      {showAdd && (
        <div className="lm-pop mb-5 rounded-[28px] border-2 border-brand-ink bg-card p-5 shadow-sticker space-y-3">
          <div className="grid grid-cols-2 gap-2.5">
            {(["udhaar", "jama"] as const).map((d) => (
              <button
                key={d}
                onClick={() => setForm({ ...form, direction: d })}
                className={clsx(
                  "rounded-full border-2 py-3 font-display text-[14px] transition-all",
                  form.direction === d
                    ? d === "udhaar"
                      ? "bg-[#F03749] text-brand-cream border-brand-ink shadow-sticker-sm"
                      : "bg-brand-green text-brand-cream border-brand-ink shadow-sticker-sm"
                    : "bg-background border-brand-ink/15 text-brand-ink/60",
                )}
              >
                {d === "udhaar" ? "Udhaar diya" : "Jama aaya"}
              </button>
            ))}
          </div>
          <input
            value={form.customerName}
            onChange={(e) => setForm({ ...form, customerName: e.target.value })}
            placeholder="Customer ka naam"
            className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
          />
          <div className="flex items-center rounded-2xl border-2 border-brand-ink/15 bg-background px-4">
            <span className="font-display text-[15px] text-brand-ink/40">₹</span>
            <input
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value.replace(/[^0-9]/g, "") })}
              placeholder="Amount"
              inputMode="numeric"
              className="w-full bg-transparent px-2 py-3 font-extrabold text-[15px] outline-none"
            />
          </div>
          <input
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
            placeholder="Note (optional) — jaise: atta + dal"
            className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
          />
          <button
            onClick={submit}
            disabled={add.isPending}
            className="w-full rounded-full border-2 border-brand-ink bg-brand-ink text-brand-yellow font-display text-[14.5px] py-3.5 shadow-sticker active:translate-y-[3px] active:shadow-none transition-all disabled:opacity-50"
          >
            Khate mein likho →
          </button>
        </div>
      )}

      {khata.isLoading && (
        <div className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card h-[72px] animate-pulse" />
          ))}
        </div>
      )}

      {data?.entries.length === 0 && (
        <EmptyState
          icon={<BookOpenText className="w-7 h-7" />}
          title="Khata khaali hai"
          sub="Pehli entry likho — udhaar ya jama, sab yahin rahega."
        />
      )}

      <div className="space-y-2.5">
        {data?.entries.map((e, i) => (
          <div
            key={e.id}
            className="lm-pop rounded-3xl border-2 border-brand-ink/10 bg-card p-4 flex items-center gap-3.5"
            style={{ animationDelay: `${Math.min(i, 10) * 0.03}s` }}
          >
            <span
              className={clsx(
                "w-11 h-11 rounded-2xl grid place-items-center font-display text-[16px] shrink-0 border-2 border-brand-ink",
                e.direction === "udhaar" ? "bg-[#F0374915] text-[#F03749]" : "bg-[#00914615] text-brand-green",
              )}
            >
              {e.direction === "udhaar" ? "−" : "+"}
            </span>
            <div className="flex-1 min-w-0">
              <div className="font-extrabold text-[14.5px] truncate">{e.customerName}</div>
              <div className="text-[11.5px] font-bold text-muted-foreground mt-0.5">
                {e.note ?? (e.direction === "udhaar" ? "Udhaar" : "Jama")} · {timeAgo(e.createdAt)}
              </div>
            </div>
            <div
              className={clsx(
                "font-display text-[17px] shrink-0",
                e.direction === "udhaar" ? "text-[#F03749]" : "text-brand-green",
              )}
            >
              {e.direction === "udhaar" ? "−" : "+"}{formatINR(e.amount)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
