# 🛍️ Vyapaar-Mitra

**A neighborhood demand intelligence network that helps customers find products now and helps merchants understand what the neighborhood needs next.**

Problem statement: **MU-PS-008 — The Small-Shop Digital Gap · Local Commerce Enablement**

> *"Don't force the shopkeeper to learn software. Make the software understand the shopkeeper."*

> Hackathon positioning (v2 upgrade): the product is no longer "an AI tool that helps
> customers find nearby shops". The product loop is now:

```text
Customer asks for something
        ↓
AI understands the request
        ↓
Nearby merchants respond
        ↓
Customer compares multiple offers
        ↓
Customer chooses the best shop
        ↓
YES/NO responses create demand intelligence
        ↓
Merchants see what their neighborhood is missing
        ↓
Merchants receive explainable stocking opportunities
```

---

## 1. Overview

Vyapaar-Mitra connects a customer who needs something *right now* with a shop 200 metres away
that probably has it — over Telegram, in Hindi/Hinglish, by voice, text or photo.

The merchant does not need an app, a catalogue, or a single uploaded product.

## 2. The problem

Every "digitise local commerce" product starts by asking the shopkeeper to upload inventory.
That is exactly where they drop off. A kirana or hardware shop owner has thousands of SKUs,
no barcodes, no time, and no reason to trust that the work pays off. So catalogues stay empty,
and empty catalogues mean the shop is invisible.

Meanwhile the customer's actual question was never about a catalogue. It was:
*"Who near me has this?"*

## 3. Core innovation — commerce without mandatory digital inventory

**Traditional commerce asks:** What products has this shop uploaded?
**Vyapaar-Mitra asks:** Who nearby can satisfy this customer's need?

A merchant is discoverable through:

| Signal | Example |
|---|---|
| Business category | hardware |
| Capabilities | plumbing, pipes, fittings, sealants |
| Location | 200 m from the customer |
| Customer intent | "pipe leak rokne wala safed tape" → Teflon Tape |
| Historical response | this shop usually answers, and usually has it |
| Merchant response | a one-tap YES / NO |

Sharma Hardware has **zero products uploaded** and is still the top match. That is the
entire thesis, and the seed data is built to demonstrate it.

### Why zero-inventory matters

1. **Onboarding takes 30 seconds**, not 30 hours — name, category, location, done.
2. **Day-one value**: a merchant gets real customer requests before uploading anything.
3. **Inventory becomes a reward, not a toll** — merchants who later add stock rank higher.
4. **A "NO" is still valuable** — it becomes demand intelligence for the whole neighbourhood.

## 3.5 Hackathon upgrade — neighborhood demand intelligence (v2)

The product has been upgraded from "an AI tool that helps customers find nearby
shops" into **a neighborhood demand intelligence network**. The core architecture
(FastAPI + MongoDB + Telegram bot + React/Vite) is unchanged; six new
product capabilities are layered on top of the existing services.

### 3.5.1 Multi-offer comparison + exactly-one customer choice (Priority 1)

The customer now sees **all** shops that accepted the request, not only the
first one that replies. When the first merchant YES arrives, a configurable
**offer window** (`OFFER_WINDOW_SECONDS=20`) starts — other merchants have a
chance to respond before the customer is notified. When the window elapses the
customer gets ONE batched Telegram notification listing every accepted offer,
plus a "Compare offers" button that opens the web compare screen.

The web compare card shows, per accepted offer:
- Shop name + verified tick
- Distance + address
- Merchant-confirmed price (or "Price not provided" — never invented)
- Response time (e.g. `12s` / `3m 20s`)
- Reliability/trust indicator (`Bharosemand · 84/100` or `New merchant`)
- Inventory freshness (`Confirmed just now`, `Shop-listed stock`, `Inventory
  updated 2 days ago`, `Price confirmed by merchant`, `Price not provided`)
- Match score (the same `0.30·category + 0.35·capability + 0.20·distance +
  0.15·history` breakdown that powers the matching)
- Short "Why this shop?" explanation
- Address + phone (when available) + Google Maps directions link
- Choose button (clearly only one selection permitted)

Sort options: **Best overall · Nearest · Lowest price · Most reliable ·
Fastest response**.

**Exactly-one enforcement**: the customer can pick exactly one offer. The
selection is atomic — `select_offer` issues a `update_one` with a filter on
`selected_match_id == None`, so a concurrent second selection attempt is
rejected with HTTP 409. The selection persists across refresh; a late
merchant response (after the customer picked) does NOT overwrite the chosen
offer — it just gets added to the demand intelligence, with `status=EXPIRED`
on the match row.

### 3.5.2 Stock opportunity recommendations (Priority 2)

A new merchant-facing section, **Stock Opportunities**, computes an
explainable opportunity score for each product the neighborhood is asking
for. The score is deterministic — no ML model — using:

