#!/bin/bash
while true; do
    sleep 60
    # Ping kontrolü
    PING_FAIL=0
    if ! ping -c 2 -W 3 8.8.8.8 > /dev/null 2>&1; then
        PING_FAIL=1
    fi
    # Transmit timeout kontrolü
    TX_TIMEOUT=$(dmesg --since "2 minutes ago" 2>/dev/null | grep -c "transmit queue.*timed out")
    if [ "$PING_FAIL" -eq 1 ] || [ "$TX_TIMEOUT" -gt 0 ]; then
        echo "$(date): NIC sorun tespit edildi (ping=$PING_FAIL, tx_timeout=$TX_TIMEOUT), enp7s0 resetleniyor..." >> /var/log/nic-watchdog.log
        ip link set enp7s0 down
        sleep 3
        ip link set enp7s0 up
        sleep 5
        echo "$(date): Reset tamamlandi" >> /var/log/nic-watchdog.log
    fi
done