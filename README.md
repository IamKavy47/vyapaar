# Vyapaar-Mitra

**A neighborhood demand intelligence network that helps customers find products now and helps merchants understand what their neighborhood needs next.**

> _"Don't force the shopkeeper to learn software. Make the software understand the shopkeeper."_

Problem statement: **MU-PS-008 — The Small-Shop Digital Gap · Local Commerce Enablement**

---

## TL;DR

Vyapaar-Mitra connects a customer who needs something _right now_ with a shop 200 metres away that probably has it — over Telegram or the web, in Hindi/Hinglish, by voice, text, or photo. The merchant does not need an app, a catalogue, or a single uploaded product. A YES/NO button is the whole interface.

Then the loop closes: every YES/NO becomes demand intelligence. The shopkeeper sees what their neighborhood keeps asking for and cannot find. The neighborhood's demand heatmap shows where customers are asking and where shops are unavailable.

- **Zero-inventory matching** — a shop with no catalogue upload is still matched, because we reason over category, capabilities, location, and history.
- **Multi-offer compare** — the customer sees ALL accepted offers (not just the first YES), sorts by best/nearest/cheapest/reliable/fastest, picks exactly one (atomic).
- **Demand intelligence** — explainable stock opportunity scoring (deterministic, no ML), privacy-safe heatmap, honest metrics that distinguish unique customer requests from merchant response attempts.
- **Safety & verification** — phone OTP for both sides, geotagged shopfront photo (browser GPS + JPEG EXIF cross-check), admin approval gate, in-app chat (customer phone never exposed), panic button, report flow.
- **Deterministic demo** — runs without AI keys, without Telegram polling, without real merchant taps. The flagship Teflon Tape scenario plays end-to-end with `Demo-simulated` labels so judges never confuse it with real activity.

```mermaid
flowchart TD
    A[Customer asks<br/>text / voice / photo] --> B[AI understands intent<br/>Gemini → Groq → GPT-OSS]
    B --> C[Zero-inventory matching<br/>500m → 1km → 2km → 5km]
    C --> D[Nearby merchants respond<br/>Telegram YES/NO + price]
    D --> E[Customer compares offers<br/>sort: best / nearest / cheapest / reliable / fastest]
    E --> F[Customer picks ONE shop<br/>atomic, exactly-once]
    F --> G[YES/NO becomes demand intelligence]
    G --> H[Merchants see Stock Opportunities<br/>explainable score, no ML]
    G --> I[Demand heatmap<br/>privacy-safe ~300m buckets]
    H --> J[Merchant adds to inventory plan<br/>manual confirm, no auto-stock]
    I --> J
```

---

## 1. The problem

Every "digitise local commerce" product starts by asking the shopkeeper to upload inventory. That's exactly where they drop off. A kirana or hardware shop owner has thousands of SKUs, no barcodes, no time, and no reason to trust that the work pays off. So catalogues stay empty, and empty catalogues mean the shop is invisible.

Meanwhile the customer's actual question was never about a catalogue. It was: _"Who near me has this?"_

And once you've answered that, the next question is: _"What does my neighborhood keep asking for and not finding?"_ — because the shopkeeper has no way to know.

Vyapaar-Mitra answers both, with the same data, in one product loop.

---

## 2. Architecture

```mermaid
flowchart LR
    subgraph Clients
        TG[Telegram bot<br/>customer + merchant]
        WEB[React/Vite PWA<br/>multi-offer compare +<br/>demand intelligence +<br/>admin verification UI]
    end

    subgraph Backend
        API[FastAPI<br/>/api/v1 JSON REST]
        SRV[Services layer<br/>search · matching · demand<br/>trust · opportunity · chat<br/>verification · demo]
        AI[AI providers<br/>Gemini · Groq · GPT-OSS<br/>Sarvam STT]
    end

    subgraph Data
        MONGO[(MongoDB<br/>12 collections<br/>2dsphere geo +<br/>unique indexes)]
        FILES[Static files<br/>shopfront photos]
    end

    TG <--> API
    WEB <--> API
    API --> SRV
    SRV --> AI
    SRV --> MONGO
    SRV --> FILES
```

**Architectural rule:** Telegram handlers contain _no_ business logic. Everything lives in `app/services/`. The React web app plugs into those same services through `app/api/web.py`, so web and Telegram share one database and one matching engine.

