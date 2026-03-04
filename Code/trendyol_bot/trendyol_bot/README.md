# 🚀 NeuraNovaV — E-Commerce Data Intelligence Pipeline

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Scrapy](https://img.shields.io/badge/Scrapy-2.x-green.svg)
![MongoDB](https://img.shields.io/badge/MongoDB-7.0-success.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-red.svg)
![Docker](https://img.shields.io/badge/Docker-Containerized-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 📌 About The Project

This repository contains the **autonomous data extraction and market intelligence pipeline** for **NeuraNovaV**, an AI-driven e-commerce assistant. Built with production-grade data engineering principles, this system continuously crawls Trendyol, extracts rich product metadata, and tracks price and rating fluctuations over time — without overwhelming the target servers.

The ultimate goal is to feed NeuraNovaV with real-time market intelligence so it can answer questions like:
> *"Has this product's price dropped since last week? Should I buy it now?"*

---

## ✨ Core Architecture & Features

### 🕸️ 1. Dual-Spider System

| Spider | Command | Purpose |
|---|---|---|
| `trendyol.py` | `scrapy crawl trendyol` | Discovers new products by navigating categories. Extracts full metadata: titles, dynamic attributes, image URLs, descriptions. |
| `fiyat_guncelle.py` | `scrapy crawl fiyat_guncelle` | High-speed updater. Reads existing URLs directly from MongoDB and surgically updates only prices and review counts — no category traversal needed. |

### 🛡️ 2. Fault-Tolerant Data Pipeline (`pipelines.py`)

- **Smart Upserts:** Separates immutable product data (`products` collection) from time-series market data (`price_history` collection).
- **Partial Updates:** During fast-scraping passes, only successfully scraped fields are written — older metadata (titles, images) is never overwritten with `None`.
- **Advanced Telemetry — 5-State Classification:**

| State | Meaning |
|---|---|
| `yeni_urun` | Brand new product, never seen before |
| `yeni_gun_kaydi` | Known product, but first price record of the day |
| `gun_ici_degisim` | Already recorded today, but price or rating changed |
| `drop_fiyatsiz` | Dropped — product out of stock or price unavailable |
| `drop_hata` | Dropped — malformed price format or parsing error |

- **Anti-Ban Measures:** Custom User-Agent rotation middleware, AutoThrottle, and rotating proxy support via `scrapy-rotating-proxies`.
- **Optimized Regex:** Pre-compiled regex patterns for rating extraction to reduce CPU overhead at scale.
- **URL Hygiene:** Tracking parameters (`utm_source`, `gclid`) are stripped while critical pricing parameters (`boutiqueId`, `merchantId`) are preserved.

### 📡 3. Real-Time Command Center (`dashboard.py`)

- **Live Streamlit Dashboard** — Auto-refreshes every 10 seconds via `streamlit-autorefresh`.
- **Heartbeat & Zombie Job Detection** — Pipeline sends a heartbeat to MongoDB every 10 items. Dashboard detects crashed jobs (e.g., killed via `Ctrl+C`) by checking if the last heartbeat exceeds a 120-second threshold.
- **KPI Metrics (2-row layout):**
  - Row 1: Total URLs processed, Items dropped, Last heartbeat time
  - Row 2: New products discovered, First record of the day, Intra-day price/rating changes
- **Data Quality Analytics** — Plotly donut charts show the exact breakdown of why items were dropped, in real time.
- **Live Product Feed** — A continuously updating table showing the last 5 products added to the database.
- **Category Distribution Chart** — Bar chart of the top 10 most-scraped product categories.
- **Export Capabilities:** A sidebar feature allowing one-click downloads of all historical job reports and telemetry data as a CSV file for end-of-month analysis.

---

## 🗄️ Database Schema

All data is stored in a self-hosted **MongoDB 7.0** instance running inside Docker.

### `products` — Unique Product Catalog
```json
{
  "url": "https://www.trendyol.com/pd/...",
  "title": "Product Title",
  "category": "Trendyol > Kadın > Kadın Giyim > ...",
  "attributes": { "Renk": "Siyah", "Beden": "M" },
  "images": ["https://cdn.trendyol.com/..."],
  "explanation": "Product description text...",
  "last_seen": "2026-03-04T10:00:00Z"
}
```
> `url` is uniquely indexed for O(1) lookups at any scale.

### `price_history` — Time-Series Market Data
```json
{
  "url": "https://www.trendyol.com/pd/...",
  "date": "2026-03-04",
  "price": 1299.99,
  "evaluation": 4.7,
  "evaluation_len": 312
}
```
> Compound unique index on `(url, date)` prevents duplicate daily records.

### `jobs` — Operational Telemetry
```json
{
  "job_id": "20260304_100000",
  "status": "Completed",
  "start_time": "...",
  "end_time": "...",
  "duration_seconds": 3421.5,
  "total_processed": 5000,
  "stats": {
    "yeni_urun": 320,
    "yeni_gun_kaydi": 4200,
    "gun_ici_degisim": 480,
    "drop_fiyatsiz": 0,
    "drop_hata": 0
  },
  "last_ping": "..."
}
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Scraping Framework | Scrapy |
| Database | MongoDB 7.0 (Docker) |
| DB Driver | PyMongo |
| Data Processing | Pandas, Regex |
| Visualization | Streamlit, Plotly Express |
| Anti-Ban | scrapy-rotating-proxies, Custom UA Middleware |
| Containerization | Docker |

---

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.9+
- Docker Desktop (or Docker Engine on Linux)

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/neuranovav-scraper.git
cd neuranovav-scraper
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install scrapy pymongo pandas streamlit plotly streamlit-autorefresh scrapy-rotating-proxies
```

### 4. Start MongoDB with Docker
```bash
docker run -d \
  --name neuranovav_mongo \
  --restart always \
  -p 27017:27017 \
  -v neuranovav_data:/data/db \
  mongo:7.0
```

MongoDB will be available at `mongodb://localhost:27017/`. Data is persisted in a Docker volume (`neuranovav_data`) and survives container restarts.

---

## 🚀 Usage

### Step 1 — Launch the Live Dashboard
```bash
streamlit run dashboard.py
```
Opens automatically at **http://localhost:8501**

### Step 2 — Discover New Products
```bash
scrapy crawl trendyol
```
Navigates Trendyol categories, extracts full product metadata, and stores everything in MongoDB.

### Step 3 — Fast Price Update (Daily Use)
```bash
scrapy crawl fiyat_guncelle
```
Reads all known URLs from MongoDB and updates only prices and ratings — no category traversal, maximum speed.

---

## 📁 Project Structure

```
neuranovav-scraper/
├── trendyol_bot/
│   ├── spiders/
│   │   ├── trendyol.py          # Discovery spider
│   │   ├── fiyat_guncelle.py    # Price updater spider
│   │   └── selector.py          # CSS/XPath selector definitions
│   ├── pipelines.py             # MongoDB pipeline with telemetry
│   ├── middlewares.py           # User-Agent rotation middleware
│   ├── items.py                 # Scrapy item definitions
│   └── settings.py              # Scrapy configuration
├── dashboard.py                 # Streamlit monitoring dashboard
├── scrapy.cfg
└── README.md
```

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────┐
│              Scrapy Spiders                  │
│  trendyol.py          fiyat_guncelle.py      │
│  (Full Discovery)     (Price-Only Update)    │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│           TrendyolBotPipeline               │
│  • Data validation & cleaning               │
│  • Smart upsert logic                       │
│  • 5-state telemetry classification         │
│  • Heartbeat every 10 items                 │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│          MongoDB (Docker)                    │
│  ┌──────────┐ ┌──────────────┐ ┌────────┐  │
│  │ products │ │ price_history│ │  jobs  │  │
│  └──────────┘ └──────────────┘ └────────┘  │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│       Streamlit Dashboard                    │
│  • Real-time KPIs & bot status              │
│  • Zombie job detection                      │
│  • Plotly data quality charts               │
│  • Live product feed                         │
└─────────────────────────────────────────────┘
```

---

## 🔮 Roadmap

- [ ] Docker Compose setup (MongoDB + Dashboard in single stack)
- [ ] Price drop alert system (Telegram / email notifications)
- [ ] NeuraNovaV AI integration — "Should I buy this now?" recommendations
- [ ] Proxy pool integration for large-scale production crawls
- [ ] Scheduled crawling with cron / Celery

---

## 📄 License

This project is part of the **NeuraNovaV** ecosystem.  
Built with ❤️ for AI-driven e-commerce intelligence.