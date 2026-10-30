import json, os

W = 800
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT, exist_ok=True)


def at(**a):
    return " ".join('%s="%s"' % (k.replace("_", "-"), v) for k, v in a.items())


def path(d, **a):
    return '<path d="%s" %s/>' % (d, at(**a))


def sym(content):
    return content + '<g transform="translate(800 0) scale(-1 1)">%s</g>' % content


def half_to_path(start, segs):
    pts = [start] + [s[2] for s in segs]
    d = "M%s,%s " % start
    for c1, c2, p in segs:
        d += "C%s,%s %s,%s %s,%s " % (c1 + c2 + p)
    for i in range(len(segs) - 1, -1, -1):
        c1, c2, p = segs[i]
        prev = pts[i]
        m = lambda q: (W - q[0], q[1])
        d += "C%s,%s %s,%s %s,%s " % (m(c2) + m(c1) + m(prev))
    return d + "Z"


# ---------- reusable detail pieces (use CSS variables so colors can change) ----------
GAR = "var(--garment, #f2f2ef)"
TRIM = "var(--trim, var(--garment, #f2f2ef))"


def fold(pid, d, w=10, blur=5, op=0.12, color="#000"):
    if color == "#fff":
        op = min(op * 2.0, 0.5)
    return path(d, fill="none", stroke=color, stroke_width=w, stroke_linecap="round",
                opacity=op, filter="url(#%sb%d)" % (pid, blur))


def stitch(d, op=0.3, color="#000"):
    return (path(d, fill="none", stroke=color, stroke_width=1.1, stroke_dasharray="3.5 3", opacity=op) +
            path(d, fill="none", stroke="#fff", stroke_width=1.0, stroke_dasharray="3.5 3", opacity=0.20, transform="translate(0 1.2)"))


def rib(d, w, base=GAR, ribs=0.17):
    s = path(d, fill="none", stroke="#000", stroke_width=w + 3, opacity=0.2)
    s += path(d, fill="none", stroke=base, stroke_width=w)
    s += path(d, fill="none", stroke="#000", stroke_width=w, stroke_dasharray="1.3 2.9", opacity=ribs)
    s += path(d, fill="none", stroke="#fff", stroke_width=w, stroke_dasharray="0.8 3.4", opacity=0.17)
    return s


def inner_dark(d, op=0.36):
    return path(d, fill=GAR) + path(d, fill="#000", opacity=op)


# ---------- garment geometry ----------
TEE_SEGS = [
    ((372, 138), (345, 142), (322, 152)),
    ((290, 165), (240, 180), (205, 196)),
    ((168, 222), (125, 275), (90, 318)),
    ((108, 330), (128, 342), (148, 352)),
    ((185, 338), (230, 318), (260, 300)),
    ((252, 360), (262, 440), (262, 520)),
    ((262, 590), (256, 640), (250, 690)),
    ((300, 694), (350, 696), (400, 696)),
]
HOODIE_SEGS = [
    ((375, 170), (345, 170), (326, 176)),
    ((290, 184), (245, 200), (212, 226)),
    ((172, 300), (136, 470), (122, 610)),
    ((138, 614), (160, 620), (182, 626)),
    ((190, 540), (228, 430), (262, 362)),
    ((256, 430), (263, 490), (263, 540)),
    ((263, 610), (259, 655), (258, 692)),
    ((310, 696), (360, 698), (400, 698)),
]
JERSEY_SEGS = [
    ((375, 142), (352, 144), (334, 150)),
    ((318, 150), (300, 154), (284, 160)),
    ((300, 215), (285, 300), (244, 352)),
    ((240, 410), (246, 470), (244, 530)),
    ((244, 600), (238, 650), (232, 694)),
    ((290, 698), (350, 700), (400, 700)),
]

