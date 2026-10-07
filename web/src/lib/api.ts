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
  phone_verified?: boolean;
  trusted_contact_phone?: string | null;
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
  shopfrontPhotoUrl?: string | null;
  verificationStatus?: "pending" | "photo_pending" | "verified" | "rejected";
  photoUploadedAt?: string | null;
  photoApprovedAt?: string | null;
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
  imageUrl?: string | null;
  imageSource?: "manual" | "ai_fetched" | "none";
  createdAt?: string | null;
  updatedAt?: string | null;
}

/** Product card as returned by /catalog/products — an inventory item joined
 * with shop info + distance. Used by the Browse page (grid + map view). */
export interface ProductCard {
  id: string;
  shopId: string;
  name: string;
  price?: number | null;
  unit: string;
  quantity: number;
  inStock: boolean;
  brand?: string | null;
  imageUrl?: string | null;
  imageSource?: "manual" | "ai_fetched" | "none";
  shop: {
    id: string;
    name: string;
    categoryKey: string;
    categoryLabel: string;
    address?: string | null;
    phone?: string | null;
    lat?: number | null;
    lng?: number | null;
    isVerified: boolean;
    shopfrontPhotoUrl?: string | null;
    distanceMeters?: number | null;
  };
}

export interface ProductsResponse {
  products: ProductCard[];
  page: number;
  limit: number;
  total: number;
  hasMore: boolean;
}

export interface RecommendationsResponse {
  recommendations: ProductCard[];
  dominantCategory?: string | null;
  pickedShopCount?: number;
  reason?: string;
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
  selectedMatchId?: string | null;
  selectedAt?: string | null;
  offerWindowExpiresAt?: string | null;
  customerNotifiedAt?: string | null;
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
  scoreBreakdown?: Record<string, number>;
  hasInventoryHint: boolean;
  source?: "real" | "demo_simulated";
  isDemoSimulated?: boolean;
  createdAt?: string | null;
  notifiedAt?: string | null;
  respondedAt?: string | null;
  responseSeconds?: number | null;
  inventoryUpdatedAt?: string | null;
  trust?: TrustInfo | null;
  freshness?: FreshnessInfo | null;
  whyRecommended?: string[];
  shop?: Shop;
  request?: CustomerRequest;
}

/** Explainable merchant trust score. Computed server-side from shop counters
 * + recent response-time history. New shops get a neutral 50/100 — never a
 * low score that would unfairly hurt a brand-new shop. */
export interface TrustInfo {
  responseRate: number;
  acceptanceRate: number;
  averageResponseSeconds: number | null;
  reliabilityScore: number;
  label: string;
  isNewMerchant: boolean;
  sampleSize: number;
  isVerified: boolean;
  reason: string;
}

/** Freshness signals for an offer — proves the data shown is current, never
 * presents stale information as guaranteed current availability. */
export interface FreshnessInfo {
  statusLabel: string;
  priceLabel: string;
  respondedSecondsAgo: number | null;
}

export interface TrendingProduct {
  product: string;
  categoryKey: string;
  requests: number;
  unavailable: number;
}

export interface UniqueRequestedProduct extends TrendingProduct {
  category?: string | null;
  uniqueRequests: number;
  available: number;
  unavailableRate: number;
  averageSearchDistanceMeters?: number | null;
  last_seen?: string | null;
}

/** Honest demand metrics — distinguishes unique customer requests from
 * merchant response attempts (one request with 5 merchant YESes is still
 * 1 unique customer request, never 5). */
export interface HonestDemandStats {
  uniqueCustomerRequests: number;
  requestsMatched: number;
  requestsUnmatched: number;
  zeroInventoryMatches: number;
  successfulCustomerSelections: number;
  merchantResponseAttempts: number;
  availableResponses: number;
  unavailableResponses: number;
  pendingResponses: number;
  unavailableRate: number;
  avgSearchDistanceMeters?: number | null;
  periodDays: number;
}

