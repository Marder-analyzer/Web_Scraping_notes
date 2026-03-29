#!/bin/bash
while true; do
    sleep 60
    if ! ping -c 2 -W 3 8.8.8.8 > /dev/null 2>&1; then
        echo "$(date): Baglanti koptu, enp7s0 resetleniyor..." >> /var/log/nic-watchdog.log
        ip link set enp7s0 down
        sleep 3
        ip link set enp7s0 up
        sleep 5
        echo "$(date): Reset tamamlandi" >> /var/log/nic-watchdog.log
    fi
done