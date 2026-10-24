"""犬キャラのショートアニメを台本JSONから自動生成する

使い方:
  python story_maker.py --story stories/wan_high_ep1.json

出力: デスクトップの「YouTube動画」/<slug>/ に（Mac 以外は output/<slug>/） video.mp4・thumbnail.png・youtube.txt
"""
import argparse
import json
import math
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import toon
import video_maker as vm
from video_maker import FPS, SR, H, W

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 話者ごとの声と名札
#   voicevox : VOICEVOX の「キャラ名/スタイル」（--list-voices で一覧表示）
#   vv_speed / vv_pitch : VOICEVOX の話速（1.0が標準）・高さ（-0.15〜0.15）
#   voice / pitch / rate : edge-tts の声・高さ・速さ
#   half_tone / speed : pyopenjtalk の高さ（半音）・速さ
# 台本JSONの "voices" で、話ごとに上書きできる
VOICES = {
    "narrator": dict(name="", voicevox="冥鳴ひまり/ノーマル",
                     voice="ja-JP-NanamiNeural", pitch="+0Hz", rate="+5%", half_tone=0.0, speed=1.15),
    "kotaro": dict(name="コタロウ", color=(176, 104, 54), voicevox="白上虎太郎/びくびく",
                   voice="ja-JP-KeitaNeural", pitch="+14Hz", rate="+0%", half_tone=-1.0, speed=1.1),
    "leon": dict(name="レオン", color=(219, 39, 119), voicevox="玄野武宏/喜び", vv_speed=1.15,
                 voice="ja-JP-KeitaNeural", pitch="+4Hz", rate="+18%", half_tone=-2.5, speed=1.3),
    "gou": dict(name="ゴウ", color=(190, 30, 45), voicevox="青山龍星/ノーマル", vv_speed=0.95,
                voice="ja-JP-KeitaNeural", pitch="-20Hz", rate="-8%", half_tone=-7.0, speed=0.95),
    "poms": dict(name="チア部", color=(234, 88, 12), voicevox="ずんだもん/あまあま", vv_speed=1.15,
                 voice="ja-JP-NanamiNeural", pitch="+30Hz", rate="+15%", half_tone=3.0, speed=1.3,
                 members=["pom1", "pom2", "pom3"], chorus=True),
    "yanki": dict(name="不良たち", color=(71, 85, 105), voicevox="剣崎雌雄/ノーマル", vv_speed=1.1,
                  voice="ja-JP-KeitaNeural", pitch="-6Hz", rate="+12%", half_tone=-5.0, speed=1.25,
                  members=["yanki1", "yanki2"], chorus=True),
}

GAP = 0.22  # セリフ同士の間
VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")


# ────────────────────────────── 音声 ──────────────────────────────

class VoicevoxClient:
    """ローカルで起動した VOICEVOX（アプリ or エンジン）に HTTP で話しかける"""

    def __init__(self, url=VOICEVOX_URL):
        import urllib.request

        self.url = url.rstrip("/")
        # localhost 宛てなのでプロキシを通さない
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._speakers = None
        self._ids = {}

    def _req(self, path, data=None, timeout=60, json_body=None):
        import urllib.request

        headers = {}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.url + path, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
        with self.opener.open(req, timeout=timeout) as r:
            return r.read()

    def available(self):
        try:
            self._req("/version", timeout=1.5)
            return True
        except Exception:
            return False

    def speakers(self):
        if self._speakers is None:
            self._speakers = json.loads(self._req("/speakers"))
        return self._speakers

    def style_id(self, spec):
        """「キャラ名/スタイル」をスタイルIDに変換する（数字ならそのまま）"""
        if isinstance(spec, int) or str(spec).isdigit():
            return int(spec)
        if spec in self._ids:
            return self._ids[spec]
        name, _, style = str(spec).partition("/")
        for sp in self.speakers():
            if sp["name"] == name:
                styles = sp["styles"]
                hit = next((st for st in styles if st["name"] == style), None)
                if hit is None:
                    hit = styles[0]
                    if style:
                        print(f"  └ ⚠️ {name} にスタイル「{style}」がないので「{hit['name']}」を使います")
                self._ids[spec] = hit["id"]
                return hit["id"]
        names = "、".join(sp["name"] for sp in self.speakers())
        raise RuntimeError(f"VOICEVOX に「{name}」が見つかりません。使えるキャラ: {names}")

    def tts(self, text, v):
        from urllib.parse import quote

        sid = self.style_id(v["voicevox"])
        query = json.loads(self._req(f"/audio_query?text={quote(text)}&speaker={sid}", data=b""))
        query["speedScale"] = v.get("vv_speed", 1.0)
        query["pitchScale"] = v.get("vv_pitch", 0.0)
        query["intonationScale"] = v.get("vv_intonation", 1.0)
        return self._req(f"/synthesis?speaker={sid}", json_body=query)