/** Stock opportunity recommendation. Score is deterministic (no ML), every
 * input is shown to the merchant, recommended quantity is clearly labelled
 * as a heuristic — never a sales forecast. */
export interface StockOpportunity {
  product: string;
  category?: string | null;
  uniqueRequests: number;
  unavailableRequests: number;
  availableRequests: number;
  unavailableRate: number;
  trend: "rising" | "stable" | "falling";
  trendRatio?: number | null;
  averageSearchDistanceMeters?: number | null;
  nearbyInventoryCoverage: number;
  merchantCategoryAffinity: number;
  merchantAlreadyStocks: boolean;
  opportunityScore: number;
  recommendedQuantity: number;
  reason: string;
  breakdown?: Record<string, number> | null;
}

/** Privacy-safe demand heatmap bucket. Each point represents a *bucket* of
 * demand (not an individual customer), snapped to a ~300m grid centre. */
export interface HeatmapPoint {
  latitude: number;
  longitude: number;
  product: string;
  category?: string | null;
  uniqueRequests: number;
  unavailableRequests: number;
  unavailableRate: number;
  periodDays: number;
}

export interface NeighborhoodInsight {
  product: string;
  productKey?: string;
  category?: string | null;
  uniqueRequests: number;
  unavailableRequests: number;
  availableRequests: number;
  unavailableRate: number;
  averageSearchDistanceMeters?: number | null;
  radius: string;
  reason: string;
}

