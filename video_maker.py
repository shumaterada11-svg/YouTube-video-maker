"""ショート動画（YouTube Shorts / X 向け 1080x1920）自動生成スクリプト

使い方:
  # 台本JSONから動画を作る
  python video_maker.py --script video_scripts/chrome_shortcuts.json

  # テーマだけ渡して Claude に台本を書かせてから動画を作る（ANTHROPIC_API_KEY が必要）
  python video_maker.py --topic "Chromeが爆速になる神ショートカット5選"

出力: output/<名前>/ に video.mp4・thumbnail.png・youtube.txt・script.json
"""
import argparse
import asyncio
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

W, H = 1080, 1920
FPS = 30
SR = 48000

BG_TOP = (15, 23, 42)
BG_BOTTOM = (30, 41, 59)
ACCENT = (56, 189, 248)
RED = (225, 29, 72)
WHITE = (255, 255, 255)
SLATE_100 = (241, 245, 249)
SLATE_300 = (203, 213, 225)
SLATE_400 = (148, 163, 184)
SLATE_700 = (51, 65, 85)
SLATE_900 = (15, 23, 42)

# ナレーションの前後に置く余白（秒）
LEAD = 0.3
TAIL = 0.35

# キーキャップに添える記号（フォントに字形があるものだけ）
KEY_SYMBOLS = {"cmd": "⌘", "command": "⌘", "shift": "⇧"}

# 行頭に置かない文字
NO_LINE_START = set("、。，．・：；？！ー」』）】〉》ぁぃぅぇぉっゃゅょァィゥェォッャュョ")


# ────────────────────────────── 設定・フォント ──────────────────────────────

def load_anthropic_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    path = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("ANTHROPIC_API_KEY", "")
    raise RuntimeError("ANTHROPIC_API_KEY が見つかりません。")


_font_cache = {}

def get_font(size, bold=True):
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    weight = "Bold" if bold else "Regular"
    candidates = [
        f"/usr/share/fonts/opentype/noto/NotoSansCJK-{weight}.ttc",
        f"/usr/share/fonts/truetype/noto/NotoSansCJK-{weight}.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc" if bold else "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                _font_cache[key] = font
                return font
            except Exception:
                continue
    raise RuntimeError("日本語フォントが見つかりません（fonts-noto-cjk をインストールしてください）。")


# ────────────────────────────── 台本生成（Claude） ──────────────────────────────

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "slug": {"type": "string"},
        "youtube_title": {"type": "string"},
        "youtube_description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "hook": {
            "type": "object",
            "properties": {
                "tag": {"type": "string"},
                "title": {"type": "string"},
                "sub": {"type": "string"},
                "narration": {"type": "string"},
            },
            "required": ["tag", "title", "sub", "narration"],
            "additionalProperties": False,
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "keys": {"type": "array", "items": {"type": "string"}},
                    "alt": {"type": "string"},
                    "desc": {"type": "string"},
                    "narration": {"type": "string"},
                },
                "required": ["title", "keys", "alt", "desc", "narration"],
                "additionalProperties": False,
            },
        },
        "outro": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "sub": {"type": "string"},
                "cta": {"type": "string"},
                "narration": {"type": "string"},
            },
            "required": ["title", "sub", "cta", "narration"],
            "additionalProperties": False,
        },
    },
    "required": ["slug", "youtube_title", "youtube_description", "tags", "hook", "items", "outro"],
    "additionalProperties": False,
}