- Unique customer requests (deduped by `request_id`)
- Unavailable response rate
- Recent demand trend (last 7d vs previous 7d)
- Average search distance
- Nearby inventory coverage (how many shops already list it)
- Merchant category affinity (the existing `CATEGORY_AFFINITY` map)
- Whether the merchant already stocks it

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

The **Add to inventory plan** button prefills the merchant's inventory form
but does NOT add stock without confirmation.

### 3.5.3 Demand heatmap (Priority 3)

A privacy-safe Leaflet map (`/merchant/impact`) renders demand buckets
centred on the merchant's shop. Every customer location is snapped to the
centre of a ~300m grid cell (`HEATMAP_BUCKET_METERS=300`), and demand is
deduplicated by `request_id` so one request routed to 5 merchants still
counts as one bucket entry. Customer identity is never exposed.

Filters: 7-day / 30-day / 90-day, plus optional category filter. Each circle
is sized by unique request volume and coloured by unmet rate (red = high
unmet, orange = some unmet, yellow = popular, green = healthy).

### 3.5.4 Honest demand metrics (Priority 4)

Demand analytics deliberately distinguishes **unique customer requests** from
**merchant response attempts**. A single customer request sent to 5
merchants is still 1 unique customer request, never 5. The merchant demand
dashboard now reads:

```text
12 unique customers asked for Teflon Tape
29 merchant responses were collected
21 merchants said unavailable
8 merchants confirmed availability
```

The unique-request counts come from the `product_requests` collection (one
row per request); the merchant-response counts come from `merchant_matches`
(one row per merchant per request, with a unique index on
`(request_id, merchant_id)` preventing double-counting even at the database
level).

### 3.5.5 Trust and freshness labels (Priority 5)

Every offer card shows two new badges:

- **Trust badge**: `Bharosemand · 84/100 — usually responds quickly` (or
  `New merchant` for shops with fewer than `TRUST_MIN_SAMPLE=5` responses,
  so a brand-new shop never gets unfairly penalised for missing history).
  Computed from response rate + acceptance rate + median response time +
  completed selections + verified status.
- **Freshness labels**: `Confirmed just now`, `Confirmed 5 minutes ago`,
  `Shop-listed stock`, `Inventory updated 2 days ago`, `Price confirmed by
  merchant`, `Price not provided`. Stale information is labelled stale,
  never presented as guaranteed current availability.

### 3.5.6 Judge-friendly impact dashboard (Priority 6)

A new page at `/merchant/impact` shows in under 30 seconds:

- Unique customer requests
- Requests matched to ≥1 shop
- Zero-inventory matches (the innovation metric)
- Successful customer selections
- Merchant response rate
- Unmet demand discovered
- Estimated search distance saved (clearly labelled as an estimate)
- "What would improve this neighborhood most?" — single top unmet-demand
  product with its reason and suggested action

When DEMO_MODE is on, a `Demo data` sticker is shown everywhere so judges
never confuse seeded activity with real production analytics.

### 3.5.7 Deterministic demo mode (Priority 8)

When `DEMO_MODE=true` AND `RUN_BOT=false`, the new `app/services/demo_service.py`
schedules simulated merchant YES/NO responses for the flagship Teflon Tape
scenario, each tagged `source="demo_simulated"` so the customer UI clearly
labels them as `Demo-simulated merchant response`. The flow is fully
deterministic — same scenario always schedules the same shops / prices /
delays — so a hackathon demo always lands:

```text
Customer:  "Mere sink ke neeche pipe leak ho raha hai, safed tape chahiye."
Intent  :  Teflon Tape (Hardware)
Shops   :  Sharma Hardware  (zero inventory, capable, ~200m) — YES ₹30 (5s)
           Gupta Electricals (inventory listed, ₹25, ~650m)   — YES ₹25 (12s)
           Raj Plumbing     (capable, ~1.2km)                  — NO    (18s)
Outcome :  2 offers → customer compares → picks one (e.g. Gupta at ₹25)
           Raj's NO becomes demand intelligence → Raj sees a Stock Opportunity
           for Teflon Tape with score 87/100 → "Add to inventory plan"
```

AI providers, Sarvam STT and Telegram are NOT required for the demo — the
rule-based fallback parser handles intent extraction, and demo simulation
handles merchant responses. The system never claims demo data is real.

### 3.5.8 Explainability (Priority 9)

Every recommendation surfaces a short, plain-language explanation through
the API and the UI:

- **Match**: "Same category · Capability match · ~200m away · Strong
  response history · Verified shop"
- **Stock opportunity**: "14 nearby customer requests · 79% unavailable ·
  Demand increased over the last 30 days · Only 2 nearby shops list this"

Raw prompts, provider secrets, and internal stack traces are never exposed.

### 3.5.9 Data quality and privacy safeguards (Priority 10)

