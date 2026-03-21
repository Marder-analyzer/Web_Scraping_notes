#!/bin/bash
cd ~/trendyol/trendyol_bot
source venv/bin/activate
nohup python -u bot_manager.py > logs/manager.log 2>&1 &
nohup streamlit run dashboard.py > logs/dashboard.log 2>&1 &
echo "Bot Manager ve Dashboard başlatıldı"