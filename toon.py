"""プログラムで描く二足歩行の犬キャラクター・背景・演出エフェクト"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

from video_maker import H, W, get_font

SS = 2  # 2倍で描いて縮小し、輪郭をなめらかにする
OL = (45, 30, 30)  # 輪郭線の色


def ellipse_poly(cx, cy, rx, ry, angle=0, n=56):
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return pts


def darker(c, f=0.75):
    return tuple(int(v * f) for v in c[:3])


class Pen:
    """座標を倍率 k で拡大して描くための ImageDraw ラッパー"""

    def __init__(self, img, k):
        self.d = ImageDraw.Draw(img, "RGBA")
        self.k = k

    def _p(self, pts):
        return [(x * self.k, y * self.k) for x, y in pts]

    def ellipse(self, cx, cy, rx, ry, fill, outline=OL, width=5, angle=0):
        if angle:
            self.poly(ellipse_poly(cx, cy, rx, ry, angle), fill, outline, width)
            return
        k = self.k
        self.d.ellipse([(cx - rx) * k, (cy - ry) * k, (cx + rx) * k, (cy + ry) * k],
                       fill=fill, outline=outline, width=int(width * k) if outline else 0)

    def circle(self, cx, cy, r, fill, outline=OL, width=5):
        self.ellipse(cx, cy, r, r, fill, outline, width)

    def rrect(self, x0, y0, x1, y1, r, fill, outline=OL, width=5):
        k = self.k
        self.d.rounded_rectangle([x0 * k, y0 * k, x1 * k, y1 * k], radius=r * k, fill=fill,
                                 outline=outline, width=int(width * k) if outline else 0)

    def poly(self, pts, fill, outline=OL, width=5):
        self.d.polygon(self._p(pts), fill=fill)
        if outline:
            pp = self._p(pts)
            self.d.line(pp + [pp[0]], fill=outline, width=int(width * self.k), joint="curve")

    def line(self, pts, fill, width=5):
        self.d.line(self._p(pts), fill=fill, width=int(width * self.k), joint="curve")
        r = width / 2
        for x, y in (pts[0], pts[-1]):
            self.ellipse(x, y, r, r, fill, None)

    def limb(self, pts, fill, width):
        """輪郭付きの太い線（腕）"""
        for w, col in ((width + 10, OL), (width, fill)):
            self.d.line(self._p(pts), fill=col, width=int(w * self.k), joint="curve")
            for x, y in pts:
                self.ellipse(x, y, w / 2, w / 2, col, None)

    def text(self, xy, s, size, fill, anchor="mm", stroke=0, stroke_fill=OL):
        self.d.text((xy[0] * self.k, xy[1] * self.k), s, font=get_font(int(size * self.k)), fill=fill,
                    anchor=anchor, stroke_width=int(stroke * self.k), stroke_fill=stroke_fill)


# ────────────────────────────── キャラクター ──────────────────────────────

CHARACTERS = {
    "kotaro": dict(breed="dachshund", fur=(176, 104, 54), ear=(122, 66, 30), muzzle=(206, 150, 100),
                   outfit="blazer", jacket=(36, 58, 104), tie=(206, 40, 60), pants=(60, 64, 80),
                   shoes=(80, 50, 35), glasses=True, body_len=1.18, leg_len=0.5, tail="thin"),
    "leon": dict(breed="poodle", fur=(240, 205, 160), ear=(222, 178, 128), muzzle=(250, 228, 196),
                 outfit="blazer_open", jacket=(36, 58, 104), pants=(60, 64, 80), shoes=(250, 250, 250),
                 sunglasses=True, chain=True, tail="puff"),
    "gou": dict(breed="pitbull", fur=(44, 44, 52), ear=(30, 30, 36), muzzle=(70, 70, 82), blaze=(235, 235, 240),
                outfit="gakuran", jacket=(34, 26, 56), inner=(205, 30, 45), pants=(34, 26, 56),
                shoes=(20, 20, 24), scar=True, size=1.18, head_rx=142, torso_w=220, dark=True, tail="thin"),
    "yanki1": dict(breed="bulldog", fur=(150, 152, 165), ear=(110, 112, 125), muzzle=(190, 192, 202),
                   outfit="gakuran", jacket=(30, 30, 36), inner=(240, 240, 240), pants=(30, 30, 36),
                   shoes=(20, 20, 24), mask=True, head_rx=136, torso_w=210, tail="stub"),
    "yanki2": dict(breed="bulldog", fur=(196, 150, 100), ear=(150, 105, 65), muzzle=(230, 200, 160),
                   outfit="gakuran", jacket=(30, 30, 36), inner=(240, 240, 240), pants=(30, 30, 36),
                   shoes=(20, 20, 24), pompadour=True, head_rx=136, torso_w=210, tail="stub"),
}
for i, bow in enumerate([(230, 40, 70), (40, 140, 230), (250, 190, 30)], 1):
    CHARACTERS[f"pom{i}"] = dict(breed="pom", fur=(244, 158, 66), ear=(214, 120, 40), muzzle=(252, 214, 160),
                                 outfit="cheer", top=(255, 255, 255), accent=(240, 96, 40), shoes=(255, 255, 255),
                                 bow=bow, size=0.82, torso_w=172, leg_len=0.75, tail="fluffy", eye=1.15)

POSES = {
    "stand": {"R": (14, 6), "L": (14, 6)},
    "wave_a": {"R": (150, 168), "L": (14, 6)},
    "wave_b": {"R": (138, 205), "L": (14, 6)},
    "point": {"R": (82, 95), "L": (14, 6)},
    "cheer_a": {"R": (145, 165), "L": (145, 165)},
    "cheer_b": {"R": (112, 122), "L": (112, 122)},
    "banzai": {"R": (165, 178), "L": (165, 178)},
    "fist": {"R": (35, 172), "L": (14, 6)},
    "shy": {"R": (-8, -55), "L": (-8, -55)},
    "notebook": {"R": (20, -120), "L": (20, -120), "prop": "notebook"},
    "flyer": {"R": (78, 100), "L": (14, 6), "prop": "flyer"},
    "trash": {"R": (-6, -40), "L": (16, 8), "prop": "trash"},
    "bump": {"R": (88, 90), "L": (14, 6)},
    "crossed": {},
}

EXPRESSIONS = {
    "normal": dict(eye="oval", brow=0, mouth="w"),
    "happy": dict(eye="happy", brow=-4, mouth="smile"),
    "shy": dict(eye="down", brow=-11, mouth="wavy", blush=True, sweat=True),
    "sad": dict(eye="down", brow=-12, mouth="sad"),
    "shocked": dict(eye="shock", brow=-16, mouth="O", sweat=True),
    "determined": dict(eye="oval", brow=12, mouth="firm"),
    "cool": dict(eye="half", brow=7, mouth="smirk"),
    "soft": dict(eye="half", brow=-6, mouth="smile_small"),
    "wink": dict(eye=("happy", "oval"), brow=0, mouth="smile"),
    "moved": dict(eye="sparkle", brow=-11, mouth="w", tears=True, blush=True),
}


class Dog:
    UA, LA = 84, 76  # 上腕・前腕の長さ

    def __init__(self, cid):
        self.cid = cid
        self.p = CHARACTERS[cid]

    def render(self, expr="normal", pose="stand", mouth=False, blink=False, wag=0, scale=1.0):
        """スプライトと足元の基準点 (x, y) を返す"""
        P = self.p
        k = SS * scale * P.get("size", 1.0)
        hrx, hry = P.get("head_rx", 126), P.get("head_ry", 112)
        tw = P.get("torso_w", 190)
        th = 190 * P.get("body_len", 1.0)
        ll = 130 * P.get("leg_len", 0.8)
        hc = 150 + hry
        top = hc + hry * 0.78
        bottom = top + th
        feet = bottom + ll + 18
        cw, chh = 760, feet + 24
        cx = cw / 2
        img = Image.new("RGBA", (int(cw * k), int(chh * k)), (0, 0, 0, 0))
        pen = Pen(img, k)
        g = dict(cx=cx, hc=hc, hrx=hrx, hry=hry, top=top, bottom=bottom, tw=tw, ll=ll, feet=feet)

        self._tail(pen, g, wag)
        self._legs(pen, g)
        self._torso(pen, g)
        paws, prop_paws = self._arms(pen, g, pose)
        self._head(pen, g, expr, mouth, blink)
        self._props(pen, g, pose, prop_paws)
        for x, y in paws:
            pen.circle(x, y, 24, P["fur"])
        if P["outfit"] == "cheer" and pose != "crossed":
            for x, y in paws:
                self._pompom(pen, x, y)

        final = (int(cw * k / SS), int(chh * k / SS))
        img = img.resize(final, Image.LANCZOS)
        return img, cx * k / SS, feet * k / SS

    # ── 体のパーツ ──

    def _tail(self, pen, g, wag):
        P = self.p
        x, y = g["cx"] + g["tw"] / 2 - 6, g["bottom"] - 40
        kind = P.get("tail", "thin")
        ang = -50 - wag * 18
        if kind == "thin":
            pen.ellipse(x + 30, y - 30, 14, 60, P["fur"], angle=ang)
        elif kind == "puff":
            pen.circle(x + 30, y - 40, 30, P["ear"])
        elif kind == "fluffy":
            pen.ellipse(x + 20, y - 70, 55, 42, P["fur"], angle=ang + 20)
        elif kind == "stub":
            pen.circle(x + 12, y - 10, 16, P["fur"])

    def _legs(self, pen, g):
        P = self.p
        cx, b, ll = g["cx"], g["bottom"], g["ll"]
        leg_col = P.get("pants", P["fur"])
        for s in (-1, 1):
            lx = cx + s * 46
            pen.rrect(lx - 27, b - 20, lx + 27, b + ll + 4, 18, leg_col)
            if P["outfit"] == "cheer":
                pen.rrect(lx - 27, b + ll - 24, lx + 27, b + ll + 4, 10, (255, 255, 255))
            pen.ellipse(lx + s * 6, b + ll + 6, 40, 20, P.get("shoes", P["fur"]))

    def _torso(self, pen, g):
        P = self.p
        cx, t, b, tw = g["cx"], g["top"], g["bottom"], g["tw"]
        x0, x1 = cx - tw / 2, cx + tw / 2
        o = P["outfit"]
        if o == "blazer":
            pen.rrect(x0, t, x1, b, 48, P["jacket"])
            pen.poly([(cx - 40, t + 4), (cx + 40, t + 4), (cx, t + 92)], (250, 250, 250))
            pen.poly([(cx - 12, t + 20), (cx + 12, t + 20), (cx + 16, t + 105), (cx, t + 122), (cx - 16, t + 105)], P["tie"], width=4)
            pen.circle(cx, t + 18, 13, P["tie"], width=4)
            pen.line([(cx - 40, t + 6), (cx - 4, t + 96)], darker(P["jacket"], 0.6), 4)
            pen.line([(cx + 40, t + 6), (cx + 4, t + 96)], darker(P["jacket"], 0.6), 4)
            pen.circle(cx + 52, t + 70, 13, (250, 200, 60), width=3)
            for yy in (t + 130, t + 175):
                if yy < b - 12:
                    pen.circle(cx + 18, yy, 6, (250, 200, 60), width=2)
        elif o == "blazer_open":
            pen.rrect(x0, t, x1, b, 48, P["jacket"])
            pen.rrect(cx - 34, t + 2, cx + 34, b - 2, 10, (250, 250, 250), width=4)
            pen.poly([(cx - 26, t + 2), (cx + 26, t + 2), (cx, t + 54)], P["muzzle"], width=0, outline=None)
            if P.get("chain"):
                for i in range(11):
                    a = math.pi * i / 10
                    pen.circle(cx - 30 * math.cos(a), t + 12 + 58 * math.sin(a), 5, (250, 200, 50), width=2)
        elif o == "gakuran":
            coat_b = b + g["ll"] * 0.55
            pen.rrect(x0, t, x1, coat_b, 44, P["jacket"])
            pen.line([(cx, b - 10), (cx, coat_b - 4)], darker(P["jacket"], 0.5), 4)
            pen.rrect(cx - 46, t - 6, cx + 46, t + 26, 10, P["jacket"])
            pen.poly([(cx - 22, t + 26), (cx + 22, t + 26), (cx, t + 64)], P["inner"], width=3)
            for i in range(4):
                pen.circle(cx, t + 84 + i * 42, 7, (250, 200, 60), width=2)
        elif o == "cheer":
            pen.rrect(x0, t, x1, b, 44, P["top"])
            pen.rrect(x0 + 3, t + 52, x1 - 3, t + 82, 4, P["accent"], outline=None)
            pen.text((cx, t + 125), "W", 64, P["accent"])
            pen.poly([(x0 + 4, b - 26), (x1 - 4, b - 26), (x1 + 24, b + 52), (x0 - 24, b + 52)], P["accent"])
            for i in range(1, 5):
                xx = x0 + tw * i / 5
                pen.line([(xx, b - 20), (xx + (xx - cx) * 0.2, b + 46)], (255, 255, 255), 3)

    def _arms(self, pen, g, pose):
        P = self.p
        cx, t, tw = g["cx"], g["top"], g["tw"]
        sleeve = P["fur"] if P["outfit"] == "cheer" else P.get("jacket", P["fur"])
        if pose == "crossed":
            y = t + 92
            pen.poly([(cx - tw / 2 + 8, y - 34), (cx + tw / 2 - 30, y - 6), (cx + tw / 2 - 30, y + 34), (cx - tw / 2 + 8, y + 8)], sleeve)
            pen.poly([(cx + tw / 2 - 8, y - 34), (cx - tw / 2 + 30, y - 6), (cx - tw / 2 + 30, y + 34), (cx + tw / 2 - 8, y + 8)], sleeve)
            return [(cx + tw / 2 - 30, y + 12), (cx - tw / 2 + 30, y + 12)], {}
        spec = POSES.get(pose, POSES["stand"])
        paws, prop_paws = [], {}
        for side, key in ((1, "R"), (-1, "L")):
            au, al = spec[key]
            sx, sy = cx + side * (tw / 2 - 14), t + 42
            ex = sx + side * math.sin(math.radians(au)) * self.UA
            ey = sy + math.cos(math.radians(au)) * self.UA
            px = ex + side * math.sin(math.radians(al)) * self.LA
            py = ey + math.cos(math.radians(al)) * self.LA
            pen.limb([(sx, sy), (ex, ey), (px, py)], sleeve, 40)
            paws.append((px, py))
            prop_paws[key] = (px, py)
        return paws, prop_paws

    def _props(self, pen, g, pose, pp):
        prop = POSES.get(pose, {}).get("prop")
        if prop == "notebook":
            (rx, ry), (lx, ly) = pp["R"], pp["L"]
            mx, my = (rx + lx) / 2, (ry + ly) / 2 - 46
            pen.rrect(mx - 84, my - 66, mx + 84, my + 62, 8, (250, 250, 245))
            pen.rrect(mx - 84, my - 66, mx - 64, my + 62, 6, (220, 60, 70))
            for i in range(5):
                pen.line([(mx - 50, my - 38 + i * 22), (mx + 66, my - 38 + i * 22)], (120, 160, 220), 3)
        elif prop == "flyer":
            x, y = pp["R"]
            pen.rrect(x - 36, y - 70, x + 36, y + 20, 4, (255, 255, 250), width=4)
            pen.rrect(x - 26, y - 60, x + 26, y - 36, 3, (230, 60, 80), outline=None)
            for i in range(3):
                pen.line([(x - 24, y - 24 + i * 14), (x + 24, y - 24 + i * 14)], (150, 150, 160), 3)
        elif prop == "trash":
            x, y = pp["L"]
            pen.ellipse(x, y + 62, 54, 62, (236, 240, 245))
            pen.line([(x - 12, y + 8), (x + 12, y + 8)], OL, 5)

    def _pompom(self, pen, x, y):
        rnd = random.Random(int(x * 7 + y))
        cols = [(255, 214, 40), (255, 150, 40), (255, 240, 120)]
        pen.circle(x, y, 46, cols[0], width=4)
        for i in range(10):
            a = rnd.uniform(0, 2 * math.pi)
            r = rnd.uniform(10, 32)
            pen.circle(x + math.cos(a) * r, y + math.sin(a) * r, rnd.uniform(14, 20), cols[i % 3], outline=None)

    # ── 頭 ──

    def _head(self, pen, g, expr, mouth, blink):
        P = self.p
        cx, hc, hrx, hry = g["cx"], g["hc"], g["hrx"], g["hry"]
        breed = P["breed"]
        top = hc - hry

        # 頭の後ろ側のパーツ
        if breed == "pom":
            for i in range(16):
                a = 2 * math.pi * i / 16
                pen.circle(cx + math.cos(a) * (hrx + 6), hc + 10 + math.sin(a) * (hry + 4), 38, P["fur"])
            for s in (-1, 1):
                pen.poly([(cx + s * 40, top + 22), (cx + s * 92, top - 52), (cx + s * 108, top + 34)], P["ear"])
                pen.poly([(cx + s * 58, top + 18), (cx + s * 88, top - 26), (cx + s * 96, top + 24)], (250, 180, 170), outline=None)
        elif breed in ("pitbull", "bulldog"):
            # 半分折れた小さなローズイヤー
            for s in (-1, 1):
                pen.poly([(cx + s * (hrx - 70), top + 26), (cx + s * (hrx - 30), top - 6),
                          (cx + s * (hrx + 22), top + 30), (cx + s * (hrx + 4), top + 58)], P["ear"])
        elif breed == "poodle":
            for dx, dy, r in ((-58, 8, 40), (-20, -14, 44), (22, -14, 44), (60, 8, 40), (0, 14, 40)):
                pen.circle(cx + dx, top + dy, r, P["ear"])

        pen.ellipse(cx, hc, hrx, hry, P["fur"])

        if breed == "pitbull":
            pen.ellipse(cx, hc - 22, 9, 22, P["blaze"], outline=None)
        if P.get("pompadour"):
            pen.ellipse(cx, top - 6, 84, 46, (34, 30, 30))
            pen.line([(cx - 40, top - 22), (cx + 30, top - 34)], (110, 110, 120), 6)

        mz_rx = {"pitbull": 80, "bulldog": 84, "dachshund": 62}.get(breed, 58)
        mz_ry = {"dachshund": 50, "bulldog": 52}.get(breed, 46)
        pen.ellipse(cx, hc + 54, mz_rx, mz_ry, P["muzzle"], width=4)
        if breed == "bulldog":
            for s in (-1, 1):
                pen.ellipse(cx + s * 44, hc + 72, 44, 34, P["muzzle"], width=4)

        e = EXPRESSIONS.get(expr, EXPRESSIONS["normal"])
        self._face(pen, g, e, mouth, blink)

        # 顔の前側のパーツ
        if breed == "dachshund":
            for s in (-1, 1):
                pen.ellipse(cx + s * (hrx - 2), hc + 30, 44, 100, P["ear"], angle=-s * 12)
        elif breed == "poodle":
            for s in (-1, 1):
                for dy in (10, 50, 90):
                    pen.circle(cx + s * (hrx + 4), hc + dy, 36, P["ear"])
        if P.get("bow"):
            bx, by = cx + 62, top + 20
            pen.poly([(bx, by), (bx - 44, by - 28), (bx - 44, by + 28)], P["bow"], width=4)
            pen.poly([(bx, by), (bx + 44, by - 28), (bx + 44, by + 28)], P["bow"], width=4)
            pen.circle(bx, by, 13, P["bow"], width=4)
        if P.get("sunglasses"):
            for s in (-1, 1):
                pen.rrect(cx + s * 40 - 30, top + 26, cx + s * 40 + 30, top + 58, 12, (30, 30, 42))
                pen.line([(cx + s * 40 - 16, top + 34), (cx + s * 40 - 4, top + 34)], (150, 160, 190), 4)
            pen.line([(cx - 10, top + 36), (cx + 10, top + 36)], (30, 30, 42), 6)

    def _face(self, pen, g, e, mouth, blink):
        P = self.p
        cx, hc, hrx = g["cx"], g["hc"], g["hrx"]
        es = P.get("eye", 1.0)
        dark = P.get("dark", False)
        ey = hc - 4
        eye = e["eye"]

        for s in (-1, 1):
            ex = cx + s * 48
            kind = eye[0 if s < 0 else 1] if isinstance(eye, tuple) else eye
            if blink and kind in ("oval", "down", "half", "sparkle", "shock"):
                kind = "closed"
            if dark and kind not in ("happy", "closed"):
                pen.ellipse(ex, ey, 22 * es, 25 * es, (245, 245, 245), width=3)
            self._eye(pen, ex, ey, kind, es)

            # 眉
            b = e["brow"]
            inner_dy = b
            by = ey - 38 * es + (6 if b > 5 else 0)
            col = (235, 235, 235) if dark else darker(P["fur"], 0.45)
            pen.line([(ex - s * 18, by + inner_dy), (ex + s * 18, by - inner_dy * 0.4)], col, 7)

        if P.get("glasses"):
            for s in (-1, 1):
                pen.circle(cx + s * 48, ey, 32, None, outline=(70, 45, 30), width=6)
            pen.line([(cx - 16, ey - 4), (cx + 16, ey - 4)], (70, 45, 30), 6)
        if P.get("scar"):
            pen.line([(cx - 74, ey - 54), (cx - 44, ey - 22)], (170, 170, 185), 6)
            pen.line([(cx - 70, ey - 32), (cx - 58, ey - 42)], (170, 170, 185), 5)

        if e.get("blush"):
            for s in (-1, 1):
                pen.ellipse(cx + s * 82, hc + 36, 24, 13, (255, 110, 130, 150), outline=None)
        if e.get("tears"):
            for s in (-1, 1):
                pen.ellipse(cx + s * 52, ey + 34, 8, 14, (120, 200, 255, 230), outline=None)
                pen.ellipse(cx + s * 56, ey + 60, 6, 10, (120, 200, 255, 200), outline=None)

        # 鼻と口
        ny = hc + 30
        pen.ellipse(cx, ny, 20, 13, (30, 22, 24), width=3)
        pen.ellipse(cx - 6, ny - 4, 6, 3, (200, 200, 210), outline=None)
        pen.line([(cx, ny + 12), (cx, ny + 18)], OL, 4)
        m = e["mouth"]
        my = ny + 18
        if mouth:
            if m in ("smile", "smile_small", "w"):
                pen.d.pieslice([(cx - 30) * pen.k, (my - 8) * pen.k, (cx + 30) * pen.k, (my + 44) * pen.k], 0, 180,
                               fill=(130, 30, 45), outline=OL, width=int(4 * pen.k))
                pen.ellipse(cx, my + 28, 13, 7, (240, 120, 140), outline=None)
            elif m == "O":
                pen.ellipse(cx, my + 18, 18, 24, (110, 25, 40), width=4)
            else:
                pen.ellipse(cx, my + 14, 17, 15, (130, 30, 45), width=4)
                pen.ellipse(cx, my + 21, 10, 6, (240, 120, 140), outline=None)
        else:
            if m in ("w", "smile"):
                if m == "smile":
                    pen.d.pieslice([(cx - 26) * pen.k, (my - 6) * pen.k, (cx + 26) * pen.k, (my + 30) * pen.k], 0, 180,
                                   fill=(130, 30, 45), outline=OL, width=int(4 * pen.k))
                    pen.ellipse(cx, my + 18, 11, 6, (240, 120, 140), outline=None)
                else:
                    pen.line([(cx - 22, my - 2), (cx - 11, my + 8), (cx, my)], OL, 5)
                    pen.line([(cx, my), (cx + 11, my + 8), (cx + 22, my - 2)], OL, 5)
            elif m == "smile_small":
                pen.line([(cx - 18, my + 2), (cx, my + 10), (cx + 18, my + 2)], OL, 5)
            elif m == "sad":
                pen.line([(cx - 16, my + 12), (cx, my + 4), (cx + 16, my + 12)], OL, 5)
            elif m == "wavy":
                pen.line([(cx - 20, my + 6), (cx - 10, my + 1), (cx, my + 7), (cx + 10, my + 1), (cx + 20, my + 6)], OL, 4)
            elif m == "O":
                pen.ellipse(cx, my + 12, 11, 14, (110, 25, 40), width=4)
            elif m == "firm":
                pen.line([(cx - 16, my + 6), (cx + 16, my + 6)], OL, 5)
            elif m == "smirk":
                pen.line([(cx - 16, my + 8), (cx + 20, my + 1)], OL, 5)

        if P.get("mask"):
            pen.rrect(cx - 70, hc + 18, cx + 70, hc + 100, 22, (245, 245, 248), width=4)
            for i in range(3):
                pen.line([(cx - 50, hc + 40 + i * 18), (cx + 50, hc + 40 + i * 18)], (205, 205, 215), 3)

        if e.get("sweat"):
            sx, sy = cx + hrx - 6, hc - 62
            pen.poly([(sx, sy - 26), (sx + 14, sy + 4), (sx - 14, sy + 4)], (140, 210, 255), width=3)
            pen.circle(sx, sy + 6, 14, (140, 210, 255), width=3)

    def _eye(self, pen, x, y, kind, es):
        if kind == "happy":
            pen.line([(x - 17, y + 6), (x, y - 9), (x + 17, y + 6)], OL, 7)
        elif kind == "closed":
            pen.line([(x - 17, y), (x, y + 6), (x + 17, y)], OL, 7)
        elif kind == "shock":
            pen.circle(x, y, 22 * es, (255, 255, 255), width=4)
            pen.circle(x, y, 6 * es, (20, 20, 20), outline=None)
        elif kind == "half":
            pen.ellipse(x, y + 4, 14 * es, 15 * es, (25, 20, 22), outline=None)
            pen.line([(x - 20, y - 6), (x + 20, y - 6)], OL, 8)
            pen.circle(x + 4, y + 2, 4, (255, 255, 255), outline=None)
        elif kind == "down":
            pen.ellipse(x, y + 6, 13 * es, 16 * es, (25, 20, 22), outline=None)
            pen.circle(x + 4, y + 1, 4, (255, 255, 255), outline=None)
        elif kind == "sparkle":
            pen.ellipse(x, y, 17 * es, 22 * es, (25, 20, 22), outline=None)
            pen.circle(x + 5, y - 8, 7, (255, 255, 255), outline=None)
            pen.circle(x - 6, y + 8, 4, (255, 255, 255), outline=None)
        else:
            pen.ellipse(x, y, 14 * es, 19 * es, (25, 20, 22), outline=None)
            pen.circle(x + 5, y - 7, 5 * es, (255, 255, 255), outline=None)


# ────────────────────────────── 背景 ──────────────────────────────

FLOOR_Y = {"school_gate": 1400, "hallway": 1410, "sunset": 1400, "stage": 1330, "results": 1420}


def _vgrad(img, y0, y1, c0, c1):
    d = ImageDraw.Draw(img)
    for y in range(int(y0), int(y1)):
        f = (y - y0) / max(1, y1 - y0)
        d.line([(0, y), (img.width, y)], fill=tuple(int(a + (b - a) * f) for a, b in zip(c0, c1)))


def _vertical_text(pen, x, y, s, size, fill):
    for i, ch in enumerate(s):
        pen.text((x, y + i * size * 1.08), ch, size, fill)


def _cloud(pen, x, y, s=1.0):
    for dx, dy, r in ((-60, 10, 46), (-10, -20, 60), (50, 0, 50), (90, 18, 36)):
        pen.circle(x + dx * s, y + dy * s, r * s, (255, 255, 255), outline=None)


def _tree(pen, x, y, s=1.0, col=(90, 160, 90), trunk=(120, 80, 50)):
    pen.rrect(x - 22 * s, y - 160 * s, x + 22 * s, y, 8, trunk, outline=None)
    for dx, dy, r in ((-70, -200, 90), (60, -210, 95), (0, -290, 110), (-20, -170, 80), (40, -150, 70)):
        pen.circle(x + dx * s, y + dy * s, r * s, col, outline=None)


def _school_building(pen, sign=True):
    pen.rrect(60, 520, 1020, 1160, 6, (246, 236, 214), outline=(170, 150, 128), width=4)
    pen.rrect(40, 498, 1040, 540, 6, (200, 92, 72), outline=None)
    for r in range(4):
        for c in range(6):
            x, y = 110 + c * 150, 580 + r * 140
            if 420 < x < 640 and r < 2:
                continue
            pen.rrect(x, y, x + 100, y + 90, 4, (160, 210, 240), outline=(255, 255, 255), width=5)
    pen.rrect(430, 320, 650, 540, 6, (246, 236, 214), outline=(170, 150, 128), width=4)
    pen.poly([(400, 330), (540, 230), (680, 330)], (200, 92, 72), outline=None)
    pen.circle(540, 430, 62, (255, 255, 255), outline=(120, 100, 90), width=5)
    pen.line([(540, 430), (540, 388)], (60, 50, 50), 6)
    pen.line([(540, 430), (572, 446)], (60, 50, 50), 6)
    if sign:
        pen.rrect(870, 560, 950, 1080, 4, (255, 255, 255), outline=(200, 60, 60), width=4)
        _vertical_text(pen, 910, 610, "生徒会長選挙", 64, (200, 40, 50))


def bg_school_gate(pen):
    _school_building(pen)
    pen.poly([(420, 1160), (660, 1160), (1080, 1920), (0, 1920)], (226, 214, 196), outline=None)
    pen.poly([(0, 1160), (420, 1160), (0, 1920)], (132, 194, 112), outline=None)
    pen.poly([(1080, 1160), (660, 1160), (1080, 1920)], (132, 194, 112), outline=None)
    for x in range(-20, 1100, 70):
        if 380 < x < 700:
            continue
        pen.circle(x, 1160, 52, (96, 160, 90), outline=None)
    for x in (130, 950):
        pen.rrect(x - 50, 940, x + 50, 1420, 6, (176, 176, 184), outline=(120, 120, 130), width=4)
        pen.rrect(x - 62, 920, x + 62, 960, 6, (150, 150, 160), outline=None)
    pen.rrect(102, 990, 158, 1300, 4, (255, 255, 255), outline=(80, 80, 80), width=3)
    _vertical_text(pen, 130, 1024, "ワンダフル高校", 38, (40, 40, 40))
    _tree(pen, -30, 1180, 1.2)
    _tree(pen, 1110, 1180, 1.2)


def bg_hallway(pen):
    pen.rrect(0, 1250, 1080, 1920, 0, (204, 162, 112), outline=None)
    y, step = 1260, 30
    while y < 1920:
        pen.line([(0, y), (1080, y)], (176, 134, 90), 3)
        y += step
        step *= 1.18
    for c in range(4):
        x = 30 + c * 270
        pen.rrect(x, 150, x + 220, 520, 4, (186, 222, 245), outline=(255, 255, 255), width=8)
        pen.line([(x + 110, 150), (x + 110, 520)], (255, 255, 255), 6)
    pen.rrect(0, 1230, 1080, 1260, 0, (150, 120, 90), outline=None)
    for c in range(4):
        x = c * 136
        pen.rrect(x + 4, 660, x + 132, 1232, 6, (112, 150, 192), outline=(70, 100, 140), width=4)
        for i in range(4):
            pen.line([(x + 40, 700 + i * 18), (x + 96, 700 + i * 18)], (70, 100, 140), 4)
        pen.rrect(x + 100, 930, x + 112, 990, 3, (220, 220, 230), outline=None)
    pen.rrect(600, 640, 1030, 1130, 10, (196, 150, 100), outline=(130, 90, 60), width=10)
    pen.rrect(640, 676, 990, 1096, 2, (255, 255, 252), outline=(200, 200, 200), width=2)
    pen.text((815, 760), "生徒会長選挙", 62, (210, 40, 55))
    pen.text((815, 850), "立候補者募集！", 46, (40, 40, 60))
    for dx, dy, r in ((0, 0, 34), (-40, -44, 15), (-14, -58, 15), (14, -58, 15), (40, -44, 15)):
        pen.circle(815 + dx, 1000 + dy, r, (210, 40, 55), outline=None)
    for x in (660, 970):
        pen.circle(x, 690, 9, (240, 70, 70), width=2)


def bg_sunset(img, pen):
    _vgrad(img, 0, 1080 * SS, (255, 140, 90), (255, 214, 150))
    pen.circle(760, 880, 130, (255, 236, 170), outline=None)
    sil = (120, 70, 96)
    pen.rrect(0, 760, 700, 1090, 0, sil, outline=None)
    pen.rrect(250, 620, 420, 780, 0, sil, outline=None)
    pen.poly([(230, 630), (335, 540), (440, 630)], sil, outline=None)
    pen.rrect(0, 1080, 1080, 1920, 0, (196, 132, 92), outline=None)
    _vgrad(img, 1080 * SS, 1920 * SS, (205, 140, 98), (150, 96, 76))
    pen.line([(0, 1300), (1080, 1240)], (235, 190, 150), 6)
    pen.line([(860, 1000), (860, 1110), (1080, 1110)], (250, 240, 230), 8)
    pen.line([(860, 1000), (1080, 1000)], (250, 240, 230), 8)
    _tree(pen, 1000, 1090, 0.9, col=(110, 62, 92), trunk=(90, 50, 70))
    _tree(pen, 60, 1090, 1.1, col=(110, 62, 92), trunk=(90, 50, 70))


def bg_stage(img, pen):
    _vgrad(img, 0, 1920 * SS, (52, 32, 44), (90, 60, 50))
    pen.rrect(80, 150, 1000, 1340, 0, (168, 34, 54), outline=None)
    for x in range(100, 1000, 60):
        pen.line([(x, 260), (x, 1330)], (130, 22, 44), 14)
    for s in (-1, 1):
        x0 = 540 + s * 460
        pen.poly([(x0, 120), (x0 - s * 170, 120), (x0 - s * 90, 700), (x0 - s * 140, 1340), (x0, 1340)], (140, 20, 42), outline=None)
    for i in range(10):
        x = 60 + i * 100
        pen.ellipse(x + 50, 200, 56, 70, (128, 18, 40), outline=None)
    pen.rrect(0, 100, 1080, 200, 0, (128, 18, 40), outline=None)
    pen.rrect(130, 320, 950, 470, 6, (255, 255, 250), outline=(200, 170, 80), width=6)
    pen.text((540, 368), "生徒会長選挙", 58, (200, 30, 50))
    pen.text((540, 432), "立会演説会", 44, (40, 40, 50))
    pen.rrect(0, 1330, 1080, 1440, 0, (206, 154, 98), outline=None)
    pen.rrect(0, 1440, 1080, 1520, 0, (150, 100, 62), outline=None)
    pen.rrect(0, 1520, 1080, 1920, 0, (222, 182, 124), outline=None)
    for x in range(0, 1080, 120):
        pen.line([(x, 1520), (x, 1920)], (200, 160, 104), 3)


def fg_stage(pen):
    """手前に重ねるもの（演台と観客）"""
    pen.rrect(330, 1140, 510, 1340, 8, (140, 90, 56), outline=(80, 50, 30), width=5)
    pen.rrect(316, 1124, 524, 1150, 6, (160, 106, 66), outline=(80, 50, 30), width=5)
    pen.circle(420, 1240, 34, (250, 200, 60), width=4)
    pen.line([(460, 1126), (470, 1070), (452, 1036)], (60, 60, 66), 6)
    pen.ellipse(448, 1028, 13, 17, (40, 40, 46), width=3)
    rnd = random.Random(4)
    cols = [(110, 80, 60), (70, 60, 60), (150, 120, 90), (90, 90, 100), (60, 50, 50), (170, 140, 110)]
    for row, (y, r) in enumerate(((1760, 72), (1880, 84))):
        x = -20 + row * 60
        while x < 1120:
            c = rnd.choice(cols)
            kind = rnd.choice(["floppy", "pointy", "round"])
            if kind == "pointy":
                for s in (-1, 1):
                    pen.poly([(x + s * 20, y - r + 20), (x + s * 56, y - r - 46), (x + s * 66, y - r + 30)], darker(c, 0.85), outline=None)
            pen.ellipse(x, y, r, r * 0.95, c, outline=None)
            if kind == "floppy":
                for s in (-1, 1):
                    pen.ellipse(x + s * (r - 6), y + 10, 26, 56, darker(c, 0.8), outline=None, angle=-s * 12)
            x += r * 2 + rnd.randint(-10, 20)


def bg_results(img, pen):
    _vgrad(img, 0, 1160 * SS, (130, 196, 255), (206, 236, 255))
    _cloud(pen, 200, 160, 1.0)
    _cloud(pen, 860, 240, 0.8)
    bg_school_gate(pen)
    pen.rrect(150, 300, 930, 900, 10, (170, 120, 76), outline=(110, 74, 44), width=8)
    pen.rrect(180, 330, 900, 870, 4, (255, 255, 252), outline=None)
    pen.text((540, 400), "生徒会長選挙 結果", 50, (60, 60, 70))
    pen.text((540, 640), "？", 200, (200, 200, 210))
    cols = [(240, 70, 80), (255, 200, 40), (60, 160, 240), (90, 200, 120)]
    pen.line([(0, 150), (540, 210), (1080, 150)], (90, 80, 70), 4)
    for i in range(14):
        x = 20 + i * 78
        y = 150 + 60 * (1 - abs(x - 540) / 540)
        pen.poly([(x - 30, y), (x + 30, y), (x, y + 60)], cols[i % 4], outline=None)


def results_paper(pen):
    """結果発表で背景の掲示板に重ねる当選の貼り紙"""
    pen.rrect(180, 450, 900, 870, 4, (255, 255, 252), outline=None)
    pen.circle(300, 600, 80, None, outline=(220, 30, 40), width=10)
    pen.text((300, 600), "当選", 58, (220, 30, 40))
    pen.text((620, 600), "コタロウ", 104, (30, 30, 40))
    pen.text((540, 790), "おめでとう！", 52, (220, 30, 40))
    for i in range(8):
        a = 2 * math.pi * i / 8
        pen.circle(210 + math.cos(a) * 34, 360 + math.sin(a) * 34, 26, (230, 40, 60), outline=None)
    pen.circle(210, 360, 24, (255, 210, 60), outline=None)


def make_backgrounds():
    """背景・前景（演台など）・結果発表で重ねる貼り紙の画像を作る"""
    bgs, fgs, reveals = {}, {}, {}
    for name in ("school_gate", "hallway", "sunset", "stage", "results"):
        img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 255))
        pen = Pen(img, SS)
        if name == "school_gate":
            _vgrad(img, 0, 1160 * SS, (130, 196, 255), (206, 236, 255))
            _cloud(pen, 220, 200)
            _cloud(pen, 850, 300, 0.8)
            bg_school_gate(pen)
        elif name == "hallway":
            img.paste((240, 234, 218), (0, 0, W * SS, 1250 * SS))
            bg_hallway(pen)
        elif name == "sunset":
            bg_sunset(img, pen)
        elif name == "stage":
            bg_stage(img, pen)
            fg = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
            fg_stage(Pen(fg, SS))
            fgs[name] = fg.resize((W, H), Image.LANCZOS)
        elif name == "results":
            bg_results(img, pen)
            paper = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
            results_paper(Pen(paper, SS))
            reveals[name] = paper.resize((W, H), Image.LANCZOS)
        bgs[name] = img.resize((W, H), Image.LANCZOS)
    return bgs, fgs, reveals


# ────────────────────────────── エフェクト ──────────────────────────────

def make_focus_lines(seed, color=(20, 20, 30, 150)):
    """マンガの集中線"""
    rnd = random.Random(seed)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = W / 2, H * 0.45
    for _ in range(140):
        a = rnd.uniform(0, 2 * math.pi)
        r0 = rnd.uniform(380, 520)
        r1 = 1500
        w = rnd.uniform(0.006, 0.02)
        pts = [(cx + math.cos(a) * r0, cy + math.sin(a) * r0),
               (cx + math.cos(a - w) * r1, cy + math.sin(a - w) * r1),
               (cx + math.cos(a + w) * r1, cy + math.sin(a + w) * r1)]
        d.polygon(pts, fill=color)
    return img


def make_spotlight(x):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon([(x - 60, 0), (x + 60, 0), (x + 260, 1360), (x - 260, 1360)], fill=(255, 245, 200, 70))
    d.ellipse([x - 260, 1300, x + 260, 1380], fill=(255, 245, 200, 90))
    return img.filter(ImageFilter.GaussianBlur(14))


class Confetti:
    def __init__(self, n=140, seed=1):
        rnd = random.Random(seed)
        cols = [(240, 70, 80), (255, 200, 40), (60, 160, 240), (90, 200, 120), (250, 130, 200), (255, 255, 255)]
        self.p = [(rnd.uniform(0, W), rnd.uniform(-H, 0), rnd.uniform(220, 420), rnd.uniform(0, 6.28),
                   rnd.uniform(2, 6), rnd.choice(cols), rnd.uniform(10, 18)) for _ in range(n)]

    def draw(self, frame, t):
        d = ImageDraw.Draw(frame, "RGBA")
        for x0, y0, vy, ph, spin, col, s in self.p:
            y = y0 + vy * t
            if y < -40 or y > H + 40:
                continue
            x = x0 + math.sin(t * 2 + ph) * 40
            a = t * spin + ph
            ca, sa = math.cos(a), math.sin(a)
            hw, hh = s, s * 0.55 * abs(math.cos(t * spin * 0.7 + ph)) + 2
            pts = [(x + dx * ca - dy * sa, y + dx * sa + dy * ca) for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
            d.polygon(pts, fill=col)