- Demand is deduplicated by customer `request_id`, never by merchant response.
- Duplicate merchant responses are impossible: `merchant_matches` has a unique
  index on `(request_id, merchant_id)`, and `demand_events` has a unique
  index on the same compound key.
- Heatmap locations are aggregated into ~300m buckets — customer identities
  are never exposed to merchants.
- Merchant reliability uses a minimum-sample guard so new shops aren't
  unfairly penalised.
- Old prices and inventory are labelled stale.
- Demo data is clearly labelled `Demo data` everywhere it appears.
- Merchant-only analytics endpoints require `require_my_shop` authorisation.
- Customer offer endpoints require `require_user` + an inline
  `str(request.customer_id) == str(user._id)` check.
- Merchant response endpoints verify `str(match.merchant_id) == str(shop._id)`.

## 4. Architecture

```
Telegram  (customer + merchant interface)
    │
    ▼
FastAPI   (backend + minimal HTML auth pages + /api/v1 JSON for the web app)
    ▲          ▲
    │          └── Web  (React app in web/ — LocalMart UI)
    ▼
Business services   (search, matching, demand, khata, inventory, auth, email)
    │
    ▼
MongoDB   (geospatial 2dsphere, aggregation pipelines)
    │
    ▼
AI services
    ├── Sarvam AI  — Indian-language speech to text
    ├── Google Gemini — intent, vision, structured extraction
    └── Groq / GPT-OSS — fast fallback inference
```

**Architectural rule:** Telegram handlers contain *no* business logic. Everything lives in
`app/services/` — the React web app (`web/`) plugs into those same services through
`app/api/web.py`, so web and Telegram share one database and one matching engine:

- A customer searching on the **web** triggers the same zero-inventory matching, and
  merchants still get the request on **Telegram** (plus their web inbox).
- A merchant answering YES/NO in the **web inbox** runs the same
  `handle_merchant_response` path as the bot — demand events are recorded and the
  customer is notified on Telegram if they linked their account.
