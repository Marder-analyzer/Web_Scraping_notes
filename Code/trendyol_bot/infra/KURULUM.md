# Sunucu Kurulum Notları

## NIC Watchdog (Ağ Kartı Otomatik Reset)
Realtek r8169 sürücüsü yoğun trafikte donabiliyor. Çözüm:

### 1. Sürücü parametresi (kalıcı)
sudo cp infra/r8169.conf /etc/modprobe.d/r8169.conf
sudo update-initramfs -u

### 2. Watchdog servisi
sudo cp infra/nic-watchdog.sh /usr/local/bin/nic-watchdog.sh
sudo chmod +x /usr/local/bin/nic-watchdog.sh
sudo cp infra/nic-watchdog.service /etc/systemd/system/nic-watchdog.service
sudo systemctl daemon-reload
sudo systemctl enable nic-watchdog
sudo systemctl start nic-watchdog

### 3. CPU frekans limiti (ısınma önleme)
sudo cpupower frequency-set -u 4050MHz
# Kalıcı yapmak için rc.local'a ekli

## Reboot sonrası kontrol
sudo systemctl status nic-watchdog
sensors | grep "Package id"

