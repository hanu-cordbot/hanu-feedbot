"""Quizizz-style question cards, drawn with Pillow and sent as an embed image.

One function per screen: the question, the answer reveal (solo or live, with how many
people picked each tile), the live podium and the solo score. Each returns PNG bytes.
Text comes from uploaded files, so anything the font can't draw (mostly emoji) is dropped
rather than shown as boxes.
"""
import io
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
PAD = 36
LETTERS = "ABCDEF"

BG_TOP, BG_BOTTOM = (58, 20, 82), (24, 8, 38)
PANEL = (0, 0, 0, 90)
WHITE = (255, 255, 255)
MUTED = (205, 190, 225)
PILL = (255, 255, 255, 38)
GREEN = (0, 200, 120)
RED = (229, 57, 53)
# Quizizz answer colours, in option order. The answer buttons use the matching square emoji.
TILE_COLOURS = [(47, 109, 174), (44, 156, 166), (236, 168, 44), (212, 84, 106), (154, 66, 146), (227, 121, 59)]
TILE_EMOJI = ["🟦", "🟩", "🟨", "🟥", "🟪", "🟧"]
MEDALS = [(255, 196, 37), (196, 205, 214), (205, 127, 50)]

FONT_DIRS = ("/usr/share/fonts/truetype/noto", "/usr/share/fonts/noto", "/usr/share/fonts/truetype/dejavu")
BOLD_FILES = ("NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf")
REGULAR_FILES = ("NotoSans-Regular.ttf", "DejaVuSans.ttf")


def _find_font(names: Sequence[str]) -> Optional[str]:
    for d in FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return str(p)
    return None


@lru_cache(maxsize=None)
def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = _find_font(BOLD_FILES if bold else REGULAR_FILES)
    if path is None:
        return ImageFont.load_default(size)
    return ImageFont.truetype(path, size)


def clean(text: str) -> str:
    """Drops emoji and other symbols the font can't draw; keeps letters with diacritics (Vietnamese etc.)."""
    out = []
    for ch in (text or "").replace("\r", ""):
        cat = unicodedata.category(ch)
        if cat in ("So", "Cs", "Co", "Cn") or 0xFE00 <= ord(ch) <= 0xFE0F or ord(ch) == 0x200D:
            continue
        out.append(" " if ch == "\t" else ch)
    return " ".join("".join(out).split(" ")).strip()


def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if f.getlength(trial) <= width:
                line = trial
                continue
            if line:
                lines.append(line)
            # A single word wider than the box gets broken by characters.
            while f.getlength(word) > width:
                cut = max(1, int(len(word) * width / f.getlength(word)) - 1)
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


def fit(text: str, width: int, height: int, largest: int, smallest: int, bold: bool = True,
        spacing: float = 1.18) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """The largest font size at which the wrapped text fits the box; truncates at the smallest size."""
    text = clean(text) or " "
    for size in range(largest, smallest - 1, -2):
        f = font(size, bold)
        lines = wrap(text, f, width)
        line_h = int(size * spacing)
        if line_h * len(lines) <= height:
            return f, lines, line_h
    f = font(smallest, bold)
    line_h = int(smallest * spacing)
    lines = wrap(text, f, width)[: max(1, height // line_h)]
    last = lines[-1]
    while last and f.getlength(last + "…") > width:
        last = last[:-1]
    lines[-1] = last.rstrip() + "…"
    return f, lines, line_h


def draw_block(d: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, largest: int, smallest: int,
               colour=WHITE, bold: bool = True, align: str = "center") -> None:
    x0, y0, x1, y1 = box
    f, lines, line_h = fit(text, x1 - x0, y1 - y0, largest, smallest, bold)
    y = y0 + ((y1 - y0) - line_h * len(lines)) // 2
    for line in lines:
        w = f.getlength(line)
        x = x0 + ((x1 - x0) - w) / 2 if align == "center" else x0
        d.text((x, y + (line_h - f.size) * 0.35), line, font=f, fill=colour)
        y += line_h


def background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_BOTTOM)
    top = Image.new("RGB", (W, H), BG_TOP)
    mask = Image.linear_gradient("L").resize((W, H)).point(lambda v: 255 - v)
    img.paste(top, (0, 0), mask)
    # A few soft circles, like the Quizizz game screen.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for cx, cy, r, a in ((140, 120, 220, 26), (1180, 640, 260, 22), (1040, 90, 120, 18)):
        g.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(170, 90, 220, a))
    img.paste(glow.filter(ImageFilter.GaussianBlur(40)), (0, 0), glow.filter(ImageFilter.GaussianBlur(40)))
    return img