- Web users connect their Telegram from **Account → Connect Telegram** (a one-time
  `t.me` deep link consumed by the bot's `/start web_<token>` handler).

FastAPI also serves the legacy HTML auth pages under `/auth`, and when `web/dist`
exists it serves the built React app at `/` with SPA fallback — one process for
frontend, REST API and bot.

## 5. AI architecture

A provider abstraction (`app/ai/base.py`) defines `LLMProvider` (`generate_text`,
`generate_structured`, `analyze_image`) and `STTProvider` (`transcribe`). Business logic never
imports Gemini or Groq directly.

```
Text tasks:   Gemini ──fail──▶ Groq ──fail──▶ GPT-OSS ──fail──▶ honest error to the user
Speech:       Sarvam ──fail──▶ "voice unavailable, please type"
Vision:       Gemini ──fail──▶ ask for a text description
```

Model responsibilities (the cheapest capable model wins — not every task goes to every model):

| Provider | Used for |
|---|---|
| **Sarvam AI** | Hindi / Hinglish / noisy Telegram voice notes |
| **Gemini** | intent extraction, product identification, image understanding, category classification |
| **Groq** | fast fallback inference, query normalisation, lightweight text |
| **GPT-OSS (20B / 120B)** | configurable open-weight provider, any OpenAI-compatible endpoint |

> **GROQ ≠ Grok.** GROQ is the inference provider used here. Grok is an unrelated xAI model.

**We never fabricate AI output.** If every provider fails, the bot says so.

### Confidence handling

| Confidence | Behaviour |
|---|---|
| ≥ 0.80 | direct matching |
| 0.60 – 0.79 | match, but internally flagged uncertain and disclosed to the merchant |
| < 0.60 | ask the customer to clarify (1️⃣ 2️⃣ 3️⃣ or send a photo) |

## 6. MongoDB architecture

Collections: `users`, `customers`, `shops`, `inventory_items`, `product_requests`,
`merchant_matches`, `demand_events`, `khata_entries`, `auth_tokens`, `sessions`,
`notifications`, `merchant_cooldowns`.

Locations are **always** GeoJSON points — never a bare latitude/longitude pair:

```json
{ "type": "Point", "coordinates": [75.0686, 24.0734] }
```

`2dsphere` indexes on `shops.location`, `customers.location`, `product_requests.location` and
`demand_events.location` let `$geoNear` do the distance work inside the database rather than
loading every merchant into Python. TTL indexes expire `auth_tokens`, `sessions` and
`merchant_cooldowns` automatically.

### Matching algorithm

```
score = 0.30·category + 0.35·capability + 0.20·distance + 0.15·history
```

Radius expands automatically: **500 m → 1 km → 2 km → 5 km** until candidates are found.
Weights and radii are all configurable in `.env`.

## 7. Authentication architecture

Passwords never travel through Telegram.

```
Telegram  🔐 Login / Register
    │  bot creates a cryptographically random token (secrets.token_urlsafe)
    │  stores ONLY sha256(token), single-use, 10-minute TTL
    ▼
https://your-domain/auth/telegram?token=ONE_TIME_TOKEN
    │  server-rendered login/register form (Jinja2, CSRF-protected)
    ▼
Account created/verified → linked to telegram_user_id → signed session cookie
    │
    ├─▶ browser:  "Telegram account linked successfully."
    └─▶ Telegram: "✅ Account successfully connected."
```

- Argon2id password hashing (bcrypt fallback), never plaintext, never in logs or URLs
- Single-use tokens, hashed at rest, invalidated on reuse and on issuing a new one
- Signed, HttpOnly, SameSite session cookies
- Rate limiting on `/auth/login`, `/auth/register`, `/auth/telegram` and on AI operations
- Role-based authorization (customer / shopkeeper / admin)

## 8. Feature list

**Core** · customer & shopkeeper onboarding · role selection with shop category and
location captured at registration · secure account linking · Telegram logout (unlinks
without deleting the account) · location sharing · voice / text / image search · Sarvam
STT · Gemini intent · Groq & GPT-OSS fallback · category and capability inference ·
geospatial hyperlocal search · **zero-inventory matching** · merchant YES/NO · merchant
price · customer notification · demand events · demand analytics · merchant cooldown

**Browse & navigate** · browse nearby shops and their listed stock without typing a
search · browse by category · reserve a specific in-stock item (routes through the same
YES/NO confirmation as search — no payments, no orders) · shop address, phone and a
one-tap Google Maps navigation link shown to the customer on every match and reservation
· a real Telegram map pin dropped alongside the text

**Hackathon v2 upgrade (Priorities 1–10)** · multi-offer comparison with sort (best /
nearest / cheapest / reliable / fastest) · exactly-one atomic customer selection that
persists across refresh · batched "you have N offers" customer notification (offer window)
· trust score with new-merchant guard · freshness labels (just-confirmed / shop-listed /
stale / price-not-provided) · why-recommended explanations on every offer · stock
opportunity scoring with "Add to inventory plan" · privacy-safe demand heatmap (300m
buckets, request_id deduplication) · honest demand metrics (unique requests vs merchant
responses) · judge-friendly impact dashboard · "what would improve this neighborhood
most?" insight · deterministic demo mode (Teflon Tape scenario, demo-simulated labels) ·
merchant-cooldown + demand_events unique indexes for double-count protection

**Business** · Digital Khata (typed & voice) · optional inventory · voice inventory ·
invoice/shelf photo inventory · smart deal comparison · search history · demand reports

**Communication** · Telegram notifications · optional SMTP email, verification, khata
reminders, scheduled demand reports

**Reliability** · a typed error hierarchy (`app/utils/errors.py`) shared by the bot and
the API: every failure gets a short reference id shown to the user and logged with full
context, so a support conversation can be traced straight to the stack trace that caused
it, without ever showing the user a raw exception

## 9. Project structure

```
vyapaar-mitra/
├── app/
│   ├── main.py                 FastAPI entry point + lifespan
│   ├── config/settings.py      all environment configuration
│   ├── database/               mongo.py, indexes.py
│   ├── models/                 document builders, enums, taxonomy
│   ├── schemas/                Pydantic contracts (ProductIntent, etc.)
│   ├── ai/
│   │   ├── base.py             LLMProvider / STTProvider interfaces
│   │   ├── providers/          gemini.py, groq.py, gpt_oss.py, sarvam.py
│   │   ├── intent_engine.py    text/voice → ProductIntent (+ fallback chain)
│   │   ├── vision_engine.py    images → ProductIntent / inventory lines
│   │   ├── khata_engine.py     ledger notes → structured entries
│   │   └── prompts.py
│   ├── services/               all business logic
│   ├── bot/                    Telegram interface only
│   │   ├── bot.py, keyboards.py, states.py, middleware.py
│   │   └── handlers/           start, auth, customer, merchant, search, browse,
│   │                           inventory, khata, demand, admin, router
│   ├── api/                    health, auth, shops, requests, demand
│   │   └── web.py              /api/v1 JSON REST API for the React web app
│   ├── templates/              base, login, register, _shop_fields, telegram_link,
│   │                           success, error
│   ├── static/css/auth.css · static/js/shop-fields.js
│   └── utils/                  geo, security, parsing, logging, errors
├── web/                        LocalMart React frontend (Vite + Tailwind + shadcn)
│   ├── src/pages/              customer (Home, SearchFlow, Browse, Compare, …)
│   │                           merchant (Inbox, Inventory, Khata, Demand)
│   ├── src/lib/api.ts          REST client for /api/v1 (React Query)
│   └── dist/                   production build — served by FastAPI at /
├── tests/
├── scripts/                    seed_demo_data.py, test_pipeline.py
├── requirements.txt · Dockerfile · docker-compose.yml · .env.example
```

## 10. Installation

```bash
git clone <your-repo> vyapaar-mitra && cd vyapaar-mitra
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then fill in the keys below
```

Shopkeepers now set their shop's category and pin their location on the registration
page itself (browser geolocation, with a manual fallback of sending the pin from
Telegram later) — both are asked for once because neither changes day to day, and a
shop with no category or no location cannot be matched to anyone.

### MongoDB setup

**Local**
```bash
docker run -d --name vyapaar-mongo -p 27017:27017 -v vyapaar_data:/data/db mongo:7
# MONGODB_URI=mongodb://localhost:27017
```

**Atlas** — create a free M0 cluster, add your IP to the access list, then
`MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net`.

Indexes (including 2dsphere) are created automatically on startup.

### Telegram setup
1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token into `TELEGRAM_BOT_TOKEN`
3. Get your numeric id from [@userinfobot](https://t.me/userinfobot) → `ADMIN_TELEGRAM_IDS`

### Sarvam setup
Sign up at [sarvam.ai](https://www.sarvam.ai), create an API subscription key →
`SARVAM_API_KEY`. Model defaults to `saarika:v2`, language `hi-IN`.

### Gemini setup
Create a key in [Google AI Studio](https://aistudio.google.com/app/apikey) → `GEMINI_API_KEY`.
Default model `gemini-2.0-flash`.

### Groq setup
Create a key at [console.groq.com](https://console.groq.com) → `GROQ_API_KEY`.
Default model `llama-3.3-70b-versatile`.

### GPT-OSS configuration
Any OpenAI-compatible endpoint works:

```env
# Groq-hosted
GPT_OSS_BASE_URL=https://api.groq.com/openai/v1
GPT_OSS_MODEL=openai/gpt-oss-20b     # or openai/gpt-oss-120b where supported
GPT_OSS_API_KEY=<groq key>

# Self-hosted vLLM / Ollama
GPT_OSS_BASE_URL=http://localhost:11434/v1
GPT_OSS_MODEL=gpt-oss:20b
GPT_OSS_API_KEY=ollama
```

### SMTP setup (optional)
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=<app password>
SMTP_FROM_EMAIL=you@gmail.com
```
Leave blank to run without email — Telegram is unaffected.

### Public URL for login links
Telegram login links must be reachable from the user's phone:
```bash
ngrok http 8000        # then PUBLIC_BASE_URL=https://<id>.ngrok-free.app
```

## 11. Running locally

```bash
uvicorn app.main:app --reload --port 8000
# or
python -m app.main
# or the whole stack
docker compose up --build
```

Check `http://localhost:8000/health` — it reports database status and which AI providers are
configured.

### Web app (React frontend in `web/`)

```bash
cd web
npm install
npm run dev        # http://localhost:3000 — proxies /api to the backend on :8000
```

For production, build the frontend once and let FastAPI serve everything:

```bash
cd web && npm run build && cd ..   # outputs web/dist
python -m app.main                 # open http://localhost:8000 — React app + API + bot
```

Register on the web (email + password), pick your role, and the same account works on
Telegram: **Account → Connect Telegram** opens the bot with a one-time link.
If no AI provider keys are configured, web search falls back to an honest rule-based
keyword parser (`provider="rules"`) so the flow still works end to end.

## 12. Seeding demo data

```bash
python -m scripts.seed_demo_data --reset
```

Seeds ten shops around `SEED_CENTER_LAT/LNG` (Mandsaur, MP by default). **Five of them have
zero inventory on purpose**, including Sharma Hardware, which is the star of the demo.

To make a seeded shop receive live Telegram requests: open the bot as that shopkeeper, press
🔐 Login / Register, log in with `shop1@vyapaar-mitra.local` / `VyapaarDemo123`, then share
the shop's location.

## 13. Running tests

```bash
pytest                    # unit tests: no MongoDB or API keys needed
pytest -v tests/test_matching.py
pytest -v tests/test_hackathon_upgrade.py   # v2: opportunity, trust, freshness, heatmap, demo
python -m scripts.test_pipeline    # full pipeline against a live MongoDB
```

Covered: Haversine, GeoJSON, category matching, capability matching, merchant ranking,
zero-inventory precedence, cooldown configuration, intent validation and clamping, auth token
expiry, password hashing, role authorization, khata arithmetic, demand aggregation output,
**opportunity score calculation (high/low/zero-history/category-filter/already-stocked/quantity-cap)**,
**trust score (zero-history, low-history, strong-history, median response time, label changes)**,
**freshness labels (just-confirmed / minutes-ago / inventory-listed / stale-inventory / price-not-provided)**,
**heatmap bucket aggregation (privacy collapse of nearby points, far-apart points don't collapse, 4dp output)**,
**explainability bullets**, **demo determinism (scenario matching + fixed responses)**,
**offer sorting by best/nearest/cheapest/reliable/fastest**.

Total: 121 tests (96 baseline + 25 new hackathon-upgrade regression tests).

## 13.1 Frontend build

```bash
cd web
npm install
npm run check      # TypeScript check
npm run build      # Vite production build (code-splits Leaflet)
```

The web app compiles cleanly with strict TypeScript; the Leaflet heatmap is
lazy-loaded so it sits in its own JS chunk and never enters the main bundle
unless a user opens the Impact page.

**Verification status.** This project was authored in a sandbox without network access, so the
third-party dependencies could never be installed there. Every module compiles, and the
dependency-free suites (`test_geo.py`, `test_khata.py` — 16 tests) were executed and pass. The
suites that import pydantic, bson or httpx have *not* been run yet. Run `pytest` once after
`pip install -r requirements.txt` before relying on them.

## 14. Demo script (2 minutes)

The demo now runs **without** live AI keys, **without** Telegram polling,
and **without** anyone needing to type a YES as a merchant. The
deterministic demo simulator handles merchant responses automatically.

**Setup:**
```bash
cp .env.example .env       # ensure DEMO_MODE=true and RUN_BOT=false (defaults)
docker compose up -d mongo  # or any local MongoDB on 27017
python -m scripts.seed_demo_data --reset
uvicorn app.main:app --reload --port 8000   # backend
# in another terminal:
cd web && npm run dev       # http://localhost:3000
```

Login as the demo customer (`demo.customer@vyapaar-mitra.local` /
`VyapaarDemo123`) — or register a new customer account. Make sure the
customer's location is shared (browser geolocation button on Home).

**The 9-step end-to-end demo:**

1. **Customer** types in the search bar:
   *"Mere sink ke neeche pipe leak ho raha hai, safed tape chahiye."*
2. **AI / rule-based fallback** returns `Teflon Tape · hardware · plumbing`
   — labelled `via rules` (or `via gemini`) on the intent card.
3. **Matching** expands 500m → 1km → 2km → 5km and finds 3 candidates:
   - Sharma Hardware — zero inventory, capable, ~200m, no Telegram needed
   - Gupta Electricals — inventory listed, ₹25, ~650m
   - Raj Plumbing — capable, ~1.2km
4. **Demo simulator** fires after delays: Sharma YES ₹30 (5s), Gupta YES
   ₹25 (12s), Raj NO (18s). Each offer card on the customer's compare
   screen is clearly labelled `Demo-simulated merchant response`.
5. **Offer window** (`OFFER_WINDOW_SECONDS=20` default) elapses → customer
   sees the live offers in the web UI (the polling pulls them every 4s).
   Sort by `Lowest price` to put Gupta (₹25) first.
6. **Customer picks Gupta** — `Yahi final` button → atomic exactly-one
   selection (HTTP 200). Try picking again → HTTP 409 "already chosen".
   The chosen card now shows "✓ Aapne is dukaan ko chuna" and a green
   `Deal pakki!` panel with the shop's address + Route + Call buttons.
7. **Merchant side**: switch to the Gupta Electricals merchant account
   (`shop3@vyapaar-mitra.local` / `VyapaarDemo123`) → `/merchant` inbox
   shows the customer's request. Or: open Raj Plumbing (`shop10@…`) →
   `/merchant/demand` shows the Stock Opportunities section.
8. **Demand dashboard**: `/merchant/demand` for Raj Plumbing shows
   `Teflon Tape · 87/100` opportunity score with reason *"14 nearby
   customers ne is product ki request bheji, 79% ko nahi mila, demand
   badh rahi hai..."* and an **Add to inventory plan** button (which
   prefills the inventory form, doesn't auto-add).
9. **Impact dashboard**: `/merchant/impact` shows the headline metrics
   (unique customer requests, matched, zero-inventory matches,
   successful selections, unmet demand discovered, estimated search
   distance saved), the "What would improve this neighborhood most?"
   insight (Teflon Tape), and the demand heatmap with red/orange/yellow
   demand buckets around the merchant's shop.

Closing line:

> Traditional commerce asks: *What products has this shop uploaded?*
> Vyapaar-Mitra asks: *Who nearby can satisfy this customer's need — and
> what does the neighborhood need next?*

No Telegram handy? `python -m scripts.test_pipeline` prints the same flow
end to end, and `POST /api/test/match` runs it over HTTP.

## 15. API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status, DB, AI provider configuration |
| GET | `/api/shops` | list/search shops (`category`, `latitude`, `longitude`, `radius_meters`) |
| GET | `/api/shops/{id}` | one shop |
| GET | `/api/requests/{request_id}` | request status |
| GET | `/api/requests/{request_id}/offers` | confirmed offers |
| POST | `/api/test/match` | run the full pipeline without Telegram |
| GET | `/api/demand` | top products + category breakdown |
| GET | `/api/demand/nearby` | demand around a point |
| GET/POST | `/auth/login`, `/auth/register` | HTML auth pages |
| GET | `/auth/telegram?token=…` | one-time linking page |
| POST | `/auth/telegram/complete` | completes linking |

### Web app API (`/api/v1`, cookie session — used by `web/`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` · `/api/v1/auth/login` · `/api/v1/auth/logout` | JSON auth (sets `vm_session` cookie) |
| GET | `/api/v1/auth/me` | current user or `null` |
| GET | `/api/v1/auth/telegram-link` | one-time `t.me` deep link to connect Telegram |
| GET/POST | `/api/v1/profile`, `/profile/role`, `/profile/claim-shop`, `/profile/create-shop` | onboarding & shop management |
| GET | `/api/v1/catalog/shops` · `/catalog/shops/{id}` · `/catalog/price-search` · `/catalog/trending` | storefront data |
| POST | `/api/v1/requests` | customer search — same matching + Telegram notify as the bot |
| GET | `/api/v1/requests/mine` · `/api/v1/requests/{id}` | history & live offers (with trust / freshness / why-recommended) |
| GET | `/api/v1/requests/{id}/offers` | explicit offers-only endpoint (lighter polling) |
| POST | `/api/v1/requests/choose` | atomic exactly-one customer selection |
| GET/POST | `/api/v1/merchant/shop` · `/inbox` · `/respond` | merchant inbox (same YES/NO as bot buttons) |
| GET/POST/PATCH/DELETE | `/api/v1/merchant/inventory…` | inventory CRUD + stock toggle |
| POST | `/api/v1/merchant/inventory/plan` | prefill inventory form from a stock opportunity (no auto-add) |
| GET/POST | `/api/v1/merchant/khata` | digital ledger |
| GET | `/api/v1/merchant/demand` | honest demand (unique requests vs merchant responses, demo-flagged) |
| GET | `/api/v1/merchant/demand/opportunities` | explainable stock opportunity recommendations |
| GET | `/api/v1/merchant/demand/heatmap` | privacy-safe demand heatmap buckets (~300m grid) |
| GET | `/api/v1/merchant/demand/impact` | judge-friendly impact dashboard metrics + neighborhood insight |

```bash
curl -X POST http://localhost:8000/api/test/match \
  -H 'Content-Type: application/json' \
  -d '{"text":"teflon tape chahiye","latitude":24.0734,"longitude":75.0686}'
```

## 16. Telegram commands

`/start` `/menu` `/help` `/login` `/logout` `/history` `/khata` `/khata_summary`
`/inventory` `/browse` `/demand` `/compare <product>` `/category` `/shop` `/admin`
`/admin_demand`

`/logout` unlinks the Telegram account (with a confirm step) without deleting any
data — shop, inventory, khata and history are all still there on the next login.
`/browse` opens the nearby-stock menu, an alternative to `/history`'s search-and-ask
flow for customers who'd rather look at what's already listed.

## 17. Troubleshooting

| Symptom | Fix |
|---|---|
| Bot doesn't respond | `TELEGRAM_BOT_TOKEN` missing, or another process is already polling the same bot |
| `MongoDB connection failed` | Mongo not running, or Atlas IP allow-list / credentials |
| Login link opens but nothing happens | `PUBLIC_BASE_URL` must be reachable from the phone (use ngrok) |
| "This link has expired" | Links last 10 minutes and are single-use — request a new one |
| No merchants matched | Shops need a location; seed data, then share each shop's location |
| Voice search fails | `SARVAM_API_KEY` missing — text search still works |
| `AI providers unavailable` | No Gemini/Groq/GPT-OSS key configured, or all are failing |
| Merchant stopped getting requests | Cooldown after a NO (12 h), or the shop was paused |
| Emails never arrive | SMTP is optional; blank config silently disables it |

## 18. Future roadmap

- WhatsApp Business interface reusing the same service layer
- Push the demand heatmap to a neighborhood-wide view (multi-shop aggregation)
- Cross-shop restock sharing: a merchant who stocks an opportunity product can
  ping nearby shops in the same category to co-stock
- Regional language expansion beyond Hindi/Hinglish via Sarvam
- Offline-first SMS fallback for feature phones
- Verified-shop tier with completed-selection milestone badges

## 18.1 Demo vs real data — what's simulated and what isn't

| Surface | Real | Demo-simulated (clearly labelled) |
|---|---|---|
| Customer search intent | AI (Gemini/Groq/GPT-OSS) when keys are set; otherwise the rule-based fallback parser (labelled `via rules`) | — |
| Customer request creation | Real — writes to `product_requests` | — |
| Merchant matching | Real — `merchant_matching.find_candidates` geospatial pipeline | — |
| Merchant YES/NO | Real when a live Telegram bot is polling, OR when a merchant taps via the web inbox | Demo-simulated by `app/services/demo_service.py` when `DEMO_MODE=true` AND `RUN_BOT=false` — tagged `source="demo_simulated"` and labelled `Demo-simulated merchant response` in the UI |
| Demand events / heatmap / opportunity scoring | Real — computed from `product_requests` and `merchant_matches` | The merchant responses that feed demand events may be demo-simulated; every dashboard surfaces a `Demo data` sticker when `DEMO_MODE=true` |
| Customer selection | Real — the customer taps `Yahi final` themselves | — |

The system never claims a sale happened, never invents a price, and never
labels demo-simulated activity as real production analytics.

## 18.2 Metrics definitions

| Metric | Definition | Source |
|---|---|---|
| **Unique customer requests** | Distinct `request_id`s in the period — one per customer ask, regardless of how many merchants were asked | `product_requests` |
| **Requests matched** | Requests with at least one ACCEPTED merchant_match | `product_requests.status ∈ {MATCHED, COMPLETED}` |
| **Requests unmatched** | Requests with no ACCEPTED merchant_match (EXPIRED / CANCELLED) | `product_requests.status ∈ {EXPIRED, CANCELLED}` |
| **Zero-inventory matches** | ACCEPTED matches on shops that have NO inventory row for the requested product_key — the zero-inventory innovation | `merchant_matches` JOIN `inventory_items` |
| **Successful customer selections** | Requests in COMPLETED state with `selected_match_id` set | `product_requests.selected_match_id` |
| **Merchant response attempts** | Count of `merchant_matches` rows in the period (one per merchant asked, per request) | `merchant_matches` |
| **Available responses** | `merchant_matches.status = ACCEPTED` | `merchant_matches` |
| **Unavailable responses** | `merchant_matches.status = DECLINED` | `merchant_matches` |
| **Merchant response rate** | `(accepted + declined) / total attempts` | `merchant_matches` |
| **Avg search distance** | Average `radius_used_meters` across requests | `product_requests.radius_used_meters` |
| **Estimated search distance saved** | `(MAX_MATCH_RADIUS_METERS - avg_radius) × matched_count` — clearly labelled as an estimate, not a hard number | computed |
| **Opportunity score** | Deterministic weighted sum: 30% volume + 25% unmet + 15% trend + 10% search difficulty + 10% coverage gap + 10% category fit (capped 0–100) | `opportunity_service.opportunity_score` |
| **Reliability score** | 50% response rate + 25% acceptance rate + 15% response speed + 10% reputation (verified + completed selections), with new-merchant guard for <5 samples | `trust_service.compute_trust_score` |

## 19. Design notes / non-goals

Deliberately **not** built: Next.js, a large web dashboard that replaces Telegram,
a native mobile app, payments, delivery management, worker marketplaces,
microservices, Kubernetes, Kafka, Celery, Redis, or a vector database. The
MVP-plus-upgrade runs on one process and one database, with Telegram as the
primary merchant interface and a focused React web app for the multi-offer
compare + demand intelligence surfaces. An MVP that runs on one process and one
database is the point — adding infra would dilute the value proposition.

One more thing the system never does: claim a sale happened. A merchant's YES
means *"I have this in stock"* — nothing more. The customer still walks in and
buys. The same rule applies to demo-simulated merchant responses — they are
clearly labelled as such so judges never confuse them with real production
activity.

## 19.1 Known limitations

- The opportunity score is a heuristic, not a sales forecast. The recommended
  quantity is labelled clearly as an estimate; the merchant must confirm
  before adding stock.
- Trust score requires ≥5 merchant responses before showing a non-neutral
  score. New shops get the `New merchant` label and a neutral 50/100 — never
  a low score.
- Heatmap buckets are ~300m grid cells. At very low demand (few requests),
  the heatmap may show only one or two buckets — that's expected, and the
  UI shows an empty state.
- Demo simulation only triggers for the flagship Teflon Tape scenario.
  Other products work end-to-end via the real pipeline (rule-based intent
  + a live merchant via web inbox), but won't get simulated responses.
- Docker / `docker compose` is the recommended deployment; the Dockerfile is
  a multi-stage build that produces the React app and serves it via FastAPI.
  (This sandbox does not include a Docker runtime, so `docker build` was
  not executed here — the Dockerfile is unchanged from upstream and was
  validated there.)
- Live AI providers (Gemini/Groq/Sarvam) need API keys to fully exercise
  intent extraction, voice transcription, and image understanding. Without
  keys, the rule-based fallback parser handles text input end-to-end so
  the demo flow still completes.


