#!/usr/bin/env bash
# SVG2Plotter Network — Setup script
# Linux Mint / Ubuntu / Raspberry Pi OS
# © 2026 David Marques · CICF · CDI Portugal

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="SVG2Plotter Network"
PORT=7733

echo ""
echo "══════════════════════════════════════════════════════"
echo "  ${APP_NAME}  v1.0  — Setup"
echo "  Centro de Inovação Carlos Fiolhais · CDI Portugal"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 1. Python ─────────────────────────────────────────────────────────────────
echo "[1/5] Checking Python..."
if ! command -v python3 &>/dev/null; then
    echo "      ✗ python3 not found. Install with: sudo apt install python3"
    exit 1
fi
PY=$(python3 --version)
echo "      ✓ ${PY}"

# ── 2. pip dependencies ───────────────────────────────────────────────────────
echo "[2/5] Installing Python dependencies..."
pip3 install flask flask-socketio pyserial --break-system-packages --quiet \
  || pip3 install flask flask-socketio pyserial --quiet
echo "      ✓ flask, flask-socketio, pyserial"

# ── 3. Serial port permissions (Linux) ───────────────────────────────────────
echo "[3/5] Configuring serial port permissions..."
if groups "$USER" | grep -q dialout; then
    echo "      ✓ User already in dialout group"
else
    sudo usermod -aG dialout "$USER"
    echo "      ✓ Added $USER to dialout group (re-login required for effect)"
fi

# ── 4. Create launcher script ─────────────────────────────────────────────────
echo "[4/5] Creating launcher..."
LAUNCHER="${APP_DIR}/start.sh"
cat > "${LAUNCHER}" << EOF
#!/usr/bin/env bash
cd "${APP_DIR}"
python3 server.py
EOF
chmod +x "${LAUNCHER}"
echo "      ✓ ${LAUNCHER}"

# ── 5. Desktop shortcut ───────────────────────────────────────────────────────
echo "[5/5] Creating Desktop shortcut..."
DESKTOP_DIR="${HOME}/Desktop"
mkdir -p "${DESKTOP_DIR}"
ENTRY="${DESKTOP_DIR}/SVG2Plotter-Network.desktop"
cat > "${ENTRY}" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SVG2Plotter Network
Comment=HPGL Vinyl Cutter — Network Server (port ${PORT})
Exec=bash "${LAUNCHER}"
Terminal=true
Categories=Graphics;
EOF
chmod +x "${ENTRY}"
echo "      ✓ ${ENTRY}"

# ── Summary ───────────────────────────────────────────────────────────────────
LOCAL_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "your-ip")
echo ""
echo "══════════════════════════════════════════════════════"
echo "  SETUP COMPLETE"
echo ""
echo "  To start the server:"
echo "    bash ${LAUNCHER}"
echo "    — or use the Desktop shortcut"
echo ""
echo "  Then open in any browser on your network:"
echo "    http://localhost:${PORT}"
echo "    http://${LOCAL_IP}:${PORT}"
echo ""
echo "  ⚠  If serial port was just configured, re-login"
echo "     for group permissions to take effect."
echo "══════════════════════════════════════════════════════"
echo ""