# Stage O.1.2: primary printable = full visible flat front/back of the mockup
# (body + sleeves as drawn on the 2D SVG). Not 3D wrap / separate sleeve jobs.
# Jersey back keeps name/number as optional sub-guides inside the primary back panel.
# Coordinates are 800×800 editor units (not physical print cm).
# Tuned to clipPath silhouette extents (tee/polo ~90–710×138–696; hoodie ~122–678;
# jersey side-sleeve silhouette ~232–568).
AREAS = {
    "tee": {
        "front": [("front", "Front", 100, 160, 600, 520)],
        "back": [("back", "Back", 100, 155, 600, 525)],
    },
    "polo": {
        "front": [("front", "Front", 100, 175, 600, 505)],
        "back": [("back", "Back", 100, 160, 600, 510)],
    },
    "hoodie": {
        "front": [("front", "Front", 130, 185, 540, 495)],
        "back": [("back", "Back", 130, 210, 540, 470)],
    },
    "jersey": {
        "front": [("front", "Front", 240, 165, 320, 520)],
        "back": [
            ("back", "Back", 240, 160, 320, 520),
            ("name", "Name", 300, 215, 200, 70),
            ("number", "Number", 320, 300, 160, 260),
        ],
    },
}

# ---------- per-garment detail builders ----------

def tee_details(pid, view):
    s = ""
    if view == "front":
        NF = "M322,152 C330,205 365,232 400,232 C435,232 470,205 478,152"
        s += inner_dark("M322,152 C345,142 372,138 400,138 C428,138 455,142 478,152 C470,205 435,232 400,232 C365,232 330,205 322,152 Z")
        s += rib(NF, 15)
    else:
        NB = "M322,152 C340,168 372,175 400,175 C428,175 460,168 478,152"
        s += inner_dark("M322,152 C345,142 372,138 400,138 C428,138 455,142 478,152 C460,168 428,175 400,175 C372,175 340,168 322,152 Z")
        s += rib(NB, 15)
        s += stitch("M300,210 C350,236 450,236 500,210", 0.25)
    s += sym(stitch("M205,196 C222,238 246,280 260,300", 0.3))
    s += sym(stitch("M97,306 C115,318 135,328 155,340", 0.3))
    s += sym(stitch("M252,672 C300,676 350,678 400,678", 0.3))
    return s


def tee_shade(pid, view):
    s = sym(fold(pid, "M266,325 C288,385 300,440 322,505", 12, 6, 0.13))
    s += sym(fold(pid, "M278,322 C300,382 312,437 334,500", 10, 6, 0.12, "#fff"))
    s += sym(fold(pid, "M270,560 C310,585 350,590 392,584", 8, 5, 0.09))
    s += sym(fold(pid, "M168,232 C150,262 132,292 118,322", 9, 5, 0.12))
    s += sym(fold(pid, "M182,238 C166,268 148,298 134,326", 8, 5, 0.10, "#fff"))
    s += sym(fold(pid, "M240,182 C275,172 300,165 322,160", 10, 5, 0.15, "#fff"))
    if view == "back":
        s += fold(pid, "M400,260 C398,380 402,480 400,600", 16, 10, 0.06)
    s += sym('<ellipse cx="262" cy="312" rx="48" ry="62" fill="url(#%sarm)"/>' % pid)
    return s


def polo_details(pid, view):
    s = ""
    if view == "front":
        s += inner_dark("M326,150 C350,140 372,138 400,138 C428,138 450,140 474,150 L400,236 Z", 0.5)
        s += rib("M324,150 C348,138 372,134 400,134 C428,134 452,138 476,150", 18, GAR, 0.0)
        flap = "M400,208 L324,142 C312,160 304,176 302,190 C340,205 372,222 400,240 Z"
        s += sym(path(flap, fill="#000", opacity=0.28, transform="translate(0 4)", filter="url(#%sb3)" % pid))
        s += sym(path(flap, fill=GAR) + path(flap, fill="#fff", opacity=0.07) +
                 path(flap, fill="none", stroke="#000", stroke_width=1.2, opacity=0.35))
        s += path("M388,214 H412 V336 H388 Z", fill="#000", opacity=0.22, transform="translate(1.5 2)", filter="url(#%sb2)" % pid)
        s += path("M388,214 H412 V336 H388 Z", fill=GAR) + path("M388,214 H412 V336 H388 Z", fill="#fff", opacity=0.06)
        s += stitch("M388,214 V336", 0.35) + stitch("M412,214 V336", 0.35)
        for y in (246, 282, 318):
            s += '<circle cx="400" cy="%d" r="5.2" fill="#f3f0e8" stroke="#000" stroke-opacity=".4" stroke-width="1"/>' % y
            s += '<circle cx="398.6" cy="%d" r="0.9" fill="#000" opacity=".5"/><circle cx="401.4" cy="%d" r="0.9" fill="#000" opacity=".5"/>' % (y - 1, y + 1)
    else:
        s += inner_dark("M322,152 C345,142 372,138 400,138 C428,138 455,142 478,152 C460,168 428,175 400,175 C372,175 340,168 322,152 Z")
        s += rib("M322,152 C346,166 374,172 400,172 C426,172 454,166 478,152", 20, GAR, 0.0)
        s += stitch("M300,212 C350,238 450,238 500,212", 0.25)
    s += sym(rib("M95,310 C113,321 132,333 153,344", 16))
    s += sym(stitch("M205,196 C222,238 246,280 260,300", 0.3))
    s += sym(stitch("M252,672 C300,676 350,678 400,678", 0.3))
    return s


