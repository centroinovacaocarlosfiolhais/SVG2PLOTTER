"""
SVG2Plotter Network  v1.0
─────────────────────────────────────────────────────────────────────
Flask + SocketIO server — exposes the vinyl cutter on the LAN
Access from any browser: http://<host-ip>:7733

Centro de Inovação Carlos Fiolhais · CDI Portugal
Developed by David Marques — Vibe Coding with Claude.ai
© 2026 CC BY-NC-ND 4.0
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import serial, serial.tools.list_ports
import xml.etree.ElementTree as ET
import re, math, os, sys, time, threading, json, uuid, tempfile
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
PORT        = 7733
HOST        = "0.0.0.0"
UPLOAD_DIR  = Path(tempfile.gettempdir()) / "svg2plotter_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

HPGL_UNITS_PER_MM = 40

app    = Flask(__name__, static_folder="static", template_folder="static")
app.config["SECRET_KEY"] = "svg2plotter-cicf-2026"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Global job state ──────────────────────────────────────────────────────────
job_state = {
    "running":  False,
    "cancel":   False,
    "progress": 0,
    "status":   "READY",
}

# ═══════════════════════════════════════════════════════════════════════════════
#  SVG PROCESSING  (identical core to desktop app)
# ═══════════════════════════════════════════════════════════════════════════════

def _mat_mul(a, b):
    return [
        a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
        a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
        a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5],
    ]

def _parse_transform(t):
    if not t: return [1,0,0,1,0,0]
    m = [1,0,0,1,0,0]
    for fn, args_str in re.findall(r'(\w+)\s*\(([^)]*)\)', t):
        try: a = [float(v) for v in re.split(r'[\s,]+', args_str.strip()) if v]
        except: continue
        if   fn=='matrix'    and len(a)>=6: t2=a[:6]
        elif fn=='translate': tx,ty=a[0],(a[1] if len(a)>1 else 0); t2=[1,0,0,1,tx,ty]
        elif fn=='scale':     sx,sy=a[0],(a[1] if len(a)>1 else a[0]); t2=[sx,0,0,sy,0,0]
        elif fn=='rotate':
            ang=math.radians(a[0]); ca,sa=math.cos(ang),math.sin(ang)
            if len(a)==3: cx,cy=a[1],a[2]; t2=[ca,sa,-sa,ca,cx*(1-ca)+cy*sa,cy*(1-ca)-cx*sa]
            else: t2=[ca,sa,-sa,ca,0,0]
        elif fn=='skewX': t2=[1,0,math.tan(math.radians(a[0])),1,0,0]
        elif fn=='skewY': t2=[1,math.tan(math.radians(a[0])),0,1,0,0]
        else: continue
        m = _mat_mul(m, t2)
    return m

def _tf(m, x, y):
    return (m[0]*x+m[2]*y+m[4], m[1]*x+m[3]*y+m[5])

def parse_dim(val, default=100.0):
    if not val: return default
    val = str(val).strip()
    for s, f in [('mm',1),('cm',10),('in',25.4),('px',25.4/96),('pt',25.4/72)]:
        if val.endswith(s):
            try: return float(val[:-len(s)])*f
            except: return default
    try: return float(val)*(25.4/96)
    except: return default

def get_svg_size(path):
    root = ET.parse(path).getroot()
    vb   = root.get('viewBox')
    if vb:
        v = [float(x) for x in re.split(r'[\s,]+', vb.strip())]
        vw, vh = v[2], v[3]
    else:
        vw, vh = None, None
    wa, ha = root.get('width'), root.get('height')
    if wa and ha:
        wm, hm = parse_dim(wa), parse_dim(ha)
        if vw is None: vw, vh = wm, hm
    elif vw is not None:
        px = 25.4/96
        if wa:   wm=parse_dim(wa); hm=vh*(wm/vw)
        elif ha: hm=parse_dim(ha); wm=vw*(hm/vh)
        else:    wm=vw*px;         hm=vh*px
    else:
        wm,hm,vw,vh = 100.0,100.0,100.0,100.0
    return wm, hm, vw, vh

def extract_paths(path):
    root      = ET.parse(path).getroot()
    polylines = []

    def sn(tag): return tag.split('}')[-1] if '}' in tag else tag
    def add(pts):
        if len(pts) >= 2: polylines.append(list(pts))

    def path_pts(d, m):
        toks = re.findall(
            r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?', d)
        i=0; cx=cy=sx=sy=0.0; cur=[]; lc=None

        def flush():
            nonlocal cur; add(cur); cur=[]
        def move(x,y):
            nonlocal cx,cy,sx,sy,cur
            if cur: flush()
            cx,cy=x,y; sx,sy=x,y; cur=[_tf(m,cx,cy)]
        def lineto(x,y):
            nonlocal cx,cy; cx,cy=x,y; cur.append(_tf(m,cx,cy))

        while i < len(toks):
            t = toks[i]
            if re.match(r'[MmLlHhVvCcSsQqTtAaZz]', t): cmd=t; lc=t; i+=1
            else: cmd=lc
            try:
                if   cmd=='M': move(float(toks[i]),float(toks[i+1])); i+=2; lc='L'
                elif cmd=='m': move(cx+float(toks[i]),cy+float(toks[i+1])); i+=2; lc='l'
                elif cmd=='L': lineto(float(toks[i]),float(toks[i+1])); i+=2
                elif cmd=='l': lineto(cx+float(toks[i]),cy+float(toks[i+1])); i+=2
                elif cmd=='H': lineto(float(toks[i]),cy); i+=1
                elif cmd=='h': lineto(cx+float(toks[i]),cy); i+=1
                elif cmd=='V': lineto(cx,float(toks[i])); i+=1
                elif cmd=='v': lineto(cx,cy+float(toks[i])); i+=1
                elif cmd in('Z','z'): lineto(sx,sy); flush()
                elif cmd in('C','c'):
                    p=[float(toks[i+j]) for j in range(6)]; i+=6
                    if cmd=='c': p=[cx+p[0],cy+p[1],cx+p[2],cy+p[3],cx+p[4],cy+p[5]]
                    for tv in [.2,.4,.6,.8,1.0]:
                        lineto((1-tv)**3*cx+3*(1-tv)**2*tv*p[0]+3*(1-tv)*tv**2*p[2]+tv**3*p[4],
                               (1-tv)**3*cy+3*(1-tv)**2*tv*p[1]+3*(1-tv)*tv**2*p[3]+tv**3*p[5])
                    cx,cy=p[4],p[5]
                elif cmd in('Q','q'):
                    p=[float(toks[i+j]) for j in range(4)]; i+=4
                    if cmd=='q': p=[cx+p[0],cy+p[1],cx+p[2],cy+p[3]]
                    for tv in [.33,.66,1.0]:
                        lineto((1-tv)**2*cx+2*(1-tv)*tv*p[0]+tv**2*p[2],
                               (1-tv)**2*cy+2*(1-tv)*tv*p[1]+tv**2*p[3])
                    cx,cy=p[2],p[3]
                elif cmd in('S','s'):
                    p=[float(toks[i+j]) for j in range(4)]; i+=4
                    if cmd=='s': p=[cx+p[0],cy+p[1],cx+p[2],cy+p[3]]
                    lineto(p[2],p[3]); cx,cy=p[2],p[3]
                elif cmd in('T','t'):
                    ex,ey=float(toks[i]),float(toks[i+1]); i+=2
                    if cmd=='t': ex,ey=cx+ex,cy+ey
                    lineto(ex,ey); cx,cy=ex,ey
                elif cmd in('A','a'):
                    p=[float(toks[i+j]) for j in range(7)]; i+=7
                    ex,ey=(cx+p[5],cy+p[6]) if cmd=='a' else (p[5],p[6])
                    for s in range(1,9): lineto(cx+(ex-cx)*s/8, cy+(ey-cy)*s/8)
                    cx,cy=ex,ey
                else: i+=1
            except (IndexError, ValueError): i+=1
        if cur: flush()

    def traverse(elem, pm=None):
        if pm is None: pm=[1,0,0,1,0,0]
        lm = _parse_transform(elem.get('transform',''))
        m  = _mat_mul(pm, lm)
        tag = sn(elem.tag)

        if tag=='rect':
            x,y=float(elem.get('x',0)),float(elem.get('y',0))
            w,h=float(elem.get('width',0)),float(elem.get('height',0))
            if w>0 and h>0:
                add([_tf(m,x,y),_tf(m,x+w,y),_tf(m,x+w,y+h),_tf(m,x,y+h),_tf(m,x,y)])
        elif tag=='circle':
            cx,cy,r=float(elem.get('cx',0)),float(elem.get('cy',0)),float(elem.get('r',0))
            if r>0:
                n=max(36,int(r*2))
                add([_tf(m,cx+r*math.cos(2*math.pi*s/n),cy+r*math.sin(2*math.pi*s/n))
                     for s in range(n+1)])
        elif tag=='ellipse':
            cx,cy=float(elem.get('cx',0)),float(elem.get('cy',0))
            rx,ry=float(elem.get('rx',0)),float(elem.get('ry',0))
            if rx>0 and ry>0:
                add([_tf(m,cx+rx*math.cos(2*math.pi*s/48),cy+ry*math.sin(2*math.pi*s/48))
                     for s in range(49)])
        elif tag=='line':
            add([_tf(m,float(elem.get('x1',0)),float(elem.get('y1',0))),
                 _tf(m,float(elem.get('x2',0)),float(elem.get('y2',0)))])
        elif tag in('polyline','polygon'):
            ns=[float(v) for v in re.findall(
                r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?', elem.get('points',''))]
            pts=[_tf(m,ns[i],ns[i+1]) for i in range(0,len(ns)-1,2)]
            if tag=='polygon' and pts: pts.append(pts[0])
            add(pts)
        elif tag=='path':
            d=elem.get('d','')
            if d: path_pts(d, m)
        if tag != 'defs':
            for child in elem: traverse(child, m)

    traverse(root)
    return polylines

def svg_to_hpgl(path, offset_x_mm=0, offset_y_mm=0, scale=1.0, mirror=False):
    wm,hm,vw,vh = get_svg_size(path)
    sx = (wm/vw)*HPGL_UNITS_PER_MM*scale
    sy = (hm/vh)*HPGL_UNITS_PER_MM*scale
    ox = int(offset_x_mm*HPGL_UNITS_PER_MM)
    oy = int(offset_y_mm*HPGL_UNITS_PER_MM)
    if mirror:
        def hx(x): return int(float(x)*sx)+ox
    else:
        def hx(x): return int((vw-float(x))*sx)+ox
    def hy(y): return int((vh-float(y))*sy)+oy

    cmds=[]; polys=extract_paths(path)
    for poly in polys:
        if len(poly)<2: continue
        cmds.append(f'PU{hy(poly[0][1])},{hx(poly[0][0])};')
        cmds.append(f'PD{",".join(f"{hy(y)},{hx(x)}" for x,y in poly[1:])};')
        cmds.append('PU;')
    return cmds

# ═══════════════════════════════════════════════════════════════════════════════
#  IN-MEMORY SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════════

session = {
    "svgs":   [],   # list of dicts: {id, name, path, w_mm, h_mm, vb_w, vb_h, x_mm, scale}
    "port":   "",
    "baud":   9600,
    "width":  1350,
    "gap":    5,
    "mirror": False,
}

def _layout():
    """Recalculate x_mm positions for all SVGs."""
    g = session["gap"]; x = g
    for item in session["svgs"]:
        item["x_mm"] = x
        x += item["w_mm"] * item["scale"] + g

def _svg_dict(item):
    """Return serialisable dict for frontend."""
    polys = extract_paths(item["path"])
    return {
        "id":     item["id"],
        "name":   item["name"],
        "w_mm":   item["w_mm"],
        "h_mm":   item["h_mm"],
        "vb_w":   item["vb_w"],
        "vb_h":   item["vb_h"],
        "x_mm":   item["x_mm"],
        "scale":  item["scale"],
        "polys":  polys,
    }

# ═══════════════════════════════════════════════════════════════════════════════
#  REST API
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/ports")
def api_ports():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return jsonify(ports=ports)

@app.route("/api/state")
def api_state():
    return jsonify(
        svgs    = [_svg_dict(s) for s in session["svgs"]],
        port    = session["port"],
        baud    = session["baud"],
        width   = session["width"],
        gap     = session["gap"],
        mirror  = session["mirror"],
        job     = job_state,
    )

@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.json
    for k in ("port","baud","width","gap","mirror"):
        if k in data:
            session[k] = data[k]
    if "gap" in data or "width" in data:
        _layout()
    return jsonify(ok=True, svgs=[_svg_dict(s) for s in session["svgs"]])

@app.route("/api/upload", methods=["POST"])
def api_upload():
    results = []
    for f in request.files.getlist("files"):
        if not f.filename.lower().endswith(".svg"):
            continue
        fid  = str(uuid.uuid4())[:8]
        dest = UPLOAD_DIR / f"{fid}_{f.filename}"
        f.save(str(dest))
        try:
            wm,hm,vb_w,vb_h = get_svg_size(str(dest))
            item = {
                "id":   fid,
                "name": f.filename,
                "path": str(dest),
                "w_mm": wm, "h_mm": hm,
                "vb_w": vb_w, "vb_h": vb_h,
                "x_mm": 0, "scale": 1.0,
            }
            session["svgs"].append(item)
            results.append({"id": fid, "name": f.filename,
                            "w_mm": round(wm,1), "h_mm": round(hm,1)})
        except Exception as e:
            dest.unlink(missing_ok=True)
            results.append({"error": str(e), "name": f.filename})
    _layout()
    return jsonify(ok=True, uploaded=results,
                   svgs=[_svg_dict(s) for s in session["svgs"]])

@app.route("/api/remove/<fid>", methods=["DELETE"])
def api_remove(fid):
    session["svgs"] = [s for s in session["svgs"] if s["id"] != fid]
    _layout()
    return jsonify(ok=True, svgs=[_svg_dict(s) for s in session["svgs"]])

@app.route("/api/reorder", methods=["POST"])
def api_reorder():
    order = request.json.get("order", [])
    by_id = {s["id"]: s for s in session["svgs"]}
    session["svgs"] = [by_id[i] for i in order if i in by_id]
    _layout()
    return jsonify(ok=True, svgs=[_svg_dict(s) for s in session["svgs"]])

@app.route("/api/scale", methods=["POST"])
def api_scale():
    fid   = request.json.get("id")
    scale = float(request.json.get("scale", 1.0))
    for s in session["svgs"]:
        if s["id"] == fid:
            s["scale"] = max(0.01, scale)
            break
    _layout()
    return jsonify(ok=True, svgs=[_svg_dict(s) for s in session["svgs"]])

@app.route("/api/move", methods=["POST"])
def api_move():
    """Update x_mm for a single SVG (manual drag from canvas)."""
    fid  = request.json.get("id")
    x_mm = float(request.json.get("x_mm", 0))
    for s in session["svgs"]:
        if s["id"] == fid:
            s["x_mm"] = max(0, x_mm)
            break
    return jsonify(ok=True)

@app.route("/api/test", methods=["POST"])
def api_test():
    port = session["port"]
    baud = int(session["baud"])
    if not port:
        return jsonify(ok=False, error="No port selected")
    try:
        s = serial.Serial(port, baud, timeout=2)
        time.sleep(0.3)
        s.write(b'IN;\x03')
        time.sleep(0.3)
        s.close()
        return jsonify(ok=True, msg=f"Connected: {port} @ {baud}")
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    job_state["cancel"] = True
    return jsonify(ok=True)

# ── Cut job ───────────────────────────────────────────────────────────────────
def _emit_log(msg):
    socketio.emit("log", {"msg": msg})

def _run_job():
    job_state["running"]  = True
    job_state["cancel"]   = False
    job_state["progress"] = 0
    job_state["status"]   = "CUTTING"

    port   = session["port"]
    baud   = int(session["baud"])
    mirror = session["mirror"]

    try:
        _emit_log(f"{'─'*48}")
        _emit_log(f"JOB START  {len(session['svgs'])} file(s)  {time.strftime('%H:%M:%S')}")
        _emit_log(f"MODE  {'MIRROR (glass)' if mirror else 'NORMAL'}")

        cmds = ["IN;","SP1;"]
        for item in session["svgs"]:
            n = len(extract_paths(item["path"]))
            _emit_log(f"  {item['name']}  {n} paths  @{item['x_mm']:.1f}mm  ×{item['scale']:.2f}")
            cmds += svg_to_hpgl(item["path"],
                                offset_x_mm=item["x_mm"],
                                offset_y_mm=0,
                                scale=item["scale"],
                                mirror=mirror)
        cmds.append("SP0;")
        total = len(cmds)
        _emit_log(f"COMMANDS  {total}  →  opening {port} ...")

        ser = serial.Serial(port, baud, timeout=2,
                            bytesize=serial.EIGHTBITS,
                            parity=serial.PARITY_NONE,
                            stopbits=serial.STOPBITS_ONE)
        time.sleep(0.5)
        _emit_log("CONNECTED  cutting ...")

        for i, cmd in enumerate(cmds):
            if job_state["cancel"]:
                break
            ser.write((cmd+'\x03').encode('ascii'))
            time.sleep(0.02)
            pct = int((i+1)/total*100)
            job_state["progress"] = pct
            if i % 30 == 0:
                job_state["status"] = f"CUTTING {pct}%"
                socketio.emit("progress", {"pct": pct})

        ser.close()
        result = "CANCELLED" if job_state["cancel"] else "DONE"
        job_state["status"]   = result
        job_state["progress"] = 100 if not job_state["cancel"] else pct
        _emit_log(f"{'─'*48}")
        _emit_log(f"JOB {result}  {time.strftime('%H:%M:%S')}")
        socketio.emit("job_done", {"result": result})

    except Exception as e:
        _emit_log(f"ERROR  {e}")
        job_state["status"] = "ERROR"
        socketio.emit("job_done", {"result": "ERROR", "error": str(e)})
    finally:
        job_state["running"] = False

@app.route("/api/send", methods=["POST"])
def api_send():
    if job_state["running"]:
        return jsonify(ok=False, error="Job already running")
    if not session["svgs"]:
        return jsonify(ok=False, error="No SVG files loaded")
    if not session["port"]:
        return jsonify(ok=False, error="No port selected")
    threading.Thread(target=_run_job, daemon=True).start()
    return jsonify(ok=True)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import socket
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "127.0.0.1"

    print(f"""
╔══════════════════════════════════════════════════════╗
║  SVG2Plotter Network  v1.0                           ║
║  Centro de Inovação Carlos Fiolhais · CDI Portugal   ║
╠══════════════════════════════════════════════════════╣
║  Local:    http://localhost:{PORT}                   ║
║  Network:  http://{local_ip}:{PORT}                  ║
║                                                      ║
║  Open the URL in any browser on this network         ║
║  Press Ctrl+C to stop                                ║
╚══════════════════════════════════════════════════════╝
""")
    socketio.run(app, host=HOST, port=PORT, debug=False)