class Voice:
    def __init__(self, engine="auto"):
        self.engine = engine
        self.vv = VoicevoxClient()
        self.credits = []  # VOICEVOX の利用規約で必要なクレジット表記

    def _voicevox(self, text, v):
        import tempfile

        wav = self.vv.tts(text, v)
        name = str(v["voicevox"]).partition("/")[0]
        if not str(name).isdigit() and name not in self.credits:
            self.credits.append(name)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "v.wav")
            with open(path, "wb") as f:
                f.write(wav)
            return vm.decode_audio(path)

    def _edge(self, text, v):
        import asyncio
        import tempfile

        import edge_tts

        async def run(path):
            proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
            await edge_tts.Communicate(text, v["voice"], rate=v["rate"], pitch=v["pitch"], proxy=proxy).save(path)

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "v.mp3")
            asyncio.run(run(path))
            return vm.decode_audio(path)

    def _jtalk(self, text, v):
        import pyopenjtalk

        x, sr = pyopenjtalk.tts(text, speed=v["speed"], half_tone=v["half_tone"])
        x = (x / 32768.0).astype(np.float32)
        if sr != SR:
            x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x).astype(np.float32)
        return x

    def speak(self, who, text):
        v = VOICES[who]
        if self.engine == "auto" and self.vv.available():
            self.engine = "voicevox"
        if self.engine == "voicevox":
            x = self._voicevox(text, v)
        if self.engine in ("auto", "edge"):
            try:
                x = self._edge(text, v)
                self.engine = "edge"
            except Exception as e:
                if self.engine == "edge":
                    raise
                print(f"  └ ⚠️ edge-tts が使えないため pyopenjtalk に切り替えます ({type(e).__name__})")
                self.engine = "openjtalk"
        if self.engine == "openjtalk":
            x = self._jtalk(text, v)
        x = vm.trim_silence(x)
        x = x / (np.max(np.abs(x)) or 1.0) * 0.8
        if v.get("chorus"):
            # 少しずらして重ね、大勢で声をそろえているように聞かせる
            d1, d2 = int(0.035 * SR), int(0.07 * SR)
            out = np.zeros(len(x) + d2, dtype=np.float32)
            out[: len(x)] += x * 0.6
            out[d1: d1 + len(x)] += x * 0.45
            out[d2: d2 + len(x)] += x * 0.35
            x = out / (np.max(np.abs(out)) or 1.0) * 0.8
        return x


def speech_text(line):
    """読み上げ用の文字列（say があれば優先、記号は除く）"""
    s = line.get("say", line["text"])
    return re.sub(r"[☆★♪〜~「」『』]", "", s)


def mouth_track(x):
    """1フレームごとの口の開閉（音量で判定）"""
    hop = SR // FPS
    n = len(x) // hop + 1
    rms = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2) + 1e-12) for i in range(n)])
    thr = 0.18 * (np.max(rms) or 1)
    open_ = rms > thr
    # 開きっぱなしにならないよう、長く続く区間は 2 フレームおきに閉じる
    for i in range(2, n, 4):
        if open_[i] and open_[i - 1]:
            open_[i] = False
    return open_


# ────────────────────────────── 音楽・効果音 ──────────────────────────────

