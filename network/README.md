# ✂ SVG2Plotter Network

**HPGL Vinyl Cutter — LAN Server Edition**  
_Access your vinyl cutter from any browser on your network_

> Developed by **David Marques** — *Vibe Coding with Claude.ai*  
> Centro de Inovação Carlos Fiolhais · CDI Portugal

---

## What is this?

SVG2Plotter Network virtualises a physical vinyl cutter on your local network. Instead of running a desktop application on the machine connected to the cutter, you run a lightweight server — and control everything from any browser on the same network.

Same SVG processing engine as [SVG2Plotter Desktop](https://github.com/centroinovacaocarlosfiolhais/svg2plotter). Full HPGL support. No client installation required.

```
┌─────────────────────┐         LAN          ┌──────────────────────┐
│   Host machine      │◄────────────────────►│  Any browser         │
│   (or Pi Zero 2W)   │   http://<ip>:7733   │  Chrome, Firefox...  │
│                     │   WebSocket          │                      │
│   server.py         │                      │  Upload SVG          │
│   Flask + SocketIO  │                      │  Layout preview      │
│   pyserial          │                      │  Send to cut         │
└────────┬────────────┘                      └──────────────────────┘
         │ USB-Serial
    ┌────▼──────┐
    │ SK1350    │
    └───────────┘
```

---

## Features

- **Browser-based UI** — works on any device with a browser, no install on client
- **Real-time log** — WebSocket pushes cut progress and status live to the browser
- **Full SVG support** — same parser as the desktop app: transforms, groups, Inkscape files
- **Multi-file layout** — load multiple SVGs, drag to reposition, auto-layout
- **Scale tool** — save a value, apply to any SVG independently
- **Normal / Mirror mode** — for opaque surfaces or glass/window application
- **Drag & drop upload** — drop SVGs directly onto the canvas
- **Cross-platform server** — runs on Linux, Windows, macOS, Raspberry Pi OS

---

## Requirements

| | |
|---|---|
| Python | 3.8 or newer |
| flask | `pip install flask` |
| flask-socketio | `pip install flask-socketio` |
| pyserial | `pip install pyserial` |
| Browser | Any modern browser — Chrome, Firefox, Safari, Edge |

---

## Quick Start

### Linux / Linux Mint (MVP / testing)

```bash
git clone https://github.com/centroinovacaocarlosfiolhais/svg2plotter.git
cd svg2plotter/network

bash setup-network.sh     # installs deps, serial permissions, Desktop shortcut
bash start.sh             # start the server
```

Open in browser:
```
http://localhost:7733
http://<host-ip>:7733     # from any device on the LAN
```

### Windows

```bash
python setup-network.py   # installs deps, creates start-network.bat, Desktop shortcut
start-network.bat         # start the server
```

> **Firewall:** On first run, allow port 7733 when Windows Defender asks.  
> Or run in PowerShell (Admin):
> ```powershell
> netsh advfirewall firewall add rule name="SVG2Plotter" dir=in action=allow protocol=TCP localport=7733
> ```

### Manual (any OS)

```bash
pip install flask flask-socketio pyserial
python server.py
```

---

## File Structure

```
network/
├── server.py              # Flask + SocketIO backend
├── static/
│   └── index.html         # Complete web UI (single file)
├── setup-network.sh       # Setup script — Linux / Raspberry Pi OS
├── setup-network.py       # Setup script — Windows
└── README.md
```

---

## Usage

### 1 — Connect the cutter
Plug the vinyl cutter via USB. The serial port appears automatically in the PORT dropdown (click **↻** to refresh).

### 2 — Load SVGs
Click **+ ADD** or drag and drop SVG files onto the canvas.

### 3 — Arrange the layout
- Drag SVGs horizontally on the canvas to reposition
- Use **▲ ▼** to change the print order
- **⟳ AUTO** recalculates positions automatically
- Scroll to zoom, **FIT** to reset view

### 4 — Scale (optional)
① Type a scale factor (e.g. `2.0`) → ② **SAVE** → ③ select an SVG → ④ **APPLY**

### 5 — Choose cut mode

| Mode | Use case |
|---|---|
| **◼ NORMAL** | Vinyl applied to opaque surfaces — reads correctly from the front |
| **⟺ MIRROR** | Vinyl applied to glass/windows from behind — reads correctly from outside |

### 6 — Send
Click **▶ TEST** to verify the connection, then **✂ SEND** to cut.  
The log panel streams live progress via WebSocket.

---

## Raspberry Pi Migration

The MVP runs on a laptop connected to the cutter. Once validated, the same setup moves to a **Raspberry Pi Zero 2W** for a standalone network node — no laptop required.

```bash
# On the Pi
scp -r network/ pi@raspberrypi.local:~/svg2plotter-network/
ssh pi@raspberrypi.local
cd ~/svg2plotter-network
bash setup-network.sh
bash start.sh
```

Then access from any browser on the LAN:
```
http://raspberrypi.local:7733
```

**Recommended hardware:**
- Raspberry Pi Zero 2W (~€15) — has built-in WiFi
- microSD 8GB Class 10
- USB micro OTG adapter → USB-A for the cutter cable
- Optional: case + power supply

---

## HPGL Axis Mapping (SK1350)

```
HPGL X → cutter head movement  (max 54000 units = 1350 mm)
HPGL Y → vinyl/paper feed      (unlimited)

Normal mode:  SVG X (flipped)  → HPGL Y  |  SVG Y (inverted) → HPGL X
Mirror mode:  SVG X (as-is)    → HPGL Y  |  SVG Y (inverted) → HPGL X

1 mm = 40 HPGL units
Command terminator: \x03 (ETX — required by SK1350)
```

Compatible with any HPGL cutter — not limited to the SK1350.

---

## API Reference

The server exposes a REST + WebSocket API, making it easy to integrate or extend.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/ports` | List available serial ports |
| GET | `/api/state` | Full session state (SVGs, settings, job status) |
| POST | `/api/settings` | Update port, baud, width, gap, mirror |
| POST | `/api/upload` | Upload one or more SVG files |
| DELETE | `/api/remove/<id>` | Remove an SVG by ID |
| POST | `/api/reorder` | Reorder SVGs by ID list |
| POST | `/api/scale` | Apply scale to a specific SVG |
| POST | `/api/move` | Update X position for a specific SVG |
| POST | `/api/test` | Test serial connection |
| POST | `/api/send` | Start a cut job |
| POST | `/api/cancel` | Cancel the running job |

**WebSocket events (server → client):**

| Event | Payload | Description |
|---|---|---|
| `log` | `{msg}` | Log line from the cut job |
| `progress` | `{pct}` | Cut progress 0–100 |
| `job_done` | `{result, error?}` | Job completed or errored |

---

## Development

Built as an extension of [SVG2Plotter Desktop](https://github.com/centroinovacaocarlosfiolhais/svg2plotter) using [Claude.ai](https://claude.ai).

> *"Vibe Coding with Claude.ai"* — the entire network edition (server, web UI, installers) was developed iteratively through conversation with Claude, starting from the validated desktop codebase.

**Design language:** CNC terminal aesthetic — amber on near-black, monospace-heavy, scanline overlay, oscilloscope/industrial control feel. Built with vanilla JS and HTML5 Canvas, no frontend framework.

---

## Related

- **[SVG2Plotter Desktop](https://github.com/centroinovacaocarlosfiolhais/svg2plotter)** — the original tkinter desktop application for Windows

---

## License

**© 2026 David Marques · Centro de Inovação Carlos Fiolhais · CDI Portugal**

[![CC BY-NC-ND 4.0](https://licensebuttons.net/l/by-nc-nd/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc-nd/4.0/)

Licensed under [Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International](https://creativecommons.org/licenses/by-nc-nd/4.0/).  
Share with attribution. No commercial use. No derivatives without written authorisation.