def generate_script(topic, anthropic_key):
    import anthropic

    client = anthropic.Anthropic(api_key=anthropic_key)
    prompt = f"""
あなたはYouTubeショートで「神ショートカット」「即効時短術」を発信して再生数を伸ばしている動画クリエイターです。
次のテーマで、30〜45秒の縦型ショート動画の台本を作ってください。

【テーマ】: {topic}

【構成】
- hook: 冒頭2〜4秒で視聴者を止める。tag は「完全保存版」などの短い帯（8字以内）。title は画面に大きく出す見出しで、
  強調したい語を **語** で囲む（例: Chromeが**爆速**になる\\n神ショートカット5選）。改行は \\n で入れ、1行9字以内・最大3行。
  sub は補足の一言（16字以内）。
- items: ショートカットを4〜5個。title は操作名（12字以内）、keys は押すキーを1つずつ並べた配列
  （例: ["Cmd", "Shift", "T"]。Mac表記を基本にする）、alt は別OSでの操作（例: "Windows: Ctrl + Shift + T"、共通なら "Mac / Windows 共通"）、
  desc は効果の説明（28字以内）。実在し、現行バージョンで正しく動くショートカットだけを使うこと。
- outro: title（10字以内）、sub（18字以内）、cta（例: 保存して明日から使おう）。

【ナレーション（narration）のルール】
- 音声合成で読み上げるため、英字のキー名はカタカナで書く（Cmd→コマンド、Shift→シフト、T→ティー、Ctrl→コントロール、L→エル）。
- 「OK」などの英字もカタカナにする。1シーン30〜60字、話し言葉で歯切れよく。
- 各 item は「1つ目。」「2つ目。」のように番号から始める。

【その他】
- slug は英小文字とハイフンだけのファイル名（例: chrome-shortcuts-5）。
- youtube_title は「#shorts」を含め60字以内。youtube_description は2〜3行。tags は5〜8個。
"""
    response = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": SCRIPT_SCHEMA},
        },
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude が台本の生成を断りました。テーマを変えてください。")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


# ────────────────────────────── 音声合成 ──────────────────────────────

def decode_audio(path):
    """任意の音声ファイルを 48kHz モノラル float32 に変換する"""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


def tts_edge(text, voice, rate):
    import edge_tts

    async def run(path):
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        communicate = edge_tts.Communicate(text, voice, rate=rate, proxy=proxy)
        await communicate.save(path)

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "voice.mp3")
        asyncio.run(run(path))
        return decode_audio(path)


def tts_openjtalk(text, speed):
    import pyopenjtalk

    x, sr = pyopenjtalk.tts(text, speed=speed)
    x = (x / 32768.0).astype(np.float32)
    if sr != SR:
        idx = np.arange(0, len(x), sr / SR)
        x = np.interp(idx, np.arange(len(x)), x).astype(np.float32)
    return x


class Narrator:
    """edge-tts（高品質・要ネット）を優先し、使えなければ pyopenjtalk（オフライン）に切り替える"""

    def __init__(self, engine="auto", voice="ja-JP-NanamiNeural", rate="+15%", speed=1.3):
        self.engine = engine
        self.voice = voice
        self.rate = rate
        self.speed = speed

    def speak(self, text):
        if self.engine in ("auto", "edge"):
            try:
                audio = tts_edge(text, self.voice, self.rate)
                self.engine = "edge"
                return trim_silence(audio)
            except Exception as e:
                if self.engine == "edge":
                    raise
                print(f"  └ ⚠️ edge-tts が使えないため pyopenjtalk に切り替えます ({type(e).__name__})")
                self.engine = "openjtalk"
        return trim_silence(tts_openjtalk(text, self.speed))


def trim_silence(x, threshold=0.01):
    idx = np.where(np.abs(x) > threshold)[0]
    if len(idx) == 0:
        return x
    start = max(0, idx[0] - int(0.03 * SR))
    end = min(len(x), idx[-1] + int(0.08 * SR))
    return x[start:end]


# ────────────────────────────── BGM・効果音 ──────────────────────────────

