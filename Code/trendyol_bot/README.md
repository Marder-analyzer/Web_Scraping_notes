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
| Bot dies on restart, restarts from page 1 | Scrapy `JOBDIR` resumes from exact position |
| Headless Chrome leaks RAM and crashes server | Anti-Leak architecture with `gc.collect()` |
| No visibility into what's running | Streamlit Dashboard with real-time control |
| All control via SSH terminal | MongoDB-backed command bus — control from browser |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    🖥️  STREAMLIT DASHBOARD                       │
│              (Command Center — browser accessible)               │
│    [Start] [Stop] [Force Kill] [Panic] [RAM Monitor]            │
└─────────────────────┬───────────────────────────────────────────┘
                      │  writes commands
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    🍃  MONGODB (Docker Container)                │
│                                                                  │
│  bot_commands ──── jobs ──── products ──── price_history        │
│  failed_urls  ──── proxy_performance ──── url_queue             │
└──────────┬──────────────────────────────────────────────────────┘
           │  listens & executes
           ▼
┌─────────────────────────────────────────────────────────────────┐
│               🎯  BOT MANAGER (bot_manager.py)                   │
│                  runs: nohup in background                       │
│                                                                  │
│  • Reads pending commands from bot_commands                      │
│  • Launches / monitors / force-kills bots                        │
│  • RAM Defense: kills zombie Chromes at >92%                     │
│  • Sends email alerts (80% warning, 92% auto-shutdown)           │
└───────────────┬──────────────────────────┬──────────────────────┘
                │                          │
                ▼                          ▼
┌───────────────────────┐    ┌─────────────────────────────────────┐
│  🕷️  SCRAPY BOT        │    │     🎭  PLAYWRIGHT WORKERS           │
│  (trendyol.py)        │    │     (playwright_worker.py)           │
│                       │    │                                      │
│  • URL Discovery      │    │  Worker 1 — İtfaiye (Firefighter)   │
│  • Category crawler   │    │    → Fixes 403/CAPTCHA blocked URLs  │
│  • JOBDIR resume ✅   │    │                                      │
│  • 403 error logging  │    │  Worker 2 — Hızlı Fiyat (Fast Price)│
│  • Proxy rotation     │    │    → Updates JS-rendered prices      │
│                       │    │                                      │
└───────────────────────┘    │  Worker 3 — Liste Kurtar (Recovery) │
                             │    → Recovers full listing pages     │
                             │    → Extracts all 24 products/page   │
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
- **RAM Defense System:** monitors system memory, auto-kills Playwright at >92%
- Sends HTML email alerts for bot lifecycle events and RAM pressure
- Survives server restarts — syncs with DB on startup to recover zombie processes

---

### 🕷️ Scrapy Discovery Bot (`trendyol.py`)

The high-throughput crawler responsible for discovering new products across all categories and price ranges.

**Key Features:**
- Covers **450+ category × price-range combinations** across all Trendyol departments
- **JOBDIR Resume System:** uses `-s JOBDIR=crawls/trendyol_state` — if stopped, resumes from exact URL on restart with **zero RAM overhead**
- Rotating proxy middleware with ban detection and exponential backoff
- Automatic 403 error logging to `failed_urls` with `sayfa_turu` tagging (`liste` vs `urun`)
- Heartbeat pings to `jobs` collection every 10 items for zombie detection

---

### 🎭 Playwright Workers (`playwright_worker.py`)

Headless Chromium-based workers that handle tasks Scrapy cannot. Three operational modes:

| Mode | Command | Purpose |
|------|---------|---------|
| `hata_coz` | İtfaiye | Retries 403/price-missing URLs with real browser |
| `fiyat_guncelle` | Hızlı Fiyat | Updates today's prices for known products |
| `liste_kurtar` | Liste Kurtar | Enters blocked listing pages, extracts all 24 products |

**Anti-Memory-Leak Architecture:**
```python
browser = p.chromium.launch(
    headless=True,
    args=[
        "--disable-dev-shm-usage",    # Prevents /dev/shm crash on Linux
        "--disk-cache-size=1",         # Disables disk cache (no thrashing)
        "--disable-disk-cache",
        "--js-flags=--max-old-space-size=512",  # Hard RAM cap per tab
        "--disable-gpu",
        "--no-sandbox",
    ]
)
# After each session:
context.close()
browser.close()
gc.collect()  # Force Python GC — zero residue
```

