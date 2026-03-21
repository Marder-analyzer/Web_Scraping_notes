# 🕵️ NeuraNovaV — E-Commerce Data Intelligence Pipeline

> **Fault-Tolerant, Multi-Agent, Asynchronous Data Pipeline**  
> Deployed on Ubuntu Server · 450,000+ Products · Zero Memory Leaks

[![Python](https://img.shields.io/badge/Python-3.14-blue?logo=python)](https://python.org)
[![Scrapy](https://img.shields.io/badge/Scrapy-2.14.1-green?logo=scrapy)](https://scrapy.org)
[![MongoDB](https://img.shields.io/badge/MongoDB-7.0-green?logo=mongodb)](https://mongodb.com)
[![Playwright](https://img.shields.io/badge/Playwright-latest-orange?logo=playwright)](https://playwright.dev)
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red?logo=streamlit)](https://streamlit.io)

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Architecture](#-system-architecture)
- [Components](#-components)
- [Database Schema](#-database-schema)
- [Tech Stack](#-tech-stack)
- [Installation](#-installation)
- [Running the System](#-running-the-system)
- [Dashboard](#-dashboard)
- [Fault Tolerance](#-fault-tolerance--resume-system)
- [RAM Defense System](#-ram-defense-system)

---

## 🌐 Overview

NeuraNovaV is a production-grade e-commerce intelligence pipeline built to continuously discover, extract, and track product data from Trendyol at scale. The system operates 24/7 on an Ubuntu server (CasaOS), manages a catalog of **450,000+ products**, and is designed to survive server restarts, proxy bans, and memory pressure without losing a single data point.

### The Core Paradigm: Monolith Killer with Micro-Workers

| Problem | Solution |
|---|---|
| Scrapy can't render JS-heavy dynamic prices | Playwright Workers handle complex rendering |
| Bot dies on restart, loses progress | MongoDB unique index prevents duplicates — real progress tracked from DB |
| Headless Chrome leaks RAM and crashes server | Dynamic RAM pay system + Anti-Leak architecture with `gc.collect()` |
| No visibility into what's running | Streamlit Dashboard with real-time control |
| All control via SSH terminal | MongoDB-backed command bus — control from browser |
| Multiple bots competing for RAM | Centralized weighted RAM allocation per bot count |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    🖥️  STREAMLIT DASHBOARD                       │
│              (Command Center — browser accessible)               │
│    [Start] [Stop] [Force Kill] [Panic] [RAM Monitor]            │
│    [Progress from DB] [Estimated Completion] [Proxy Countdown]  │
└─────────────────────┬───────────────────────────────────────────┘
                      │  writes commands
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    🍃  MONGODB (Docker Container)                │
│                                                                  │
│  bot_commands ──── jobs ──── products ──── price_history        │
│  failed_urls  ──── proxy_performance ──── proxy_logs            │
│  ram_shares (bot_commands) ── ram_throttle (bot_commands)       │
└──────────┬──────────────────────────────────────────────────────┘
           │  listens & executes
           ▼
┌─────────────────────────────────────────────────────────────────┐
│               🎯  BOT MANAGER (bot_manager.py)                   │
│                  runs: nohup in background                       │
│                                                                  │
│  • Reads pending commands from bot_commands every 2s            │
│  • Launches / monitors / force-kills bots                        │
│  • recalculate_ram_shares() on every bot start/stop             │
│  • Dynamic RAM pay system (weighted allocation)                  │
│  • Kills zombie Chromes at system >92%                           │
│  • Sends rich HTML email alerts with live system summary         │
└───────────────┬──────────────────────────┬──────────────────────┘
                │                          │
                ▼                          ▼
┌───────────────────────┐    ┌─────────────────────────────────────┐
│  🕷️  SCRAPY BOTS       │    │     🎭  PLAYWRIGHT WORKERS           │
│                       │    │     (playwright_worker.py)           │
│  trendyol.py          │    │                                      │
│  • URL Discovery      │    │  Worker 1 — İtfaiye (Firefighter)   │
│  • 450+ categories    │    │    → Fixes 403/CAPTCHA blocked URLs  │
│  • RAM throttle ✅    │    │    → Reads from failed_urls queue    │
│  • 403 error logging  │    │                                      │
│                       │    │  Worker 2 — Hızlı Fiyat (Fast Price)│
│  fiyat_guncelle.py    │    │    → Updates Playwright-added prices │
│  • Price-only updates │    │                                      │
│  • RAM throttle ✅    │    │  Worker 3 — Liste Kurtar (Recovery) │
│                       │    │    → Recovers full listing pages     │
└───────────────────────┘    │    → Extracts all 24 products/page  │
                             │    → RAM check before each URL ✅   │
                             └─────────────────────────────────────┘
```

---

## 🧩 Components

### 🎯 Bot Manager (`bot_manager.py`)

The orchestration brain of the entire system. Runs continuously in the background via `nohup`.

**Responsibilities:**
- Polls `bot_commands` MongoDB collection every 2 seconds
- Launches Scrapy and Playwright bots as subprocesses
- Monitors running processes for crashes (exit code tracking)
- Force-kills unresponsive processes (`force_stop`, `panic_kill` commands)
- **Centralized RAM Pay System:** calls `recalculate_ram_shares()` on every bot start/stop
- **RAM Defense System:** monitors system memory, auto-kills Playwright at >92%
- Sends rich HTML email alerts with live system summary for every bot lifecycle event
- Survives server restarts — syncs with DB on startup to recover zombie processes

**Important:** Email notifications are sent exclusively from Bot Manager. Pipeline-level mail was removed to eliminate duplicate notifications.

---

### 🕷️ Scrapy Discovery Bot (`trendyol.py`)

The high-throughput crawler responsible for discovering new products across all categories and price ranges.

**Key Features:**
- Covers **450+ category × price-range combinations** across all Trendyol departments
- **No JOBDIR** — resume logic is handled by MongoDB `url` unique index. Duplicate prevention is at the pipeline level; progress is tracked from the real product count in DB
- Rotating proxy middleware with ban detection and exponential backoff
- Automatic error logging to `failed_urls` with `sayfa_turu` tagging (`liste` vs `urun`)
- **RAM Throttle:** reads `scrapy_limit` from `bot_commands` every 50 requests and adjusts `concurrent` dynamically
- Heartbeat pings to `jobs` collection every 10 items for zombie detection

**RAM Throttle Logic:**

```python
# Every 50 requests:
shares = cmd_col.find_one({"bot_id": "ram_shares"})
scrapy_limit = shares.get("scrapy_limit", 80)

if   proje_yuzde > scrapy_limit:              concurrent = 2
elif proje_yuzde > scrapy_limit * 0.90:       concurrent = 4
elif proje_yuzde > scrapy_limit * 0.75:       concurrent = 8
else:                                          concurrent = 16
```

---

### 💰 Price Update Bot (`fiyat_guncelle.py`)

Runs independently from discovery. Never visits category pages — reads existing product URLs directly from MongoDB and updates only price and rating data.

| Feature | trendyol.py | fiyat_guncelle.py |
|---|---|---|
| Purpose | New product discovery | Price / rating update |
| Resource Usage | High (category traversal) | Low (direct URL hits) |
| Data Collected | Full metadata | Price + rating only |
| Frequency | Weekly / monthly | Daily |

---

### 🎭 Playwright Workers (`playwright_worker.py`)

Headless Chromium-based workers that handle tasks Scrapy cannot. Three operational modes:

| Mode | Command | Purpose |
|------|---------|---------|
| `hata_coz` | İtfaiye | Retries 403/price-missing/timeout URLs with real browser |
| `fiyat_guncelle` | Hızlı Fiyat | Updates prices for Playwright-added products |
| `liste_kurtar` | Liste Kurtar | Enters blocked listing pages, extracts all 24 products |

**Error Queue Filter (mod1):**
```python
# Playwright reads ALL normalized error types:
{"hata_tipi": {"$in": [
    "price_missing", "HTTP_403", "HTTP_429",
    "CONNECTION_ERROR",   # All timeout/connection errors normalized here
    "TCPTimedOutError", "TimeoutError"
]}}
```

**RAM Check Before Each URL:**
```python
asil_limit, proje_yuzde, limit = check_playwright_ram()
if asil_limit:
    time.sleep(10)   # Wait 10s, let RAM drop
    asil_limit, _, _ = check_playwright_ram()
    if asil_limit:
        continue     # Still high — skip this URL
```

**Anti-Memory-Leak Architecture:**
```python
browser = p.chromium.launch(
    headless=True,
    args=[
        "--disable-dev-shm-usage",
        "--disk-cache-size=1",
        "--disable-disk-cache",
        "--js-flags=--max-old-space-size=512",
        "--disable-gpu",
        "--no-sandbox",
    ]
)
context.close()
browser.close()
gc.collect()
```

---

### 📊 Streamlit Dashboard (`dashboard.py`)

A fully functional command-and-control interface accessible from any browser on the local network.

**Features:**
- Real-time job status with zombie detection (160s heartbeat timeout)
- Bot control buttons that write directly to MongoDB command bus
- **Progress tracking from DB** — `products.count_documents({})` instead of job counter; never resets on bot restart
- **Estimated completion time** — calculated from current scraping speed (days/hours remaining)
- **Proxy countdown** — time since last update and time until next update (mm:ss)
- **Proxy intelligence** — active / retired / total proxy counts + per-source breakdown
- Live system RAM gauge with per-bot RAM breakdown
- URL error tracking — resolved vs unresolved breakdown, error type distribution
- 🚨 **Panic Button** — kills all zombie Chrome processes instantly
- **Unified email system** — manual report sender with full system summary

---

## 🗄️ Database Schema

**MongoDB Database:** `neuranovav_db`

| Collection | Purpose |
|---|---|
| `products` | Master product catalog (url, title, category, images, attributes, scrape_method) |
| `price_history` | Daily price snapshots per product (url + date unique index) |
| `jobs` | Scraping session tracking (status, stats, heartbeat, hourly snapshots) |
| `bot_commands` | Command bus + RAM pay data (ram_shares, ram_throttle, proxy_stats) |
| `failed_urls` | Error queue — normalized error types, sayfa_turu tag, cozuldu flag |
| `proxy_performance` | Per-proxy ban/success counters and retirement tracking |
| `proxy_logs` | Per-source proxy fetch history (toplam, tr, yabanci, cop, yeni_eklenen) |

**5-State Telemetry (per job):**
```
yeni_urun       → Brand new product inserted
yeni_gun_kaydi  → Existing product, new price record for today
gun_ici_degisim → Price updated within same day
drop_fiyatsiz   → Dropped: no price found
drop_hata       → Dropped: parse error
```

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Discovery Crawler | Scrapy 2.14.1 |
| JS Rendering | Playwright (Chromium) |
| Database | MongoDB 7.0 (Docker) |
| Dashboard | Streamlit |
| Orchestration | Custom Bot Manager (Python) |
| Process Monitoring | psutil |
| Proxy Rotation | rotating-proxies + custom LiveProxyUpdater |
| Server OS | Ubuntu 24.04 (CasaOS) |
| Containerization | Docker |

---

## ⚙️ Installation

### 1. Clone & Setup

```bash
git clone https://github.com/Marder-analyzer/Web_Scraping_notes.git
cd Web_Scraping_notes/Code/trendyol_bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Install Playwright (Linux — required on Ubuntu)

```bash
playwright install chromium
playwright install-deps chromium
```

### 3. Environment Variables

Create a `.env` file in the project root:

```env
MAIL_SENDER=your_gmail@gmail.com
MAIL_APP_PASS=your_app_password
```

### 4. MongoDB (Docker)

```bash
docker run -d \
  --name neuranovav_mongo \
  -p 27017:27017 \
  -v mongo_data:/data/db \
  --restart unless-stopped \
  mongo:7.0
```

---

## 🚀 Running the System

### Ubuntu Server (Production)

```bash
# 1. Start Bot Manager (background, persistent)
nohup python -u bot_manager.py > logs/manager.log 2>&1 &

# 2. Start Dashboard (background, accessible at :8501)
nohup streamlit run dashboard.py > logs/dashboard.log 2>&1 &

# 3. Monitor logs
tail -f logs/manager.log
tail -f logs/ana_bot.log
```

### First Run — Clean Start on New Server

> ⚠️ **WARNING:** If you have existing product data you want to **keep**, do **NOT** drop the database. The pipeline uses `upsert` logic — it will update existing records and add new ones without duplicates.

```bash
# Fresh start — wipe all data
python -c "
import pymongo
db = pymongo.MongoClient()['neuranovav_db']
db.failed_urls.drop()
db.proxy_performance.drop()
db.jobs.drop()
db.price_history.drop()
db.products.drop()
db.proxy_logs.drop()
db.bot_commands.drop()
print('Clean slate ready.')
"
python -c "open('proxies.txt', 'w').close()"
```

### Subsequent Runs — Just Start Bot Manager

No action needed. Progress is tracked from the actual product count in MongoDB — not from any file-based state. The Bot Manager detects already-running processes via `sync_with_db()` on startup.

---

## 🔄 Fault Tolerance & Resume System

The system is designed to survive unexpected shutdowns at every layer:

| Layer | Mechanism | Recovery |
|---|---|---|
| Scrapy | MongoDB `url` unique index | Same URL processed twice → upsert, no duplicate |
| Progress Tracking | `products.count_documents({})` | Dashboard never resets on bot restart |
| Playwright Workers | MongoDB `cozuldu: False` queue | Retries all unresolved errors on next run |
| Bot Manager | `sync_with_db()` on startup | Recovers zombie PIDs from DB |
| Dashboard | MongoDB state | Always reflects true system state |

**Note:** JOBDIR was removed in the current version. The file-based resume mechanism caused unnecessary disk I/O and RAM pressure (loading all URL hashes on startup). MongoDB unique index provides the same duplicate-prevention guarantee at the pipeline level with zero overhead.

---

## 🛡️ RAM Defense System

The system uses a **three-layer** RAM defense strategy:

### Layer 1 — Centralized Pay System (`recalculate_ram_shares`)

Triggered on every bot start/stop. Writes weighted allocations to MongoDB:

| Bot | Weight | Reason |
|---|---|---|
| ana_bot | 1x | Scrapy — CPU-heavy, RAM-light |
| scrapy_fiyat | 1x | Scrapy — direct URL hits |
| pw_hata | 2x | Playwright — Chrome instance |
| pw_fiyat | 2x | Playwright — Chrome instance |
| pw_liste | 2x | Playwright — Chrome instance |

**Allocation rules:**
- **1 bot running** → full access up to 88% system RAM, no limits
- **Multiple bots** → 78% shared pool (88% minus 10% fixed for MongoDB/dashboard) split by weight
- **Bot stops** → shares automatically recalculated, remaining bots get more

### Layer 2 — Per-Bot RAM Throttle

**Scrapy bots** (every 50 requests):
```
RAM < limit × 75%  → concurrent = 16  (full speed)
RAM < limit × 90%  → concurrent = 8
RAM < limit × 100% → concurrent = 4
RAM > limit        → concurrent = 2   (minimum)
```

**Playwright bots** (before every URL):
```
RAM < limit × 90%  → proceed normally
RAM < limit        → log warning, proceed
RAM > limit        → sleep 10s → recheck → skip if still high
```

### Layer 3 — System-Level Safety Shutdown

```
System RAM < 80%  → Normal operation
System RAM > 80%  → Warning email (max once per hour)
System RAM > 92%  → AUTO-SHUTDOWN:
                    • All Playwright bots killed
                    • Zombie Chrome processes cleared
                    • Python GC forced
                    • WSL shutdown (Windows) / drop_caches (Linux)
                    • Report email sent
```

**Panic Button** (Dashboard): Manually triggers the same cleanup sequence on demand.

---

## 📁 Project Structure

```
trendyol_bot/
├── bot_manager.py          # Orchestrator — the brain
├── dashboard.py            # Streamlit command center
├── playwright_worker.py    # Playwright workers (3 modes)
├── proxies.txt             # Active proxy list (auto-managed by LiveProxyUpdater)
├── logs/
│   ├── ana_bot.log
│   ├── pw_hata.log
│   ├── pw_liste.log
│   ├── pw_fiyat.log
│   └── manager.log
├── trendyol_bot/
│   ├── spiders/
│   │   ├── trendyol.py         # Main discovery spider
│   │   ├── fiyat_guncelle.py   # Price update spider
│   │   ├── kategoriler.py      # Category definitions
│   │   └── fiyatlar.py         # Price range definitions
│   ├── pipelines.py            # MongoDB write pipeline
│   ├── extensions.py           # LiveProxyUpdater
│   ├── middlewares.py          # RandomUserAgentMiddleware
│   ├── items.py
│   └── settings.py
├── tests/
│   ├── test_pipeline.py
│   ├── test_spider.py
│   └── test_temizleyiciler.py
└── .env                        # Gmail credentials (not committed)
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with obsession for reliability. NeuraNovaV doesn't stop.*