def polo_shade(pid, view):
    return tee_shade(pid, view)


def hoodie_details(pid, view):
    s = ""
    if view == "front":
        s += inner_dark("M330,178 C328,120 362,84 400,84 C438,84 472,120 470,178 C450,210 426,222 400,222 C374,222 350,210 330,178 Z", 0.55)
        s += fold(pid, "M400,88 C398,140 402,190 400,220", 14, 8, 0.25)
        s += rib("M330,178 C328,120 362,84 400,84 C438,84 472,120 470,178", 13, GAR, 0.0)
        s += rib("M330,178 C350,210 374,222 400,222 C426,222 450,210 470,178", 10, GAR, 0.0)
        s += sym(path("M372,214 C370,250 366,285 364,320", fill="none", stroke="#000", stroke_width=6, opacity=0.35, stroke_linecap="round"))
        s += sym(path("M372,214 C370,250 366,285 364,320", fill="none", stroke="var(--string, #e9e5da)", stroke_width=4, stroke_linecap="round"))
        s += sym(path("M364,320 L363,336", fill="none", stroke="#8c887c", stroke_width=6, stroke_linecap="butt"))
        s += sym('<circle cx="382" cy="206" r="4" fill="#000" opacity=".5"/>')
        pocket = "M296,470 L504,470 L536,615 Q537,628 523,628 L277,628 Q263,628 264,615 Z"
        s += path(pocket, fill="#fff", opacity=0.04)
        s += path(pocket, fill="none", stroke="#000", stroke_width=1.5, opacity=0.3)
        s += stitch("M300,478 L500,478", 0.3)
        s += sym(path("M296,470 L264,606", fill="none", stroke="#000", stroke_width=4, opacity=0.3, filter="url(#%sb2)" % pid))
    else:
        s += path("M318,178 C288,245 326,338 400,360 C474,338 512,245 482,178", fill="none", stroke="#000",
                  stroke_width=12, opacity=0.25, filter="url(#%sb6)" % pid, transform="translate(0 4)")
        hood = "M318,178 C282,120 326,56 400,56 C474,56 518,120 482,178 C512,245 474,338 400,360 C326,338 288,245 318,178 Z"
        s += path(hood, fill=GAR) + path(hood, fill="#000", opacity=0.06)
        s += path(hood, fill="none", stroke="#000", stroke_width=1.4, opacity=0.3)
        s += stitch("M400,58 C402,160 398,260 400,358", 0.3)
        s += fold(pid, "M345,250 C360,300 380,330 400,340", 10, 6, 0.10)
        s += fold(pid, "M455,250 C440,300 420,330 400,340", 10, 6, 0.10)
    s += sym(rib("M124,596 C145,602 165,608 184,612", 26))
    s += rib("M258,676 C310,682 360,684 400,684 C440,684 490,682 542,676", 26)
    s += sym(stitch("M212,226 C226,270 246,330 262,362", 0.3))
    return s


