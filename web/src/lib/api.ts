/**
 * LocalMart web API client.
 *
 * Talks to the Vyapaar-Mitra FastAPI backend (the same backend that runs the
 * Telegram bot) over its JSON REST surface at `/api/v1`. Auth is the backend's
 * `vm_session` cookie, so every request goes out with credentials included.
 *
 * The export shape deliberately mirrors the old tRPC hooks
 * (`api.catalog.shops.useQuery(...)`, `api.useUtils()`...) so pages stayed
 * almost untouched — but underneath everything is plain fetch + React Query.
 */
import {
  QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    credentials: "include",
    headers: options.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? "Some fields were invalid. Please check and try again."
          : `Request failed (${res.status})`;
    throw new ApiError(res.status, message);
  }
  return data as T;
}

function qs(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const str = search.toString();
  return str ? `?${str}` : "";
}

type QueryOpts<O> = Omit<UseQueryOptions<O, ApiError>, "queryKey" | "queryFn">;
type MutationOpts<O, I> = Omit<UseMutationOptions<O, ApiError, I>, "mutationFn">;

function Q<I, O>(key: string, fn: (input: I) => Promise<O>) {
  return {
    useQuery: (input?: I, opts?: QueryOpts<O>) =>
      useQuery({
        queryKey: [key, input ?? null],
        queryFn: () => fn(input as I),
        ...opts,
      }),
  };
}

function M<I, O>(fn: (input: I) => Promise<O>) {
  return {
    useMutation: (opts?: MutationOpts<O, I>) =>
      useMutation({ mutationFn: (input: I) => fn(input), ...opts }),
  };
}

/* ------------------------------------------------------------------ types */

export interface WebUser {
  id: string;
  full_name: string;
  email: string;
  phone?: string;
  role: "customer" | "shopkeeper" | "admin";
  telegram_user_id?: number | null;
  is_verified: boolean;
  created_at?: string;
}

export interface Shop {
  id: string;
  name: string;
  categoryKey: string;
  backendCategory: string;
  categoryLabel: string;
  subcategories: string[];
  capabilities: string[];
  address?: string | null;
  phone?: string | null;
  lat?: number | null;
  lng?: number | null;
  isVerified: boolean;
  isActive: boolean;
  description?: string | null;
  distanceMeters?: number | null;
  inventoryCount: number;
  createdAt?: string | null;
}

