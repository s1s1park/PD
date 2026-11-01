"""장면표(YAML)를 읽어서 9:16 릴스 영상을 자동으로 만든다.

사용법:
    python3 render.py <장면표.yaml> <원본폴더> <출력.mp4> [--fonts 폰트폴더] [--only 3,4]
"""
import argparse
import math
import random
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS, SR = 1080, 1920, 30, 48000
COLOR = "eq=contrast=1.08:saturation=1.22:brightness=0.02"


# ---------- 공통 도구 ----------

def ease_out_back(x):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_out_cubic(x):
    return 1 - (1 - min(max(x, 0), 1)) ** 3


def won(v):
    return f"{int(round(v)):,}원"


def probe_duration(path):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


def has_audio(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(path)])
    return bool(out.strip())


class Fonts:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.cache = {}

    def __call__(self, size, weight="ExtraBold"):
        key = (size, weight)
        if key not in self.cache:
            self.cache[key] = ImageFont.truetype(str(self.folder / f"Pretendard-{weight}.otf"), size)
        return self.cache[key]


# ---------- 타임라인 ----------

@dataclass
class Event:
    t: float          # 영상 전체 기준 시각
    kind: str         # card, flash, glitch, shake, stamp
    data: dict = field(default_factory=dict)


@dataclass
class Timeline:
    scenes: list
    starts: list
    total: float
    events: list
    counter_adds: list  # (t, 금액, 단백질g)

    def scene_at(self, t):
        for i in range(len(self.scenes) - 1, -1, -1):
            if t >= self.starts[i]:
                return i
        return 0


def build_timeline(spec):
    scenes = spec["scenes"]
    starts, events, adds, t = [], [], [], 0.0
    for sc in scenes:
        starts.append(t)
        for c in sc.get("cards", []):
            events.append(Event(t + c["at"], "card", c))
            if c.get("add") or c.get("protein"):
                adds.append((t + c["at"], c.get("add", 0), c.get("protein", 0)))
        for e in sc.get("effects", []):
            events.append(Event(t + e.get("at", 0), e["type"], e))
        if sc.get("receipt"):
            events.append(Event(t + sc["receipt"].get("stamp_at", 3.6), "stamp", {}))
        t += sc["dur"]
    return Timeline(scenes, starts, t, events, adds)


# ---------- 그래픽 ----------