def hoodie_shade(pid, view):
    s = sym(fold(pid, "M160,410 C175,420 195,420 215,408", 7, 4, 0.16))
    s += sym(fold(pid, "M160,402 C175,412 195,412 215,400", 6, 4, 0.10, "#fff"))
    s += sym(fold(pid, "M150,445 C168,457 190,457 208,445", 7, 4, 0.13))
    s += sym(fold(pid, "M140,500 C152,508 170,508 184,498", 6, 4, 0.10))
    s += sym(fold(pid, "M268,385 C280,420 288,450 292,470", 12, 6, 0.12))
    s += sym(fold(pid, "M242,236 C275,224 300,214 326,210", 10, 5, 0.15, "#fff"))
    s += sym('<ellipse cx="262" cy="372" rx="46" ry="60" fill="url(#%sarm)"/>' % pid)
    if view == "front":
        s += fold(pid, "M290,640 C340,652 460,652 510,640", 10, 6, 0.10)
    return s


def jersey_details(pid, view):
    panel = "M244,352 C240,410 246,470 244,530 C244,600 238,650 232,694 L254,694 C259,650 262,600 262,530 C262,470 257,410 258,352 Z"
    s = sym(path(panel, fill=TRIM))
    s += sym(stitch("M260,356 C258,410 264,470 262,530 C262,600 259,650 254,692", 0.3))
    if view == "front":
        s += inner_dark("M334,150 C352,144 375,142 400,142 C425,142 448,144 466,150 C464,205 434,252 400,252 C366,252 336,205 334,150 Z")
        s += rib("M334,150 C336,205 366,252 400,252 C434,252 464,205 466,150", 14, TRIM, 0.12)
    else:
        s += inner_dark("M334,150 C352,144 375,142 400,142 C425,142 448,144 466,150 C448,168 424,176 400,176 C376,176 352,168 334,150 Z")
        s += rib("M334,150 C350,168 374,176 400,176 C426,176 450,168 466,150", 14, TRIM, 0.12)
    s += sym(rib("M290,162 C306,215 292,298 250,350", 14, TRIM, 0.12))
    s += rib("M234,684 C290,688 350,690 400,690 C450,690 510,688 566,684", 9, TRIM, 0.1)
    return s


def jersey_shade(pid, view):
    s = sym(fold(pid, "M262,380 C268,430 274,480 272,520", 14, 8, 0.10))
    s += sym(fold(pid, "M290,172 C300,200 300,230 292,260", 8, 5, 0.12, "#fff"))
    s += sym('<ellipse cx="246" cy="356" rx="40" ry="56" fill="url(#%sarm)"/>' % pid)
    s += fold(pid, "M290,600 C340,612 460,612 510,600", 9, 6, 0.08)
    return s


GARMENTS = {
    "tee": dict(label="T-shirt", segs=TEE_SEGS, top=(400, 138), details=tee_details, shade=tee_shade, extra=[]),
    "polo": dict(label="Polo shirt", segs=TEE_SEGS, top=(400, 138), details=polo_details, shade=polo_shade, extra=[]),
    "hoodie": dict(label="Hoodie", segs=HOODIE_SEGS, top=(400, 170), details=hoodie_details, shade=hoodie_shade, extra="hood"),
    "jersey": dict(label="Jersey", segs=JERSEY_SEGS, top=(400, 142), details=jersey_details, shade=jersey_shade, extra=[]),
}

HOOD_FRONT = "M308,184 C280,120 322,50 400,50 C478,50 520,120 492,184 Z"
HOOD_BACK = "M318,178 C282,120 326,56 400,56 C474,56 518,120 482,178 C512,245 474,338 400,360 C326,338 288,245 318,178 Z"


