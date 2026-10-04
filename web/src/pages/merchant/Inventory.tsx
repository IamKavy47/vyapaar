import { useState } from "react";
import { toast } from "sonner";
import { Plus, Package, Trash2 } from "lucide-react";
import { api as trpc } from "@/lib/api";
import { TopBar } from "@/components/shell";
import { EmptyState, Sticker } from "@/components/brand";
import { formatINR, clsx } from "@/lib/format";

export default function Inventory() {
  const utils = trpc.useUtils();
  const items = trpc.merchant.inventory.useQuery();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", price: "", quantity: "", unit: "piece" });

  const invalidate = () => utils.merchant.inventory.invalidate();

  const addItem = trpc.merchant.addItem.useMutation({
    onSuccess: () => {
      toast.success("Item add ho gaya!");
      setForm({ name: "", price: "", quantity: "", unit: "piece" });
      setShowAdd(false);
      invalidate();
    },
    onError: (e) => toast.error(e.message),
  });
  const toggle = trpc.merchant.toggleStock.useMutation({ onSuccess: invalidate });
  const remove = trpc.merchant.removeItem.useMutation({
    onSuccess: () => {
      toast.success("Item hataya");
      invalidate();
    },
  });

  const submit = () => {
    const price = Number(form.price);
    const quantity = Number(form.quantity || "0");
    if (form.name.trim().length < 2 || !price) {
      toast.error("Naam aur daam toh bharo");
      return;
    }
    addItem.mutate({ name: form.name.trim(), price, quantity, unit: form.unit.trim() || "piece" });
  };

  const inStockCount = items.data?.filter((i) => i.inStock).length ?? 0;

  return (
    <div>
      <TopBar
        title="Mera Stock"
        sub={items.data ? `${inStockCount}/${items.data.length} available` : ""}
        right={
          <button
            onClick={() => setShowAdd((v) => !v)}
            className="h-11 rounded-full border-2 border-brand-ink bg-brand-yellow px-4 font-extrabold text-[13px] flex items-center gap-1.5 shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all"
          >
            <Plus className="w-4 h-4" strokeWidth={2.8} /> Item
          </button>
        }
      />

      {showAdd && (
        <div className="lm-pop mb-5 rounded-[28px] border-2 border-brand-ink bg-card p-5 shadow-sticker space-y-3">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Item ka naam — jaise LED Bulb 9W"
            className="w-full rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-bold text-[15px] outline-none focus:border-brand-green"
          />
          <div className="grid grid-cols-3 gap-2.5">
            <div className="flex items-center rounded-2xl border-2 border-brand-ink/15 bg-background px-3">
              <span className="font-display text-[14px] text-brand-ink/40">₹</span>
              <input
                value={form.price}
                onChange={(e) => setForm({ ...form, price: e.target.value.replace(/[^0-9]/g, "") })}
                placeholder="Daam"
                inputMode="numeric"
                className="w-full bg-transparent px-2 py-3 font-extrabold text-[14.5px] outline-none"
              />
            </div>
            <input
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value.replace(/[^0-9]/g, "") })}
              placeholder="Qty"
              inputMode="numeric"
              className="rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-extrabold text-[14.5px] outline-none focus:border-brand-green"
            />
            <input
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
              placeholder="Unit"
              className="rounded-2xl border-2 border-brand-ink/15 bg-background px-4 py-3 font-extrabold text-[14.5px] outline-none focus:border-brand-green"
            />
          </div>
          <button
            onClick={submit}
            disabled={addItem.isPending}
            className="w-full rounded-full border-2 border-brand-ink bg-brand-green text-brand-cream font-display text-[14.5px] py-3.5 shadow-sticker active:translate-y-[3px] active:shadow-none transition-all disabled:opacity-50"
          >
            Stock mein daalo →
          </button>
        </div>
      )}

      {items.isLoading && (
        <div className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-3xl border-2 border-brand-ink/10 bg-card h-[72px] animate-pulse" />
          ))}
        </div>
      )}

      {items.data?.length === 0 && (
        <EmptyState
          icon={<Package className="w-7 h-7" />}
          title="Stock khaali hai"
          sub="Pehla item add karo — customers ko turant dikhega aur requests mein stock hint lagega."
          action={
            <button
              onClick={() => setShowAdd(true)}
              className="rounded-full border-2 border-brand-ink bg-brand-yellow px-6 py-3 font-display text-[14px] shadow-sticker-sm active:translate-y-[2px] active:shadow-none transition-all"
            >
              Pehla item →
            </button>
          }
        />
      )}

      {(items.data?.length ?? 0) > 0 && (
        <div className="mb-3 flex justify-end">
          <Sticker rot={2}>{inStockCount} live</Sticker>
        </div>
      )}

      <div className="space-y-2.5">
        {items.data?.map((it, i) => (
          <div
            key={it.id}
            className={clsx(
              "lm-pop rounded-3xl border-2 bg-card p-4 flex items-center gap-3 transition-all",
              it.inStock ? "border-brand-ink/10" : "border-brand-ink/10 opacity-70",
            )}
            style={{ animationDelay: `${Math.min(i, 10) * 0.03}s` }}
          >
            <div className="flex-1 min-w-0">
              <div className="font-extrabold text-[14.5px] leading-tight truncate">{it.name}</div>
              <div className="text-[11.5px] font-bold text-muted-foreground mt-1">
                {formatINR(it.price)} / {it.unit} · qty {it.quantity}
              </div>
            </div>
            <button
              onClick={() => toggle.mutate({ id: it.id })}
              disabled={toggle.isPending}
              className={clsx(
                "rounded-full px-3.5 py-2 text-[11px] font-extrabold border-2 transition-all active:scale-95",
                it.inStock
                  ? "bg-brand-green text-brand-cream border-brand-green"
                  : "bg-card text-[#F03749] border-[#F0374955]",
              )}
            >
              {it.inStock ? "In stock" : "Out"}
            </button>
            <button
              onClick={() => remove.mutate({ id: it.id })}
              disabled={remove.isPending}
              aria-label="Delete"
              className="w-9 h-9 rounded-xl grid place-items-center text-brand-ink/30 hover:text-[#F03749] hover:bg-[#F0374910] transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
