"""정적인 클립에 움직임(켄번스 줌 + 줌 펀치) + 가격카드 + 누적 금액 카운터를 넣는 데모."""
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SRC, OUT = sys.argv[1], sys.argv[2]
FONT_DIR = sys.argv[3]
W, H, FPS = 1080, 1920, 30
PUNCH_T = 1.2  # 가격카드 등장 + 줌 펀치 시점

dur = float(subprocess.check_output(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", SRC]))
n_frames = int(dur * FPS)

bold = lambda s: ImageFont.truetype(f"{FONT_DIR}/Pretendard-Bold.otf", s)
xbold = lambda s: ImageFont.truetype(f"{FONT_DIR}/Pretendard-ExtraBold.otf", s)


def ease_out_back(x):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def zoom_at(t):
    base = 1.0 + 0.14 * (t / dur)  # 천천히 밀고 들어가기
    dt = t - PUNCH_T
    punch = 0.07 * math.exp(-dt * 7) * math.cos(dt * 18) if dt >= 0 else 0
    return base + max(punch, -0.02)


def text_with_stroke(draw, xy, text, font, fill, stroke=6, anchor="mm"):
    draw.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0), anchor=anchor)


def won(v):
    return f"{int(v):,}원"


def overlay(t):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # 상단 고정 제목
    text_with_stroke(d, (W // 2, 200), "하루 식비 1만원 챌린지", xbold(68), (255, 255, 255))

    # 누적 금액 카운터 (오른쪽 위)
    k = min(max((t - PUNCH_T) / 0.6, 0), 1)
    value = 1942 + 400 * (1 - (1 - k) ** 3)
    flash = 0 < t - PUNCH_T < 0.8
    d.rounded_rectangle((W - 330, 290, W - 50, 420), 24, fill=(0, 0, 0, 170))
    d.text((W - 190, 322), "오늘 식비", font=bold(30), fill=(200, 200, 200), anchor="mm")
    d.text((W - 190, 377), won(value), font=xbold(50),
           fill=(255, 214, 0) if flash else (255, 255, 255), anchor="mm")

    # 하단 자막 (인스타 UI에 가리지 않게 아래 여백 확보)
    text_with_stroke(d, (W // 2, H - 520), "바나나 하나 추가", xbold(72), (255, 255, 255), stroke=8)

    # 가격카드 팝인
    if t >= PUNCH_T:
        p = min((t - PUNCH_T) / 0.35, 1)
        s = max(ease_out_back(p), 0.01)
        card = Image.new("RGBA", (560, 230), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, 559, 229), 36, fill=(255, 255, 255, 245))
        cd.text((280, 70), "바나나 1개", font=bold(48), fill=(60, 60, 60), anchor="mm")
        cd.text((280, 155), "약 400원", font=xbold(84), fill=(230, 60, 40), anchor="mm")
        shadow = Image.new("RGBA", (600, 270), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((20, 30, 580, 260), 36, fill=(0, 0, 0, 110))
        shadow = shadow.filter(ImageFilter.GaussianBlur(14))
        cw, ch = int(560 * s), int(230 * s)
        cx, cy = W // 2, H // 2 + 60
        sw, sh = int(600 * s), int(270 * s)
        layer.alpha_composite(shadow.resize((sw, sh)), (cx - sw // 2, cy - sh // 2))
        layer.alpha_composite(card.resize((cw, ch)), (cx - cw // 2, cy - ch // 2))
    return layer


dec = subprocess.Popen(
    ["ffmpeg", "-v", "error", "-i", SRC, "-vf",
     f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
     "eq=contrast=1.08:saturation=1.25:brightness=0.02",
     "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
enc = subprocess.Popen(
    ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
     "-r", str(FPS), "-i", "-", "-i", SRC, "-map", "0:v", "-map", "1:a:0", "-shortest",
     "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
     "-c:a", "aac", "-b:a", "128k", OUT], stdin=subprocess.PIPE)

for i in range(n_frames):
    raw = dec.stdout.read(W * H * 3)
    if len(raw) < W * H * 3:
        break
    t = i / FPS
    frame = Image.frombytes("RGB", (W, H), raw)
    z = zoom_at(t)
    cw, ch = W / z, H / z
    drift = 30 * (t / dur)  # 살짝 위로 흐르는 패닝
    left, top = (W - cw) / 2, (H - ch) / 2 - drift
    frame = frame.resize((W, H), Image.BICUBIC, box=(left, top, left + cw, top + ch)).convert("RGBA")
    frame.alpha_composite(overlay(t))
    enc.stdin.write(frame.convert("RGB").tobytes())

enc.stdin.close()
enc.wait()
dec.wait()
