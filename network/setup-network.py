"""
SVG2Plotter Network  v1.0 — Windows Setup
──────────────────────────────────────────
Installs dependencies, creates start.bat and Desktop shortcut.
Run once: python setup-network.py

Centro de Inovação Carlos Fiolhais · CDI Portugal
© 2026 David Marques — Vibe Coding with Claude.ai
"""

import sys, os, subprocess, platform, textwrap

APP_NAME = "SVG2Plotter Network"
VERSION  = "1.0"
PORT     = 7733

def banner():
    print("\n" + "═"*58)
    print(f"  {APP_NAME}  v{VERSION}  —  Windows Setup")
    print("  Centro de Inovação Carlos Fiolhais · CDI Portugal")
    print("═"*58 + "\n")

def step(n, total, msg): print(f"  [{n}/{total}] {msg}")
def ok(msg=""):  print(f"         ✓  {msg}" if msg else "         ✓")
def err(msg):    print(f"         ✗  ERROR: {msg}")
def warn(msg):   print(f"         ⚠  {msg}")

def check_python():
    step(1, 5, "Checking Python version...")
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 8):
        err(f"Python 3.8+ required (found {v.major}.{v.minor})")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")

def install_deps():
    step(2, 5, "Installing dependencies...")
    deps = ["flask", "flask-socketio", "pyserial"]
    for dep in deps:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep, "--quiet"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            ok(dep)
        else:
            err(f"pip failed for {dep}:\n{result.stderr}")
            sys.exit(1)

def create_launcher():
    step(3, 5, "Creating launcher...")
    install_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(install_dir, "server.py")

    if not os.path.exists(server_path):
        err(f"server.py not found at: {server_path}")
        sys.exit(1)

    bat_path = os.path.join(install_dir, "start-network.bat")
    bat = textwrap.dedent(f"""\
        @echo off
        title SVG2Plotter Network v{VERSION}
        cd /d "{install_dir}"
        echo.
        echo  SVG2Plotter Network v{VERSION}
        echo  Open in browser: http://localhost:{PORT}
        echo  Press Ctrl+C to stop
        echo.
        "{sys.executable}" "{server_path}"
        pause
    """)
    with open(bat_path, "w") as f:
        f.write(bat)
    ok(f"Launcher: {bat_path}")
    return bat_path, install_dir

def generate_icon(install_dir):
    """Generate svg2plotter-network.ico in pure Python."""
    import struct, math

    def make_ico(size):
        AMBER = (245, 166, 35, 255)
        DARK  = (14,  17,  32, 255)
        WHITE = (255, 255, 255, 255)
        NONE  = (0,   0,   0,   0)
        cx = cy = size / 2
        r  = size / 2 - 1

        def d(x, y, px, py): return math.sqrt((x-px)**2+(y-py)**2)

        pixels = [[NONE]*size for _ in range(size)]
        for y in range(size):
            for x in range(size):
                fx, fy = x+0.5, y+0.5
                dc = d(fx, fy, cx, cy)
                if dc <= r:                              pixels[y][x] = DARK
                if d(fx,fy,size*.27,size*.27)<size*.13:  pixels[y][x] = AMBER
                if d(fx,fy,size*.27,size*.73)<size*.13:  pixels[y][x] = AMBER
                if d(fx,fy,size*.27,size*.27)<size*.07:  pixels[y][x] = DARK
                if d(fx,fy,size*.27,size*.73)<size*.07:  pixels[y][x] = DARK
                if fx>=size*.30 and dc>size*.07:
                    if abs((fy-fx)*.707) < 1.8:          pixels[y][x] = WHITE
                    if abs((fy-(size-fx))*.707) < 1.8:   pixels[y][x] = WHITE
                if dc < size*.08:                        pixels[y][x] = AMBER

        raw = b''
        for row in reversed(pixels):
            for r2,g,b,a in row: raw += bytes([b,g,r2,a])

        hdr  = struct.pack('<IiiHHIIiiII', 40, size, size*2, 1, 32, 0, len(raw), 0,0,0,0)
        mask = b'\x00' * (((size+31)//32)*4 * size)
        img  = hdr + raw + mask
        return struct.pack('<HHH',0,1,1) + struct.pack('<BBBBHHII',
            min(size,255),min(size,255),0,0,1,32,len(img),22) + img

    ico_path = os.path.join(install_dir, "svg2plotter-network.ico")
    try:
        with open(ico_path, 'wb') as f: f.write(make_ico(32))
        return ico_path
    except Exception as e:
        warn(f"Icon skipped: {e}"); return None

def create_desktop_shortcut(bat_path, install_dir, ico_path=None):
    step(4, 5, "Creating Desktop shortcut...")
    desktop  = os.path.join(os.path.expanduser("~"), "Desktop")
    lnk_path = os.path.join(desktop, "SVG2Plotter Network.lnk")
    ico_str  = ico_path if ico_path else ""

    vbs = textwrap.dedent(f"""\
        Set ws = WScript.CreateObject("WScript.Shell")
        Set sc = ws.CreateShortcut("{lnk_path}")
        sc.TargetPath = "{bat_path}"
        sc.WorkingDirectory = "{install_dir}"
        sc.Description = "SVG2Plotter Network v{VERSION} — LAN Server"
        sc.WindowStyle = 1
        sc.IconLocation = "{ico_str}"
        sc.Save
    """)
    vbs_path = os.path.join(install_dir, "_create_net_shortcut.vbs")
    with open(vbs_path, "w") as f: f.write(vbs)
    result = subprocess.run(["cscript", "//nologo", vbs_path],
                            capture_output=True, text=True)
    try: os.remove(vbs_path)
    except: pass

    if result.returncode == 0 and os.path.exists(lnk_path):
        ok("Desktop shortcut: SVG2Plotter Network.lnk")
    else:
        warn("Could not create .lnk — use start-network.bat directly")

def check_firewall():
    step(5, 5, "Firewall note...")
    warn(f"Windows Firewall may block port {PORT} from other devices.")
    print(f"         → To allow LAN access, run in PowerShell (as Admin):")
    print(f"           netsh advfirewall firewall add rule name=\"SVG2Plotter\" "
          f"dir=in action=allow protocol=TCP localport={PORT}")
    print(f"         → Or allow it when Windows asks on first run.")

def test_imports():
    print("\n  Verifying installation...")
    for mod, pkg in [("flask","flask"),("flask_socketio","flask-socketio"),("serial","pyserial")]:
        try:
            __import__(mod); ok(pkg)
        except ImportError:
            err(f"import {mod} failed — try: pip install {pkg}"); sys.exit(1)

def main():
    banner()
    check_python()
    install_deps()
    bat_path, install_dir = create_launcher()
    ico_path = generate_icon(install_dir)
    ok(f"Icon: {ico_path}" if ico_path else "Icon: skipped")
    create_desktop_shortcut(bat_path, install_dir, ico_path)
    check_firewall()
    test_imports()

    import socket
    try:    local_ip = socket.gethostbyname(socket.gethostname())
    except: local_ip = "your-ip"

    print("\n" + "═"*58)
    print(f"  SETUP COMPLETE")
    print(f"")
    print(f"  Start the server:")
    print(f"    Double-click 'SVG2Plotter Network' on Desktop")
    print(f"    — or run: start-network.bat")
    print(f"")
    print(f"  Open in browser:")
    print(f"    http://localhost:{PORT}")
    print(f"    http://{local_ip}:{PORT}  (from other devices)")
    print("═"*58 + "\n")

if __name__ == "__main__":
    main()