def pill(d: ImageDraw.ImageDraw, x: int, y: int, text: str, fill=PILL, colour=WHITE, size: int = 26, right: bool = False) -> int:
    f = font(size)
    text = clean(text)
    w = int(f.getlength(text)) + 36
    h = size + 22
    if right:
        x -= w
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=fill)
    d.text((x + 18, y + (h - size) / 2 - size * 0.12), text, font=f, fill=colour)
    return w


def check(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, ok: bool) -> None:
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN if ok else RED, outline=WHITE, width=4)
    s = r * 0.5
    if ok:
        d.line([(cx - s, cy + s * 0.05), (cx - s * 0.25, cy + s * 0.7), (cx + s, cy - s * 0.6)], fill=WHITE, width=max(4, r // 4), joint="curve")
    else:
        d.line([(cx - s * 0.7, cy - s * 0.7), (cx + s * 0.7, cy + s * 0.7)], fill=WHITE, width=max(4, r // 4))
        d.line([(cx - s * 0.7, cy + s * 0.7), (cx + s * 0.7, cy - s * 0.7)], fill=WHITE, width=max(4, r // 4))


def _dim(colour: tuple[int, int, int], amount: float = 0.55) -> tuple[int, int, int]:
    grey = sum(colour) / 3
    return tuple(int((c * 0.35 + grey * 0.65) * (1 - amount) + 40 * amount) for c in colour)


def _darker(colour: tuple[int, int, int], f: float = 0.72) -> tuple[int, int, int]:
    return tuple(int(c * f) for c in colour)


def tiles(img: Image.Image, options: list[str], top: int, *, correct: Optional[int] = None,
          chosen: Optional[int] = None, counts: Optional[list[int]] = None) -> None:
    """The coloured answer tiles. With `correct` set, the card shows the reveal."""
    d = ImageDraw.Draw(img, "RGBA")
    n = len(options)
    cols = n if n <= 4 else 3
    rows = 1 if n <= 4 else 2
    gap = 18
    tile_w = (W - 2 * PAD - gap * (cols - 1)) // cols
    tile_h = (H - top - PAD - gap * (rows - 1)) // rows
    total = max(1, sum(counts)) if counts else 1
    for i, opt in enumerate(options):
        r, c = divmod(i, cols)
        x0 = PAD + c * (tile_w + gap)
        y0 = top + r * (tile_h + gap)
        x1, y1 = x0 + tile_w, y0 + tile_h
        colour = TILE_COLOURS[i % len(TILE_COLOURS)]
        revealed = correct is not None
        is_right = revealed and i == correct
        is_wrong_pick = revealed and chosen is not None and i == chosen and i != correct
        face = colour if not revealed or is_right else (_dim(colour, 0.3) if is_wrong_pick else _dim(colour))
        # Chunky bottom edge, like Quizizz's 3D buttons.
        d.rounded_rectangle((x0, y0 + 8, x1, y1), radius=22, fill=_darker(face, 0.65))
        d.rounded_rectangle((x0, y0, x1, y1 - 8), radius=22, fill=face)
        if is_right:
            d.rounded_rectangle((x0 - 5, y0 - 5, x1 + 5, y1 + 3), radius=26, outline=GREEN, width=7)
        if is_wrong_pick:
            d.rounded_rectangle((x0 - 5, y0 - 5, x1 + 5, y1 + 3), radius=26, outline=RED, width=7)
        # Letter badge, matching the buttons.
        d.rounded_rectangle((x0 + 14, y0 + 14, x0 + 62, y0 + 62), radius=12, fill=(0, 0, 0, 70))
        lf = font(28)
        d.text((x0 + 38 - lf.getlength(LETTERS[i]) / 2, y0 + 19), LETTERS[i], font=lf, fill=WHITE)
        bottom_reserved = 54 if counts is not None else 16
        text_colour = WHITE if not revealed or is_right or is_wrong_pick else (225, 225, 225)
        draw_block(d, (x0 + 22, y0 + 70, x1 - 22, y1 - 8 - bottom_reserved), opt, 40 if n <= 4 else 34, 16, text_colour)
        if is_right or is_wrong_pick:
            check(d, x1 - 38, y0 + 38, 24, is_right)
        if counts is not None:
            share = counts[i] / total
            bx0, by0, bx1, by1 = x0 + 18, y1 - 8 - 40, x1 - 18, y1 - 8 - 18
            d.rounded_rectangle((bx0, by0, bx1, by1), radius=11, fill=(0, 0, 0, 80))
            if counts[i]:
                d.rounded_rectangle((bx0, by0, bx0 + max(22, int((bx1 - bx0) * share)), by1), radius=11, fill=(255, 255, 255, 220))
            label = f"{counts[i]}"
            cf = font(22)
            d.text((bx1 - cf.getlength(label) - 8, by0 - 30), label, font=cf, fill=WHITE)


def _top_bar(d: ImageDraw.ImageDraw, number: int, total: int, right: str = "", timer: Optional[str] = None,
             progress: Optional[float] = None) -> None:
    pill(d, PAD, PAD - 6, f"{number}/{total}")
    if timer:
        pill(d, PAD + 130, PAD - 6, timer)
    if right:
        pill(d, W - PAD, PAD - 6, right, right=True)
    # Progress through the quiz, along the top edge.
    frac = progress if progress is not None else number / max(1, total)
    d.rounded_rectangle((0, 0, W, 8), radius=0, fill=(255, 255, 255, 30))
    d.rounded_rectangle((0, 0, int(W * max(0.0, min(1.0, frac))), 8), radius=0, fill=(140, 82, 255))


def _question_panel(d: ImageDraw.ImageDraw, stem: str, top: int, bottom: int) -> None:
    d.rounded_rectangle((PAD, top, W - PAD, bottom), radius=26, fill=PANEL)
    draw_block(d, (PAD + 40, top + 22, W - PAD - 40, bottom - 22), stem, 50, 20)


def _split(n_options: int) -> int:
    """Where the question panel ends and the tiles begin."""
    return 300 if n_options <= 4 else 250


def question_card(q: dict, number: int, total: int, *, order: Optional[list[int]] = None, right: str = "",
                  timer: Optional[str] = None) -> bytes:
    """The question with blank answer tiles. `order` maps displayed tile -> stored option index."""
    order = order or list(range(len(q["options"])))
    img = background()
    d = ImageDraw.Draw(img, "RGBA")
    _top_bar(d, number, total, right, timer, progress=(number - 1) / max(1, total))
    split = _split(len(order))
    _question_panel(d, q["stem"], 92, split)
    tiles(img, [q["options"][i] for i in order], split + 24)
    return png(img)


def reveal_card(q: dict, number: int, total: int, *, order: Optional[list[int]] = None, chosen: Optional[int] = None,
                counts: Optional[list[int]] = None, right: str = "", banner: Optional[str] = None) -> bytes:
    """The answer screen. `chosen` and `counts` are in displayed order; counts are for live games."""
    order = order or list(range(len(q["options"])))
    correct = order.index(q["correct_index"])
    img = background()
    d = ImageDraw.Draw(img, "RGBA")
    _top_bar(d, number, total, right, progress=number / max(1, total))
    if banner:
        ok = chosen == correct
        colour = GREEN if ok else (RED if chosen is not None else (120, 80, 200))
        bf = font(30)
        bw = int(bf.getlength(banner)) + 60
        x = (W - bw) // 2
        d.rounded_rectangle((x, PAD - 8, x + bw, PAD + 44), radius=26, fill=colour)
        d.text((x + 30, PAD - 4), banner, font=bf, fill=WHITE)
    split = _split(len(order))
    _question_panel(d, q["stem"], 92, split)
    tiles(img, [q["options"][i] for i in order], split + 24, correct=correct, chosen=chosen, counts=counts)
    return png(img)


def podium_card(ranked: list[tuple[str, int]], title: str = "Game over") -> bytes:
    """Top three on a podium, the rest listed underneath."""
    img = background()
    d = ImageDraw.Draw(img, "RGBA")
    tf = font(54)
    d.text(((W - tf.getlength(title)) / 2, 40), title, font=tf, fill=WHITE)
    slots = [(1, 400, 300), (0, 640, 400), (2, 880, 220)]  # rank index, centre x, block height
    bw = 220
    base = 640
    for rank, cx, h in slots:
        if rank >= len(ranked):
            continue
        name, pts = ranked[rank]
        x0, x1 = cx - bw // 2, cx + bw // 2
        y0 = base - h
        d.rounded_rectangle((x0, y0, x1, base), radius=18, fill=(255, 255, 255, 34))
        d.rounded_rectangle((x0, y0, x1, y0 + 14), radius=7, fill=MEDALS[rank])
        mf = font(64)
        num = str(rank + 1)
        d.text(((x0 + x1 - mf.getlength(num)) / 2, y0 + 30), num, font=mf, fill=MEDALS[rank])
        draw_block(d, (x0 - 30, y0 - 96, x1 + 30, y0 - 46), name, 34, 18)
        sf = font(28, bold=False)
        s = f"{pts:,}"
        d.text(((x0 + x1 - sf.getlength(s)) / 2, y0 - 44), s, font=sf, fill=MUTED)
    if not ranked:
        draw_block(d, (PAD, 280, W - PAD, 420), "Nobody answered this time", 44, 24, MUTED)
    rest = ranked[3:8]
    if rest:
        rf = font(24, bold=False)
        line = "   ".join(f"{i + 4}. {clean(n)[:20]} {p:,}" for i, (n, p) in enumerate(rest))
        d.text(((W - rf.getlength(line)) / 2, base + 26), line, font=rf, fill=MUTED)
    return png(img)


def score_card(right: int, total: int, title: str = "Quiz complete") -> bytes:
    """Solo result: an accuracy ring and the score."""
    img = background()
    d = ImageDraw.Draw(img, "RGBA")
    pct = round(100 * right / total) if total else 0
    cx, cy, r = W // 2, 330, 190
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, 40), width=34)
    if pct:
        colour = GREEN if pct >= 70 else (236, 168, 44) if pct >= 40 else RED
        d.arc((cx - r, cy - r, cx + r, cy + r), start=-90, end=-90 + 360 * pct / 100, fill=colour, width=34)
    pf = font(96)
    d.text((cx - pf.getlength(f"{pct}%") / 2, cy - 72), f"{pct}%", font=pf, fill=WHITE)
    sf = font(30, bold=False)
    s = f"{right} of {total} correct"
    d.text((cx - sf.getlength(s) / 2, cy + 42), s, font=sf, fill=MUTED)
    tf = font(48)
    d.text(((W - tf.getlength(title)) / 2, 580), title, font=tf, fill=WHITE)
    return png(img)


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=6)
    return buf.getvalue()
