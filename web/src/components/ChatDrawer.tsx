import { useEffect, useRef, useState } from "react";
import { Send, X, ShieldCheck, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api as trpc, ApiError, type ChatMessage } from "@/lib/api";
import { clsx, timeAgo } from "@/lib/format";

interface ChatDrawerProps {
  requestId: string;
  shopName?: string;
  shopfrontPhotoUrl?: string | null;
  shopAddress?: string | null;
  /** Customer side opens chat with the shop they picked. */
  side: "customer" | "shopkeeper";
  onClose?: () => void;
}

/**
 * Real-time-ish chat between customer and shopkeeper. Uses REST polling
 * every 1.5 seconds (no WebSocket — simpler and works through any
 * corporate firewall). Messages are scoped to the request_id, both sides
 * are anonymised — the customer's phone is NEVER exposed to the shopkeeper.
 */
export function ChatDrawer({
  requestId, shopName, shopfrontPhotoUrl, shopAddress, side, onClose,
}: ChatDrawerProps) {
  const [text, setText] = useState("");
  const [allMessages, setAllMessages] = useState<ChatMessage[]>([]);
  const lastSinceRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const isCustomer = side === "customer";
  const sendMutation = isCustomer
    ? trpc.request.sendChatMessage.useMutation()
    : trpc.merchant.sendChatMessage.useMutation();

  // Polling loop — fetch new messages every 1.5s using `since` for efficiency.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      if (cancelled) return;
      try {
        const result = isCustomer
          ? await (trpc as any).request.chatHistory.fetch({ id: requestId, since: lastSinceRef.current ?? undefined })
          : await (trpc as any).merchant.conversationHistory.fetch({ requestId, since: lastSinceRef.current ?? undefined });
        if (cancelled) return;
        if (result.messages && result.messages.length > 0) {
          setAllMessages((prev) => {
            // Merge new messages with existing ones, deduplicated by id.
            const seen = new Set(prev.map((m) => m.id));
            const newOnes = result.messages.filter((m: ChatMessage) => !seen.has(m.id));
            return [...prev, ...newOnes];
          });
          // Update `since` to the latest message's createdAt.
          const latest = result.messages[result.messages.length - 1];
          if (latest?.createdAt) lastSinceRef.current = latest.createdAt;
        }
      } catch (e) {
        // Silent — keep polling. Show a toast only on the first failure.
        if (!lastSinceRef.current) {
          toast.error(e instanceof ApiError ? e.message : "Chat fetch nahi ho paayi.");
        }
      } finally {
        if (!cancelled) timer = setTimeout(poll, 1500);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [requestId, isCustomer]);

  // Scroll to bottom whenever new messages arrive.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [allMessages.length]);

  const send = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    try {
      await sendMutation.mutateAsync({ requestId, text: trimmed });
      setText("");
      // Immediate poll so the user sees their own message instantly.
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Message bhej nahi paaye.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-brand-ink/80 backdrop-blur-sm">
      <div className="mt-auto max-h-[88vh] rounded-t-[28px] border-t-2 border-brand-ink bg-brand-cream flex flex-col">
        {/* header */}
        <div className="flex items-center gap-3 p-4 border-b-2 border-brand-ink/10">
          {shopfrontPhotoUrl ? (
            <img
              src={shopfrontPhotoUrl}
              alt={shopName || "Shop"}
              className="w-11 h-11 rounded-xl object-cover border-2 border-brand-ink shrink-0"
            />
          ) : (
            <div className="w-11 h-11 rounded-xl bg-brand-ink/10 grid place-items-center text-[16px] font-display text-brand-ink/50 shrink-0">
              {(shopName || "S")[0]}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="font-extrabold text-[15px] truncate">{shopName || "Shop"}</div>
            {shopAddress && (
              <div className="text-[11px] font-bold text-muted-foreground truncate">{shopAddress}</div>
            )}
          </div>
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-green/15 text-brand-green px-2 py-0.5 text-[9.5px] font-extrabold uppercase tracking-wide">
            <ShieldCheck className="w-3 h-3" /> Phone hidden
          </span>
          {onClose && (
            <button
              onClick={onClose}
              aria-label="Close chat"
              className="w-9 h-9 rounded-2xl border-2 border-brand-ink/15 bg-background grid place-items-center text-brand-ink/55"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2.5 bg-background">
          {allMessages.length === 0 && (
            <div className="text-center text-[12px] font-bold text-muted-foreground py-8">
              Chat shuru karne ke liye neeche message bhejiye.
            </div>
          )}
          {allMessages.map((m) => {
            const mine = isCustomer
              ? m.senderRole === "customer"
              : m.senderRole === "shopkeeper";
            const isSystem = m.senderRole === "system";
            if (isSystem) {
              return (
                <div key={m.id} className="text-center">
                  <span className="inline-block rounded-full bg-brand-ink/8 text-brand-ink/55 px-3 py-1 text-[10.5px] font-bold">
                    {m.text}
                  </span>
                </div>
              );
            }
            return (
              <div
                key={m.id}
                className={clsx("flex", mine ? "justify-end" : "justify-start")}
              >
                <div
                  className={clsx(
                    "max-w-[78%] rounded-2xl px-3.5 py-2",
                    mine
                      ? "bg-brand-green text-brand-cream rounded-br-md"
                      : "bg-card text-brand-ink rounded-bl-md border-2 border-brand-ink/8",
                  )}
                >
                  <div className="text-[14px] font-bold leading-snug whitespace-pre-wrap break-words">{m.text}</div>
                  <div className={clsx(
                    "text-[9px] font-bold mt-1",
                    mine ? "text-brand-cream/65" : "text-muted-foreground",
                  )}>
                    {timeAgo(m.createdAt)}
                  </div>
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>

        {/* input */}
        <div className="p-3 border-t-2 border-brand-ink/10 bg-brand-cream safe-bottom">
          <div className="flex items-center gap-2 rounded-full border-2 border-brand-ink/15 bg-background pl-4 pr-1 py-1">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder={`Message ${shopName || "shop"} ko bhejiye…`}
              maxLength={1000}
              className="min-w-0 flex-1 bg-transparent py-2.5 text-[14px] font-bold outline-none"
            />
            <button
              onClick={send}
              disabled={sendMutation.isPending || !text.trim()}
              className="shrink-0 rounded-full bg-brand-ink text-brand-yellow w-10 h-10 grid place-items-center disabled:opacity-50"
              aria-label="Send message"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="mt-1.5 text-[10px] font-bold text-brand-ink/40 text-center flex items-center justify-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            Saari baatcheet Vyapaar-Mitra servers par logged hai — agar kuch galat ho to evidence available hai.
          </p>
        </div>
      </div>
    </div>
  );
}
