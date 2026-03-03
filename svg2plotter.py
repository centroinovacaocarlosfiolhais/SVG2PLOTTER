"""
SVG2Plotter  v2.0
Centro de Inovação Carlos Fiolhais — CICF / CDI Portugal
HPGL Vinyl Cutter Controller — Seikitech SK1350
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import serial
import serial.tools.list_ports
import xml.etree.ElementTree as ET
import re, math, time, threading, os, sys

# ─── Constants ────────────────────────────────────────────────────────────────
VERSION           = "2.0"
APP_NAME          = "SVG2Plotter"
ORG_NAME          = "Centro de Inovação Carlos Fiolhais"
HPGL_UNITS_PER_MM = 40

# ─── Design System ────────────────────────────────────────────────────────────
# Industrial technical dark — reference: CNC control / oscilloscope software
DS = {
    # Backgrounds
    "bg_base":    "#080a0f",   # deepest background
    "bg_surface": "#0e1117",   # panels
    "bg_raised":  "#141820",   # elevated cards
    "bg_input":   "#1a1f2a",   # input fields
    "bg_hover":   "#1e2535",   # hover state
    "bg_sel":     "#162035",   # selected row

    # Borders
    "border":     "#1e2535",
    "border_hi":  "#2d3a50",
    "border_acc": "#0e7ba8",

    # Accent (cyan-blue, technical)
    "acc":        "#2196f3",
    "acc_dim":    "#1565c0",
    "acc_glow":   "#42a5f5",

    # Semantic
    "success":    "#00c48c",
    "warn":       "#f5a623",
    "error":      "#e53935",
    "info":       "#7986cb",

    # Canvas
    "canvas_bg":  "#060810",
    "grid":       "#0d1220",
    "area_fill":  "#0a1018",
    "area_bord":  "#1a3a5a",
    "path_norm":  "#2196f3",
    "path_sel":   "#ffc107",
    "box_norm":   "#0d1525",
    "box_sel":    "#162040",

    # Text
    "text":       "#d0d8e8",
    "text_dim":   "#7a8499",
    "text_muted": "#3d4560",

    # Fonts
    "font_ui":    ("Segoe UI", 14),
    "font_sm":    ("Segoe UI", 12),
    "font_mono":  ("Consolas", 12),
    "font_mono9": ("Consolas", 14),
    "font_h1":    ("Segoe UI", 18, "bold"),
    "font_h2":    ("Segoe UI", 14, "bold"),
    "font_title": ("Segoe UI", 20, "bold"),
}

# ═════════════════════════════════════════════════════════════════════════════
#  SVG TRANSFORM HELPERS
# ═════════════════════════════════════════════════════════════════════════════

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
        m=_mat_mul(m,t2)
    return m

def _tf(m, x, y):
    return (m[0]*x+m[2]*y+m[4], m[1]*x+m[3]*y+m[5])

# ═════════════════════════════════════════════════════════════════════════════
#  SVG PARSER
# ═════════════════════════════════════════════════════════════════════════════

def parse_dim(val, default=100.0):
    if not val: return default
    val=str(val).strip()
    for s,f in [('mm',1),('cm',10),('in',25.4),('px',25.4/96),('pt',25.4/72)]:
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
    root     = ET.parse(path).getroot()
    polylines= []

    def sn(tag): return tag.split('}')[-1] if '}' in tag else tag
    def add(pts):
        if len(pts)>=2: polylines.append(list(pts))

    def path_pts(d, m):
        toks=re.findall(r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?', d)
        i=0; cx=cy=sx=sy=0.0; cur=[]; lc=None

        def flush():
            nonlocal cur; add(cur); cur=[]
        def move(x,y):
            nonlocal cx,cy,sx,sy,cur
            if cur: flush()
            cx,cy=x,y; sx,sy=x,y; cur=[_tf(m,cx,cy)]
        def lineto(x,y):
            nonlocal cx,cy
            cx,cy=x,y; cur.append(_tf(m,cx,cy))

        while i<len(toks):
            t=toks[i]
            if re.match(r'[MmLlHhVvCcSsQqTtAaZz]',t): cmd=t; lc=t; i+=1
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
            except (IndexError,ValueError): i+=1
        if cur: flush()

    def traverse(elem, pm=None):
        if pm is None: pm=[1,0,0,1,0,0]
        lm=_parse_transform(elem.get('transform',''))
        m=_mat_mul(pm,lm)
        tag=sn(elem.tag)

        if tag=='rect':
            x,y=float(elem.get('x',0)),float(elem.get('y',0))
            w,h=float(elem.get('width',0)),float(elem.get('height',0))
            if w>0 and h>0:
                add([_tf(m,x,y),_tf(m,x+w,y),_tf(m,x+w,y+h),_tf(m,x,y+h),_tf(m,x,y)])
        elif tag=='circle':
            cx,cy,r=float(elem.get('cx',0)),float(elem.get('cy',0)),float(elem.get('r',0))
            if r>0:
                n=max(36,int(r*2))
                add([_tf(m,cx+r*math.cos(2*math.pi*s/n),cy+r*math.sin(2*math.pi*s/n)) for s in range(n+1)])
        elif tag=='ellipse':
            cx,cy=float(elem.get('cx',0)),float(elem.get('cy',0))
            rx,ry=float(elem.get('rx',0)),float(elem.get('ry',0))
            if rx>0 and ry>0:
                add([_tf(m,cx+rx*math.cos(2*math.pi*s/48),cy+ry*math.sin(2*math.pi*s/48)) for s in range(49)])
        elif tag=='line':
            add([_tf(m,float(elem.get('x1',0)),float(elem.get('y1',0))),
                 _tf(m,float(elem.get('x2',0)),float(elem.get('y2',0)))])
        elif tag in('polyline','polygon'):
            ns=[float(v) for v in re.findall(r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?',elem.get('points',''))]
            pts=[_tf(m,ns[i],ns[i+1]) for i in range(0,len(ns)-1,2)]
            if tag=='polygon' and pts: pts.append(pts[0])
            add(pts)
        elif tag=='path':
            d=elem.get('d','')
            if d: path_pts(d,m)

        if tag!='defs':
            for child in elem: traverse(child,m)

    traverse(root)
    return polylines

def svg_to_hpgl(path, offset_x_mm=0, offset_y_mm=0, scale=1.0, mirror=False, log=None):
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
    if log: log(f"  {os.path.basename(path)}: {len(polys)} paths  off=({offset_x_mm:.1f},{offset_y_mm:.1f})mm")
    for poly in polys:
        if len(poly)<2: continue
        cmds.append(f'PU{hy(poly[0][1])},{hx(poly[0][0])};')
        cmds.append(f'PD{",".join(f"{hy(y)},{hx(x)}" for x,y in poly[1:])};')
        cmds.append('PU;')
    return cmds

# ═════════════════════════════════════════════════════════════════════════════
#  DATA MODEL
# ═════════════════════════════════════════════════════════════════════════════

class SvgItem:
    _id=0
    def __init__(self, path):
        SvgItem._id+=1
        self.id=SvgItem._id
        self.path=path
        self.name=os.path.basename(path)
        self.w_mm,self.h_mm,self.vb_w,self.vb_h=get_svg_size(path)
        self.x_mm=0.0
        self.scale=1.0
        self._cache=None
    @property
    def polylines(self):
        if self._cache is None: self._cache=extract_paths(self.path)
        return self._cache
    @property
    def width(self):  return self.w_mm*self.scale
    @property
    def height(self): return self.h_mm*self.scale

# ═════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═════════════════════════════════════════════════════════════════════════════

class App:
    def __init__(self, root):
        self.root=root
        self.root.title(f"{APP_NAME} v{VERSION} — {ORG_NAME}")
        self.root.geometry("1200x780")
        self.root.configure(bg=DS["bg_base"])
        self.root.minsize(960,640)

        self.svgs=[]
        self.selected=None
        self._drag=None
        self._cancel=False
        self._cscale=1.0
        self._pan_x=40.0
        self._pan_y=40.0
        self._pending_scale=1.0
        self.mirror_var=tk.BooleanVar(value=False)

        self.port_var  =tk.StringVar(value="COM5")
        self.baud_var  =tk.StringVar(value="9600")
        self.width_var =tk.StringVar(value="1350")
        self.gap_var   =tk.StringVar(value="5")
        self.sel_scale =tk.StringVar(value="1.00")
        self.saved_lbl =tk.StringVar(value="—")
        self.status_var=tk.StringVar(value="READY")

        self._build_ui()
        self.refresh_ports()

    # ── ttk style ─────────────────────────────────────────────────────────────
    def _style(self):
        s=ttk.Style(); s.theme_use('clam')
        bg,inp,txt,dim=DS["bg_surface"],DS["bg_input"],DS["text"],DS["text_dim"]
        s.configure('TFrame',      background=bg)
        s.configure('TLabel',      background=bg, foreground=txt, font=DS["font_ui"])
        s.configure('TEntry',      fieldbackground=inp, foreground=txt, font=DS["font_mono9"],
                                   insertcolor=DS["acc"], borderwidth=1, relief='flat')
        s.configure('TCombobox',   fieldbackground=inp, foreground=txt, font=DS["font_mono9"],
                                   arrowcolor=dim, borderwidth=1)
        s.configure('Horizontal.TProgressbar',
                    troughcolor=DS["bg_input"], background=DS["acc"], borderwidth=0)
        s.map('TCombobox', fieldbackground=[('readonly',inp)])

    def _btn(self, p, text, cmd, bg=None, fg=None, size=9, w=None):
        bg  = bg  or DS["bg_raised"]
        fg  = fg  or DS["text"]
        cfg = dict(text=text, command=cmd, bg=bg, fg=fg,
                   font=("Segoe UI",size,"bold"), relief='flat',
                   activebackground=DS["bg_hover"], activeforeground=fg,
                   cursor='hand2', pady=5, padx=10, bd=0,
                   highlightthickness=1, highlightbackground=DS["border_hi"])
        if w: cfg['width']=w
        return tk.Button(p, **cfg)

    def _label(self, p, text, color=None, font=None, **kw):
        return tk.Label(p, text=text,
                        bg=kw.pop('bg', DS["bg_surface"]),
                        fg=color or DS["text_dim"],
                        font=font or DS["font_sm"], **kw)

    def _sep(self, p, orient='h', color=None):
        color=color or DS["border"]
        f=tk.Frame(p, bg=color)
        if orient=='h': f.configure(height=1)
        else:           f.configure(width=1)
        return f

    def _entry(self, p, var, w=8, mono=True):
        return tk.Entry(p, textvariable=var, width=w,
                        bg=DS["bg_input"], fg=DS["text"],
                        insertbackground=DS["acc"],
                        font=DS["font_mono9"] if mono else DS["font_ui"],
                        relief='flat', bd=0,
                        highlightthickness=1, highlightbackground=DS["border"])

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._style()
        self.root.configure(bg=DS["bg_base"])

        # ── Titlebar ──────────────────────────────────────────────────────────
        tb=tk.Frame(self.root, bg=DS["bg_surface"], height=46)
        tb.pack(fill='x')
        tb.pack_propagate(False)

        # Left: logo area
        logo_f=tk.Frame(tb, bg=DS["acc_dim"], width=46)
        logo_f.pack(side='left', fill='y')
        logo_f.pack_propagate(False)
        tk.Label(logo_f, text="✂", font=("Segoe UI",22), bg=DS["acc_dim"],
                 fg="white").pack(expand=True)

        # Title
        tk.Label(tb, text=APP_NAME, font=DS["font_title"],
                 bg=DS["bg_surface"], fg=DS["text"]).pack(side='left', padx=(14,4), pady=12)
        tk.Label(tb, text=f"v{VERSION}", font=("Segoe UI",12),
                 bg=DS["bg_surface"], fg=DS["acc"]).pack(side='left', pady=16)

        self._sep(tb, 'v').pack(side='left', fill='y', pady=10, padx=14)

        tk.Label(tb, text=ORG_NAME, font=("Segoe UI",12),
                 bg=DS["bg_surface"], fg=DS["text_dim"]).pack(side='left')

        # Right: status badge
        status_f=tk.Frame(tb, bg=DS["bg_surface"])
        status_f.pack(side='right', padx=16)
        self._label(status_f, "STATUS", color=DS["text_muted"], bg=DS["bg_surface"],
                    font=("Segoe UI",11)).pack(side='left', padx=(0,4))
        tk.Label(status_f, textvariable=self.status_var,
                 bg=DS["bg_surface"], fg=DS["acc"],
                 font=("Consolas",14,"bold")).pack(side='left')

        # ── Body ──────────────────────────────────────────────────────────────
        self._sep(self.root).pack(fill='x')

        body=tk.Frame(self.root, bg=DS["bg_base"])
        body.pack(fill='both', expand=True)

        self._build_sidebar(body)
        self._sep(body,'v',DS["border"]).pack(side='left', fill='y')
        self._build_main(body)

        # ── Bottom status bar ─────────────────────────────────────────────────
        self._sep(self.root, color=DS["border"]).pack(fill='x')
        self._build_statusbar()

    def _build_sidebar(self, parent):
        sb=tk.Frame(parent, bg=DS["bg_surface"], width=240)
        sb.pack(side='left', fill='y')
        sb.pack_propagate(False)

        # ── Section: Files ────────────────────────────────────────────────────
        self._section_header(sb, "SVG FILES")

        btn_row=tk.Frame(sb, bg=DS["bg_surface"])
        btn_row.pack(fill='x', padx=8, pady=(0,6))
        self._btn(btn_row, "+ ADD", self.add_svg, DS["acc_dim"],
                  size=8).pack(side='left', fill='x', expand=True, padx=(0,3))
        self._btn(btn_row, "− REMOVE", self.remove_svg, DS["bg_raised"],
                  size=8).pack(side='left', fill='x', expand=True)

        # Listbox with custom styling
        list_f=tk.Frame(sb, bg=DS["border"], pady=1, padx=1)
        list_f.pack(fill='x', padx=8, pady=(0,6))
        self.listbox=tk.Listbox(list_f, bg=DS["bg_input"], fg=DS["text"],
                                 selectbackground=DS["bg_sel"],
                                 selectforeground=DS["acc_glow"],
                                 font=DS["font_mono"], relief='flat', bd=0,
                                 activestyle='none', cursor='hand2', height=9,
                                 highlightthickness=0)
        self.listbox.pack(fill='both')
        self.listbox.bind('<<ListboxSelect>>', self._on_list_sel)

        ord_row=tk.Frame(sb, bg=DS["bg_surface"])
        ord_row.pack(fill='x', padx=8, pady=(0,4))
        for txt,cmd in [("▲ UP",self.move_up),("▼ DOWN",self.move_down),("⟳ AUTO",self.auto_layout)]:
            self._btn(ord_row, txt, cmd, size=7).pack(side='left', padx=(0,3), fill='x', expand=True)

        # ── Section: Selected ─────────────────────────────────────────────────
        self._sep(sb, color=DS["border"]).pack(fill='x', pady=6)
        self._section_header(sb, "SELECTED")

        info_f=tk.Frame(sb, bg=DS["bg_raised"], highlightthickness=1,
                        highlightbackground=DS["border"])
        info_f.pack(fill='x', padx=8, pady=(0,8))

        self.info_var=tk.StringVar(value="— no selection —")
        tk.Label(info_f, textvariable=self.info_var,
                 bg=DS["bg_raised"], fg=DS["text_dim"],
                 font=DS["font_mono"], wraplength=210, justify='left',
                 anchor='w').pack(fill='x', padx=8, pady=6)

        # ── Section: Scale Tool ───────────────────────────────────────────────
        self._sep(sb, color=DS["border"]).pack(fill='x', pady=6)
        self._section_header(sb, "SCALE TOOL")

        self._label(sb, "① type  ② SAVE  ③ select  ④ APPLY",
                    bg=DS["bg_surface"],
                    font=("Segoe UI",11)).pack(padx=10, anchor='w', pady=(0,4))

        sc_row=tk.Frame(sb, bg=DS["bg_surface"])
        sc_row.pack(fill='x', padx=8, pady=(0,4))

        self._label(sc_row, "SCALE", bg=DS["bg_surface"],
                    font=("Segoe UI",11,"bold")).pack(side='left', padx=(0,4))
        se=self._entry(sc_row, self.sel_scale, w=7)
        se.pack(side='left', padx=(0,4))
        se.bind('<Return>', lambda e: self.save_scale())
        self._btn(sc_row, "SAVE", self.save_scale, DS["bg_raised"], size=8
                  ).pack(side='left', padx=(0,3))
        self._btn(sc_row, "APPLY", self.apply_scale, DS["acc_dim"], size=8
                  ).pack(side='left')

        saved_f=tk.Frame(sb, bg=DS["bg_input"], highlightthickness=1,
                         highlightbackground=DS["border"])
        saved_f.pack(fill='x', padx=8, pady=(0,4))
        tk.Label(saved_f, textvariable=self.saved_lbl,
                 bg=DS["bg_input"], fg=DS["success"],
                 font=DS["font_mono"], anchor='w').pack(fill='x', padx=6, pady=3)

        # ── Section: Layout Info ──────────────────────────────────────────────
        self._sep(sb, color=DS["border"]).pack(fill='x', pady=6)
        self._section_header(sb, "LAYOUT")
        self.layout_var=tk.StringVar(value="—")
        tk.Label(sb, textvariable=self.layout_var,
                 bg=DS["bg_surface"], fg=DS["text_dim"],
                 font=DS["font_mono"], justify='left',
                 anchor='w').pack(fill='x', padx=12, pady=(0,8))

    def _build_main(self, parent):
        main=tk.Frame(parent, bg=DS["bg_base"])
        main.pack(side='left', fill='both', expand=True)

        # ── Canvas toolbar ────────────────────────────────────────────────────
        ctb=tk.Frame(main, bg=DS["bg_surface"], height=34)
        ctb.pack(fill='x')
        ctb.pack_propagate(False)

        self._label(ctb, " LAYOUT PREVIEW", bg=DS["bg_surface"],
                    color=DS["text_dim"], font=("Segoe UI",12,"bold")).pack(side='left')
        self._label(ctb, " ·  drag to reposition  ·  scroll to zoom",
                    bg=DS["bg_surface"], font=("Segoe UI",11)).pack(side='left')
        self._btn(ctb, "FIT", self.fit_view, size=7).pack(side='right', padx=4, pady=4)

        self._sep(main, color=DS["border"]).pack(fill='x')

        # ── Canvas ────────────────────────────────────────────────────────────
        self.canvas=tk.Canvas(main, bg=DS["canvas_bg"], relief='flat',
                               highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>',       lambda e: self.root.after(120, self.fit_view))
        self.canvas.bind('<ButtonPress-1>',   self._on_press)
        self.canvas.bind('<B1-Motion>',       self._on_motion)
        self.canvas.bind('<ButtonRelease-1>', lambda e: setattr(self,'_drag',None))
        self.canvas.bind('<MouseWheel>',      self._on_wheel)
        self.canvas.bind('<Motion>',          self._on_hover)

        self._sep(main, color=DS["border"]).pack(fill='x')

        # ── Connection panel ──────────────────────────────────────────────────
        conn=tk.Frame(main, bg=DS["bg_surface"])
        conn.pack(fill='x')
        self._build_conn_panel(conn)

        # ── Log ───────────────────────────────────────────────────────────────
        self._sep(main, color=DS["border"]).pack(fill='x')
        log_hdr=tk.Frame(main, bg=DS["bg_surface"])
        log_hdr.pack(fill='x')
        self._label(log_hdr, " OUTPUT LOG", bg=DS["bg_surface"],
                    color=DS["text_muted"], font=("Segoe UI",11,"bold")).pack(side='left', pady=3)
        self._btn(log_hdr, "CLEAR", lambda: self.log_box.delete('1.0','end'),
                  size=7).pack(side='right', pady=2, padx=4)

        self.log_box=tk.Text(main, height=5, font=DS["font_mono"],
                              bg=DS["bg_base"], fg=DS["acc_glow"],
                              insertbackground=DS["acc"], relief='flat',
                              state='normal', wrap='none',
                              highlightthickness=0)
        sb_log=ttk.Scrollbar(main, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb_log.set)
        self.log_box.pack(fill='x', side='left', expand=True)
        sb_log.pack(side='right', fill='y')

    def _build_conn_panel(self, p):
        row1=tk.Frame(p, bg=DS["bg_surface"])
        row1.pack(fill='x', padx=10, pady=(8,4))

        # Port
        self._label(row1, "PORT", bg=DS["bg_surface"],
                    font=("Segoe UI",11,"bold")).pack(side='left', padx=(0,3))
        self.port_cb=ttk.Combobox(row1, textvariable=self.port_var, width=10,
                                   font=DS["font_mono9"])
        self.port_cb.pack(side='left', padx=(0,3))
        self._btn(row1, "↻", self.refresh_ports, size=8).pack(side='left', padx=(0,10))

        # Baud
        self._label(row1, "BAUD", bg=DS["bg_surface"],
                    font=("Segoe UI",11,"bold")).pack(side='left', padx=(0,3))
        ttk.Combobox(row1, textvariable=self.baud_var,
                     values=['2400','4800','9600','19200'], width=8,
                     font=DS["font_mono9"]).pack(side='left', padx=(0,10))

        # Width
        self._label(row1, "WIDTH mm", bg=DS["bg_surface"],
                    font=("Segoe UI",11,"bold")).pack(side='left', padx=(0,3))
        self._entry(row1, self.width_var, w=7).pack(side='left', padx=(0,10))

        # Gap
        self._label(row1, "GAP mm", bg=DS["bg_surface"],
                    font=("Segoe UI",11,"bold")).pack(side='left', padx=(0,3))
        self._entry(row1, self.gap_var, w=4).pack(side='left', padx=(0,10))

        self.width_var.trace_add('write', lambda *a: self._on_settings_change())
        self.gap_var.trace_add('write',   lambda *a: self._on_settings_change())

        # Row 2: action buttons + mode
        row2=tk.Frame(p, bg=DS["bg_surface"])
        row2.pack(fill='x', padx=10, pady=(0,8))

        self.test_btn=self._btn(row2, "▶  TEST", self.test_conn,
                                 DS["bg_raised"], DS["acc_glow"])
        self.test_btn.pack(side='left', padx=(0,4))

        self.send_btn=self._btn(row2, "✂  SEND ALL TO PLOTTER", self.send_to_plotter,
                                 DS["acc_dim"], "white")
        self.send_btn.pack(side='left', padx=(0,4))

        self.cancel_btn=self._btn(row2, "⏹  CANCEL", self.cancel_job,
                                   DS["error"], "white")
        self.cancel_btn.config(state='disabled')
        self.cancel_btn.pack(side='left', padx=(0,14))

        # Separator
        self._sep(row2, 'v', DS["border_hi"]).pack(side='left', fill='y', pady=3, padx=(0,12))

        # Cut mode
        self._label(row2, "CUT MODE", bg=DS["bg_surface"],
                    font=("Segoe UI",11,"bold")).pack(side='left', padx=(0,8))

        for txt, val, acc_col in [("◼  NORMAL", False, DS["acc"]),
                                    ("⟺  MIRROR", True,  DS["warn"])]:
            rb=tk.Radiobutton(row2, text=txt, variable=self.mirror_var, value=val,
                bg=DS["bg_surface"], fg=DS["text_dim"],
                selectcolor=DS["bg_input"],
                activebackground=DS["bg_surface"],
                font=("Segoe UI",12), cursor='hand2',
                indicatoron=0, relief='flat', bd=0,
                padx=8, pady=4,
                highlightthickness=1, highlightbackground=DS["border"])
            rb.pack(side='left', padx=(0,4))
            # Highlight selected
            def _on_rb_change(w=rb, v=val, c=acc_col):
                def _upd(*_):
                    if self.mirror_var.get()==v:
                        w.config(fg=c, highlightbackground=c)
                    else:
                        w.config(fg=DS["text_dim"], highlightbackground=DS["border"])
                return _upd
            self.mirror_var.trace_add('write', _on_rb_change())

        # Progress
        self.progress=ttk.Progressbar(row2, mode='determinate', length=120)
        self.progress.pack(side='left', padx=(12,6))

    def _build_statusbar(self):
        bar=tk.Frame(self.root, bg=DS["bg_raised"], height=22)
        bar.pack(fill='x')
        bar.pack_propagate(False)

        items=[
            ("SVG2Plotter", DS["acc"]),
            (f"v{VERSION}", DS["text_muted"]),
            ("·", DS["text_muted"]),
            (ORG_NAME, DS["text_muted"]),
        ]
        for txt, col in items:
            tk.Label(bar, text=txt, bg=DS["bg_raised"], fg=col,
                     font=("Segoe UI",11)).pack(side='left', padx=6)

        # Right: port status
        self.port_status=tk.Label(bar, text="● DISCONNECTED",
                                   bg=DS["bg_raised"], fg=DS["error"],
                                   font=("Consolas",11))
        self.port_status.pack(side='right', padx=8)

    def _section_header(self, p, text):
        f=tk.Frame(p, bg=DS["bg_surface"])
        f.pack(fill='x', padx=8, pady=(4,6))
        tk.Frame(f, bg=DS["acc_dim"], width=3).pack(side='left', fill='y')
        tk.Label(f, text=f"  {text}", font=("Segoe UI",11,"bold"),
                 bg=DS["bg_surface"], fg=DS["acc"]).pack(side='left')

    # ── SVG Management ────────────────────────────────────────────────────────
    def add_svg(self):
        paths=filedialog.askopenfilenames(title="Add SVG files",
            filetypes=[("SVG","*.svg"),("All","*.*")])
        for p in paths:
            try:
                item=SvgItem(p)
                self.svgs.append(item)
                self.listbox.insert('end', f" {item.name}")
                self.log(f"+ {item.name}  [{item.w_mm:.1f}×{item.h_mm:.1f}mm]")
            except Exception as e:
                self.log(f"ERROR loading {p}: {e}")
        self.auto_layout()

    def remove_svg(self):
        sel=self.listbox.curselection()
        if not sel: return
        idx=sel[0]; removed=self.svgs.pop(idx)
        self.listbox.delete(idx)
        if self.selected is removed: self.selected=None
        self.log(f"- {removed.name}")
        self.auto_layout()

    def move_up(self):
        sel=self.listbox.curselection()
        if not sel or sel[0]==0: return
        i=sel[0]; self.svgs[i-1],self.svgs[i]=self.svgs[i],self.svgs[i-1]
        n=self.listbox.get(i); self.listbox.delete(i); self.listbox.insert(i-1,n)
        self.listbox.select_set(i-1); self.auto_layout()

    def move_down(self):
        sel=self.listbox.curselection()
        if not sel or sel[0]>=len(self.svgs)-1: return
        i=sel[0]; self.svgs[i+1],self.svgs[i]=self.svgs[i],self.svgs[i+1]
        n=self.listbox.get(i); self.listbox.delete(i); self.listbox.insert(i+1,n)
        self.listbox.select_set(i+1); self.auto_layout()

    def save_scale(self):
        try:
            v=max(0.01,float(self.sel_scale.get()))
            self._pending_scale=v
            self.sel_scale.set(f"{v:.2f}")
            self.saved_lbl.set(f"SAVED  {v:.2f}×  →  select + APPLY")
            self.log(f"Scale {v:.2f}× saved.")
        except ValueError:
            self.log("ERROR: invalid scale value")

    def apply_scale(self):
        if not self.selected:
            self.log("Select a drawing first, then APPLY"); return
        s=self._pending_scale
        self.selected.scale=s; self.selected._cache=None
        self._update_info()
        self.auto_layout(); self.fit_view()
        self.saved_lbl.set(f"APPLIED  {s:.2f}×  →  {self.selected.name}")
        self.log(f"Scale {s:.2f}× → {self.selected.name}")

    # ── Layout ────────────────────────────────────────────────────────────────
    def _max_w(self):
        try: return float(self.width_var.get())
        except: return 1350.0
    def _gap(self):
        try: return float(self.gap_var.get())
        except: return 5.0

    def auto_layout(self):
        g=self._gap(); x=g
        for item in self.svgs: item.x_mm=x; x+=item.width+g
        self._update_layout_info(); self.redraw()

    def _layout_h(self): return max((item.height for item in self.svgs), default=0)
    def _layout_w(self):
        if not self.svgs: return 0
        g=self._gap(); return sum(item.width for item in self.svgs)+g*(len(self.svgs)+1)

    def _update_layout_info(self):
        mw=self._max_w(); lw=self._layout_w(); lh=self._layout_h()
        pct=(lw/mw*100) if mw>0 else 0
        self.layout_var.set(
            f"width  {mw:.0f} mm\n"
            f"height {lh:.1f} mm\n"
            f"used   {lw:.1f} mm  ({pct:.0f}%)\n"
            f"files  {len(self.svgs)}"
        )

    def _on_settings_change(self): self.auto_layout()

    # ── Canvas ────────────────────────────────────────────────────────────────
    def mm2px(self, x, y):
        lh=self._layout_h() or 100
        return (self._pan_x+x*self._cscale, self._pan_y+(lh-y)*self._cscale)

    def px2mm(self, px, py):
        lh=self._layout_h() or 100
        return ((px-self._pan_x)/self._cscale, lh-(py-self._pan_y)/self._cscale)

    def fit_view(self, *_):
        cw=self.canvas.winfo_width()  or 800
        ch=self.canvas.winfo_height() or 400
        mw=self._max_w(); lh=self._layout_h() or 100
        m=50
        self._cscale=min((cw-m*2)/mw,(ch-m*2)/lh)
        self._pan_x=m; self._pan_y=m
        self.redraw()

    def redraw(self):
        c=self.canvas; c.delete('all')
        mw=self._max_w(); lh=self._layout_h() or 100

        # Grid
        grid_step=self._cscale*50
        if grid_step>8:
            x1,y1=self.mm2px(0,0); x2,y2=self.mm2px(mw,lh)
            for gx in range(int(x1), int(x2)+1, max(1,int(grid_step))):
                c.create_line(gx,y2,gx,y1, fill=DS["grid"], width=1)
            for gy in range(int(y2), int(y1)+1, max(1,int(grid_step))):
                c.create_line(x1,gy,x2,gy, fill=DS["grid"], width=1)

        # Print area
        ax1,ay1=self.mm2px(0,0); ax2,ay2=self.mm2px(mw,lh)
        c.create_rectangle(ax1,ay1,ax2,ay2, fill=DS["area_fill"],
                           outline=DS["area_bord"], width=1)

        # Corner marks
        sz=8
        for px,py in [(ax1,ay2),(ax2,ay2),(ax2,ay1),(ax1,ay1)]:
            c.create_rectangle(px-sz/2,py-sz/2,px+sz/2,py+sz/2,
                               fill=DS["border_hi"], outline='', width=0)

        # Ruler
        for xr in range(0,int(mw)+1,100):
            px,py=self.mm2px(xr,0)
            c.create_line(px,py,px,py-6, fill=DS["border_hi"])
            c.create_text(px,py+10, text=f"{xr}", fill=DS["text_muted"],
                          font=("Consolas",8))
        for yr in range(0,int(lh)+1,50):
            px,py=self.mm2px(0,yr)
            c.create_line(px,py,px-6,py, fill=DS["border_hi"])
            c.create_text(px-20,py, text=f"{yr}", fill=DS["text_muted"],
                          font=("Consolas",8))

        # Dimension readout
        c.create_text(ax1+6, ay2+18, anchor='w',
                      text=f"↔ {mw:.0f}mm   ↕ {lh:.1f}mm",
                      fill=DS["text_muted"], font=("Consolas",11))

        for item in self.svgs:
            self._draw_item(item)

    def _draw_item(self, item):
        sel=item is self.selected
        bc = DS["box_sel"]  if sel else DS["box_norm"]
        pc = DS["path_sel"] if sel else DS["path_norm"]
        bw = 1

        w,h=item.width,item.height; x0=item.x_mm
        bx1,by1=self.mm2px(x0,0); bx2,by2=self.mm2px(x0+w,h)

        c=self.canvas
        c.create_rectangle(bx1,by1,bx2,by2, fill=bc,
                           outline=pc, width=bw, dash=(4,3) if not sel else ())

        # Corner accent
        if sel:
            sz=5
            for px,py in [(bx1,by1),(bx2,by1),(bx2,by2),(bx1,by2)]:
                c.create_rectangle(px-sz,py-sz,px+sz,py+sz,
                                   fill=DS["path_sel"], outline='')

        # Name label
        mid_x=(bx1+bx2)/2
        c.create_text(mid_x, by1-11, text=item.name[:24],
                      fill=pc, font=("Consolas",11,"bold"), anchor='center')
        c.create_text(mid_x, by2+11,
                      text=f"{w:.0f}×{h:.0f}mm  @{x0:.0f}mm  ×{item.scale:.2f}",
                      fill=DS["text_muted"], font=("Consolas",8), anchor='center')

        # Paths
        sr=w/item.vb_w; sy_r=h/item.vb_h
        lh=self._layout_h() or 100
        for poly in item.polylines:
            if len(poly)<2: continue
            pts=[]
            for vx,vy in poly:
                px=self._pan_x+(x0+vx*sr)*self._cscale
                py=self._pan_y+(lh-vy*sy_r)*self._cscale
                pts.extend([px,py])
            if len(pts)>=4:
                c.create_line(*pts, fill=pc, width=1)

    # ── Interaction ───────────────────────────────────────────────────────────
    def _item_at(self, cx, cy):
        xm,ym=self.px2mm(cx,cy)
        for item in reversed(self.svgs):
            if item.x_mm<=xm<=item.x_mm+item.width and 0<=ym<=item.height:
                return item
        return None

    def _on_press(self, e):
        item=self._item_at(e.x,e.y)
        prev=self.selected; self.selected=item
        if item:
            self._drag={'item':item,'sx':e.x,'ox':item.x_mm}
            if item is not prev: self._sync_list(item)
        self._update_info(); self.redraw()

    def _on_motion(self, e):
        if not self._drag: return
        dx=(e.x-self._drag['sx'])/self._cscale
        self._drag['item'].x_mm=max(0,self._drag['ox']+dx)
        self._update_layout_info(); self.redraw()

    def _on_hover(self, e):
        self.canvas.config(cursor='fleur' if self._item_at(e.x,e.y) else '')

    def _on_wheel(self, e):
        f=1.1 if e.delta>0 else 0.9
        self._pan_x=e.x-(e.x-self._pan_x)*f
        self._pan_y=e.y-(e.y-self._pan_y)*f
        self._cscale*=f; self.redraw()

    def _on_list_sel(self, e):
        sel=self.listbox.curselection()
        self.selected=self.svgs[sel[0]] if sel else None
        self._update_info(); self.redraw()

    def _sync_list(self, item):
        try:
            i=self.svgs.index(item)
            self.listbox.selection_clear(0,'end')
            self.listbox.selection_set(i); self.listbox.see(i)
        except ValueError: pass

    def _update_info(self):
        if self.selected:
            s=self.selected
            self.info_var.set(
                f" {s.name}\n"
                f" orig   {s.w_mm:.1f} × {s.h_mm:.1f} mm\n"
                f" scaled {s.width:.1f} × {s.height:.1f} mm\n"
                f" x pos  {s.x_mm:.1f} mm\n"
                f" scale  {s.scale:.2f}×"
            )
        else:
            self.info_var.set("— no selection —")

    # ── Utilities ─────────────────────────────────────────────────────────────
    def log(self, msg):
        self.log_box.insert('end', msg+"\n")
        self.log_box.see('end')
        self.root.update_idletasks()

    def set_status(self, text, color=None):
        self.status_var.set(text)
        if color:
            for w in self.root.winfo_children():
                pass  # status label updated via StringVar

    def refresh_ports(self):
        ports=[p.device for p in serial.tools.list_ports.comports()]
        self.port_cb['values']=ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])
        self.log(f"PORTS: {', '.join(ports) if ports else 'none detected'}")
        self.port_status.config(
            text=f"● {ports[0]}" if ports else "● NO PORT",
            fg=DS["success"] if ports else DS["error"])

    # ── Plotter ───────────────────────────────────────────────────────────────
    def test_conn(self):
        port=self.port_var.get(); baud=int(self.baud_var.get())
        self.log(f"TEST  {port} @ {baud}bps ...")
        try:
            s=serial.Serial(port,baud,timeout=2)
            time.sleep(0.3); s.write(b'IN;\x03'); time.sleep(0.3); s.close()
            self.log("OK  plotter responded")
            self.port_status.config(text=f"● {port}  CONNECTED", fg=DS["success"])
            messagebox.showinfo("Connected", f"Plotter on {port} responded.")
        except Exception as e:
            self.log(f"ERROR  {e}")
            messagebox.showerror("Connection Failed", str(e))

    def cancel_job(self):
        self._cancel=True; self.log("CANCEL requested")
        self.status_var.set("CANCELLING")

    def send_to_plotter(self):
        if not self.svgs:
            messagebox.showwarning("No files","Add at least one SVG."); return
        mw=self._max_w(); lw=self._layout_w()
        if lw>mw and not messagebox.askyesno("Width exceeded",
            f"Layout {lw:.1f}mm > plotter max {mw:.0f}mm.\nContinue?"):
            return
        self._cancel=False
        self.send_btn.config(state='disabled')
        self.cancel_btn.config(state='normal')
        self.status_var.set("CUTTING")
        threading.Thread(target=self._send_job, daemon=True).start()

    def _send_job(self):
        port=self.port_var.get(); baud=int(self.baud_var.get())
        try:
            self.log(f"\n{'─'*52}")
            self.log(f"JOB START  {len(self.svgs)} file(s)  {time.strftime('%H:%M:%S')}")
            cmds=['IN;','SP1;']
            mirror=self.mirror_var.get()
            self.log(f"MODE  {'MIRROR (glass)' if mirror else 'NORMAL'}")
            for item in self.svgs:
                cmds+=svg_to_hpgl(item.path,
                    offset_x_mm=item.x_mm, offset_y_mm=0,
                    scale=item.scale, mirror=mirror, log=self.log)
            cmds.append('SP0;')
            total=len(cmds)
            self.log(f"COMMANDS  {total}   opening {port} ...")
            ser=serial.Serial(port,baud,timeout=2,
                bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE)
            time.sleep(0.5)
            self.log("OK  cutting ...")
            for i,cmd in enumerate(cmds):
                if self._cancel: break
                ser.write((cmd+'\x03').encode('ascii'))
                time.sleep(0.02)
                pct=int((i+1)/total*100)
                self.progress['value']=pct
                if i%30==0: self.status_var.set(f"CUTTING  {pct}%")
            ser.close()
            result="CANCELLED" if self._cancel else "DONE"
            self.log(f"{'─'*52}\nJOB {result}  {time.strftime('%H:%M:%S')}")
            self.status_var.set(result)
            self.progress['value']=100 if not self._cancel else self.progress['value']
        except Exception as e:
            self.log(f"ERROR  {e}")
            messagebox.showerror("Job Error", str(e))
            self.status_var.set("ERROR")
        finally:
            self.send_btn.config(state='normal')
            self.cancel_btn.config(state='disabled')

# ─── Entry ────────────────────────────────────────────────────────────────────
if __name__=='__main__':
    root=tk.Tk()
    try:
        root.iconbitmap(default='')
    except: pass
    App(root)
    root.mainloop()