export interface InventoryItem {
  id: string;
  shopId: string;
  name: string;
  price?: number | null;
  quantity: number;
  unit: string;
  inStock: boolean;
  brand?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export type RequestStatusFE = "matching" | "offers" | "completed" | "no_match";

export interface CustomerRequest {
  id: string;
  product: string;
  categoryKey: string;
  backendCategory: string;
  subCategory?: string | null;
  quantity: number;
  unit: string;
  confidence: number;
  status: RequestStatusFE;
  backendStatus: string;
  inputType: "text" | "voice" | "image" | string;
  rawText?: string | null;
  matchedCount: number;
  createdAt?: string | null;
}

export interface Offer {
  id: string;
  requestId: string;
  shopId: string;
  status: "pending" | "accepted" | "declined" | "expired";
  price?: number | null;
  distanceMeters: number;
  matchScore: number;
  hasInventoryHint: boolean;
  createdAt?: string | null;
  respondedAt?: string | null;
  shop?: Shop;
  request?: CustomerRequest;
}

export interface TrendingProduct {
  product: string;
  categoryKey: string;
  requests: number;
  unavailable: number;
}

export interface CreateRequestResult {
  requestId: string;
  intent: {
    product: string;
    categoryKey: string;
    backendCategory: string;
    subCategory?: string | null;
    quantity: number;
    unit: string;
    confidence: number;
  };
  candidates: Array<{
    shopId: string;
    shop: Shop;
    distanceMeters: number;
    matchScore: number;
    hasInventoryHint: boolean;
    knownPrice?: number | null;
  }>;
}

/** Inbox rows always carry their parent request. */
export type InboxItem = Offer & { request: CustomerRequest };

export interface KhataEntry {
  id: string;
  customerName: string;
  amount: number;
  direction: "udhaar" | "jama";
  note?: string | null;
  createdAt?: string | null;
}

/* ------------------------------------------------------------------ hooks */

export const api = {
  auth: {
    me: Q<void, WebUser | null>("auth.me", () => apiFetch("/auth/me")),
    login: M<{ email: string; password: string }, { user: WebUser }>((body) =>
      apiFetch("/auth/login", { method: "POST", body }),
    ),
    register: M<
      { fullName: string; email: string; phone?: string; password: string; role?: string },
      { user: WebUser }
    >((body) => apiFetch("/auth/register", { method: "POST", body })),
    logout: M<void, { ok: boolean }>(() =>
      apiFetch("/auth/logout", { method: "POST" }),
    ),
    telegramLink: M<void, { linked: boolean; url?: string; telegramUserId?: number }>(
      () => apiFetch("/auth/telegram-link"),
    ),
  },

  profile: {
    get: Q<void, { appRole: "customer" | "shopkeeper" | null; shop: Shop | null }>(
      "profile.get",
      () => apiFetch("/profile"),
    ),
    setRole: M<{ role: "customer" | "shopkeeper" }, { ok: boolean }>((body) =>
      apiFetch("/profile/role", { method: "POST", body }),
    ),
    claimableShops: Q<void, Shop[]>("profile.claimableShops", () =>
      apiFetch("/profile/claimable-shops"),
    ),
    claimShop: M<{ shopId: string }, { ok: boolean }>((body) =>
      apiFetch("/profile/claim-shop", { method: "POST", body }),
    ),
    createShop: M<
      {
        name: string;
        categoryKey: string;
        categoryLabel?: string;
        address?: string;
        phone?: string;
        lat: number;
        lng: number;
      },
      { ok: boolean }
    >((body) => apiFetch("/profile/create-shop", { method: "POST", body })),
  },

  catalog: {
    shops: Q<{ lat?: number; lng?: number; category?: string; query?: string }, Shop[]>(
      "catalog.shops",
      (input) => apiFetch(`/catalog/shops${qs(input ?? {})}`),
    ),
    shop: Q<{ id: string; lat?: number; lng?: number }, Shop & { inventory: InventoryItem[] }>(
      "catalog.shop",
      (input) => apiFetch(`/catalog/shops/${input.id}${qs({ lat: input.lat, lng: input.lng })}`),
    ),
    priceSearch: Q<
      { query: string; lat?: number; lng?: number },
      Array<{ item: InventoryItem; shop: Shop; distanceMeters: number | null }>
    >("catalog.priceSearch", (input) => apiFetch(`/catalog/price-search${qs(input)}`)),
    trending: Q<void, TrendingProduct[]>("catalog.trending", () =>
      apiFetch("/catalog/trending"),
    ),
  },

  request: {
    create: M<
      { rawText: string; inputType?: string; lat: number; lng: number },
      CreateRequestResult
    >((body) => apiFetch("/requests", { method: "POST", body })),
    mine: Q<void, CustomerRequest[]>("request.mine", () => apiFetch("/requests/mine")),
    detail: Q<{ id: string }, { request: CustomerRequest; offers: Offer[] }>(
      "request.detail",
      (input) => apiFetch(`/requests/${input.id}`),
    ),
    choose: M<{ offerId: string }, { ok: boolean }>((body) =>
      apiFetch("/requests/choose", { method: "POST", body }),
    ),
  },

  merchant: {
    myShop: Q<void, Shop>("merchant.myShop", () => apiFetch("/merchant/shop")),
    inbox: Q<void, InboxItem[]>("merchant.inbox", () => apiFetch("/merchant/inbox")),
    respond: M<{ offerId: string; accept: boolean; price?: number }, { ok: boolean }>(
      (body) => apiFetch("/merchant/respond", { method: "POST", body }),
    ),
    inventory: Q<void, InventoryItem[]>("merchant.inventory", () =>
      apiFetch("/merchant/inventory"),
    ),
    addItem: M<
      { name: string; price: number; quantity: number; unit: string },
      { ok: boolean }
    >((body) => apiFetch("/merchant/inventory", { method: "POST", body })),
    updateItem: M<
      { id: string; name?: string; price?: number; quantity?: number; unit?: string },
      { ok: boolean }
    >(({ id, ...patch }) =>
      apiFetch(`/merchant/inventory/${id}`, { method: "PATCH", body: patch }),
    ),
    toggleStock: M<{ id: string }, { ok: boolean; inStock: boolean }>((body) =>
      apiFetch(`/merchant/inventory/${body.id}/toggle`, { method: "POST" }),
    ),
    removeItem: M<{ id: string }, { ok: boolean }>((body) =>
      apiFetch(`/merchant/inventory/${body.id}`, { method: "DELETE" }),
    ),
    khata: Q<void, { entries: KhataEntry[]; udhaar: number; jama: number; outstanding: number }>(
      "merchant.khata",
      () => apiFetch("/merchant/khata"),
    ),
    addKhata: M<
      { customerName: string; amount: number; direction: "udhaar" | "jama"; note?: string },
      { ok: boolean }
    >((body) => apiFetch("/merchant/khata", { method: "POST", body })),
    demand: Q<
      void,
      {
        products: TrendingProduct[];
        categories: Array<{ categoryKey: string; requests: number }>;
        total: number;
      }
    >("merchant.demand", () => apiFetch("/merchant/demand")),
  },

  useUtils: () => {
    const qc = useQueryClient();
    const byKey = (key: string) => () => qc.invalidateQueries({ queryKey: [key] });
    return {
      invalidate: () => qc.invalidateQueries(),
      profile: { get: { invalidate: byKey("profile.get") } },
      merchant: {
        inbox: { invalidate: byKey("merchant.inbox") },
        inventory: { invalidate: byKey("merchant.inventory") },
        khata: { invalidate: byKey("merchant.khata") },
      },
    };
  },
};