class Graphics:
    def __init__(self, spec, tl, fonts):
        self.spec, self.tl, self.f = spec, tl, fonts

    def text(self, d, xy, text, size, fill=(255, 255, 255), stroke=8, weight="ExtraBold", anchor="mm"):
        d.text(xy, text, font=self.f(size, weight), fill=fill, stroke_width=stroke,
               stroke_fill=(0, 0, 0), anchor=anchor)

    def counter_value(self, t):
        money = protein = 0.0
        for at, amount, prot in self.tl.counter_adds:
            k = ease_out_cubic((t - at) / 0.6)
            money += amount * k
            protein += prot * k
        return money, protein

    def counters(self, d, t):
        money, protein = self.counter_value(t)
        money_rolling = any(0 < t - at < 0.8 for at, a, _ in self.tl.counter_adds if a)
        prot_rolling = any(0 < t - at < 0.8 for at, _, p in self.tl.counter_adds if p)
        goal = self.spec.get("protein_goal")
        x0, x1 = W - 370, W - 40
        cx = (x0 + x1) // 2
        d.rounded_rectangle((x0, 290, x1, 540 if goal else 420), 24, fill=(0, 0, 0, 170))
        d.text((cx, 322), "오늘 식비", font=self.f(30, "Bold"), fill=(200, 200, 200), anchor="mm")
        d.text((cx, 377), won(money), font=self.f(50),
               fill=(255, 214, 0) if money_rolling else (255, 255, 255), anchor="mm")
        if not goal:
            return
        done = protein >= goal - 0.5
        green = (80, 220, 120)
        d.text((cx, 445), f"단백질 {int(round(protein))}g / {goal}g", font=self.f(32, "Bold"),
               fill=green if done else ((255, 214, 0) if prot_rolling else (255, 255, 255)), anchor="mm")
        bx0, bx1, by = x0 + 30, x1 - 30, 490
        d.rounded_rectangle((bx0, by, bx1, by + 22), 11, fill=(255, 255, 255, 60))
        fill_w = (bx1 - bx0) * min(protein / goal, 1)
        if fill_w > 22:
            d.rounded_rectangle((bx0, by, bx0 + fill_w, by + 22), 11,
                                fill=green if done else (255, 214, 0))

    def card(self, layer, cx, cy, label, price, sub, scale, big=False):
        cw, ch = (720, 330) if big else (560, 230)
        if sub:
            ch += 60
        card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, cw - 1, ch - 1), 36, fill=(255, 255, 255, 245))
        label_y = 75 if big else 70
        cd.text((cw // 2, label_y), label, font=self.f(58 if big else 46, "Bold"), fill=(60, 60, 60), anchor="mm")
        cd.text((cw // 2, label_y + (115 if big else 85)), price, font=self.f(120 if big else 84),
                fill=(230, 60, 40), anchor="mm")
        if sub:
            cd.text((cw // 2, ch - 50), sub, font=self.f(40, "Bold"), fill=(40, 120, 220), anchor="mm")
        shadow = Image.new("RGBA", (cw + 40, ch + 40), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((20, 30, cw + 20, ch + 30), 36, fill=(0, 0, 0, 110))
        shadow = shadow.filter(ImageFilter.GaussianBlur(14))
        s = max(scale, 0.01)
        sw, sh = int((cw + 40) * s), int((ch + 40) * s)
        layer.alpha_composite(shadow.resize((sw, sh)), (cx - sw // 2, cy - sh // 2))
        w2, h2 = int(cw * s), int(ch * s)
        layer.alpha_composite(card.resize((w2, h2)), (cx - w2 // 2, cy - h2 // 2))

    def receipt(self, layer, rc, lt):
        pw, ph = 780, 1020
        x0, y0 = (W - pw) // 2, 330
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle((x0 + 12, y0 + 18, x0 + pw + 12, y0 + ph + 18), 28, fill=(0, 0, 0, 90))
        d.rounded_rectangle((x0, y0, x0 + pw, y0 + ph), 28, fill=(252, 250, 244, 255))
        d.text((W // 2, y0 + 90), rc.get("title", "재무팀장 정산"), font=self.f(66), fill=(30, 30, 30), anchor="mm")
        d.line((x0 + 50, y0 + 160, x0 + pw - 50, y0 + 160), fill=(180, 180, 180), width=3)
        y = y0 + 230
        step = rc.get("line_step", 0.45)
        for i, (name, amount) in enumerate(rc["lines"]):
            k = (lt - 0.3 - i * step) / 0.25
            if k <= 0:
                break
            a = int(255 * min(k, 1))
            dy = int(20 * (1 - min(k, 1)))
            d.text((x0 + 70, y + dy), name, font=self.f(50, "Bold"), fill=(70, 70, 70, a), anchor="lm")
            d.text((x0 + pw - 70, y + dy), won(amount), font=self.f(54), fill=(30, 30, 30, a), anchor="rm")
            y += 100
        total_t = 0.3 + len(rc["lines"]) * step
        if lt > total_t:
            ty = y0 + ph - 190
            d.line((x0 + 50, ty - 70, x0 + pw - 50, ty - 70), fill=(60, 60, 60), width=4)
            total = sum(a for _, a in rc["lines"])
            k = ease_out_cubic((lt - total_t) / 0.5)
            d.text((x0 + 70, ty), "합계", font=self.f(60), fill=(30, 30, 30), anchor="lm")
            d.text((x0 + pw - 70, ty), won(total * k), font=self.f(76), fill=(230, 60, 40), anchor="rm")
            if rc.get("note") and lt > total_t + 0.6:
                d.text((W // 2, ty + 110), rc["note"], font=self.f(40, "Bold"), fill=(120, 120, 120), anchor="mm")
        stamp_at = rc.get("stamp_at", 3.6)
        if lt > stamp_at:
            k = min((lt - stamp_at) / 0.18, 1)
            s = 2.2 - 1.2 * k
            st = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
            sd = ImageDraw.Draw(st)
            sd.ellipse((10, 10, 350, 350), outline=(220, 40, 40, 230), width=16)
            sd.text((180, 158), rc.get("stamp", "결재"), font=self.f(96), fill=(220, 40, 40, 230), anchor="mm")
            sd.text((180, 240), "완료", font=self.f(52), fill=(220, 40, 40, 230), anchor="mm")
            st = st.rotate(-14, resample=Image.BICUBIC)
            size = int(360 * s)
            st = st.resize((size, size))
            layer.alpha_composite(st, (x0 + pw - 170 - size // 2, y0 + ph + 40 - size // 2))

    def overlay(self, t, si, lt):
        sc = self.tl.scenes[si]
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        if sc.get("receipt"):
            self.receipt(layer, sc["receipt"], lt)

        if self.spec.get("title") and sc.get("title", True):
            self.text(d, (W // 2, 200), self.spec["title"], 68)

        if sc.get("counter", True):
            self.counters(d, t)

        if sc.get("hook"):
            k = ease_out_back(min(lt / 0.35, 1))
            size = int(104 * max(k, 0.05))
            for i, line in enumerate(sc["hook"]):
                self.text(d, (W // 2, H // 2 - 170 + i * 140), line, size, stroke=10,
                          fill=(255, 214, 0) if i == len(sc["hook"]) - 1 else (255, 255, 255))

        # 가격카드: 현재 장면에서 가장 최근에 나온 카드 하나만 보여준다
        cards = [c for c in sc.get("cards", []) if c["at"] <= lt]
        if cards:
            c = cards[-1]
            p = min((lt - c["at"]) / 0.35, 1)
            cy = H // 2 + c.get("dy", 60)
            self.card(layer, W // 2, cy, c.get("label", ""), c.get("price", ""), c.get("sub"),
                      ease_out_back(p), big=c.get("big", False))

        subs = sc.get("subtitle")
        if subs:
            if isinstance(subs, str):
                subs = [{"at": 0, "text": subs}]
            cur = [s for s in subs if s["at"] <= lt]
            if cur:
                self.text(d, (W // 2, H - 520), cur[-1]["text"], 72, stroke=8)
        return layer


# ---------- 영상 소스 ----------

def stabilize_filter(path, start, length, cache_dir):
    """흔들림 보정: 1차로 흔들림을 분석해 파일로 저장하고, 2차 필터 문자열을 돌려준다."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    trf = cache_dir / f"{path.stem}_{start:.2f}_{length:.2f}.trf"
    if not trf.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(length), "-i", str(path),
                        "-vf", f"vidstabdetect=shakiness=6:accuracy=12:result='{trf}'", "-f", "null", "-"],
                       check=True)
    return f"vidstabtransform=input='{trf}':smoothing=20:optzoom=1:interpol=bicubic,"


def clip_frames(src_dir, clip, n, cache_dir):
    path = Path(src_dir) / clip["file"]
    start, length = clip.get("start", 0), n / FPS + 0.5
    # 휴대폰 촬영 원본(IMG_)은 기본으로 흔들림 보정, 화면 녹화 등은 끔
    stab = stabilize_filter(path, start, length, cache_dir) \
        if clip.get("stabilize", path.name.startswith("IMG_")) else ""
    fit = clip.get("fit", "cover")
    if fit == "blur":
        vf = (f"{stab}split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"boxblur=40:4,eq=brightness=-0.12[bg];[b]scale={W}:-2[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},{COLOR}")
    else:
        vf = f"{stab}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},{COLOR}"
    if clip.get("bg_blur"):
        vf += ",boxblur=30:3,eq=brightness=-0.25"
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(length),
           "-i", str(path), "-filter_complex" if fit == "blur" else "-vf", vf,
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    last = None
    for _ in range(n):
        raw = proc.stdout.read(W * H * 3)
        if len(raw) == W * H * 3:
            last = Image.frombytes("RGB", (W, H), raw)
        yield last if last is not None else Image.new("RGB", (W, H))
    proc.kill()
    proc.wait()


def clip_audio(src_dir, clip, n_samples):
    path = Path(src_dir) / clip["file"]
    vol = clip.get("volume", 0.45)
    if vol <= 0 or not has_audio(path):
        return np.zeros((n_samples, 2), np.float32)
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-ss", str(clip.get("start", 0)), "-t", str(n_samples / SR),
         "-i", str(path), "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"])
    a = np.frombuffer(raw, np.float32).reshape(-1, 2)[:n_samples]
    out = np.zeros((n_samples, 2), np.float32)
    out[:len(a)] = a * vol
    fade = min(int(0.04 * SR), n_samples // 2)
    if fade:
        ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
        out[:fade] *= ramp
        out[-fade:] *= ramp[::-1]
    return out


# ---------- 효과음 ----------

def sfx(kind):
    rng = np.random.default_rng(len(kind))
    def tt(sec):
        return np.arange(int(sec * SR)) / SR
    if kind == "pop":
        t = tt(0.14)
        f = 900 * np.exp(-t * 14) + 280
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 28) * 0.55
    elif kind == "ding":
        t = tt(0.4)
        y = (np.sin(2 * np.pi * 1568 * t) + 0.6 * np.sin(2 * np.pi * 2093 * t)) * np.exp(-t * 9) * 0.22
    elif kind == "whoosh":
        t = tt(0.38)
        noise = rng.standard_normal(len(t))
        noise = np.convolve(noise, np.ones(18) / 18, mode="same")
        env = np.sin(np.pi * t / t[-1]) ** 2
        y = noise * env * 0.5
    elif kind == "stamp":
        t = tt(0.35)
        y = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 16) * 0.9
        y[:int(0.03 * SR)] += rng.standard_normal(int(0.03 * SR)) * 0.4
    elif kind == "glitch":
        t = tt(0.3)
        y = np.sign(np.sin(2 * np.pi * 220 * t * (1 + 3 * (t * 10 % 1)))) * 0.12
        y *= (rng.random(len(t)) > 0.3)
    else:
        return np.zeros((0, 2), np.float32)
    return np.repeat(y.astype(np.float32)[:, None], 2, axis=1)


def mix_at(track, clip, t):
    i = int(t * SR)
    if i >= len(track) or len(clip) == 0:
        return
    j = min(len(track), i + len(clip))
    track[i:j] += clip[:j - i]


# ---------- 화면 효과 ----------

def apply_motion(frame, z, drift, shake_xy):
    z = max(z, 1.0)
    cw, ch = W / z, H / z
    left = (W - cw) / 2 + shake_xy[0]
    top = (H - ch) / 2 - drift + shake_xy[1]
    left = min(max(left, 0), W - cw)
    top = min(max(top, 0), H - ch)
    return frame.resize((W, H), Image.BICUBIC, box=(left, top, left + cw, top + ch))


def glitch(frame, strength, rng):
    a = np.asarray(frame).copy()
    sh = int(26 * strength)
    a[:, :, 0] = np.roll(a[:, :, 0], sh, axis=1)
    a[:, :, 2] = np.roll(a[:, :, 2], -sh, axis=1)
    for _ in range(int(8 * strength) + 1):
        y = rng.integers(0, H - 80)
        h = rng.integers(20, 120)
        a[y:y + h] = np.roll(a[y:y + h], rng.integers(-90, 90), axis=1)
    return Image.fromarray(a)


# ---------- 메인 ----------

def render(spec_path, src_dir, out_path, fonts_dir, only=None):
    spec = yaml.safe_load(Path(spec_path).read_text())
    if only:
        spec["scenes"] = [s for s in spec["scenes"] if s["id"] in only]
    tl = build_timeline(spec)
    gfx = Graphics(spec, tl, Fonts(fonts_dir))
    rng = np.random.default_rng(7)
    punches = [e.t for e in tl.events if e.kind in ("card", "stamp")]
    shakes = [e.t for e in tl.events if e.kind in ("shake", "stamp")]
    flashes = [e.t for e in tl.events if e.kind == "flash"]
    glitches = [(e.t, e.data.get("dur", 0.4)) for e in tl.events if e.kind == "glitch"]

    total_frames = int(round(tl.total * FPS))
    audio = np.zeros((int(tl.total * SR) + SR, 2), np.float32)

    tmp_video = Path(out_path).with_suffix(".video.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", str(tmp_video)], stdin=subprocess.PIPE)

    frame_i = 0
    for si, sc in enumerate(tl.scenes):
        s0 = tl.starts[si]
        sc_frames = int(round((s0 + sc["dur"]) * FPS)) - frame_i
        clips = sc["clips"]
        # 클립 길이: 지정이 없으면 장면 길이를 나눠 가짐
        fixed = sum(c.get("dur", 0) for c in clips)
        free = [c for c in clips if "dur" not in c]
        each = (sc["dur"] - fixed) / len(free) if free else 0
        durs = [c.get("dur", each) for c in clips]
        counts, acc = [], 0.0
        for k, d in enumerate(durs):
            acc += d
            end = sc_frames if k == len(durs) - 1 else int(round(acc * FPS))
            counts.append(end - sum(counts))

        ct = s0
        for clip, n in zip(clips, counts):
            mix_at(audio, clip_audio(src_dir, clip, int(n / FPS * SR)), ct)
            z0, z1 = clip.get("zoom", [1.0, 1.1])
            for k, frame in enumerate(clip_frames(src_dir, clip, n, Path(out_path).parent / ".stab")):
                t = frame_i / FPS
                lt = t - s0
                p = k / max(n - 1, 1)
                z = z0 + (z1 - z0) * p
                for pt in punches:
                    dt = t - pt
                    if 0 <= dt < 0.6:
                        z += max(0.07 * math.exp(-dt * 7) * math.cos(dt * 18), -0.02)
                sx = sy = 0.0
                for st in shakes:
                    dt = t - st
                    if 0 <= dt < 0.45:
                        amp = 28 * (1 - dt / 0.45)
                        sx += rng.uniform(-amp, amp)
                        sy += rng.uniform(-amp, amp)
                img = apply_motion(frame, z, 30 * p, (sx, sy))
                for gt, gd in glitches:
                    if 0 <= t - gt < gd:
                        img = glitch(img, 1 - (t - gt) / gd, rng)
                img = img.convert("RGBA")
                img.alpha_composite(gfx.overlay(t, si, lt))
                for ft in flashes:
                    dt = t - ft
                    if 0 <= dt < 0.28:
                        img = Image.blend(img, Image.new("RGBA", (W, H), (255, 255, 255, 255)),
                                          0.85 * (1 - dt / 0.28))
                enc.stdin.write(img.convert("RGB").tobytes())
                frame_i += 1
            ct += n / FPS
        print(f"장면 {sc['id']} 완료 ({frame_i}/{total_frames})", file=sys.stderr)

    enc.stdin.close()
    enc.wait()

    for e in tl.events:
        kind = {"card": "pop", "flash": "whoosh", "stamp": "stamp", "glitch": "glitch"}.get(e.kind)
        if kind:
            mix_at(audio, sfx(kind), e.t)
    for at, _, _ in tl.counter_adds:
        mix_at(audio, sfx("ding"), at + 0.45)
    audio = audio[:int(tl.total * SR)]
    peak = np.abs(audio).max()
    if peak > 0.98:
        audio *= 0.98 / peak
    tmp_audio = Path(out_path).with_suffix(".wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    str(tmp_audio)], input=audio.tobytes(), check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp_video), "-i", str(tmp_audio),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out_path)], check=True)
    tmp_video.unlink()
    tmp_audio.unlink()
    print(f"완성: {out_path} ({tl.total:.1f}초)", file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("src_dir")
    ap.add_argument("out")
    ap.add_argument("--fonts", default=str(Path(__file__).parent / "fonts"))
    ap.add_argument("--only", help="일부 장면만 (예: 3,4)")
    a = ap.parse_args()
    only = [int(x) for x in a.only.split(",")] if a.only else None
    render(a.spec, a.src_dir, a.out, a.fonts, only)