---

### 📊 Streamlit Dashboard (`dashboard.py`)

A fully functional command-and-control interface accessible from any browser on the local network.

**Features:**
- Real-time job status with zombie detection (160s heartbeat timeout)
- Bot control buttons that write directly to MongoDB command bus
- Live system RAM gauge with per-bot RAM breakdown
- 🚨 **Panic Button** — kills all zombie Chrome processes instantly
- Email notification system for alerts and reports
- Proxy performance monitoring
- Hourly scraping speed snapshots

---

## 🗄️ Database Schema

**MongoDB Database:** `neuranovav_db`

| Collection | Purpose |
|---|---|
| `products` | Master product catalog (url, title, category, images, attributes) |
| `price_history` | Daily price snapshots per product (url + date unique index) |
| `jobs` | Scraping session tracking (status, stats, heartbeat, hourly snapshots) |
| `bot_commands` | Command bus between Dashboard and Bot Manager |
| `failed_urls` | Error queue for 403s, price-missing, timeouts (with `sayfa_turu` tag) |
| `proxy_performance` | Per-proxy ban/success counters and retirement tracking |
| `url_queue` | Resume queue for Scrapy (pending/processing/done states) |

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
```

### First Run — Clean Start on New Server

> ⚠️ **WARNING:** If you have existing product data on the server that you want to **keep**, do **NOT** drop the database. The pipeline uses `upsert` logic — it will update existing records and add new ones without creating duplicates.

```bash
# Only wipe the Scrapy resume state to force a fresh scan from Page 1
# This does NOT touch your MongoDB data
rm -rf crawls/
```

Scrapy will begin from page 1, build a fresh `crawls/trendyol_state/` directory automatically, and use upsert to update existing records without data loss.

> 🗑️ **Only drop the database if you are setting up on a completely empty server with zero existing data:**
> ```bash
> mongosh
> use neuranovav_db
> db.dropDatabase()  # DANGER: deletes ALL 450,000+ records — only for fresh empty servers
> exit
> ```

### Subsequent Runs — Resume from Checkpoint

No action needed. The Bot Manager detects the `crawls/trendyol_state/` directory and Scrapy automatically resumes from the last processed URL.

---

## 🔄 Fault Tolerance & Resume System

The system is designed to survive unexpected shutdowns at every layer:

| Layer | Mechanism | Recovery |
|---|---|---|
| Scrapy | `JOBDIR=crawls/trendyol_state` | Resumes from last URL on restart |
| Playwright Workers | MongoDB `cozuldu: False` queue | Retries all unresolved errors |
| Bot Manager | `sync_with_db()` on startup | Recovers zombie PIDs from DB |
| Dashboard | MongoDB state | Always reflects true system state |

---

## 🛡️ RAM Defense System

The system monitors RAM usage in real-time and responds automatically:

```
RAM < 80%   → Normal operation
RAM > 80%   → Warning email sent (max once per hour)
RAM > 92%   → AUTO-SHUTDOWN: all Playwright bots killed, zombies cleared,
               WSL shutdown (Windows) / drop_caches (Linux), report email sent
```

**Panic Button** (Dashboard): Manually triggers the same cleanup sequence on demand.

---

## 📁 Project Structure

```
trendyol_bot/
├── bot_manager.py          # Orchestrator — the brain
├── dashboard.py            # Streamlit command center
├── playwright_worker.py    # Playwright workers (3 modes)
├── crawls/
│   └── trendyol_state/     # Scrapy JOBDIR resume checkpoint
├── logs/
│   ├── ana_bot.log
│   ├── pw_liste.log
│   └── manager.log
├── trendyol_bot/
│   ├── spiders/
│   │   ├── trendyol.py     # Main discovery spider
│   │   ├── fiyat_guncelle.py
│   │   ├── kategoriler.py
│   │   └── fiyatlar.py
│   ├── pipelines.py        # MongoDB write pipeline
│   ├── items.py
│   ├── extensions.py       # LiveProxyUpdater
│   └── middlewares.py
├── tests/
│   ├── test_pipeline.py
│   ├── test_spider.py
│   └── test_temizleyiciler.py
└── .env                    # Gmail credentials (not committed)
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with obsession for reliability. NeuraNovaV doesn't stop.*