def synth_music(duration, chords, bpm, bright=1.0):
    n = int(duration * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    beat = 60 / bpm
    bar = beat * 4
    for ci in range(int(duration / bar) + 1):
        chord = chords[ci % len(chords)]
        s0 = int(ci * bar * SR)
        if s0 >= n:
            break
        s1 = min(n, int((ci + 1) * bar * SR) + int(0.3 * SR))
        tt = t[s0:s1] - ci * bar
        env = np.minimum(1, tt / 0.3) * np.exp(-np.maximum(0, tt - bar) / 0.2)
        pad = sum(np.sin(2 * np.pi * vm.note_freq(m) * tt) for m in chord)
        out[s0:s1] += (0.035 * pad * env).astype(np.float32)
        for b in range(4):
            b0 = s0 + int(b * beat * SR)
            b1 = min(n, b0 + int(0.35 * SR))
            if b0 >= n:
                break
            tb = t[b0:b1] - t[b0]
            out[b0:b1] += (0.13 * np.sin(2 * np.pi * vm.note_freq(chord[0] - 12) * tb) * np.exp(-tb / 0.18)).astype(np.float32)
        melody = [chord[2] + 12, chord[1] + 12, chord[3] + 12, chord[2] + 12, chord[0] + 24, chord[3] + 12, chord[1] + 12, chord[2] + 12]
        for i, m in enumerate(melody):
            a0 = s0 + int(i * beat / 2 * SR)
            a1 = min(n, a0 + int(0.4 * SR))
            if a0 >= n:
                break
            ta = t[a0:a1] - t[a0]
            f = vm.note_freq(m)
            tone = np.sin(2 * np.pi * f * ta) + 0.3 * bright * np.sin(2 * np.pi * 2 * f * ta)
            out[a0:a1] += (0.045 * tone * np.exp(-ta / 0.13)).astype(np.float32)
    return out


def synth_tense(duration):
    n = int(duration * SR)
    t = np.arange(n) / SR
    drone = 0.12 * np.sin(2 * np.pi * 55 * t) + 0.06 * np.sin(2 * np.pi * 82.4 * t)
    pulse = 0.5 + 0.5 * np.sin(2 * np.pi * 1.6 * t)
    high = 0.025 * np.sin(2 * np.pi * 880 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 7 * t))
    return ((drone * (0.6 + 0.4 * pulse)) + high).astype(np.float32)


def sfx_boom():
    t = np.arange(int(0.7 * SR)) / SR
    f = 110 * np.exp(-t * 3) + 40
    rng = np.random.default_rng(1)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.25)
    hit = rng.standard_normal(len(t)) * np.exp(-t / 0.03)
    return (0.6 * body + 0.25 * hit).astype(np.float32)


def sfx_applause(dur=3.0):
    rng = np.random.default_rng(2)
    n = int(dur * SR)
    out = np.zeros(n, dtype=np.float32)
    click_len = int(0.012 * SR)
    env = np.exp(-np.arange(click_len) / SR / 0.003)
    for _ in range(int(dur * 260)):
        s = rng.integers(0, n - click_len)
        out[s:s + click_len] += (rng.standard_normal(click_len) * env * rng.uniform(0.1, 0.35)).astype(np.float32)
    fade = np.minimum(1, np.arange(n) / (0.3 * SR)) * np.minimum(1, (n - np.arange(n)) / (1.0 * SR))
    return out * fade * 0.6


def sfx_sparkle():
    t = np.arange(int(0.6 * SR)) / SR
    out = np.zeros_like(t)
    for i, m in enumerate([84, 88, 91, 96]):
        s = int(i * 0.06 * SR)
        tt = t[: len(t) - s]
        out[s:] += np.sin(2 * np.pi * vm.note_freq(m) * tt) * np.exp(-tt / 0.15)
    return (0.12 * out).astype(np.float32)


SFX = {"boom": sfx_boom, "applause": sfx_applause, "sparkle": sfx_sparkle,
       "pop": vm.sfx_pop, "whoosh": vm.sfx_whoosh, "click": vm.sfx_click}


# ────────────────────────────── 台本の組み立て ──────────────────────────────

class Shot:
    def __init__(self, spec, voice):
        self.spec = spec
        self.bg = spec["bg"]
        floor = toon.FLOOR_Y.get(self.bg, 1400)
        self.cast = {}
        for c in spec.get("cast", []):
            st = dict(pose="stand", expr="normal", anim="idle", scale=1.0, flip=False, y=floor)
            st.update(c)
            self.cast[c["id"]] = st
        t = spec.get("pre", 0.35)
        self.lines = []
        for ln in spec.get("lines", []):
            ln = dict(ln)
            ln["voice"] = voice.speak(ln["who"], speech_text(ln))
            ln["t0"] = t
            ln["dur"] = len(ln["voice"]) / SR
            ln["mouth"] = mouth_track(ln["voice"])
            self.lines.append(ln)
            t += ln["dur"] + ln.get("pause", GAP)
        self.duration = max(spec.get("hold", 0), t + spec.get("post", 0.3))
        self.start = 0.0
        self.confetti_from = next((ln["t0"] for ln in self.lines if "confetti" in ln.get("fx", [])),
                                  0.0 if "confetti" in spec.get("fx", []) else None)

    def state_at(self, t):
        cast = {k: dict(v) for k, v in self.cast.items()}
        for ln in self.lines:
            if ln["t0"] <= t:
                for cid, ch in ln.get("set", {}).items():
                    cast.setdefault(cid, {}).update(ch)
        return cast

    def active_line(self, t):
        for ln in self.lines:
            if ln["t0"] <= t < ln["t0"] + ln["dur"] + ln.get("pause", GAP):
                return ln
        return None