def note_freq(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def synth_bgm(duration):
    """著作権フリーの自作BGM（ローファイ風のパッド＋アルペジオ＋ベース）"""
    n = int(duration * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    bpm = 96
    beat = 60 / bpm
    bar = beat * 4
    # Fmaj7 → G6 → Em7 → Am7
    chords = [[53, 57, 60, 64], [55, 59, 62, 64], [52, 55, 59, 62], [57, 60, 64, 67]]

    for ci in range(int(duration / bar) + 1):
        chord = chords[ci % len(chords)]
        s0 = int(ci * bar * SR)
        s1 = min(n, int((ci + 1) * bar * SR) + int(0.4 * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - ci * bar
        env = np.minimum(1, tt / 0.6) * np.exp(-np.maximum(0, tt - bar) / 0.25)
        pad = np.zeros_like(tt)
        for m in chord:
            f = note_freq(m)
            pad += np.sin(2 * np.pi * f * tt) + 0.5 * np.sin(2 * np.pi * f * 1.003 * tt)
        out[s0:s1] += (0.05 * pad * env).astype(np.float32)
        # ベース
        f_root = note_freq(chord[0] - 12)
        out[s0:s1] += (0.12 * np.sin(2 * np.pi * f_root * tt) * env).astype(np.float32)
        # 8分音符のアルペジオ
        arp = chord + [chord[1] + 12, chord[2] + 12, chord[3], chord[2]]
        for k, m in enumerate(arp):
            a0 = s0 + int(k * beat / 2 * SR)
            a1 = min(n, a0 + int(0.5 * SR))
            if a0 >= n:
                break
            ta = t[a0:a1] - t[a0]
            f = note_freq(m + 12)
            pluck = np.sin(2 * np.pi * f * ta) * np.exp(-ta / 0.12)
            out[a0:a1] += (0.05 * pluck).astype(np.float32)

    # 4拍目ごとの柔らかいハイハット
    rng = np.random.default_rng(7)
    for b in range(int(duration / (beat / 2))):
        h0 = int(b * beat / 2 * SR)
        h1 = min(n, h0 + int(0.04 * SR))
        if h0 >= n:
            break
        noise = rng.standard_normal(h1 - h0).astype(np.float32)
        noise = np.diff(noise, prepend=0)
        env = np.exp(-np.arange(h1 - h0) / SR / 0.012)
        out[h0:h1] += (0.012 if b % 2 else 0.006) * noise * env

    fade_in = np.minimum(1, t / 0.8)
    fade_out = np.minimum(1, (duration - t) / 1.5)
    return (out * fade_in * np.clip(fade_out, 0, 1)).astype(np.float32)


def sfx_pop():
    t = np.arange(int(0.07 * SR)) / SR
    f = 1100 - 4000 * t
    return (0.18 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.02)).astype(np.float32)


def sfx_click():
    rng = np.random.default_rng(3)
    t = np.arange(int(0.06 * SR)) / SR
    click = 0.25 * rng.standard_normal(len(t)) * np.exp(-t / 0.004)
    body = 0.3 * np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.02)
    return (click + body).astype(np.float32)


def sfx_whoosh():
    rng = np.random.default_rng(5)
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    # 簡易ローパス（移動平均）でこもった風切り音にする
    noise = np.convolve(noise, np.ones(24) / 24, mode="same")
    env = np.sin(np.pi * t / t[-1]) ** 2
    return (0.12 * noise * env).astype(np.float32)


SFX = {"pop": sfx_pop, "click": sfx_click, "whoosh": sfx_whoosh}


def add_at(buf, clip, t):
    s = int(t * SR)
    if s >= len(buf):
        return
    e = min(len(buf), s + len(clip))
    buf[s:e] += clip[: e - s]


def mix_audio(scenes, total, use_bgm, bgm_path=None):
    n = int(total * SR) + SR
    voice = np.zeros(n, dtype=np.float32)
    sfx = np.zeros(n, dtype=np.float32)
    sfx_cache = {}
    for sc in scenes:
        add_at(voice, sc.voice, sc.start + LEAD)
        add_at(sfx, SFX["whoosh"](), sc.start)
        for t, kind in sc.sfx:
            if kind not in sfx_cache:
                sfx_cache[kind] = SFX[kind]()
            add_at(sfx, sfx_cache[kind], sc.start + t)

    peak = np.max(np.abs(voice)) or 1.0
    voice *= 0.8 / peak
    mix = voice + sfx

    if use_bgm:
        if bgm_path:
            bgm = decode_audio(bgm_path)
            reps = int(math.ceil(n / len(bgm)))
            bgm = np.tile(bgm, reps)[:n] * 0.25
        else:
            bgm = synth_bgm(n / SR)
        # ナレーション中は BGM を下げる（簡易ダッキング）
        level = np.convolve(np.abs(voice), np.ones(4800) / 4800, mode="same")
        duck = 1.0 - 0.45 * np.clip(level / 0.05, 0, 1)
        mix += bgm[:n] * duck

    mix = mix[: int(total * SR)]
    mix *= 0.95 / (np.max(np.abs(mix)) or 1.0)
    return mix


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ────────────────────────────── 描画ユーティリティ ──────────────────────────────

def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def ease_out_back(p):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def parse_marked(text, base, accent):
    """「**強調**」を色付き文字列 [(文字, 色), ...] に変換する"""
    out = []
    on = False
    for part in re.split(r"(\*\*)", text):
        if part == "**":
            on = not on
            continue
        out.extend((ch, accent if on else base) for ch in part)
    return out


def wrap_chars(chars, font, max_w):
    """[(文字, 色)] を max_w に収まる行に分割する。英単語は途中で折らない"""
    tokens = []
    buf = []
    for ch, col in chars:
        if ch == "\n":
            if buf:
                tokens.append(buf)
                buf = []
            tokens.append("\n")
        elif re.match(r"[A-Za-z0-9+\-_.%/]", ch):
            buf.append((ch, col))
        else:
            if buf:
                tokens.append(buf)
                buf = []
            tokens.append([(ch, col)])
    if buf:
        tokens.append(buf)

    lines, cur = [], []
    for tok in tokens:
        if tok == "\n":
            lines.append(cur)
            cur = []
            continue
        cand = cur + tok
        text = "".join(c for c, _ in cand)
        if font.getlength(text) <= max_w or not cur or tok[0][0] in NO_LINE_START:
            cur = cand
        else:
            lines.append(cur)
            cur = [] if tok[0][0] == " " else list(tok)
    lines.append(cur)
    return [l for l in lines if l]


def text_sprite(text, size, color=WHITE, max_w=940, accent=ACCENT, bold=True,
                line_gap=1.28, stroke=0, stroke_fill=SLATE_900, align="center"):
    font = get_font(size, bold)
    lines = wrap_chars(parse_marked(text, color, accent), font, max_w)
    pad = 8 + stroke
    lh = int(size * line_gap)
    widths = [font.getlength("".join(c for c, _ in l)) for l in lines]
    w = int(max(widths) if widths else 1) + pad * 2
    h = lh * len(lines) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        x = pad + ((w - pad * 2 - widths[i]) / 2 if align == "center" else 0)
        y = pad + i * lh + (lh - size) / 2
        # 同じ色の連続部分ごとに描画
        run, run_col = "", None
        for ch, col in line + [("", None)]:
            if col != run_col and run:
                d.text((x, y), run, font=font, fill=run_col, stroke_width=stroke, stroke_fill=stroke_fill)
                x += font.getlength(run)
                run = ""
            run += ch
            run_col = col
    return img


def fit_text_sprite(text, size, max_w, color=WHITE, min_size=60, **kw):
    """明示した改行以外で折り返さない最大の文字サイズで描く"""
    n_lines = text.count("\n") + 1
    while size > min_size:
        font = get_font(size, kw.get("bold", True))
        if len(wrap_chars(parse_marked(text, color, ACCENT), font, max_w)) <= n_lines:
            break
        size -= 4
    return text_sprite(text, size, color, max_w=max_w, **kw)


def pill_sprite(text, size, fg, bg, outline=None, pad_x=34, pad_y=16):
    font = get_font(size)
    tw = font.getlength(text)
    w, h = int(tw + pad_x * 2), int(size + pad_y * 2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=bg, outline=outline, width=3 if outline else 0)
    d.text((w / 2, h / 2), text, font=font, fill=fg, anchor="mm")
    return img


def keycap_sprite(label, pressed=False, height=170):
    symbol = KEY_SYMBOLS.get(label.strip().lower())
    size = 64 if len(label) <= 3 else 52
    font = get_font(size)
    tw = font.getlength(label)
    w = int(max(height, tw + 70))
    depth = 6 if pressed else 18
    img = Image.new("RGBA", (w, height + 18), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    top = 18 - depth
    face_col = ACCENT if pressed else SLATE_100
    side_col = (14, 116, 144) if pressed else SLATE_400
    d.rounded_rectangle([0, top + depth, w - 1, height + 17], radius=26, fill=side_col)
    d.rounded_rectangle([0, top, w - 1, top + height - 4], radius=26, fill=face_col)
    d.rounded_rectangle([10, top + 8, w - 11, top + height - 16], radius=20,
                        fill=(255, 255, 255) if not pressed else (125, 211, 252))
    cy = top + (height - 4) / 2
    if symbol:
        d.text((w / 2, cy - 30), symbol, font=get_font(40), fill=SLATE_700, anchor="mm")
        d.text((w / 2, cy + 26), label, font=get_font(min(size, 50)), fill=SLATE_900, anchor="mm")
    else:
        d.text((w / 2, cy), label, font=font, fill=SLATE_900, anchor="mm")
    return img


def card_sprite(w, h, fill=(30, 41, 59, 235), outline=SLATE_700, radius=32):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=fill, outline=outline, width=3)
    return img


def compose(base, sprite, x, y):
    """base 上の座標 (x, y) を左上として sprite を合成する（はみ出しは切り取る）"""
    x, y = int(round(x)), int(round(y))
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1 = min(sprite.width, base.width - x)
    sy1 = min(sprite.height, base.height - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    if (sx0, sy0, sx1, sy1) != (0, 0, sprite.width, sprite.height):
        sprite = sprite.crop((sx0, sy0, sx1, sy1))
    base.alpha_composite(sprite, (x + sx0, y + sy0))


def with_alpha(sprite, a):
    if a >= 0.999:
        return sprite
    s = sprite.copy()
    s.putalpha(s.getchannel("A").point(lambda v: int(v * a)))
    return s


def make_background():
    grad = np.linspace(0, 1, H)[:, None]
    top, bottom = np.array(BG_TOP), np.array(BG_BOTTOM)
    rgb = (top + (bottom - top) * grad[..., None]).repeat(W, axis=1)
    # 中央上部のほのかな光
    yy, xx = np.mgrid[0:H, 0:W]
    glow = np.exp(-(((xx - W / 2) / 700) ** 2 + ((yy - 780) / 600) ** 2))
    rgb = rgb + glow[..., None] * np.array([20, 50, 80]) * 0.6
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(img)
    for gy in range(60, H, 60):
        for gx in range(30, W, 60):
            d.point((gx, gy), fill=(71, 85, 105, 255))
    return img


# ────────────────────────────── シーン ──────────────────────────────

class Element:
    def __init__(self, sprite, cx, cy, t_in=0.0, anim="rise", dur=0.45, alt=None, alt_from=None, alt_to=None):
        self.sprite = sprite
        self.cx, self.cy = cx, cy
        self.t_in, self.anim, self.dur = t_in, anim, dur
        # alt_from〜alt_to の間だけ別スプライト（キーを押した状態など）に差し替える
        self.alt, self.alt_from, self.alt_to = alt, alt_from, alt_to
        self.pulse = False

    def draw(self, frame, t, scene_dur):
        if t < self.t_in:
            return
        p = min(1.0, (t - self.t_in) / self.dur)
        sprite = self.sprite
        if self.alt is not None and self.alt_from <= t < self.alt_to:
            sprite = self.alt
        alpha, scale, dy = 1.0, 1.0, 0.0
        if self.anim == "rise":
            e = ease_out_cubic(p)
            alpha, dy = e, (1 - e) * 70
        elif self.anim == "pop":
            alpha = min(1.0, p * 2.5)
            scale = 0.55 + 0.45 * ease_out_back(p)
        elif self.anim == "fade":
            alpha = p
        if self.pulse and p >= 1:
            scale *= 1 + 0.04 * math.sin((t - self.t_in) * 2 * math.pi * 1.2)
        # シーン末尾でフェードアウト
        out = min(1.0, max(0.0, (scene_dur - t) / 0.18))
        alpha *= out
        if alpha <= 0.01:
            return
        if abs(scale - 1) > 0.005:
            nw, nh = max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))
            sprite = sprite.resize((nw, nh), Image.BILINEAR)
        sprite = with_alpha(sprite, alpha)
        compose(frame, sprite, self.cx - sprite.width / 2, self.cy - sprite.height / 2 + dy)


class Scene:
    def __init__(self, voice, subtitle_text, min_dur=0.0):
        self.voice = voice
        self.voice_dur = len(voice) / SR
        self.duration = max(min_dur, LEAD + self.voice_dur + TAIL)
        self.start = 0.0
        self.elements = []
        self.sfx = []
        self.subtitles = build_subtitles(subtitle_text, self.voice_dur)

    def add(self, el):
        self.elements.append(el)
        return el


def split_subtitle(text, max_chars=17):
    sentences = [s for s in re.split(r"(?<=[。！？!?])", text) if s.strip()]
    chunks = []
    for s in sentences:
        if len(s) <= max_chars:
            chunks.append(s)
            continue
        parts = [p for p in re.split(r"(?<=[、,])", s) if p]
        cur = ""
        for p in parts:
            if cur and len(cur) + len(p) > max_chars:
                chunks.append(cur)
                cur = p
            else:
                cur += p
        if cur:
            chunks.append(cur)
    return [c.strip().rstrip("。、") for c in chunks if c.strip()]


def build_subtitles(text, voice_dur):
    chunks = split_subtitle(text)
    total = sum(len(c) for c in chunks) or 1
    subs, t = [], LEAD
    for c in chunks:
        d = voice_dur * len(c) / total
        sprite = text_sprite(c, 50, WHITE, max_w=900, stroke=5, stroke_fill=(2, 6, 23))
        subs.append((t, t + d, sprite))
        t += d
    return subs


def build_hook(scene, data):
    tag = pill_sprite(data.get("tag", "完全保存版"), 44, WHITE, RED)
    scene.add(Element(tag, W / 2, 470, 0.0, "pop", 0.4))
    scene.sfx.append((0.05, "pop"))
    title = fit_text_sprite(data["title"], 112, 980, WHITE, line_gap=1.22, stroke=4)
    scene.add(Element(title, W / 2, 470 + 70 + title.height / 2 + 30, 0.15, "rise", 0.5))
    if data.get("sub"):
        sub = text_sprite(data["sub"], 52, SLATE_300, max_w=940)
        scene.add(Element(sub, W / 2, 470 + 70 + title.height + 80 + sub.height / 2, 0.45, "rise", 0.45))


def build_item(scene, item, index, total):
    header = pill_sprite(f"SHORTCUT  {index}/{total}", 38, ACCENT, (30, 41, 59), outline=ACCENT)
    scene.add(Element(header, W / 2, 300, 0.0, "fade", 0.25))

    num = text_sprite(f"{index:02d}", 150, ACCENT)
    scene.add(Element(num, W / 2, 450, 0.0, "pop", 0.4))
    title = fit_text_sprite(item["title"], 84, 960, WHITE, stroke=3)
    scene.add(Element(title, W / 2, 590 + title.height / 2 - 40, 0.1, "rise", 0.45))

    # キーキャップ列
    keys = item["keys"]
    normal = [keycap_sprite(k) for k in keys]
    pressed = [keycap_sprite(k, pressed=True) for k in keys]
    plus = text_sprite("+", 72, SLATE_400)
    gap = 18
    total_w = sum(s.width for s in normal) + (plus.width + gap * 2) * (len(keys) - 1)
    scale = min(1.0, 980 / total_w)
    if scale < 1.0:
        normal = [s.resize((int(s.width * scale), int(s.height * scale)), Image.LANCZOS) for s in normal]
        pressed = [s.resize((int(s.width * scale), int(s.height * scale)), Image.LANCZOS) for s in pressed]
        total_w *= scale
    key_y = 900
    x = W / 2 - total_w / 2
    t_keys = 0.35
    press_at = t_keys + 0.15 * len(keys) + 0.25
    for i in range(len(keys)):
        t_in = t_keys + 0.15 * i
        scene.add(Element(normal[i], x + normal[i].width / 2, key_y, t_in, "pop", 0.35,
                          alt=pressed[i], alt_from=press_at, alt_to=press_at + 0.4))
        scene.sfx.append((t_in + 0.03, "pop"))
        x += normal[i].width
        if i < len(keys) - 1:
            scene.add(Element(plus, x + gap + plus.width / 2 * scale, key_y, t_in + 0.08, "fade", 0.2))
            x += (plus.width + gap * 2) * scale
    scene.sfx.append((press_at, "click"))

    if item.get("alt"):
        alt = text_sprite(item["alt"], 40, SLATE_400, bold=False)
        scene.add(Element(alt, W / 2, key_y + 135, press_at, "fade", 0.3))

    desc = text_sprite(item["desc"], 54, SLATE_100, max_w=840, line_gap=1.35)
    card = card_sprite(940, desc.height + 70)
    card.alpha_composite(desc, ((card.width - desc.width) // 2, 35))
    scene.add(Element(card, W / 2, 1150 + card.height / 2, press_at + 0.15, "rise", 0.45))


def build_outro(scene, data):
    title = fit_text_sprite(data["title"], 104, 980, WHITE, stroke=4)
    scene.add(Element(title, W / 2, 600, 0.0, "rise", 0.45))
    if data.get("sub"):
        sub = text_sprite(data["sub"], 54, SLATE_300, max_w=940)
        scene.add(Element(sub, W / 2, 600 + title.height / 2 + 60 + sub.height / 2, 0.2, "rise", 0.45))
    cta = pill_sprite(data.get("cta", "保存して明日から使おう"), 50, SLATE_900, ACCENT, pad_x=48, pad_y=24)
    el = scene.add(Element(cta, W / 2, 1060, 0.45, "pop", 0.4))
    el.pulse = True
    scene.sfx.append((0.5, "pop"))


def build_scenes(script, narrator):
    scenes = []
    items = script["items"]

    print("🎙️ ナレーションを合成中...")
    hook = script["hook"]
    sc = Scene(narrator.speak(hook["narration"]), hook["narration"], min_dur=2.5)
    build_hook(sc, hook)
    scenes.append(sc)

    for i, item in enumerate(items, 1):
        sc = Scene(narrator.speak(item["narration"]), item["narration"], min_dur=3.0)
        build_item(sc, item, i, len(items))
        scenes.append(sc)

    outro = script["outro"]
    sc = Scene(narrator.speak(outro["narration"]), outro["narration"], min_dur=3.0)
    build_outro(sc, outro)
    scenes.append(sc)
    print(f"  └ ✅ 音声エンジン: {narrator.engine}")

    t = 0.0
    for sc in scenes:
        sc.start = t
        t += sc.duration
    return scenes, t


# ────────────────────────────── レンダリング ──────────────────────────────

def render_frame(bg, scene, t_local, t_global, total, handle=None):
    frame = bg.copy()
    d = ImageDraw.Draw(frame)
    # 進捗バー
    d.rectangle([0, 0, W, 10], fill=(30, 41, 59, 255))
    d.rectangle([0, 0, int(W * t_global / total), 10], fill=ACCENT + (255,))
    for el in scene.elements:
        el.draw(frame, t_local, scene.duration)
    for s0, s1, sprite in scene.subtitles:
        if s0 <= t_local < s1:
            a = min(1.0, (t_local - s0) / 0.08)
            compose(frame, with_alpha(sprite, a), W / 2 - sprite.width / 2, 1500 - sprite.height / 2)
            break
    if handle:
        hs = text_sprite(handle, 34, SLATE_400, bold=False)
        compose(frame, hs, W / 2 - hs.width / 2, 1640)
    return frame


def render_video(scenes, total, audio_path, out_path, handle=None):
    bg = make_background()
    n_frames = int(math.ceil(total * FPS))
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", audio_path,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", str(SR),
        "-shortest", "-movflags", "+faststart", out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    si = 0
    for f in range(n_frames):
        t = f / FPS
        while si < len(scenes) - 1 and t >= scenes[si].start + scenes[si].duration:
            si += 1
        sc = scenes[si]
        frame = render_frame(bg, sc, t - sc.start, t, total, handle)
        proc.stdin.write(frame.convert("RGB").tobytes())
        if f % (FPS * 5) == 0:
            print(f"  └ {f}/{n_frames} フレーム")
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg のエンコードに失敗しました。")


def render_thumbnail(script, out_path):
    """YouTube 用サムネイル（1080x1920 のフック画面を静止画で）"""
    bg = make_background()
    sc = Scene(np.zeros(SR, dtype=np.float32), "", min_dur=5)
    build_hook(sc, script["hook"])
    frame = bg.copy()
    for el in sc.elements:
        el.draw(frame, 3.0, sc.duration)
    frame.convert("RGB").save(out_path)


def write_youtube_meta(script, path):
    tags = script.get("tags", [])
    body = (
        f"【タイトル】\n{script.get('youtube_title', '')}\n\n"
        f"【説明】\n{script.get('youtube_description', '')}\n\n"
        + " ".join("#" + t.lstrip("#") for t in tags)
        + f"\n\n【タグ】\n{', '.join(t.lstrip('#') for t in tags)}\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


# ────────────────────────────── メイン ──────────────────────────────

def make_video(script, out_root, engine="auto", voice="ja-JP-NanamiNeural", use_bgm=True, bgm_path=None, handle=None):
    slug = re.sub(r"[^a-z0-9\-]", "", script.get("slug", "video").lower()) or "video"
    out_dir = os.path.join(out_root, slug)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "script.json"), "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    scenes, total = build_scenes(script, Narrator(engine, voice))
    print(f"🎵 音声をミックス中...（全長 {total:.1f} 秒）")
    audio = mix_audio(scenes, total, use_bgm, bgm_path)
    audio_path = os.path.join(out_dir, "audio.wav")
    write_wav(audio_path, audio)

    print("🎬 動画をレンダリング中...")
    video_path = os.path.join(out_dir, "video.mp4")
    render_video(scenes, total, audio_path, video_path, handle)
    os.remove(audio_path)

    render_thumbnail(script, os.path.join(out_dir, "thumbnail.png"))
    write_youtube_meta(script, os.path.join(out_dir, "youtube.txt"))
    print(f"\n🎉 完成: {video_path}")
    return video_path


def main():
    ap = argparse.ArgumentParser(description="ショートカット解説ショート動画を自動生成")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--script", help="台本JSONのパス")
    src.add_argument("--topic", help="テーマ（Claude が台本を生成）")
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "output"), help="出力先フォルダ")
    ap.add_argument("--tts", default="auto", choices=["auto", "edge", "openjtalk"], help="音声合成エンジン")
    ap.add_argument("--voice", default="ja-JP-NanamiNeural", help="edge-tts の声（例: ja-JP-KeitaNeural）")
    ap.add_argument("--bgm", help="BGMに使う音声ファイル（省略時は自動生成のBGM）")
    ap.add_argument("--no-bgm", action="store_true", help="BGMなし")
    ap.add_argument("--handle", help="画面下部に表示するアカウント名（例: @your_account）")
    args = ap.parse_args()

    if args.script:
        with open(args.script, "r", encoding="utf-8") as f:
            script = json.load(f)
    else:
        print(f"🤖 Claude で台本を生成中: {args.topic}")
        script = generate_script(args.topic, load_anthropic_key())

    make_video(script, args.out, args.tts, args.voice, not args.no_bgm, args.bgm, args.handle)


if __name__ == "__main__":
    sys.exit(main())
