import streamlit as st
import pymongo
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(page_title="NeuraNovaV Komuta Merkezi", page_icon="🛸", layout="wide")
st_autorefresh(interval=10000, limit=100000, key="auto_refresh")

# --- BAĞLANTI ---
@st.cache_resource
def init_connection():
    return pymongo.MongoClient("mongodb://localhost:27017/")

client = init_connection()
db = client["neuranovav_db"]

# --- BAŞLIK VE ÖZET ---
st.title("🛸 NeuraNovaV Veri İstihbarat Kokpiti")
st.markdown("---")

latest_job = db.jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])

if latest_job:
    stats = latest_job.get("stats", {})
    
    # --- ZOMBIE JOB KONTROLÜ ---
    is_running = latest_job.get("status") == "Running"
    status_text = "🟢 AKTİF ÇALIŞIYOR" if is_running else "🔴 TAMAMLANDI"
    
    last_ping = latest_job.get("last_ping") or latest_job.get("start_time")
    if last_ping and is_running:
        fark = (datetime.now(timezone.utc) - last_ping.replace(tzinfo=timezone.utc)).total_seconds()
        if fark > 120:  # 2 dakika sinyal yoksa
            is_running = False
            status_text = "🔴 BAĞLANTI KOPTU (Zorla Kapatıldı)"
            
    st.subheader(f"Durum: {status_text}")
    
    # --- METRİKLER (2 SATIR HALİNDE) ---
    r1_col1, r1_col2, r1_col3 = st.columns(3)
    r1_col1.metric("Toplam İşlenen URL", latest_job.get("total_processed", 0))
    
    # --- ÇÖP DETAYLANDIRMASI ---
    drop_fiyatsiz = stats.get("drop_fiyatsiz", 0)
    drop_hata = stats.get("drop_hata", 0)
    total_dropped = drop_fiyatsiz + drop_hata
    
    r1_col2.metric("🗑️ Toplam Çöpe Giden", total_dropped, delta_color="inverse")
    # Sayının hemen altına küçük gri yazıyla detay ekliyoruz
    if total_dropped > 0:
        r1_col2.caption(f"📌 Neden: {drop_fiyatsiz} Fiyatsız | {drop_hata} Hatalı Veri")
    
    if last_ping:
        local_time = last_ping.replace(tzinfo=timezone.utc).astimezone().strftime("%H:%M:%S")
    else:
        local_time = "Sinyal Yok"
    r1_col3.metric("📡 Son Heartbeat", local_time)
    
    st.write("") # Boşluk
    
    r2_col1, r2_col2, r2_col3 = st.columns(3)
    r2_col1.metric("✨ Yeni Keşfedilen Ürün", stats.get("yeni_urun", 0))
    r2_col2.metric("📅 Bugünün İlk Kaydı", stats.get("yeni_gun_kaydi", 0))
    r2_col3.metric("🔄 Gün İçi Değişim (Fiyat/Puan)", stats.get("gun_ici_degisim", 0))

    st.markdown("---")

    # --- GRAFİK BÖLÜMÜ (2 KOLON) ---
    g_col1, g_col2 = st.columns([2, 1])

    with g_col1:
        st.subheader("🔍 Veri Kalite Analizi")
        
        # --- GÜNCELLENMİŞ PASTA GRAFİĞİ ---
        drop_data = {
            "Durum": ["Yeni Ürün", "Bugünün İlk Kaydı", "Gün İçi Değişim", "Çöp (Fiyatsız)", "Çöp (Hata)"],
            "Adet": [
                stats.get("yeni_urun", 0),
                stats.get("yeni_gun_kaydi", 0),
                stats.get("gun_ici_degisim", 0),
                stats.get("drop_fiyatsiz", 0),
                stats.get("drop_hata", 0)
            ]
        }
        df_drop = pd.DataFrame(drop_data)
        
        if df_drop["Adet"].sum() > 0:
            fig = px.pie(df_drop, values='Adet', names='Durum', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Grafik için veri bekleniyor...")

    with g_col2:
        st.subheader("⚡ Veritabanı Doluluk")
        total_products = db.products.count_documents({})
        st.metric("Toplam Benzersiz Ürün", f"{total_products:,}")
        
        total_history = db.price_history.count_documents({})
        st.metric("Toplam Fiyat Geçmişi", f"{total_history:,}")

    # --- CANLI VERİ AKIŞI (SON 5 ÜRÜN) ---
    st.markdown("---")
    st.subheader("📡 Canlı Veri Akışı (Son Eklenen/Güncellenen 5 Ürün)")
    
    cursor = db.products.find({}, {"title": 1, "category": 1, "last_seen": 1}).sort("last_seen", -1).limit(5)
    recent_products = list(cursor)
    
    if recent_products:
        df_recent = pd.DataFrame(recent_products)
        if "_id" in df_recent.columns:
            df_recent = df_recent.drop(columns=["_id"])
        
        df_recent["category"] = df_recent["category"].apply(lambda x: str(x).split(">")[-1].strip() if x else "-")
        
        # --- GÜVENLİ ZAMAN DİLİMİ DÖNÜŞÜMÜ ---
        df_recent["last_seen"] = pd.to_datetime(df_recent["last_seen"], utc=True).dt.tz_convert('Europe/Istanbul').dt.strftime('%H:%M:%S')
        
        df_recent.columns = ["Ürün Adı", "Kategori", "İşlem Saati"]
        st.table(df_recent)
    else:
        st.write("Henüz veri akışı yok.")

else:
    st.error("Henüz başlatılmış bir görev bulunamadı. Lütfen botu çalıştırın: 'scrapy crawl trendyol'")
    
# --- YAN MENÜ (SIDEBAR) VE RAPOR İNDİRME ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/9/93/MongoDB_Logo.svg/512px-MongoDB_Logo.svg.png", width=150)
    st.success("MongoDB Bağlantısı Aktif")
    st.caption("Son Yenilenme: " + datetime.now().strftime("%H:%M:%S"))
    
    if st.button("🔄 Anında Yenile"):
        st.rerun()
        
    st.markdown("---")
    st.subheader("📥 Rapor Arşivi")
    st.markdown("Bugüne kadarki tüm bot çalışma geçmişini Excel formatında (CSV) indirin.")
    
    # Tüm görev geçmişini veritabanından çek (ID'ler hariç)
    all_jobs = list(db.jobs.find({}, {"_id": 0})) 
    
    if all_jobs:
        df_jobs = pd.DataFrame(all_jobs)
        
        # İç içe geçmiş 'stats' istatistiklerini tablonun sütunlarına yayıyoruz
        if 'stats' in df_jobs.columns:
            stats_df = df_jobs['stats'].apply(pd.Series)
            df_jobs = pd.concat([df_jobs.drop(['stats'], axis=1), stats_df], axis=1)
            
        # CSV formatına çevir
        csv_data = df_jobs.to_csv(index=False).encode('utf-8')
        
        # İndirme Butonu
        st.download_button(
            label="📊 Tüm Geçmişi İndir (CSV)",
            data=csv_data,
            file_name=f"neuranovav_bot_raporlari_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("Henüz indirilecek geçmiş rapor yok.")