def build(key, view):
    g = GARMENTS[key]
    pid = "%s-%s-" % (key, view)
    body = half_to_path(g["top"], g["segs"])
    sils = [body]
    if g["extra"] == "hood":
        sils.append(HOOD_FRONT if view == "front" else HOOD_BACK)

    defs = ""
    for n in (2, 3, 4, 5, 6, 8, 10, 12, 14, 28):
        defs += '<filter id="%sb%d" x="-20%%" y="-20%%" width="140%%" height="140%%"><feGaussianBlur stdDeviation="%d"/></filter>' % (pid, n, n)
    defs += ('<filter id="%sgrain" filterUnits="userSpaceOnUse" x="0" y="0" width="800" height="800">'
             '<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4" result="n"/>'
             '<feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  1.4 0 0 0 -0.55"/></filter>' % pid)
    defs += ('<linearGradient id="%slight" x1="0" y1="0" x2="1" y2="1">'
             '<stop offset="0" stop-color="#fff" stop-opacity=".18"/><stop offset=".45" stop-color="#fff" stop-opacity="0"/>'
             '<stop offset="1" stop-color="#000" stop-opacity=".14"/></linearGradient>' % pid)
    defs += ('<radialGradient id="%sarm"><stop offset="0" stop-color="#000" stop-opacity=".34"/>'
             '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>' % pid)
    defs += ('<pattern id="%sweave" width="3" height="3" patternUnits="userSpaceOnUse">'
             '<path d="M0,3 L3,0" stroke="#000" stroke-width=".45" opacity=".14"/></pattern>' % pid)
    defs += '<clipPath id="%sclip">%s</clipPath>' % (pid, "".join(path(d) for d in sils))

    clip = 'clip-path="url(#%sclip)"' % pid
    out = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="800" height="800" id="%ssvg" data-garment="%s" data-view="%s">' % (pid, key, view)
    out += "<defs>%s</defs>" % defs
    out += '<g id="%sground"><ellipse cx="400" cy="708" rx="200" ry="13" fill="#000" opacity=".18" filter="url(#%sb10)"/></g>' % (pid, pid)
    if g["extra"] == "hood":
        out += '<g id="%shood-shadow">%s</g>' % (pid, path(sils[1], fill="#000", opacity=0.0))
    out += '<g id="%sbase">%s</g>' % (pid, "".join(path(d, fill=GAR) for d in sils))
    out += '<g id="%sart" %s></g>' % (pid, clip)
    out += '<g id="%sdetails" %s>%s</g>' % (pid, clip, g["details"](pid, view))
    shade = ""
    for d in sils:
        shade += path(d, fill="none", stroke="#000", stroke_width=46, opacity=0.22, filter="url(#%sb12)" % pid)
    if g["extra"] == "hood" and view == "front":
        shade += path(HOOD_FRONT, fill="#000", opacity=0.10)
    for d in sils:
        shade += path(d, fill="none", stroke="#fff", stroke_width=5, opacity=0.16, filter="url(#%sb3)" % pid, transform="translate(-2 -2)")
    shade += '<ellipse cx="370" cy="380" rx="110" ry="190" fill="#fff" opacity=".085" filter="url(#%sb28)"/>' % pid
    shade += '<ellipse cx="450" cy="440" rx="80" ry="160" fill="#000" opacity=".06" filter="url(#%sb28)"/>' % pid
    shade += '<rect width="800" height="800" fill="url(#%slight)"/>' % pid
    shade += g["shade"](pid, view)
    shade += '<rect width="800" height="800" fill="url(#%sweave)" opacity=".2"/>' % pid
    shade += '<rect width="800" height="800" filter="url(#%sgrain)" opacity=".10"/>' % pid
    out += '<g id="%sshade" %s>%s</g>' % (pid, clip, shade)
    out += "</svg>"
    return out


svgs = {}
for k in GARMENTS:
    for v in ("front", "back"):
        s = build(k, v)
        svgs["%s-%s" % (k, v)] = s
        with open("%s/%s-%s.svg" % (OUT, k, v), "w") as f:
            f.write(s)

meta = {}
for k, g in GARMENTS.items():
    meta[k] = {"label": g["label"], "viewBox": [0, 0, 800, 800], "views": {}}
    for v in ("front", "back"):
        meta[k]["views"][v] = {
            "svg": "%s-%s.svg" % (k, v),
            "printAreas": [dict(id=a[0], name=a[1], x=a[2], y=a[3], w=a[4], h=a[5]) for a in AREAS[k][v]],
        }
with open(OUT + "/garments.json", "w") as f:
    json.dump(meta, f, indent=2)
print("built", len(svgs), "svgs")