# ────────────────────────────── 外部素材（Gemini などで作った絵・動画） ──────────────────────────────

VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def probe_video(path):
    """動画の長さ（秒）と縦横サイズを ffmpeg の出力から読む"""
    r = subprocess.run([vm.ffmpeg_exe(), "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 8.0
    m = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", r.stderr)
    size = (int(m.group(1)), int(m.group(2))) if m else (W, H)
    return dur, size


class Assets:
    """素材フォルダの shot01.png / shot07.mp4 / shot11_2.png（2つ目のセリフから切り替え）などを場面に割り当てる"""

    def __init__(self, folder):
        self.folder = folder
        self.files = {}  # (場面番号, 何番目のセリフから) -> パス（動画を優先）
        if folder and os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                m = re.fullmatch(r"shot(\d+)(?:_(\d+))?(\.\w+)", name, re.I)
                ext = m.group(3).lower() if m else ""
                if not m or ext not in VIDEO_EXTS + IMAGE_EXTS:
                    continue
                key = (int(m.group(1)), int(m.group(2) or 1))
                if key not in self.files or ext in VIDEO_EXTS:
                    self.files[key] = os.path.join(folder, name)

    def thumbnail(self):
        for ext in IMAGE_EXTS:
            path = os.path.join(self.folder or "", "thumbnail" + ext)
            if self.folder and os.path.exists(path):
                return path
        return None

    def entries(self, shot):
        """[(開始時刻, 終了時刻, パス), ...]"""
        keys = sorted(k for k in self.files if k[0] == getattr(shot, "num", None))
        out = []
        for i, k in enumerate(keys):
            start = 0.0 if k[1] <= 1 or k[1] > len(shot.lines) else shot.lines[k[1] - 1]["t0"]
            out.append([start, shot.duration, self.files[k]])
        out.sort()
        for i in range(len(out) - 1):
            out[i][1] = out[i + 1][0]
        if out:
            out[0][0] = 0.0
        return out


def fit_filter(size):
    """縦長ならそのまま切り抜き、横長ならぼかした背景の上に重ねて 1080x1920 にする"""
    w, h = size
    if w / h < 0.7:
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=30:3,eq=brightness=-0.08[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")


def fit_image(img):
    img = img.convert("RGB")
    w, h = img.size
    cover = max(W / w, H / h)
    bg = img.resize((int(w * cover) + 1, int(h * cover) + 1), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    if w / h < 0.7:
        return bg.convert("RGBA")
    bg = bg.filter(ImageFilter.GaussianBlur(30)).point(lambda v: int(v * 0.9))
    fg = img.resize((W, int(h * W / w)), Image.LANCZOS)
    bg.paste(fg, (0, (H - fg.height) // 2))
    return bg.convert("RGBA")


class ClipReader:
    """動画素材を 1080x1920・30fps で1フレームずつ読む（短い動画は少しゆっくり再生し、最後のコマで止める）"""

    def __init__(self, path, span):
        dur, size = probe_video(path)
        slow = min(1.6, max(1.0, span / max(dur, 0.1)))
        vf = f"{fit_filter(size)},setpts={slow:.3f}*PTS,fps={FPS}"
        self.proc = subprocess.Popen([vm.ffmpeg_exe(), "-v", "error", "-i", path, "-vf", vf, "-an",
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.n = 0
        self.last = Image.new("RGBA", (W, H), (0, 0, 0, 255))

    def frame(self, idx):
        while self.n <= idx and self.proc:
            buf = self.proc.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                self.close()
                break
            self.last = Image.frombuffer("RGB", (W, H), buf).convert("RGBA")
            self.n += 1
        return self.last

    def close(self):
        if self.proc:
            self.proc.stdout.close()
            self.proc.wait()
            self.proc = None


# ────────────────────────────── 描画 ──────────────────────────────

class Renderer:
    def __init__(self, assets=None):
        self.assets = assets or Assets(None)
        self.images = {}
        self.clip = None  # (パス, 開始時刻, ClipReader)
        self.bgs, self.fgs, self.reveals = toon.make_backgrounds()
        self.dogs = {cid: toon.Dog(cid) for cid in toon.CHARACTERS}
        self.cache = {}
        self.focus = [toon.make_focus_lines(i) for i in range(3)]
        self.spots = {}
        self.confetti = toon.Confetti()
        self.text_cache = {}

    def sprite(self, cid, expr, pose, mouth, blink, wag, scale, flip):
        key = (cid, expr, pose, mouth, blink, wag, round(scale, 2), flip)
        if key not in self.cache:
            img, ax, ay = self.dogs[cid].render(expr, pose, mouth, blink, wag, scale)
            if flip:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
                ax = img.width - ax
            self.cache[key] = (img, ax, ay)
            if len(self.cache) > 600:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[key]

    def text(self, key, fn):
        if key not in self.text_cache:
            self.text_cache[key] = fn()
        return self.text_cache[key]

    def draw_cast(self, frame, shot, t, speaking):
        cast = shot.state_at(t)
        for i, (cid, st) in enumerate(sorted(cast.items(), key=lambda kv: kv[1].get("y", 0))):
            if st.get("hidden"):
                continue
            phase = (sum(map(ord, cid)) % 100) / 100 * 6.28
            pose, anim = st["pose"], st.get("anim", "idle")
            dx, dy = 0.0, math.sin(t * 2 * math.pi * 0.7 + phase) * 4
            if anim == "cheer":
                pose = "cheer_a" if int((t + phase) / 0.2) % 2 == 0 else "cheer_b"
                dy = -abs(math.sin((t + phase) * math.pi * 2.5)) * 36
            elif anim == "jump":
                dy = -abs(math.sin((t + phase) * math.pi * 2.2)) * 44
            elif anim == "tremble":
                dx = math.sin(t * 90 + phase) * 3
            elif anim == "walk":
                dy = -abs(math.sin(t * math.pi * 3.2)) * 14
            elif anim == "wave":
                pose = "wave_a" if int(t / 0.22) % 2 == 0 else "wave_b"
            enter = st.get("enter")
            if enter and t < 0.6:
                p = vm.ease_out_cubic(t / 0.6)
                dx += {"left": -700, "right": 700}.get(enter, 0) * (1 - p)
                if enter == "bottom":
                    dy += 500 * (1 - p)
            mouth = False
            if speaking and cid in speaking[0]:
                ln = speaking[1]
                fi = int((t - ln["t0"]) * FPS)
                mouth = 0 <= fi < len(ln["mouth"]) and bool(ln["mouth"][fi])
            blink = ((t + phase * 0.7) % 3.1) < 0.12
            wag = 0
            if st["expr"] in ("happy", "wink", "moved") or anim in ("cheer", "jump"):
                wag = (-1, 0, 1, 0)[int(t * 10) % 4]
            img, ax, ay = self.sprite(cid, st["expr"], pose, mouth, blink, wag, st.get("scale", 1.0), st.get("flip", False))
            vm.compose(frame, img, st["x"] - ax + dx, st["y"] - ay + dy)

    def asset_frame(self, shot, t):
        """この場面・時刻に使う素材のフレーム（素材がなければ None）と、静止画かどうか"""
        for start, end, path in self.assets.entries(shot):
            if start <= t < end or (t >= end and end >= shot.duration):
                if path.lower().endswith(IMAGE_EXTS):
                    if path not in self.images:
                        self.images[path] = fit_image(Image.open(path))
                    return self.images[path].copy(), True
                key = (path, getattr(shot, "num", None), start)
                if not self.clip or self.clip[0] != key:
                    if self.clip:
                        self.clip[1].close()
                    self.clip = (key, ClipReader(path, end - start))
                return self.clip[1].frame(int((t - start) * FPS)).copy(), False
        return None, False

    def frame(self, shot, t, t_global):
        spec = shot.spec
        frame, still = self.asset_frame(shot, t)
        if frame is not None:
            return self.overlay(shot, t, frame, spec.get("zoom", [1.0, 1.10] if still else [1.0, 1.0]))
        frame = self.bgs[shot.bg].copy()
        if "spot" in spec:
            x = spec["spot"]
            if x not in self.spots:
                self.spots[x] = toon.make_spotlight(x)
            frame.alpha_composite(self.spots[x])

        if shot.bg in self.reveals:
            t_rev = 0.0 if spec.get("revealed") else next(
                (l2["t0"] for l2 in shot.lines if "reveal" in l2.get("fx", [])), None)
            if t_rev is not None and t >= t_rev:
                frame.alpha_composite(self.reveals[shot.bg])

        ln = shot.active_line(t)
        speaking = None
        if ln and ln["t0"] <= t < ln["t0"] + ln["dur"]:
            v = VOICES[ln["who"]]
            speaking = (v.get("members", [ln["who"]]), ln)
        self.draw_cast(frame, shot, t, speaking)
        if shot.bg in self.fgs and spec.get("fg", True):
            frame.alpha_composite(self.fgs[shot.bg])
        return self.overlay(shot, t, frame, spec.get("zoom", [1.0, 1.04]))

    def overlay(self, shot, t, frame, zoom):
        """演出・カメラ・字幕など、絵の上に重ねるもの"""
        spec = shot.spec
        ln = shot.active_line(t)
        fx = set(spec.get("fx", []))
        impact = None
        shake = 0.0
        flash = 0.0
        for l2 in shot.lines:
            lt = t - l2["t0"]
            for f in l2.get("fx", []):
                if f == "focus" and 0 <= lt < l2["dur"] + 0.3:
                    fx.add("focus")
                elif f == "shake" and 0 <= lt < 0.6:
                    shake = max(shake, 22 * (1 - lt / 0.6))
                elif f == "flash" and 0 <= lt < 0.35:
                    flash = max(flash, 1 - lt / 0.35)
                elif f.startswith("impact:") and 0 <= lt < l2["dur"] + 0.4:
                    impact = (f.split(":", 1)[1], lt)
        if "focus" in fx:
            frame.alpha_composite(self.focus[int(t * 12) % 3])
        if shot.confetti_from is not None and t >= shot.confetti_from:
            self.confetti.draw(frame, t - shot.confetti_from)
        if impact:
            txt, lt = impact
            spr = self.text(("impact", txt), lambda: vm.text_sprite(txt, 150, (255, 230, 60), max_w=1000, stroke=12, stroke_fill=(180, 20, 40)))
            p = min(1.0, lt / 0.25)
            sc = 0.4 + 0.6 * vm.ease_out_back(p)
            s2 = spr.resize((max(1, int(spr.width * sc)), max(1, int(spr.height * sc))), Image.BILINEAR)
            jit = math.sin(lt * 60) * 4
            vm.compose(frame, s2, W / 2 - s2.width / 2 + jit, 560 - s2.height / 2)

        # カメラ（ゆっくりズーム＋揺れ）
        z0, z1 = zoom
        z = z0 + (z1 - z0) * (t / shot.duration)
        fxp, fyp = spec.get("focus_xy", [W / 2, H * 0.55])
        if shake:
            z = max(z, 1.06)
            fxp += math.sin(t * 80) * shake
            fyp += math.cos(t * 67) * shake
        if z > 1.001:
            cw, ch = W / z, H / z
            x0 = min(max(0, fxp - cw / 2), W - cw)
            y0 = min(max(0, fyp - ch / 2), H - ch)
            frame = frame.transform((W, H), Image.EXTENT, (x0, y0, x0 + cw, y0 + ch), Image.BILINEAR)

        # 文字（カメラの影響を受けない）
        if spec.get("caption"):
            cap = self.text(("cap", spec["caption"]), lambda: self.caption_sprite(spec["caption"]))
            a = min(1.0, t / 0.3) * min(1.0, (shot.duration - t) / 0.2)
            vm.compose(frame, vm.with_alpha(cap, max(0, a)), W / 2 - cap.width / 2, 200)
        if ln:
            sub = self.text(("sub", ln["who"], ln["text"]), lambda: self.subtitle_sprite(ln))
            vm.compose(frame, sub, W / 2 - sub.width / 2, 1440)
        if spec.get("endcard"):
            ec = self.text(("end", spec["endcard"]), lambda: self.caption_sprite(spec["endcard"], (30, 30, 40), (255, 214, 60)))
            a = min(1.0, max(0.0, (t - shot.duration + 2.2) / 0.4))
            if a > 0:
                vm.compose(frame, vm.with_alpha(ec, a), W / 2 - ec.width / 2, 620)
        if flash:
            frame.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(200 * flash))))
        return frame

    def caption_sprite(self, text, fg=(255, 255, 255), bg=(225, 29, 72)):
        txt = vm.text_sprite(text, 70, fg, max_w=900, stroke=0)
        img = Image.new("RGBA", (txt.width + 90, txt.height + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=24, fill=bg, outline=(255, 255, 255), width=6)
        img.alpha_composite(txt, (45, 20))
        return img

    @staticmethod
    def break_subtitle(text, size=50, max_w=900):
        """1行に収まらない字幕は、句読点の位置で改行する（単語の途中で折れないように）"""
        font = vm.get_font(size)
        if "\n" in text or font.getlength(text) <= max_w:
            return text
        segs = re.findall(r"[^、。！？!?…]+[、。！？!?…☆]*|[、。！？!?…☆]+", text)
        lines = [""]
        for seg in segs:
            if lines[-1] and font.getlength(lines[-1] + seg) > max_w:
                lines.append(seg)
            else:
                lines[-1] += seg
        return "\n".join(lines)

    def subtitle_sprite(self, ln):
        v = VOICES[ln["who"]]
        narr = ln["who"] == "narrator"
        txt = vm.text_sprite(self.break_subtitle(ln["text"]), 50, (255, 255, 255), max_w=900, line_gap=1.3)
        box_h = max(150, txt.height + 60)
        img = Image.new("RGBA", (1000, box_h + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 40, 999, box_h + 39], radius=26,
                            fill=(15, 23, 42, 205) if not narr else (30, 20, 50, 190),
                            outline=v.get("color", (255, 255, 255)) if not narr else (200, 190, 255), width=5)
        img.alpha_composite(txt, ((1000 - txt.width) // 2, 40 + (box_h - txt.height) // 2))
        if v["name"]:
            tag = vm.pill_sprite(v["name"], 36, (255, 255, 255), v["color"], pad_x=28, pad_y=10)
            img.alpha_composite(tag, (30, 0))
        return img


# ────────────────────────────── 全体の流れ ──────────────────────────────

def build_audio(shots, total):
    n = int(total * SR) + SR
    voice = np.zeros(n, dtype=np.float32)
    sfx = np.zeros(n, dtype=np.float32)
    for i, sh in enumerate(shots):
        if i:
            vm.add_at(sfx, SFX["whoosh"](), sh.start)
        for ln in sh.lines:
            vm.add_at(voice, ln["voice"], sh.start + ln["t0"])
            for f in ln.get("fx", []):
                if f.startswith("impact:") or f == "shake":
                    vm.add_at(sfx, SFX["boom"]() * 0.8, sh.start + ln["t0"])
                if f == "flash":
                    vm.add_at(sfx, SFX["sparkle"](), sh.start + ln["t0"])
                if f == "confetti":
                    vm.add_at(sfx, SFX["pop"]() * 2, sh.start + ln["t0"])
            for s in ln.get("sfx", []):
                vm.add_at(sfx, SFX[s](), sh.start + ln["t0"])
        for s in sh.spec.get("sfx", []):
            vm.add_at(sfx, SFX[s](), sh.start)

    tracks = {
        "normal": synth_music(n / SR, [[60, 64, 67, 72], [57, 60, 64, 69], [53, 57, 60, 65], [55, 59, 62, 67]], 116),
        "happy": synth_music(n / SR, [[60, 64, 67, 72], [55, 59, 62, 67], [57, 60, 64, 69], [53, 57, 60, 65]], 128, bright=1.6),
        "tense": synth_tense(n / SR),
    }
    gains = {k: np.zeros(n, dtype=np.float32) for k in tracks}
    ramp = int(0.4 * SR)
    for sh in shots:
        mood = sh.spec.get("bgm", "normal")
        if mood in gains:
            s0, s1 = int(sh.start * SR), int((sh.start + sh.duration) * SR)
            gains[mood][s0:s1] = 1.0
    for k in gains:
        gains[k] = np.convolve(gains[k], np.ones(ramp) / ramp, mode="same").astype(np.float32)
    music = sum(tracks[k][:n] * gains[k] for k in tracks)
    level = np.convolve(np.abs(voice), np.ones(4800) / 4800, mode="same")
    music *= 1.0 - 0.5 * np.clip(level / 0.05, 0, 1)
    fade = np.minimum(1, (total - np.arange(n) / SR) / 1.5).clip(0, 1)
    mix = (voice + sfx + music * 0.8 * fade)[: int(total * SR)]
    return mix * (0.95 / (np.max(np.abs(mix)) or 1.0))


def render_video(shots, total, renderer, audio_path, out_path):
    cmd = [vm.ffmpeg_exe(), "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path,
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR),
           "-shortest", "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n_frames = int(math.ceil(total * FPS))
    si = 0
    for f in range(n_frames):
        t = f / FPS
        while si < len(shots) - 1 and t >= shots[si].start + shots[si].duration:
            si += 1
        sh = shots[si]
        proc.stdin.write(renderer.frame(sh, t - sh.start, t).convert("RGB").tobytes())
        if f % (FPS * 10) == 0:
            print(f"  └ {f}/{n_frames} フレーム")
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg のエンコードに失敗しました。")


def render_thumbnail(story, renderer, voice, path):
    spec = story["thumbnail"]
    shot = Shot(dict(spec, lines=[], hold=10), voice)
    thumb = renderer.assets.thumbnail()
    if thumb:
        frame = fit_image(Image.open(thumb))
    else:
        frame = renderer.frame(shot, 1.0, 1.0).convert("RGBA")
    title = vm.text_sprite(spec["title"], 110, (255, 255, 255), max_w=1000, stroke=12, stroke_fill=(20, 20, 40), accent=(255, 214, 60))
    vm.compose(frame, title, W / 2 - title.width / 2, 1420)
    frame.convert("RGB").save(path)


def main():
    ap = argparse.ArgumentParser(description="犬キャラのショートアニメを生成")
    ap.add_argument("--story", help="台本JSONのパス")
    ap.add_argument("--out", default=vm.default_output_dir(), help="出力先フォルダ（Mac の既定はデスクトップの「YouTube動画」）")
    ap.add_argument("--tts", default="auto", choices=["auto", "voicevox", "edge", "openjtalk"],
                    help="auto は VOICEVOX が起動していれば VOICEVOX、なければ edge-tts → pyopenjtalk の順に使う")
    ap.add_argument("--list-voices", action="store_true", help="VOICEVOX で使える声の一覧を表示")
    ap.add_argument("--assets", help="Gemini などで作った絵・動画のフォルダ（shot01.png, shot07.mp4 ...）。"
                                     "省略時は出力先の「素材」フォルダがあれば使う")
    args = ap.parse_args()

    if args.list_voices:
        vv = VoicevoxClient()
        if not vv.available():
            raise SystemExit(f"VOICEVOX に接続できません（{VOICEVOX_URL}）。アプリを起動してください。")
        for sp in vv.speakers():
            print(f"{sp['name']}: " + "、".join(f"{st['name']}" for st in sp["styles"]))
        return
    if not args.story:
        ap.error("--story を指定してください")
    if args.tts == "voicevox" and not VoicevoxClient().available():
        raise SystemExit(f"VOICEVOX に接続できません（{VOICEVOX_URL}）。アプリを起動してください。")

    with open(args.story, "r", encoding="utf-8") as f:
        story = json.load(f)
    for who, ov in story.get("voices", {}).items():
        VOICES.setdefault(who, dict(name=who, color=(100, 116, 139), voice="ja-JP-NanamiNeural", pitch="+0Hz",
                                    rate="+0%", half_tone=0.0, speed=1.1, voicevox="ずんだもん/ノーマル"))
        VOICES[who].update(ov)
    out_dir = os.path.join(args.out, story["slug"])
    os.makedirs(out_dir, exist_ok=True)

    voice = Voice(args.tts)
    print("🎙️ セリフを音声合成中...")
    shots = [Shot(s, voice) for s in story["shots"]]
    print(f"  └ ✅ 音声エンジン: {voice.engine}")
    t = 0.0
    for i, sh in enumerate(shots, 1):
        sh.num = i
        sh.start = t
        t += sh.duration
    total = t

    print(f"🎵 音声をミックス中...（全長 {total:.1f} 秒）")
    audio_path = os.path.join(out_dir, "audio.wav")
    vm.write_wav(audio_path, build_audio(shots, total))

    print("🎨 背景を描画中...")
    assets = Assets(args.assets or os.path.join(out_dir, "素材"))
    if assets.files:
        print(f"🖼️ 素材を使います: {assets.folder}（{len(assets.files)} 個）")
    renderer = Renderer(assets)
    print("🎬 アニメをレンダリング中...")
    video_path = os.path.join(out_dir, "video.mp4")
    render_video(shots, total, renderer, audio_path, video_path)
    os.remove(audio_path)

    if "thumbnail" in story:
        render_thumbnail(story, renderer, voice, os.path.join(out_dir, "thumbnail.png"))
    meta_path = os.path.join(out_dir, "youtube.txt")
    vm.write_youtube_meta(story, meta_path)
    if voice.credits:
        with open(meta_path, "a", encoding="utf-8") as f:
            f.write("\n【音声】説明文に必ず入れてください\n" + "\n".join(f"VOICEVOX:{n}" for n in voice.credits) + "\n")
    print(f"\n🎉 完成: {video_path}")
    vm.show_in_finder(video_path)


if __name__ == "__main__":
    main()
