# 🛍️ Vyapaar-Mitra

**AI-powered hyperlocal commerce without mandatory inventory**
Problem statement: **MU-PS-008 — The Small-Shop Digital Gap · Local Commerce Enablement**

> *"Don't force the shopkeeper to learn software. Make the software understand the shopkeeper."*

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
python -m scripts.test_pipeline    # full pipeline against a live MongoDB
```

Covered: Haversine, GeoJSON, category matching, capability matching, merchant ranking,
zero-inventory precedence, cooldown configuration, intent validation and clamping, auth token
expiry, password hashing, role authorization, khata arithmetic, demand aggregation output.

**Verification status.** This project was authored in a sandbox without network access, so the
third-party dependencies could never be installed there. Every module compiles, and the
dependency-free suites (`test_geo.py`, `test_khata.py` — 16 tests) were executed and pass. The
suites that import pydantic, bson or httpx have *not* been run yet. Run `pytest` once after
`pip install -r requirements.txt` before relying on them.

## 14. Demo script (2 minutes)

**Setup:** `docker compose up`, `python -m scripts.seed_demo_data --reset`, one merchant
account linked to a second Telegram account with a location within 500 m.

1. **Customer** sends a voice note:
   *"Mere sink ke niche pipe leak ho raha hai, usko rokne wala safed tape chahiye."*
2. **Bot** replies instantly: `🔍 Samajh raha hoon... Nearby shops locate kar raha hoon.`
3. **Sarvam** transcribes → **Gemini** returns `Teflon Tape · hardware · plumbing · 0.94`
4. **Matching** picks Sharma Hardware — 200 m away, hardware, plumbing capability,
   **zero inventory**
5. **Merchant** receives the request and taps **✅ YES**, then types `30`
6. **Customer** receives: `🎉 Nearby match found! Sharma Hardware · ~200m · Teflon Tape · ₹30`
7. **Second merchant** taps **❌ NO** → a `DemandEvent` is written and a 12-hour cooldown is set
8. **`/demand`** shows the aggregate: `Teflon Tape — 18 requests, 11 unavailable`
9. **Same customer** taps **🛒 Browse Nearby → 🧺 What's in stock nearby** and sees Gupta
   Electricals' listed Electrical Tape at ₹25, taps 🧭 Navigate, and Maps opens with
   walking directions already filled in

Closing line:

> Traditional commerce asks: *What products has this shop uploaded?*
> Vyapaar-Mitra asks: *Who nearby can satisfy this customer's need?*

No Telegram handy? `python -m scripts.test_pipeline` prints the same flow end to end, and
`POST /api/test/match` runs it over HTTP.

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
| GET | `/api/v1/requests/mine` · `/api/v1/requests/{id}` | history & live offers |
| POST | `/api/v1/requests/choose` | customer picks the winning shop |
| GET/POST | `/api/v1/merchant/shop` · `/inbox` · `/respond` | merchant inbox (same YES/NO as bot buttons) |
| GET/POST/PATCH/DELETE | `/api/v1/merchant/inventory…` | inventory CRUD + stock toggle |
| GET/POST | `/api/v1/merchant/khata` | digital ledger |
| GET | `/api/v1/merchant/demand` | neighbourhood demand signal |

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
- Merchant reputation and verified-shop badges
- Multi-merchant bidding with time-boxed offers
- Restock suggestions driven by demand events
- Delivery-partner hand-off (out of scope today by design)
- Regional language expansion beyond Hindi/Hinglish via Sarvam
- Offline-first SMS fallback for feature phones

## 19. Design notes / non-goals

Deliberately **not** built: Next.js or React, a large web dashboard, a mobile app, payments,
delivery management, worker marketplaces, microservices, Kubernetes, Kafka, Celery, Redis, or a
vector database. The interface is Telegram plus a few server-rendered HTML pages. An MVP that
runs on one process and one database is the point.

One more thing the system never does: claim a sale happened. A merchant's YES means
*"I have this in stock"* — nothing more. The customer still walks in and buys.