- A customer searching on the **web** triggers the same zero-inventory matching, and merchants still get the request on **Telegram** (plus their web inbox).
- A merchant answering YES/NO in the **web inbox** runs the same `handle_merchant_response` path as the bot — demand events are recorded and the customer is notified on Telegram if they linked their account.
- Web users connect their Telegram from **Account → Connect Telegram** (a one-time `t.me` deep link consumed by the bot's `/start web_<token>` handler).

FastAPI also serves the legacy HTML auth pages under `/auth`, and when `web/dist` exists it serves the built React app at `/` with SPA fallback — one process for frontend, REST API, bot, and admin verification.

---

## 3. The hackathon upgrade — what's new

The product has been upgraded from _"an AI tool that helps customers find nearby shops"_ into a **self-improving local commerce network**. The core architecture (FastAPI + MongoDB + Telegram bot + React/Vite) is unchanged; new product capabilities are layered on top of the existing services.

| Priority | Feature | Where it lives |
|---|---|---|
| 1 | Multi-offer compare + atomic exactly-one customer selection | `search_service.handle_merchant_response` + `select_offer` + `OfferCard.tsx` |
| 2 | Stock opportunity recommendations (deterministic, no ML) | `opportunity_service.opportunity_score` |
| 3 | Privacy-safe demand heatmap (~300m buckets, deduped by request_id) | `demand_engine.demand_heatmap` + `DemandHeatmap.tsx` |
| 4 | Honest demand metrics (unique requests vs merchant responses) | `demand_engine.honest_demand_stats` |
| 5 | Trust + freshness labels (new-merchant guard, stale flagging) | `trust_service.compute_trust_score` |
| 6 | Judge-friendly impact dashboard | `/merchant/impact` page |
| 7 | "What would improve this neighborhood most?" insight | `demand_engine.neighborhood_insight` |
| 8 | Deterministic demo mode (Teflon Tape scenario) | `demo_service.maybe_schedule_demo_responses` |
| 9 | Explainability ("why was this shop recommended?" / "why is this a stock opportunity?") | `opportunity_service.explain_match` |
| 10 | Data quality + privacy safeguards (unique indexes, owner checks, demo labels) | `database/indexes.py` + per-endpoint authz |
| Safety | Phone OTP for both sides + geotagged shopfront photo + admin approval + `is_verified` gate + in-app chat + report + panic | `auth_service.send_otp` + `verification_service` + `chat_service` |

---

## 4. Multi-offer compare + exactly-one selection

The customer now sees ALL shops that accepted the request, not only the first one that replies. When the first merchant YES arrives, a configurable **offer window** (`OFFER_WINDOW_SECONDS=20`) starts — other merchants have a chance to respond before the customer is notified. When the window elapses the customer gets ONE batched Telegram notification listing every accepted offer, plus a "Compare offers" button that opens the web compare screen.

```mermaid
sequenceDiagram
    participant C as Customer
    participant API as FastAPI
    participant M as Merchant(s)
    participant DB as MongoDB

    C->>API: POST /requests (text/voice/photo)
    API->>DB: insert product_request
    API->>M: Telegram notify N candidates
    M->>API: mr:yes (first YES, 5s)
    API->>DB: set offer_window_expires_at = now + 20s
    Note over API: schedule asyncio flush task
    M->>API: mr:yes (second YES, 12s) — accumulated, no notify
    M->>API: mr:no (third shop, 18s) — recorded as demand event
    Note over API: window elapses at 20s
    API->>C: ONE batched message: "2 offers available"
    C->>API: GET /requests/{id} → offers list with trust + freshness + why
    C->>API: POST /requests/choose {offerId}
    API->>DB: atomic update_one({selected_match_id: None}) — exactly once
    API->>M: "Customer ne aapko chuna!" to winner
    API->>M: "Customer chose another shop" to losers
    API->>C: Final selection message with shop details + map pin
```

The web compare card shows, per accepted offer: shop name + verified tick, distance + address, merchant-confirmed price (or "Price not provided" — never invented), response time, reliability/trust indicator, inventory freshness, match score, short "Why this shop?" explanation, address + phone (when available) + Google Maps directions link, and a Choose button.

**Sort options:** Best overall · Nearest · Lowest price · Most reliable · Fastest response.

**Exactly-one enforcement:** the customer can pick exactly one offer. The selection is atomic — `select_offer` issues an `update_one` with a filter on `selected_match_id == None`, so a concurrent second selection attempt is rejected with HTTP 409. The selection persists across refresh; a late merchant response (after the customer picked) does NOT overwrite the chosen offer — it gets added to the demand intelligence with `status=EXPIRED` on the match row.

---

## 5. Safety & verification — the 4-layer stack

A hyperlocal commerce product in India that tells a customer _"walk to this shop 600m away"_ is a real safety product, not just a tech demo. Scammers, stalkers, and worse-case kidnappers are real threats. The 4-layer stack below makes it expensive and risky for a bad actor to operate.

```mermaid
sequenceDiagram
    participant S as Shopkeeper (friend)
    participant API as FastAPI
    participant A as Admin (you, hackathon)
    participant C as Customer

    Note over S,API: Layer 1 — Phone OTP
    S->>API: POST /auth/send-otp {phone}
    API-->>S: {dev_otp: "123456"} (stub mode)
    S->>API: POST /auth/register {…, otp: "123456"}
    API->>API: consume_otp → mark_phone_verified
    Note over API: phone_verified = True

    Note over S,API: Layer 2 — Geotagged shopfront photo
    S->>API: POST /merchant/shop/shopfront-photo (multipart)
    Note over API: parse JPEG EXIF GPS via Pillow<br/>cross-check browser GPS vs EXIF GPS<br/>vs registered shop location (≤200m)
    API->>API: save to app/static/shop_photos/{shop_id}.jpg<br/>set verification_status = photo_pending

    Note over A,API: Layer 3 — Manual admin approval
    A->>API: GET /admin/shops/pending
    API-->>A: shop photo + both GPS readings + Maps deep-links
    A->>API: POST /admin/shops/{id}/approve
    API->>API: is_verified = True, verification_status = verified

    Note over C,API: Layer 4 — is_verified gate in find_candidates
    C->>API: POST /requests {product, lat, lng}
    API->>API: $geoNear query includes is_verified: True
    Note over API: unverified shops are invisible to customers

    Note over C,API: Privacy + safety net
    C->>API: POST /requests/{id}/chat/messages — in-app, phone hidden
    C->>API: POST /requests/{id}/flag {reason: "felt_unsafe"} → auto-suspend
    C->>API: POST /panic {lat, lng} → audit + SMS trusted contact
```

### The four layers

| Layer | What it does | Cost to a bad actor |
|---|---|---|
| 1. Phone OTP | 6-digit numeric OTP, hashed at rest (sha256), TTL 5 min, 5-attempt cap. Mandatory for both customers and shopkeepers before any action. | Needs a real SIM per shop — real cost per attempt. |
| 2. Geotagged shopfront photo | Shopkeeper takes a photo of their shop exterior from inside the PWA (`<input capture="environment">`). Browser GPS captured at the same moment, AND the JPEG's EXIF GPS is parsed server-side via Pillow. Both must be within ~200m of the registered shop location. | Must physically visit a real market and photograph someone else's shopfront, hoping the real owner doesn't also register. |
| 3. Manual admin approval | The shop goes into `verification_status=photo_pending`. An admin (you, for the hackathon) reviews the photo + both GPS readings at `/admin/shops/pending` and taps "Approve & make visible" — flipping `is_verified=True`. | A human looks at the photo. Social engineering possible but expensive. |
| 4. `is_verified` gate in `find_candidates` + `web_catalog_shops` | Unverified shops are NEVER matched to customers. The catalog endpoint also filters them out. | (Reinforces layers 1–3.) |

### Customer privacy + safety

- **In-app chat (Rapido-style)** — customer ↔ shopkeeper chat scoped to a `request_id`, anonymised. The customer's phone is NEVER in the chat payload. REST polling at 1.5s (no WebSocket — simpler, works through any corporate firewall). All messages logged server-side as an admissible audit trail.
- **Report button** on every offer card — 5 reason codes (`didnt_honor_price`, `felt_unsafe`, `shop_doesnt_exist`, `harassment_in_chat`, `other`). `felt_unsafe` and `shop_doesnt_exist` auto-suspend the shop pending review.
- **Panic button** in the "Deal pakki!" panel — records an audit event with the customer's current location + the chosen shop's details. In production, SMSes the trusted contact; in stub mode, logs to console.
- **Share-trip button** — deep-links to Google Maps so the customer can start live-trip sharing with their family.
- **Trusted contact** — customer sets a phone number in Account → used by the panic button.

### What this stack achieves

A scammer / kidnapper needs:
- A real SIM per shop.
- A real shopfront photo at the registered location (or a successful shopfront spoof).
- A manual review pass by an admin.
- To start with a yellow "New merchant · 50/100" badge that puts customers on guard.
- The customer to share their live trip + have a panic button + a trusted contact that's alerted.

This is roughly the safety bar Uber/Ola/Swiggy meet in India. Not perfect — you cannot 100% prevent kidnapping with software — but crossable.

---

## 6. Demand intelligence — the self-improving layer

Every YES/NO a merchant records becomes a demand signal. Over time, the shopkeeper learns what the neighborhood keeps asking for and cannot find.

```mermaid
flowchart LR
    subgraph Inputs
        PR[product_requests<br/>1 row per customer ask]
        MM[merchant_matches<br/>1 row per merchant per request<br/>unique index on (request_id, merchant_id)]
        DE[demand_events<br/>1 row per merchant response<br/>unique index on (request_id, merchant_id)]
        INV[inventory_items]
    end

    subgraph Honest aggregations
        UUR[top_unique_requested_products<br/>reads from product_requests]
        HDS[honest_demand_stats<br/>distinguishes unique customer<br/>requests from merchant responses]
        DH[demand_heatmap<br/>~300m buckets, deduped by request_id]
        NI[neighborhood_insight<br/>top unmet-demand product]
    end

    subgraph Recommendations
        OS[opportunity_score<br/>deterministic weighted sum<br/>no ML]
        EM[explain_match<br/>why-recommended bullets]
    end

    PR --> UUR
    PR --> HDS
    PR --> DH
    PR --> NI
    MM --> HDS
    DE -. legacy .-> UUR
    UUR --> OS
    INV --> OS
    MM --> EM
```

### Honest demand metrics (Priority 4)

A single customer request sent to 5 merchants is still 1 unique customer request, never 5. The merchant dashboard deliberately distinguishes the two:

```text
12 unique customers asked for Teflon Tape
29 merchant responses were collected
21 merchants said unavailable
8 merchants confirmed availability
```

The unique-request counts come from `product_requests`; the merchant-response counts come from `merchant_matches` (one row per merchant per request, with a unique index on `(request_id, merchant_id)` preventing double-counting even at the database level). `demand_events` has the same unique compound index as a defence-in-depth dedup guard.

### Stock opportunity scoring (Priority 2)

For each product the neighborhood keeps asking for, an opportunity score is computed deterministically (no ML model). The score is a weighted sum of normalised sub-scores, every weight is configurable, every input is shown to the merchant:

```text
opportunity_score = 0.30 × volume
                  + 0.25 × unmet
                  + 0.15 × trend
                  + 0.10 × search_difficulty
                  + 0.10 × coverage_gap
                  + 0.10 × category_fit
```

Example output (matches the spec):

```json
{
  "product": "PVC elbow joint",
  "category": "hardware",
  "uniqueRequests": 14,
  "unavailableRate": 0.79,
  "trend": "rising",
  "averageSearchDistanceMeters": 2100,
  "nearbyInventoryCoverage": 2,
  "opportunityScore": 87,
  "recommendedQuantity": 20,
  "reason": "14 nearby customers ne is product ki request bheji, 79% ko nahi mila, demand badh rahi hai..."
}
```

The **Add to inventory plan** button prefills the merchant's inventory form but does NOT add stock without confirmation.

### Privacy-safe demand heatmap (Priority 3)

A Leaflet map at `/merchant/impact` renders demand buckets centred on the merchant's shop. Every customer location is snapped to the centre of a ~300m grid cell (`HEATMAP_BUCKET_METERS=300`) before grouping, and demand is deduplicated by `request_id` so one request routed to 5 merchants still counts as one bucket entry. Customer identity is never exposed.

Filters: 7-day / 30-day / 90-day, plus optional category filter. Each circle is sized by unique request volume and coloured by unmet rate (red = high unmet, orange = some unmet, yellow = popular, green = healthy).

### Judge-friendly impact dashboard (Priority 6)

A new page at `/merchant/impact` shows in under 30 seconds:

- Unique customer requests · Requests matched · Zero-inventory matches · Successful customer selections
- Merchant response rate · Unmet demand discovered · Average search radius · Estimated search distance saved (clearly labelled as an estimate)
- "What would improve this neighborhood most?" — single top unmet-demand product with reason + suggested action

When `DEMO_MODE=true`, a `Demo data` sticker is shown everywhere so judges never confuse seeded activity with real production analytics.

---

## 7. Trust + freshness labels (Priority 5)

Every offer card shows two new badges:

- **Trust badge**: `Bharosemand · 84/100 — usually responds quickly` (or `New merchant` for shops with fewer than `TRUST_MIN_SAMPLE=5` responses, so a brand-new shop never gets unfairly penalised for missing history). Computed from response rate + acceptance rate + median response time + completed selections + verified status.
- **Freshness labels**: `Confirmed just now` · `Confirmed 5 minutes ago` · `Shop-listed stock` · `Inventory updated 2 days ago` · `Price confirmed by merchant` · `Price not provided`. Stale information is labelled stale, never presented as guaranteed current availability.

The trust score formula:

```text
reliability = 0.50 × response_rate
            + 0.25 × acceptance_rate
            + 0.15 × speed_score (median response seconds)
            + 0.10 × reputation (verified + completed selections)
```

Capped 0–100. New shops get a neutral 50/100 + the `New merchant` label, never a low score.

---

## 8. Explainability (Priority 9)

Every recommendation surfaces a short, plain-language explanation through the API and the UI:

- **Match**: _"Same category · Capability match · ~200m away · Strong response history · Verified shop"_
- **Stock opportunity**: _"14 nearby customer requests · 79% unavailable · Demand increased over the last 30 days · Only 2 nearby shops list this"_

Raw prompts, provider secrets, and internal stack traces are never exposed.

---

## 9. Deterministic demo mode (Priority 8)

When `DEMO_MODE=true` AND `RUN_BOT=false`, the `app/services/demo_service.py` schedules simulated merchant YES/NO responses for the flagship Teflon Tape scenario, each tagged `source="demo_simulated"` so the customer UI clearly labels them as `Demo-simulated merchant response`. The flow is fully deterministic — same scenario always schedules the same shops / prices / delays — so a hackathon demo always lands:

```mermaid
flowchart TD
    A["Customer: 'Mere sink ke neeche pipe leak ho raha hai, safed tape chahiye.'"] --> B[Intent: Teflon Tape / Hardware]
    B --> C1[Sharma Hardware · zero inventory · ~200m]
    B --> C2[Gupta Electricals · inventory listed ₹25 · ~650m]
    B --> C3[Raj Plumbing · capable · ~1.2km]

    C1 -->|"YES ₹30 (5s)"| D[Offer window expires at 20s]
    C2 -->|"YES ₹25 (12s)"| D
    C3 -->|"NO (18s)"| E[Demand intelligence event]

    D --> F[Customer compares 2 offers<br/>sorts by Lowest price → Gupta first]
    F --> G[Customer picks Gupta ₹25<br/>atomic exactly-one selection]
    G --> H["Customer opens chat<br/>(phone hidden) to coordinate"]

    E --> I[Raj Plumbing's demand dashboard<br/>shows Teflon Tape · opportunity 87/100]
    I --> J[Raj taps 'Add to inventory plan'<br/>prefill, no auto-stock]
```

AI providers, Sarvam STT, and Telegram are NOT required for the demo — the rule-based fallback parser handles intent extraction, and demo simulation handles merchant responses. The system never claims demo data is real.

---

## 10. The full demo script

The demo runs **without** live AI keys, **without** Telegram polling, and **without** anyone needing to type YES as a merchant — the deterministic demo simulator handles merchant responses automatically.

### Setup

```bash
git clone https://github.com/IamKavy47/vyapaar.git
cd vyapaar
cp .env.example .env    # DEMO_MODE=true, OTP_STUB_MODE=true, RUN_BOT=false (defaults)

docker compose up -d mongo    # or any local MongoDB on 27017
python -m scripts.seed_demo_data --reset    # seeds 11 shops + customer + admin

# Backend:
uvicorn app.main:app --reload --port 8000

# Other terminal — frontend:
cd web && npm install && npm run dev    # http://localhost:3000
```

### Demo accounts

| Role | Email | Password | What to demo |
|---|---|---|---|
| Admin (verifier) | `admin@vyapaar-mitra.local` | `VyapaarDemo123` | `/admin/shops/pending` — approve friends' shopfront photos |
| Customer | `demo.customer@vyapaar-mitra.local` | `VyapaarDemo123` | search → compare → pick → chat → impact dashboard |
| Shopkeeper (any) | `shop1@…` through `shop11@…` | `VyapaarDemo123` | inbox → respond → demand dashboard → stock opportunities |

### The 9-step end-to-end demo

1. **Friend** (Sharma Hardware) registers as a shopkeeper via the web app. Phone OTP step: phone → "Send OTP" → toast shows the OTP (stub mode) → paste → submit. Account created with `phone_verified=True`.
2. **Friend** logs in → Account page → **Shopfront Photo Capture** card. Taps "Capture photo" → rear camera opens → snaps shopfront → upload. Backend parses EXIF GPS + browser GPS, cross-checks both within 200m of the shop location.
3. **You** (admin) refresh `/admin/shops/pending` → see the friend's shop with photo + both GPS readings + Google Maps deep-links → tap **Approve & make visible** → `is_verified=True` flips → shop appears in customer searches.
4. **Customer** types in the search bar: _"Mere sink ke neeche pipe leak ho raha hai, safed tape chahiye."_
5. **AI / rule-based fallback** returns `Teflon Tape · hardware · plumbing` — labelled `via rules` (or `via gemini` if keys are set).
6. **Matching** expands 500m → 1km → 2km → 5km and finds 3 candidates (Sharma zero-inventory, Gupta inventory-listed, Raj capable). Demo simulator fires after delays: Sharma YES ₹30 (5s), Gupta YES ₹25 (12s), Raj NO (18s). Each card is clearly labelled `Demo-simulated merchant response`.
7. **Offer window** elapses → customer sees the live offers in the web UI. Sort by `Lowest price` puts Gupta (₹25) first. Customer picks Gupta → `Yahi final` → atomic exactly-one selection (HTTP 200). Try picking again → HTTP 409. The chosen card shows `✓ Aapne is dukaan ko chuna` and a green `Deal pakki!` panel.
8. **Merchant side**: switch to Raj Plumbing (`shop10@…`) → `/merchant/demand` shows Stock Opportunities. Teflon Tape at 87/100 with reason _"14 nearby customers ne is product ki request bheji, 79% ko nahi mila, demand badh rahi hai..."_ + **Add to inventory plan** button (prefills, doesn't auto-add).
9. **Impact dashboard**: `/merchant/impact` shows headline metrics (unique requests / matched / zero-inventory matches / successful selections / unmet demand discovered / estimated search distance saved), the "What would improve this neighborhood most?" insight (Teflon Tape), and the demand heatmap with red/orange/yellow demand buckets around the shop.

Closing line for judges:

> Traditional commerce asks: _What products has this shop uploaded?_
> Vyapaar-Mitra asks: _Who nearby can satisfy this customer's need — and what does the neighborhood need next?_

---

## 11. Installation

### Backend

```bash
git clone https://github.com/IamKavy47/vyapaar.git
cd vyapaar
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then fill in the keys below
```

### MongoDB setup

**Local:**
```bash
docker run -d --name vyapaar-mongo -p 27017:27017 -v vyapaar_data:/data/db mongo:7
# MONGODB_URI=mongodb://localhost:27017
```

**Atlas:** create a free M0 cluster, add your IP to the access list, then `MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net`.

Indexes (including 2dsphere + the new unique indexes on `demand_events` and `chats`) are created automatically on startup.

### Telegram setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token into `TELEGRAM_BOT_TOKEN`
3. Get your numeric id from [@userinfobot](https://t.me/userinfobot) → `ADMIN_TELEGRAM_IDS`

### AI providers (optional — rule-based fallback covers text input)

- **Sarvam AI** — Indian-language speech-to-text. Sign up at [sarvam.ai](https://www.sarvam.ai) → `SARVAM_API_KEY`. Model defaults to `saaras:v4`, language `hi-IN`.
- **Google Gemini** — intent, vision, structured extraction. [Google AI Studio](https://aistudio.google.com/app/apikey) → `GEMINI_API_KEY`. Default model `gemini-2.0-flash`.
- **Groq** — fast fallback inference. [console.groq.com](https://console.groq.com) → `GROQ_API_KEY`. Default model `llama-3.3-70b-versatile`.
- **GPT-OSS** — configurable open-weight provider via any OpenAI-compatible endpoint (Groq, vLLM, Ollama, LM Studio).

### Public URL for login links

Telegram login links must be reachable from the user's phone:
```bash
ngrok http 8000    # then PUBLIC_BASE_URL=https://<id>.ngrok-free.app
```

### New safety settings (env vars)

```env
# Phone OTP — stub mode returns the OTP in the API response for hackathon
OTP_STUB_MODE=true
OTP_TTL_MINUTES=5
OTP_LENGTH=6
SMS_GATEWAY=stub
# Production: SMS_GATEWAY=msg91, MSG91_AUTH_KEY=... (or twilio)

# Shopfront photo verification — both GPS signals must be within this many metres
SHOPFRONT_PHOTO_DISTANCE_METERS=200
SHOPFRONT_PHOTO_MAX_BYTES=5242880

# Customer safety — panic button SMS stubbed for the demo
PANIC_SMS_STUB=true
```

### Multi-offer window

```env
OFFER_WINDOW_SECONDS=20    # 0 = legacy per-YES notify, >0 = batched
```

### Trust + opportunity scoring

```env
TRUST_MIN_SAMPLE=5
TRUST_RESPONSE_TIME_FAST_SEC=60
TRUST_RESPONSE_TIME_OK_SEC=300
OPPORTUNITY_MIN_REQUESTS=3
OPPORTUNITY_RADIUS_METERS=3000
HEATMAP_BUCKET_METERS=300
```

---

## 12. Running locally

```bash
uvicorn app.main:app --reload --port 8000    # backend + bot + admin
# or the whole stack:
docker compose up --build
```

Check `http://localhost:8000/health` — it reports database status, demo mode, AI provider configuration, and match radius.

### Web app (React frontend in `web/`)

```bash
cd web
npm install
npm run dev    # http://localhost:3000 — proxies /api to the backend on :8000
```

For production:
```bash
cd web && npm run build && cd ..    # outputs web/dist
python -m app.main                    # open http://localhost:8000 — React app + API + bot
```

Register on the web (email + password + phone + OTP), pick your role, and the same account works on Telegram: **Account → Connect Telegram** opens the bot with a one-time link.

If no AI provider keys are configured, web search falls back to an honest rule-based keyword parser (`provider="rules"`) so the flow still works end to end.

---

## 13. API reference

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/health` | status, DB, AI provider configuration | none |
| POST | `/api/v1/auth/send-otp` | send 6-digit OTP to a phone | none |
| POST | `/api/v1/auth/verify-otp` | verify a standalone OTP | none |
| POST | `/api/v1/auth/register` | register with OTP — body now requires `otp` field | none |
| POST | `/api/v1/auth/login` · `/auth/logout` | JSON auth, sets `vm_session` cookie | session |
| GET | `/api/v1/auth/me` | current user or null | optional |
| GET | `/api/v1/auth/telegram-link` | one-time `t.me` deep link to connect Telegram | user |
| GET | `/api/v1/profile` · `/profile/claimable-shops` · `/profile/claim-shop` · `/profile/create-shop` | onboarding + shop management | user |
| PATCH | `/api/v1/profile/shop/location` · `/profile/location` | update shop / customer location | user |
| PATCH | `/api/v1/profile/trusted-contact` | set trusted contact phone for the panic button | verified |
| GET | `/api/v1/catalog/shops` · `/catalog/shops/{id}` · `/catalog/price-search` · `/catalog/trending` | storefront data (verified shops only) | none |
| POST | `/api/v1/requests` | customer search — same matching + Telegram notify as the bot | verified |
| GET | `/api/v1/requests/mine` · `/requests/{id}` | history + live offers with trust / freshness / why | user / owner |
| GET | `/api/v1/requests/{id}/offers` | explicit offers-only endpoint (lighter polling) | owner |
| POST | `/api/v1/requests/choose` | atomic exactly-one customer selection | verified + owner |
| GET | `/api/v1/requests/{id}/chat?since=ISO` | customer-side chat history (polls every 1.5s) | verified + owner |
| POST | `/api/v1/requests/{id}/chat/messages` | customer-side send | verified + owner |
| POST | `/api/v1/requests/{id}/flag` | customer report — 5 reasons; auto-suspend on `felt_unsafe` / `shop_doesnt_exist` | verified + owner |
| POST | `/api/v1/panic` | panic button — audit + SMS trusted contact in production | verified |
| POST | `/api/v1/requests/reserve` | reserve a listed in-stock item (same YES/NO flow) | verified |
| GET/POST | `/api/v1/merchant/shop` · `/inbox` · `/respond` | merchant inbox — same YES/NO as bot buttons | (verified shop) |
| POST | `/api/v1/merchant/shop/shopfront-photo` | multipart upload — Pillow EXIF + browser GPS cross-check | verified shop |
| GET/POST/PATCH/DELETE | `/api/v1/merchant/inventory…` | inventory CRUD + stock toggle | verified shop |
| POST | `/api/v1/merchant/inventory/plan` | prefill inventory form from a stock opportunity (no auto-add) | verified shop |
| GET | `/api/v1/merchant/conversations` · `/conversations/{id}` · `/conversations/{id}/messages` | shop-side chat | verified shop |
| GET/POST | `/api/v1/merchant/khata` | digital ledger | verified shop |
| GET | `/api/v1/merchant/demand` | honest demand stats (unique vs merchant responses) + demo flag + period selector | verified shop |
| GET | `/api/v1/merchant/demand/opportunities` | explainable stock opportunity recommendations | verified shop |
| GET | `/api/v1/merchant/demand/heatmap` | privacy-safe demand buckets (~300m grid) | verified shop |
| GET | `/api/v1/merchant/demand/impact` | judge-friendly impact dashboard + neighborhood insight | verified shop |
| GET | `/api/v1/admin/shops/pending` | admin verification queue | admin |
| POST | `/api/v1/admin/shops/{id}/approve` · `/reject` | flip `is_verified=True` or reject | admin |
| GET | `/api/shops` · `/api/shops/{id}` | legacy shop catalog (HTML/Telegram surface) | none |
| GET | `/api/requests/{id}` · `/api/requests/{id}/offers` | legacy request status | none |
| POST | `/api/test/match` | run the pipeline without Telegram (notify=false default) | none |
| GET | `/api/demand` · `/api/demand/nearby` | legacy demand analytics | none |
| GET/POST | `/auth/login` · `/auth/register` · `/auth/telegram` · `/auth/telegram/complete` · `/auth/logout` · `/auth/me` | server-rendered HTML auth pages | CSRF |

```bash
curl -X POST http://localhost:8000/api/test/match \
  -H 'Content-Type: application/json' \
  -d '{"text":"teflon tape chahiye","latitude":24.0734,"longitude":75.0686}'
```

---

## 14. Telegram commands

`/start` `/menu` `/help` `/login` `/logout` `/history` `/khata` `/khata_summary` `/inventory` `/browse` `/demand` `/compare <product>` `/category` `/shop` `/admin` `/admin_demand`

`/logout` unlinks the Telegram account (with a confirm step) without deleting any data — shop, inventory, khata, and history are all still there on the next login.

---

## 15. Project structure

```
vyapaar-mitra/
├── app/
│   ├── main.py                 FastAPI entry point + lifespan
│   ├── config/settings.py      all environment configuration (incl. OTP/photo/panic)
│   ├── database/               mongo.py (12 collections), indexes.py
│   ├── models/                 product_request, merchant_match, demand, chat, shop, user, …
│   ├── schemas/                Pydantic contracts (ProductIntent, MatchCandidate, …)
│   ├── ai/
│   │   ├── base.py             LLMProvider / STTProvider interfaces
│   │   ├── providers/          gemini.py, groq.py, gpt_oss.py, sarvam.py
│   │   ├── intent_engine.py    text/voice → ProductIntent (+ fallback chain)
│   │   ├── vision_engine.py    images → ProductIntent / inventory lines
│   │   ├── khata_engine.py     ledger notes → structured entries
│   │   └── prompts.py
│   ├── services/               ALL business logic
│   │   ├── search_service.py         multi-offer window + atomic select_offer
│   │   ├── merchant_matching.py      zero-inventory matching + is_verified gate
│   │   ├── demand_engine.py          honest stats + heatmap + neighborhood insight
│   │   ├── opportunity_service.py    explainable opportunity score (no ML)
│   │   ├── trust_service.py          reliability + freshness labels
│   │   ├── chat_service.py           anonymised customer ↔ shopkeeper chat
│   │   ├── verification_service.py   shopfront photo + admin approval
│   │   ├── demo_service.py           deterministic Teflon Tape simulator
│   │   ├── auth_service.py           OTP + sessions + Telegram linking
│   │   ├── inventory_service.py     inventory CRUD + stock plan
│   │   ├── khata_service.py          digital ledger
│   │   ├── browse_service.py        nearby-stock catalogue
│   │   ├── location_service.py      geospatial helpers
│   │   ├── notification_service.py  Telegram delivery (formats + send + log)
│   │   └── scheduler.py              APScheduler housekeeping
│   ├── bot/                    Telegram interface only (handlers stay thin)
│   │   ├── bot.py, keyboards.py, states.py, middleware.py
│   │   └── handlers/           start, auth, customer, merchant, search, browse,
│   │                           inventory, khata, demand, admin, router
│   ├── api/                    health, auth, shops, requests, demand, web (REST)
│   │   └── web.py              /api/v1 JSON REST for the React app (all new endpoints)
│   ├── templates/              server-rendered HTML auth pages
│   ├── static/                 auth.css, shop-fields.js, shop_photos/{shop_id}.jpg
│   └── utils/                  geo, security, parsing, logging, errors
├── web/                        LocalMart React frontend (Vite + Tailwind + shadcn)
│   ├── src/pages/              customer (Home, SearchFlow, Browse, Compare, History)
│   │                           merchant (Inbox, Inventory, Khata, Demand, Impact)
│   │                           admin (PendingShops)
│   ├── src/components/         OfferCard, ChatDrawer, ShopfrontPhotoCapture,
│   │                           DemandHeatmap, LocationPicker, shell, brand, ui/*
│   ├── src/lib/api.ts          REST client for /api/v1 (React Query)
│   └── dist/                   production build — served by FastAPI at /
├── tests/                      141 tests (96 baseline + 25 hackathon + 20 safety)
├── scripts/                    seed_demo_data.py, test_pipeline.py
├── requirements.txt · Dockerfile · docker-compose.yml · .env.example
```

---

## 16. Tests

```bash
pytest -q                                    # 141 tests pass (no MongoDB, no API keys)
pytest -v tests/test_matching.py             # zero-inventory matching
pytest -v tests/test_hackathon_upgrade.py    # opportunity, trust, freshness, heatmap, demo
pytest -v tests/test_safety_features.py      # OTP, EXIF GPS, chat, is_verified gate
python -m scripts.test_pipeline             # full pipeline against a live MongoDB
```

Coverage:

- **Geo**: Haversine, GeoJSON ordering, valid bounds, `humanize_distance`, `navigation_link`.
- **Models**: `build_shop_document`, `build_request_document`, `build_match_document`, `build_demand_event`, `build_chat_document`, `build_message_document`.
- **Matching**: category score, capability score, distance decay, weights sum to 1.0, new-shop neutral history, radius expansion.
- **Hackathon upgrade (Priority 1–10)**: opportunity scoring (high/low/zero-history/category-filter/already-stocked/quantity-cap, sort), trust score (zero-history, low-history, strong-history, median response time, label changes), freshness labels (just-confirmed, minutes-ago, inventory-listed, stale, price-not-provided), heatmap bucket aggregation (privacy collapse of nearby points, far-apart points don't collapse, 4dp clean output), explainability bullets, demo determinism (scenario matching + fixed responses), offer sorting by best/nearest/cheapest/reliable/fastest.
- **Safety**: phone normalisation (10-digit, 12-digit, +91 prefix, dashes, garbage), OTP hash consistency (sha256, same/different codes), OTP generation (6-digit, numeric only), EXIF DMS-to-degrees (N/E positive, S/W negative, PIL ratio tuples), JPEG EXIF parsing (returns None for non-JPEG, raises on invalid), chat model builders (status, text truncation, whitespace strip, created_at), **the safety gate assertion** — uses `inspect.getsource` to verify `"is_verified": True` is in `find_candidates` source (if anyone removes the gate, this test breaks loudly).
- **Config**: cooldown, radius steps, llm chain dedup, admin_ids CSV, email flag, confidence bands.
- **Security**: password hashing (argon2id/bcrypt), `generate_token`, `sign_session`/`load_session`, CSRF, `RateLimiter`.
- **Errors**: `new_error_ref`, `user_text`, `debug_line`, `ExternalServiceError`, `ConfigurationError`, HTTP status defaults, `to_dict` never leaks internal message.

Frontend:
```bash
cd web
npm run check    # TypeScript strict — passes clean
npm run build    # Vite production — passes clean (Leaflet code-split)
```

---

## 17. Demo vs real data — what's simulated and what isn't

| Surface | Real | Demo-simulated (clearly labelled) |
|---|---|---|
| Customer search intent | AI (Gemini/Groq/GPT-OSS) when keys are set; otherwise the rule-based fallback parser (labelled `via rules`) | — |
| Customer request creation | Real — writes to `product_requests` | — |
| Merchant matching | Real — `merchant_matching.find_candidates` geospatial pipeline | — |
| Merchant YES/NO | Real when a live Telegram bot is polling, OR when a merchant taps via the web inbox | Demo-simulated by `app/services/demo_service.py` when `DEMO_MODE=true` AND `RUN_BOT=false` — tagged `source="demo_simulated"` and labelled `Demo-simulated merchant response` in the UI |
| Demand events / heatmap / opportunity scoring | Real — computed from `product_requests` and `merchant_matches` | The merchant responses that feed demand events may be demo-simulated; every dashboard surfaces a `Demo data` sticker when `DEMO_MODE=true` |
| Customer selection | Real — the customer taps `Yahi final` themselves | — |
| Phone OTP | Real flow — `send_otp` writes a hashed code to `otp_codes`, `verify_otp` flips `phone_verified` | Stub mode (`OTP_STUB_MODE=true`): OTP returned in the API response as `dev_otp` so you can paste from the network tab. No SMS gateway needed for the demo. |
| Shopfront photo GPS check | Real — Pillow parses EXIF GPS + browser GPS cross-checked against shop location | — |
| Admin approval | Real — admin taps "Approve" | — |
| In-app chat | Real — messages stored in `chat_messages`, polled every 1.5s | — |
| Panic button | Real — audit event written to `panic_events` | SMS dispatch stubbed (`PANIC_SMS_STUB=true`); in production SMSes the trusted contact |

The system never claims a sale happened, never invents a price, and never labels demo-simulated activity as real production analytics.

---

## 18. Metrics definitions

| Metric | Definition | Source |
|---|---|---|
| Unique customer requests | Distinct `request_id`s in the period — one per customer ask, regardless of how many merchants were asked | `product_requests` |
| Requests matched | Requests with at least one ACCEPTED merchant_match | `product_requests.status ∈ {MATCHED, COMPLETED}` |
| Requests unmatched | Requests with no ACCEPTED match (EXPIRED / CANCELLED) | `product_requests.status ∈ {EXPIRED, CANCELLED}` |
| Zero-inventory matches | ACCEPTED matches on shops that have NO inventory row for the requested product_key | `merchant_matches` JOIN `inventory_items` |
| Successful customer selections | Requests in COMPLETED state with `selected_match_id` set | `product_requests.selected_match_id` |
| Merchant response attempts | Count of `merchant_matches` rows in the period | `merchant_matches` |
| Available responses | `merchant_matches.status = ACCEPTED` | `merchant_matches` |
| Unavailable responses | `merchant_matches.status = DECLINED` | `merchant_matches` |
| Merchant response rate | `(accepted + declined) / total attempts` | `merchant_matches` |
| Avg search distance | Average `radius_used_meters` across requests | `product_requests.radius_used_meters` |
| Estimated search distance saved | `(MAX_MATCH_RADIUS_METERS - avg_radius) × matched_count` — clearly labelled as an estimate | computed |
| Opportunity score | Deterministic weighted sum (30% volume + 25% unmet + 15% trend + 10% search difficulty + 10% coverage gap + 10% category fit), capped 0–100 | `opportunity_service.opportunity_score` |
| Reliability score | 50% response rate + 25% acceptance rate + 15% response speed + 10% reputation (verified + completed selections), with new-merchant guard for <5 samples | `trust_service.compute_trust_score` |

---

## 18.5. Pro subscription — the monetisation layer (₹299/month)

Vyapaar-Mitra monetises via a **single Shopkeeper SaaS tier — Pro** at ₹299/month
with a 14-day free trial (no payment required for the hackathon demo; production
wires to Razorpay the same way the customer checkout orders are).

Pro unlocks **6 analytics-driven benefits** on the Pro Dashboard at
`/merchant/pro`:

| # | Benefit | What it does | Backend service |
|---|---------|--------------|------------------|
| 1 | **Nearby hot products** | Top-10 most-requested SKUs in your pin-code (last 7/30 days) | `demand_engine.top_unique_requested_products` |
| 2 | **Demand heatmap** | Visual map of where customers are asking, ~300m buckets, privacy-safe | `demand_engine.demand_heatmap` |
| 3 | **Sales analytics** | Daily revenue trend, top sellers, slow movers, online-vs-cash breakdown | `analytics_service.sales_analytics` |
| 4 | **Smart pricing suggestions** | Recommended price vs. median competitor offers (40/60 blend) | `analytics_service.smart_pricing_suggestions` |
| 5 | **Slow-mover alerts** | Inventory items not restocked in 14+ days AND demand +30% | `analytics_service.slow_mover_alerts` |
| 6 | **Festival readiness** | Next upcoming Indian festival (6 in calendar), stock-up recommendations filtered by shop category | `analytics_service.festival_readiness` |

### Why SaaS and not marketplace commission

A commission model would create a perverse incentive — we'd earn more when
shopkeepers pay more in fees. The SaaS model aligns us with shopkeeper growth:
predictable MRR, no take-rate race-to-the-bottom, the shopkeeper who succeeds
pays the same ₹299 as the one who's just getting started.

### API endpoints (all Pro-gated by `require_pro_shop`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/merchant/pro/status` | Current Pro status (free) — used to show Subscribe CTA |
| `POST` | `/merchant/subscribe` | Start 14-day free trial |
| `POST` | `/merchant/subscribe/paid` | Grant paid 30-day Pro (admin / post-Razorpay) |
| `GET` | `/merchant/pro/nearby-hot-products` | Pro benefit #1 |
| `GET` | `/merchant/pro/sales-analytics` | Pro benefit #3 |
| `GET` | `/merchant/pro/pricing-suggestions` | Pro benefit #4 |
| `GET` | `/merchant/pro/slow-mover-alerts` | Pro benefit #5 |
| `GET` | `/merchant/pro/festival-readiness` | Pro benefit #6 |

Existing endpoints `/merchant/demand/opportunities`, `/merchant/demand/heatmap`,
and `/merchant/demand/impact` continue to work without Pro (they form the honest
demand dashboard). Pro gates only the dedicated analytics benefits — this keeps
the demo flowing without breaking any existing screen.

### Unit economics (per-shop, Year-1 stabilised assumptions)

- **ARPU**: ₹254/month (assumes 40% Free / 60% Pro mix at ₹299)
- **CAC**: ₹800 (offline field sales, local partner agent)
- **Payback**: 3.1 months
- **LTV (24-month)**: ₹6,106 → LTV/CAC = 7.6×
- **Gross margin**: ~85% (software-only — no inventory, no logistics)

### See also

- Business model PDF: `Vyapaar-Mitra-Business-Model.pdf` — full 3-year forecast
  + use-of-funds breakdown for the ₹15 lakh seed ask.
- Section 19 (Future roadmap) — the multi-tier expansion is listed as future scope;
  the current implementation ships the single Pro tier only.

---

## 19. Future roadmap

- WhatsApp Business interface reusing the same service layer (10× distribution vs Telegram in India)
- Cross-shop restock sharing: a merchant who stocks an opportunity product can ping nearby shops in the same category to co-stock
- Khata Pro subscription tier (₹99/mo) — SMS reminders, GST-ready statements, customer credit limits, multi-staff access
- Demand intelligence API for FMCG distributors — sell anonymized neighborhood demand reports to local wholesalers
- Verified `Bharosemand` tier (₹199/mo) — reputation badges + featured placement in the merchant's neighborhood
- Regional language expansion beyond Hindi/Hinglish via Sarvam
- Offline-first SMS fallback for feature phones
- WebSocket upgrade for chat (real-time push instead of 1.5s polling)
- FCM/APNs push notifications for chat messages when the app is in the background
- Anonymous VoIP via Twilio Voice API masked calls (both sides dial a relay number)

---

## 20. Design notes / non-goals

Deliberately **not** built: Next.js, a large web dashboard that replaces Telegram, a native mobile app, payments, delivery management, worker marketplaces, microservices, Kubernetes, Kafka, Celery, Redis, or a vector database. The MVP-plus-upgrade runs on one process and one database, with Telegram as the primary merchant interface and a focused React web app for the multi-offer compare + demand intelligence surfaces. An MVP that runs on one process and one database is the point — adding infra would dilute the value proposition.

One more thing the system never does: claim a sale happened. A merchant's YES means _"I have this in stock"_ — nothing more. The customer still walks in and buys. The same rule applies to demo-simulated merchant responses — they are clearly labelled as such so judges never confuse them with real production activity.

---

## 21. Known limitations

- The opportunity score is a heuristic, not a sales forecast. The recommended quantity is labelled clearly as an estimate; the merchant must confirm before adding stock.
- Trust score requires ≥5 merchant responses before showing a non-neutral score. New shops get `New merchant` + 50/100 — never a low score.
- Heatmap buckets are ~300m grid cells. At very low demand (few requests), the heatmap may show only one or two buckets — the UI shows an empty state in that case.
- Demo simulation only triggers for the flagship Teflon Tape scenario. Other products work end-to-end via the real pipeline (rule-based intent + a live merchant via web inbox), but won't get simulated responses.
- Phone OTP in stub mode (`OTP_STUB_MODE=true`) is shown in the network response — not a security model, just a hackathon convenience. Flip the flag for production.
- Shopfront photos retain EXIF GPS in the saved file. The GPS is parsed and stored on the shop doc; the photo on disk should be re-encoded without EXIF in production.
- Chat uses REST polling at 1.5s, not WebSocket. For a hackathon with 3–4 friends on the same WiFi, polling feels real-time. For production, upgrade to WebSocket or add FCM push.
- Panic SMS dispatch is stubbed (logs to console). Wire a real SMS gateway for production.
- The admin approval flow has no UI for the admin to verify their OWN identity — the admin account is seeded with `is_verified=True` and `phone_verified=True`. For production, the admin should go through the same OTP flow.
- WhatsApp Cloud API pricing is per-conversation. Run the math: at 1000 merchants × 5 conversations/day × ~₹0.13/conversation that's ~₹6,500/day. Bake it into the SaaS fee.
- DPDP Act 2023 compliance — customer PII + merchant data + selling aggregated demand to third parties needs explicit consent flows. Build the consent screen before launch, not after the first complaint.
- Khata disputes — if a customer says "the merchant recorded ₹500 extra", who arbitrates? Define this in T&Cs before the first dispute, not during it.

---

## 22. Troubleshooting

| Symptom | Fix |
|---|---|
| Bot doesn't respond | `TELEGRAM_BOT_TOKEN` missing, or another process is already polling the same bot |
| `MongoDB connection failed` | Mongo not running, or Atlas IP allow-list / credentials |
| Login link opens but nothing happens | `PUBLIC_BASE_URL` must be reachable from the phone (use ngrok) |
| "This link has expired" | Links last 10 minutes and are single-use — request a new one |
| No merchants matched | Shops need a location AND `is_verified=True` (admin must approve shopfront photo) — seed data, then share each shop's location |
| Voice search fails | `SARVAM_API_KEY` missing — text search still works |
| `AI providers unavailable` | No Gemini/Groq/GPT-OSS key configured, or all are failing — rule-based fallback handles text |
| Merchant stopped getting requests | Cooldown after a NO (12 h), or the shop was paused, or the shop was auto-suspended via a `felt_unsafe` flag |
| Emails never arrive | SMTP is optional; blank config silently disables it |
| `Could not save photo` | Photo must be < 5 MB, JPEG, AND captured within 200m of the registered shop location — EXIF + browser GPS both checked |
| `Phone number looks invalid` | OTP requires a 10-digit Indian mobile (or +91 prefix) |
| OTP not arriving in stub mode | In stub mode, the OTP is shown in the server console AND returned in the API response — check the network tab or the terminal |
| Customer can't see a shop | The shop is `is_verified=False` (admin hasn't approved the photo yet) or `is_active=False` (paused or auto-suspended) |

---

## 23. License

MIT — see `LICENSE` if present. The repo is intended for hackathon and educational use; production deployment is your responsibility (especially the safety + privacy safeguards listed in section 5).

---

## Acknowledgements

Built on the shoulders of giants: FastAPI, MongoDB, Motor, python-telegram-bot, React, Vite, Tailwind, shadcn/ui, react-leaflet, Sarvam AI, Google Gemini, Groq, Pillow, and the open-weight LLM community.

> _"A self-improving local commerce network that helps customers find products now and helps merchants understand what the neighborhood needs next."_
