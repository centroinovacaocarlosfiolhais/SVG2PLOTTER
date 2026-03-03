"""
SVG2Plotter — Installer
Centro de Inovação Carlos Fiolhais / CDI Portugal
Corre este script uma vez para instalar dependências e criar atalho no Desktop.
"""
import sys, os, subprocess, platform, textwrap

APP_NAME = "SVG2Plotter"
VERSION  = "2.0"

def banner():
    print("\n" + "═"*60)
    print(f"  {APP_NAME} v{VERSION}  —  Installer")
    print("  Centro de Inovação Carlos Fiolhais / CDI Portugal")
    print("═"*60 + "\n")

def step(n, total, msg):
    print(f"  [{n}/{total}] {msg}")

def ok(msg=""):
    print(f"         ✓  {msg}" if msg else "         ✓")

def err(msg):
    print(f"         ✗  ERROR: {msg}")


def generate_icon(install_dir):
    """Generate svg2plotter.ico in pure Python — scissors design, no external deps."""
    import struct, math

    def make_ico(size):
        ACC   = (33, 150, 243, 255)
        DARK  = (14,  17,  32, 255)
        WHITE = (255,255,255, 255)
        NONE  = (0,   0,   0,   0)
        cx = cy = size / 2
        r  = size / 2 - 1

        def d(x, y, px, py): return math.sqrt((x-px)**2+(y-py)**2)

        pixels = [[NONE]*size for _ in range(size)]
        for y in range(size):
            for x in range(size):
                fx, fy = x+0.5, y+0.5
                dc = d(fx, fy, cx, cy)
                if dc <= r:                          pixels[y][x] = DARK
                if d(fx,fy,size*.27,size*.27)<size*.13: pixels[y][x] = ACC
                if d(fx,fy,size*.27,size*.73)<size*.13: pixels[y][x] = ACC
                if d(fx,fy,size*.27,size*.27)<size*.07: pixels[y][x] = DARK
                if d(fx,fy,size*.27,size*.73)<size*.07: pixels[y][x] = DARK
                if fx>=size*.30 and dc>size*.07:
                    if abs((fy-fx)*.707) < 1.8:          pixels[y][x] = WHITE
                    if abs((fy-(size-fx))*.707) < 1.8:   pixels[y][x] = WHITE
                if dc < size*.08:                    pixels[y][x] = ACC

        raw = b''
        for row in reversed(pixels):
            for r2,g,b,a in row: raw += bytes([b,g,r2,a])

        hdr = struct.pack('<IiiHHIIiiII',
            40, size, size*2, 1, 32, 0, len(raw), 0, 0, 0, 0)
        mask = b'\x00' * (((size+31)//32)*4 * size)
        img  = hdr + raw + mask
        ico_hdr = struct.pack('<HHH', 0, 1, 1)
        entry   = struct.pack('<BBBBHHII',
            min(size,255), min(size,255), 0, 0, 1, 32, len(img), 6+16)
        return ico_hdr + entry + img

    ico_path = os.path.join(install_dir, "svg2plotter.ico")
    try:
        with open(ico_path, 'wb') as f: f.write(make_ico(32))
        return ico_path
    except Exception as e:
        print(f"         ⚠  Icon skipped: {e}")
        return None

def check_python():
    step(1, 5, "Checking Python version ...")
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 8):
        err(f"Python 3.8+ required (found {v.major}.{v.minor})")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")

def check_tkinter():
    step(2, 5, "Checking tkinter ...")
    try:
        import tkinter
        ok("tkinter available")
    except ImportError:
        err("tkinter not found.")
        if platform.system() == "Linux":
            print("         → run: sudo apt install python3-tk")
        sys.exit(1)

def install_deps():
    step(3, 5, "Installing dependencies (pyserial) ...")
    deps = ["pyserial"]
    for dep in deps:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", dep, "--quiet"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                ok(dep)
            else:
                err(f"pip failed for {dep}:\n{result.stderr}")
                sys.exit(1)
        except Exception as e:
            err(str(e)); sys.exit(1)

def create_launcher():
    step(4, 5, "Creating launcher ...")
    install_dir = os.path.dirname(os.path.abspath(__file__))
    app_path    = os.path.join(install_dir, "svg2plotter.py")

    if not os.path.exists(app_path):
        err(f"svg2plotter.py not found at: {app_path}")
        sys.exit(1)

    system = platform.system()

    if system == "Windows":
        # .bat launcher
        bat_path = os.path.join(install_dir, "SVG2Plotter.bat")
        bat_content = textwrap.dedent(f"""\
            @echo off
            cd /d "{install_dir}"
            "{sys.executable}" "{app_path}"
        """)
        with open(bat_path, "w") as f:
            f.write(bat_content)
        ico_path = generate_icon(install_dir)
        ok(f"Launcher: {bat_path}")
        return bat_path, install_dir, ico_path

    elif system == "Darwin":  # macOS
        sh_path = os.path.join(install_dir, "SVG2Plotter.command")
        with open(sh_path, "w") as f:
            f.write(f'#!/bin/bash\ncd "{install_dir}"\n"{sys.executable}" "{app_path}"\n')
        os.chmod(sh_path, 0o755)
        ico_path = generate_icon(install_dir)
        ico_path = generate_icon(install_dir)
        ok(f"Launcher: {sh_path}")
        return sh_path, install_dir, ico_path, ico_path

    else:  # Linux
        sh_path = os.path.join(install_dir, "svg2plotter.sh")
        with open(sh_path, "w") as f:
            f.write(f'#!/bin/bash\ncd "{install_dir}"\n"{sys.executable}" "{app_path}"\n')
        os.chmod(sh_path, 0o755)
        ico_path = generate_icon(install_dir)
        ok(f"Launcher: {sh_path}")
        return sh_path, install_dir, ico_path

def create_desktop_shortcut(launcher_path, install_dir, ico_path=None):
    step(5, 5, "Creating Desktop shortcut ...")
    system   = platform.system()
    app_path = os.path.join(install_dir, "svg2plotter.py")

    if system == "Windows":
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        # Use VBScript to create .lnk (no extra deps needed)
        lnk_path = os.path.join(desktop, "SVG2Plotter.lnk")
        ico_str = ico_path if ico_path else ""
        vbs = textwrap.dedent(f"""\
            Set ws = WScript.CreateObject("WScript.Shell")
            Set sc = ws.CreateShortcut("{lnk_path}")
            sc.TargetPath = "{launcher_path}"
            sc.WorkingDirectory = "{install_dir}"
            sc.Description = "SVG2Plotter v{VERSION}"
            sc.WindowStyle = 1
            sc.IconLocation = "{ico_str}"
            sc.Save
        """)
        vbs_path = os.path.join(install_dir, "_create_shortcut.vbs")
        with open(vbs_path, "w") as f:
            f.write(vbs)
        result = subprocess.run(["cscript", "//nologo", vbs_path],
                                capture_output=True, text=True)
        try: os.remove(vbs_path)
        except: pass

        if result.returncode == 0 and os.path.exists(lnk_path):
            ok(f"Desktop shortcut: SVG2Plotter.lnk")
        else:
            print(f"         ⚠  Could not create .lnk — shortcut bat: {launcher_path}")
            print(f"            Right-click SVG2Plotter.bat → Send to → Desktop")

    elif system == "Darwin":
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        link = os.path.join(desktop, "SVG2Plotter.command")
        try:
            import shutil; shutil.copy(launcher_path, link)
            os.chmod(link, 0o755)
            ok(f"Desktop shortcut created")
        except Exception as e:
            print(f"         ⚠  {e}")

    else:  # Linux / XDG
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop, exist_ok=True)
        desktop_entry = textwrap.dedent(f"""\
            [Desktop Entry]
            Version=1.0
            Type=Application
            Name=SVG2Plotter
            Comment=HPGL Vinyl Cutter Controller
            Exec=bash "{launcher_path}"
            Terminal=false
            Categories=Graphics;
        """)
        entry_path = os.path.join(desktop, "SVG2Plotter.desktop")
        with open(entry_path, "w") as f:
            f.write(desktop_entry)
        os.chmod(entry_path, 0o755)
        ok(f"Desktop shortcut: SVG2Plotter.desktop")

def test_import():
    print("\n  Verifying installation ...")
    try:
        import serial; ok(f"pyserial {serial.VERSION}")
    except ImportError:
        err("pyserial import failed — try: pip install pyserial")
        sys.exit(1)
    try:
        import xml.etree.ElementTree; ok("xml.etree (stdlib)")
    except: pass

def main():
    banner()
    check_python()
    check_tkinter()
    install_deps()
    launcher, install_dir, ico_path = create_launcher()
    create_desktop_shortcut(launcher, install_dir, ico_path)
    test_import()

    print("\n" + "═"*60)
    print(f"  INSTALLATION COMPLETE")
    print(f"  Use the Desktop shortcut to open SVG2Plotter")
    print(f"  Or run: python svg2plotter.py")
    print("═"*60 + "\n")

if __name__ == "__main__":
    main()
