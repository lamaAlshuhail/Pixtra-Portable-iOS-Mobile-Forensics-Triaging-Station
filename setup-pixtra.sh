#!/bin/bash

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log() { echo -e "${GREEN}[PIXTRA]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; }

if [ "$EUID" -ne 0 ]; then err "Run as root: sudo ./setup-pixtra.sh"; exit 1; fi

PIUSER="${SUDO_USER:-pixtra}"
HOMEDIR=$(getent passwd "$PIUSER" | cut -d: -f6)
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE_STORAGE="${PIXTRA_CASE_STORAGE:-/mnt/evidence/cases}"
ROTATE_DISPLAY="${PIXTRA_ROTATE_DISPLAY:-0}"

log "Installing Pixtra from $REPO_DIR for user $PIUSER"

log "1/7 - System packages"
apt-get update -qq
apt-get install -y -qq \
  python3 python3-pip python3-venv \
  usbmuxd libimobiledevice6 libimobiledevice-utils \
  adb fastboot libusb-1.0-0-dev \
  python3-pyqt6 python3-pyqt6.qtwebengine \
  pcscd libpcsclite-dev swig \
  sqlite3 git curl wget unzip wlr-randr
apt-get install -y -qq chromium 2>/dev/null || apt-get install -y -qq chromium-browser || warn "Chromium not installed; the browser UI is optional"

systemctl enable --now usbmuxd
systemctl enable --now pcscd

log "2/7 - Python packages"
pip3 install --break-system-packages \
  -r "$REPO_DIR/pixtra-backend/requirements.txt" \
  -r "$REPO_DIR/pixtra-backend/requirements-device.txt" \
  -r "$REPO_DIR/pixtra-qt/requirements.txt"

log "3/7 - Evidence storage at $CASE_STORAGE"
mkdir -p "$CASE_STORAGE"
chown -R "$PIUSER:$PIUSER" "$(dirname "$CASE_STORAGE")"
if ! grep -q "/mnt/evidence" /etc/fstab; then
  echo '#/dev/sda1 /mnt/evidence ext4 defaults,nofail 0 2' >> /etc/fstab
fi

log "4/7 - Network: leave tethered iPhones alone"
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/ignore-iphone.conf << 'EOC'
[keyfile]
unmanaged-devices=driver:ipheth
EOC

log "5/7 - Backend service"
cat > /etc/systemd/system/pixtra.service << EOS
[Unit]
Description=Pixtra Forensic Backend
After=network.target usbmuxd.service

[Service]
Type=simple
User=$PIUSER
WorkingDirectory=$REPO_DIR/pixtra-backend
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=3
Environment=PIXTRA_CASE_STORAGE=$CASE_STORAGE
Environment=PIXTRA_DB_PATH=$REPO_DIR/pixtra-backend/data/pixtra.db

[Install]
WantedBy=multi-user.target
EOS
systemctl daemon-reload
systemctl enable --now pixtra

log "6/7 - Touch UI autostart (kiosk)"
AUTOSTART_DIR="$HOMEDIR/.config/labwc"
sudo -u "$PIUSER" mkdir -p "$AUTOSTART_DIR"
AUTOSTART="$AUTOSTART_DIR/autostart"
touch "$AUTOSTART"; chown "$PIUSER:$PIUSER" "$AUTOSTART"
if [ "$ROTATE_DISPLAY" = "1" ] && ! grep -q "wlr-randr" "$AUTOSTART"; then
  echo 'wlr-randr --output DSI-2 --transform 180 &' >> "$AUTOSTART"
fi
if ! grep -q "pixtra-qt/main.py" "$AUTOSTART"; then
  echo "PIXTRA_KIOSK=1 python3 $REPO_DIR/pixtra-qt/main.py &" >> "$AUTOSTART"
fi

log "7/7 - checkra1n (optional, for checkm8 devices)"
if [ ! -f "$HOMEDIR/checkra1n" ]; then
  if wget -q -O "$HOMEDIR/checkra1n" \
    "https://assets.checkra.in/downloads/linux/cli/arm64/43019a573ab1c866fe88edb1f2dd5bb38b0caf135533ee0d6e3ed720256b89d0/checkra1n"; then
    chmod +x "$HOMEDIR/checkra1n"; chown "$PIUSER:$PIUSER" "$HOMEDIR/checkra1n"
  else
    warn "checkra1n download failed; the checkm8 page will report it as missing"
  fi
fi

echo ""
echo "=========================================================="
echo -e "${GREEN}  PIXTRA SETUP COMPLETE${NC}"
echo "=========================================================="
echo ""
echo "  Backend:   systemctl status pixtra"
echo "  Password:  journalctl -u pixtra | grep 'Initial password'"
echo "  Touch UI:  starts on next login, or run: PIXTRA_KIOSK=1 python3 $REPO_DIR/pixtra-qt/main.py"
echo "  Browser:   http://localhost:8080"
echo "  Cases:     $CASE_STORAGE   (mount a USB drive at /mnt/evidence for removable storage)"
echo ""
echo "  Display mounted upside down? Re-run with PIXTRA_ROTATE_DISPLAY=1"
echo ""