export interface ImpactMetrics {
  uniqueCustomerRequests: number;
  requestsMatched: number;
  requestsUnmatched: number;
  zeroInventoryMatches: number;
  successfulCustomerSelections: number;
  merchantResponseAttempts: number;
  availableResponses: number;
  unavailableResponses: number;
  merchantResponseRate: number;
  avgSearchDistanceMeters?: number | null;
  estimatedSearchDistanceSavedMeters: number;
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
    provider?: string;
    isRuleBased?: boolean;
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

/* ------------------------------------------------------------------ chat + safety */

export interface ChatMessage {
  id: string;
  chatId: string;
  requestId: string;
  senderId: string;
  senderRole: "customer" | "shopkeeper" | "system";
  text: string;
  kind: "text" | "system";
  createdAt: string;
  readAt?: string | null;
}

export interface Conversation {
  id: string;
  requestId: string;
  customerId: string;
  shopId: string;
  status: "active" | "closed";
  lastMessageAt?: string | null;
  lastMessagePreview?: string | null;
  lastMessageSenderRole?: "customer" | "shopkeeper" | "system" | null;
  unreadCount: number;
  createdAt?: string | null;
}

export interface PendingShop {
  id: string;
  shopName: string;
  category?: string | null;
  phone?: string | null;
  address?: string | null;
  shopfrontPhotoUrl?: string | null;
  photoUploadedAt?: string | null;
  photoBrowserLocation?: { lat: number; lng: number } | null;
  photoExifLocation?: { lat: number; lng: number } | null;
  verificationStatus: string;
}

export type FlagReason =
  | "didnt_honor_price"
  | "felt_unsafe"
  | "shop_doesnt_exist"
  | "harassment_in_chat"
  | "other";

/* ------------------------------------------------------------------ hooks */

export const api = {
  auth: {
    me: Q<void, WebUser | null>("auth.me", () => apiFetch("/auth/me")),
    sendOtp: M<{ phone: string }, { sent: boolean; dev_otp?: string; phone?: string }>(
      (body) => apiFetch("/auth/send-otp", { method: "POST", body }),
    ),
    verifyOtp: M<{ phone: string; code: string }, { ok: boolean; phone?: string; user_id?: string }>(
      (body) => apiFetch("/auth/verify-otp", { method: "POST", body }),
    ),
    login: M<{ email: string; password: string }, { user: WebUser }>((body) =>
      apiFetch("/auth/login", { method: "POST", body }),
    ),
    register: M<
      {
        fullName: string;
        email: string;
        phone: string;
        password: string;
        role: "customer" | "shopkeeper";
        otp: string;
      },
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
    get: Q<
      void,
      {
        appRole: "customer" | "shopkeeper" | null;
        shop: Shop | null;
        location: { lat: number; lng: number } | null;
      }
    >(
      "profile.get",
      () => apiFetch("/profile"),
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
    updateShopLocation: M<{ lat: number; lng: number }, { ok: boolean }>((body) =>
      apiFetch("/profile/shop/location", { method: "PATCH", body }),
    ),
    updateLocation: M<{ lat: number; lng: number }, { ok: boolean }>((body) =>
      apiFetch("/profile/location", { method: "POST", body }),
    ),
    setTrustedContact: M<{ phone: string }, { ok: boolean }>((body) =>
      apiFetch("/profile/trusted-contact", { method: "PATCH", body }),
    ),
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
    products: Q<
      {
        lat?: number;
        lng?: number;
        category?: string;
        query?: string;
        sort?: "nearest" | "cheapest" | "newest";
        page?: number;
        limit?: number;
      },
      ProductsResponse
    >("catalog.products", (input) => apiFetch(`/catalog/products${qs(input ?? {})}`)),
    recommendations: Q<
      { lat?: number; lng?: number; limit?: number },
      RecommendationsResponse
    >("catalog.recommendations", (input) =>
      apiFetch(`/catalog/recommendations${qs(input ?? {})}`),
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
    offers: Q<{ id: string }, { offers: Offer[] }>(
      "request.offers",
      (input) => apiFetch(`/requests/${input.id}/offers`),
    ),
    choose: M<{ offerId: string }, { ok: boolean; selectedMatchId?: string; shopId?: string }>(
      (body) => apiFetch("/requests/choose", { method: "POST", body }),
    ),
    reserve: M<
      { itemId: string; quantity?: number; lat: number; lng: number },
      { ok: boolean; requestId: string; notified: boolean }
    >((body) => apiFetch("/requests/reserve", { method: "POST", body })),
    chatHistory: Q<
      { id: string; since?: string },
      { messages: ChatMessage[]; since: string | null }
    >("request.chatHistory", (input) => {
      const q = input.since ? `?since=${encodeURIComponent(input.since)}` : "";
      return apiFetch(`/requests/${input.id}/chat${q}`);
    }),
    sendChatMessage: M<{ requestId: string; text: string }, ChatMessage>(
      ({ requestId, text }) =>
        apiFetch(`/requests/${requestId}/chat/messages`, {
          method: "POST",
          body: { text },
        }),
    ),
    flag: M<
      { requestId: string; reason: FlagReason; note?: string },
      { ok: boolean; auto_suspended?: boolean }
    >(({ requestId, ...rest }) =>
      apiFetch(`/requests/${requestId}/flag`, { method: "POST", body: rest }),
    ),
    panic: M<
      { requestId?: string; latitude: number; longitude: number },
      { ok: boolean; alerted: boolean; mode: string; message?: string }
    >((body) => apiFetch("/panic", { method: "POST", body })),
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
      { name: string; price: number; quantity: number; unit: string; imageUrl?: string },
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
    planFromOpportunity: M<
      { product: string; quantity: number; unit: string; price?: number },
      { ok: boolean; productId?: string }
    >((body) => apiFetch("/merchant/inventory/plan", { method: "POST", body })),
    uploadShopfrontPhoto: M<
      { file: File; browserLat: number; browserLng: number },
      {
        shopfrontPhotoUrl: string;
        verificationStatus: string;
        photoUploadedAt?: string;
      }
    >(async ({ file, browserLat, browserLng }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("browser_lat", String(browserLat));
      form.append("browser_lng", String(browserLng));
      // Note: apiFetch sets Content-Type to JSON; for multipart we need to
      // let the browser set the boundary. Hand-rolled fetch here.
      const res = await fetch(`${API_BASE}/merchant/shop/shopfront-photo`, {
        method: "POST",
        credentials: "include",
        body: form,
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const detail = (data as { detail?: unknown } | null)?.detail;
        const message = typeof detail === "string" ? detail
          : `Request failed (${res.status})`;
        throw new ApiError(res.status, message);
      }
      return data as {
        shopfrontPhotoUrl: string;
        verificationStatus: string;
        photoUploadedAt?: string;
      };
    }),
    conversations: Q<void, { conversations: Conversation[] }>("merchant.conversations", () =>
      apiFetch("/merchant/conversations"),
    ),
    conversationHistory: Q<
      { requestId: string; since?: string },
      { messages: ChatMessage[]; since: string | null }
    >("merchant.conversationHistory", (input) => {
      const q = input.since ? `?since=${encodeURIComponent(input.since)}` : "";
      return apiFetch(`/merchant/conversations/${input.requestId}${q}`);
    }),
    sendChatMessage: M<{ requestId: string; text: string }, ChatMessage>(
      ({ requestId, text }) =>
        apiFetch(`/merchant/conversations/${requestId}/messages`, {
          method: "POST",
          body: { text },
        }),
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
      { days?: number },
      {
        products: UniqueRequestedProduct[];
        categories: Array<{ categoryKey: string; requests: number }>;
        total: number;
        honestStats: HonestDemandStats;
        isDemoData: boolean;
        days: number;
      }
    >("merchant.demand", (input) => apiFetch(`/merchant/demand${qs(input ?? {})}`)),
    opportunities: Q<
      { days?: number; limit?: number },
      {
        opportunities: StockOpportunity[];
        isDemoData: boolean;
        radiusMeters?: number;
        days: number;
        reason?: string;
      }
    >("merchant.opportunities", (input) =>
      apiFetch(`/merchant/demand/opportunities${qs(input ?? {})}`),
    ),
    heatmap: Q<
      { days?: number; category?: string; limit?: number },
      {
        points: HeatmapPoint[];
        isDemoData: boolean;
        bucketMeters: number;
        radiusMeters: number;
        days: number;
        privacyNote: string;
        reason?: string;
      }
    >("merchant.heatmap", (input) =>
      apiFetch(`/merchant/demand/heatmap${qs(input ?? {})}`),
    ),
    impact: Q<
      { days?: number },
      {
        metrics: ImpactMetrics;
        neighborhoodInsight: NeighborhoodInsight | null;
        isDemoData: boolean;
        days: number;
      }
    >("merchant.impact", (input) => apiFetch(`/merchant/demand/impact${qs(input ?? {})}`)),
  },

  admin: {
    pendingShops: Q<void, { shops: PendingShop[] }>("admin.pendingShops", () =>
      apiFetch("/admin/shops/pending"),
    ),
    approveShop: M<{ shopId: string }, { shopId: string; isVerified: boolean; approvedAt: string }>(
      ({ shopId }) =>
        apiFetch(`/admin/shops/${shopId}/approve`, { method: "POST", body: {} }),
    ),
    rejectShop: M<
      { shopId: string; reason?: string },
      { shopId: string; isVerified: boolean; reason?: string }
    >(({ shopId, ...rest }) =>
      apiFetch(`/admin/shops/${shopId}/reject`, { method: "POST", body: rest }),
    ),
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
        demand: { invalidate: byKey("merchant.demand") },
        opportunities: { invalidate: byKey("merchant.opportunities") },
        heatmap: { invalidate: byKey("merchant.heatmap") },
        impact: { invalidate: byKey("merchant.impact") },
        conversations: { invalidate: byKey("merchant.conversations") },
        myShop: { invalidate: byKey("merchant.myShop") },
      },
      admin: { pendingShops: { invalidate: byKey("admin.pendingShops") } },
      request: {
        detail: (id: string) => qc.invalidateQueries({ queryKey: ["request.detail", { id }] }),
        offers: (id: string) => qc.invalidateQueries({ queryKey: ["request.offers", { id }] }),
        chatHistory: (id: string) => qc.invalidateQueries({ queryKey: ["request.chatHistory", { id }] }),
      },
    };
  },
};
