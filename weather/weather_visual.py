"""
Weather Visual Generator for QLDT Bot.
Creates weather images with a "glanceability" focused design.
Prioritizes: what to bring today (tips) > hour-by-hour (temp, rain, UV) > 7-day outlook.

Everything is drawn at `scale`x and shrunk by `downsample` at the end, which anti-aliases
lines, curves and the hand-drawn icons (PIL draws none of them smoothly on its own).
"""

from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Tuple, List

try:
    from PIL import Image, ImageDraw, ImageFont, ImageChops
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageChops = None
    PIL_AVAILABLE = False

from .weather_service import WeatherData, WMO_CODES, HourlyData

RGB = Tuple[int, int, int]

# Inspirational weather quotes with authors
WEATHER_QUOTES = [
    ("There's no such thing as bad weather, only inappropriate clothing.", "Billy Connolly"),
    ("Sunshine is delicious, rain is refreshing, wind braces us up.", "John Ruskin"),
    ("Climate is what we expect, weather is what we get.", "Mark Twain"),
    ("Some people feel the rain. Others just get wet.", "Bob Marley"),
    ("After rain comes sunshine, after darkness comes light.", "Vietnamese Proverb"),
    ("Life isn't about waiting for the storm to pass, it's about dancing in the rain.", "Vivian Greene"),
    ("The sun will rise and we will try again.", "Twenty One Pilots"),
    ("Every storm runs out of rain.", "Maya Angelou"),
    ("Wherever you go, no matter what the weather, always bring your own sunshine.", "Anthony J. D'Angelo"),
    ("A cloudy day is no match for a sunny disposition.", "William Arthur Ward"),
    ("Into each life some rain must fall.", "Henry Wadsworth Longfellow"),
    ("A little rain never hurt anyone.", "Vietnamese Saying"),
]

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class WeatherVisualConfig:
    """Configuration for weather visuals."""
    dark_mode: bool = True
    width: int = 800
    scale: int = 4       # Drawing resolution (multiples of the 800px layout)
    downsample: int = 2  # Output is shrunk by this much for smooth edges (1600px wide)

    # Dark mode colors
    bg_color: RGB = (24, 26, 31)
    card_bg: RGB = (36, 39, 46)
    lane_bg: RGB = (30, 33, 39)
    text_color: RGB = (255, 255, 255)
    text_secondary: RGB = (170, 175, 185)
    text_muted: RGB = (120, 125, 135)

    # AQI colors (card backgrounds) and the brighter scale colors
    aqi_good: RGB = (30, 75, 40)
    aqi_moderate: RGB = (115, 95, 25)
    aqi_sensitive: RGB = (160, 75, 30)
    aqi_unhealthy: RGB = (145, 40, 40)
    aqi_very_unhealthy: RGB = (105, 40, 105)
    aqi_hazardous: RGB = (90, 30, 30)

    # Chart colors
    temp_color: RGB = (255, 120, 100)
    feels_color: RGB = (255, 185, 120)
    rain_color: RGB = (80, 160, 255)

    # Grid
    grid_color: RGB = (50, 54, 62)

    # Tip accents
    tip_rain: RGB = (80, 160, 255)
    tip_dry: RGB = (110, 200, 130)
    tip_uv: RGB = (240, 175, 60)
    tip_heat: RGB = (255, 110, 90)
    tip_air: RGB = (200, 150, 230)
    tip_wind: RGB = (120, 190, 220)
    tip_storm: RGB = (255, 210, 80)
    tip_neutral: RGB = (150, 155, 165)

    # Icon colors
    sun_color: RGB = (255, 196, 60)
    moon_color: RGB = (215, 220, 235)
    cloud_light: RGB = (205, 212, 225)
    cloud_dark: RGB = (130, 138, 152)
    bolt_color: RGB = (255, 214, 70)


AQI_SCALE: List[Tuple[int, RGB]] = [
    (50, (80, 190, 100)), (100, (235, 200, 60)), (150, (240, 140, 50)),
    (200, (225, 70, 70)), (300, (160, 80, 170)), (500, (130, 40, 50)),
]


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _hhmm_to_hours(text: str) -> Optional[float]:
    try:
        h, m = text.split(":")[:2]
        return int(h) + int(m) / 60
    except (ValueError, AttributeError):
        return None


def _hour_span(hours: List[int]) -> str:
    """[12, 13, 14, 15] -> '12:00–16:00' (end is exclusive, like a schedule)."""
    return f"{hours[0]:02d}:00–{(hours[-1] + 1) % 24:02d}:00"


def _icon_kind(code: int) -> str:
    if code == 0:
        return "clear"
    if code == 1:
        return "mostly_clear"
    if code == 2:
        return "partly"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 57:
        return "drizzle"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "storm"
    return "cloudy"


class WeatherVisualGenerator:
    """Generates weather images with glanceability-focused design."""

    def __init__(self, config: Optional[WeatherVisualConfig] = None):
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is required for weather visuals")
        self.config = config or WeatherVisualConfig()
        self.scale = self.config.scale  # Scale factor for high-DPI rendering

    # ------------------------------------------------------------------ helpers

    def _s(self, value: float) -> int:
        """Scale a value by the scale factor."""
        return int(round(value * self.scale))

    @lru_cache(maxsize=64)
    def _get_font(self, size: float, bold: bool = False) -> "ImageFont.FreeTypeFont":
        """Get a font at the specified size (scaled)."""
        scaled_size = self._s(size)
        font_names = [
            "seguisb.ttf" if bold else "segoeui.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            "Arial Bold.ttf" if bold else "Arial.ttf",
        ]
        for font_name in font_names:
            try:
                return ImageFont.truetype(font_name, scaled_size)
            except (OSError, IOError):
                continue
        try:
            return ImageFont.load_default(scaled_size)
        except TypeError:
            return ImageFont.load_default()

    @lru_cache(maxsize=8)
    def _get_italic_font(self, size: float) -> "ImageFont.FreeTypeFont":
        """Get an italic font for quotes (scaled)."""
        scaled_size = self._s(size)
        for font_name in ["segoeuii.ttf", "DejaVuSans-Oblique.ttf", "georgia.ttf"]:
            try:
                return ImageFont.truetype(font_name, scaled_size)
            except (OSError, IOError):
                continue
        return self._get_font(size, bold=False)

    def _text_w(self, draw, text: str, font) -> int:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    def _finish(self, img: "Image.Image") -> io.BytesIO:
        img = img.convert("RGB")
        d = max(1, self.config.downsample)
        if d > 1:
            img = img.resize((img.width // d, img.height // d), Image.LANCZOS)
        output = io.BytesIO()
        img.save(output, format="PNG", optimize=True)
        output.seek(0)
        return output

    def _overlay(self, img: "Image.Image", painter) -> None:
        """Draw translucent shapes on their own layer, then composite (PIL's in-place alpha drawing
        on RGBA images overwrites what is underneath instead of blending, which is what hid the
        rain bars under the temperature fill before)."""
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        painter(ImageDraw.Draw(layer))
        img.alpha_composite(layer)

    def _gradient_bar(self, img, box, c1: RGB, c2: RGB, radius: int) -> None:
        x0, y0, x1, y1 = [int(v) for v in box]
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        grad = Image.new("RGBA", (w, 1))
        for x in range(w):
            grad.putpixel((x, 0), _mix(c1, c2, x / max(1, w - 1)) + (255,))
        grad = grad.resize((w, h))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        img.paste(grad, (x0, y0), mask)

    # ------------------------------------------------------------------ icons

    def _draw_icon(self, img, code: int, cx: float, cy: float, size: float, night: bool = False) -> None:
        """Hand-drawn weather icon, supersampled so the edges are smooth."""
        ss = 3
        px = max(8, int(size))
        big = px * ss
        layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        kind = _icon_kind(code)
        cfg = self.config

        def sun(x, y, r, rays=True):
            if rays:
                for k in range(8):
                    a = math.pi / 4 * k
                    r1, r2 = r * 1.35, r * 1.75
                    d.line([(x + r1 * math.cos(a), y + r1 * math.sin(a)),
                            (x + r2 * math.cos(a), y + r2 * math.sin(a))],
                           fill=cfg.sun_color, width=max(2, int(r * 0.22)))
            d.ellipse([x - r, y - r, x + r, y + r], fill=cfg.sun_color)

        def moon(x, y, r):
            d.ellipse([x - r, y - r, x + r, y + r], fill=cfg.moon_color)
            o = r * 0.55
            d.ellipse([x - r + o, y - r - o * 0.45, x + r + o, y + r - o * 0.45], fill=(0, 0, 0, 0))

        def cloud(x, y, w, color):
            # x, y = centre of the cloud body; w = total width
            h = w * 0.36
            d.rounded_rectangle([x - w / 2, y - h / 2 + h * 0.15, x + w / 2, y + h / 2 + h * 0.15],
                                radius=h / 2, fill=color)
            r1 = w * 0.22
            d.ellipse([x - w * 0.28 - r1, y - r1 * 0.9 - r1, x - w * 0.28 + r1, y - r1 * 0.9 + r1], fill=color)
            r2 = w * 0.29
            d.ellipse([x + w * 0.06 - r2, y - r2 * 0.85 - r2, x + w * 0.06 + r2, y - r2 * 0.85 + r2], fill=color)

        def drops(x, y, w, n, length, color, slant=0.35, dot=False):
            gap = w / n
            for k in range(n):
                dx = x - w / 2 + gap * (k + 0.5)
                if dot:
                    r = length * 0.28
                    d.ellipse([dx - r, y - r, dx + r, y + r], fill=color)
                    d.ellipse([dx - slant * length - r, y + length - r, dx - slant * length + r, y + length + r],
                              fill=color)
                else:
                    d.line([(dx, y), (dx - slant * length, y + length)], fill=color, width=max(2, int(big * 0.06)))

        b = big
        c = b / 2
        if kind == "clear":
            if night:
                moon(c, c, b * 0.3)
            else:
                sun(c, c, b * 0.24)
        elif kind == "mostly_clear":
            if night:
                moon(c * 0.85, c * 0.85, b * 0.26)
            else:
                sun(c * 0.88, c * 0.85, b * 0.2)
            cloud(c * 1.25, c * 1.38, b * 0.48, cfg.cloud_light)
        elif kind == "partly":
            if night:
                moon(c * 0.72, c * 0.7, b * 0.22)
            else:
                sun(c * 0.72, c * 0.72, b * 0.17)
            cloud(c * 1.08, c * 1.18, b * 0.72, cfg.cloud_light)
        elif kind == "cloudy":
            cloud(c * 1.18, c * 0.92, b * 0.55, cfg.cloud_dark)
            cloud(c * 0.92, c * 1.15, b * 0.78, cfg.cloud_light)
        elif kind == "fog":
            cloud(c, c * 0.8, b * 0.7, cfg.cloud_dark)
            for k, (w, yy) in enumerate([(0.7, 1.33), (0.55, 1.55), (0.68, 1.77)]):
                d.rounded_rectangle([c - b * w / 2, c * yy - b * 0.03, c + b * w / 2, c * yy + b * 0.03],
                                    radius=b * 0.03, fill=cfg.cloud_light)
        elif kind in ("drizzle", "rain", "snow", "storm"):
            dark = kind in ("rain", "storm")
            cloud(c, c * 0.9, b * 0.74, cfg.cloud_dark if dark else cfg.cloud_light)
            if kind == "drizzle":
                drops(c, c * 1.4, b * 0.55, 3, b * 0.12, cfg.rain_color, dot=True)
            elif kind == "rain":
                drops(c, c * 1.3, b * 0.6, 3, b * 0.24, cfg.rain_color)
            elif kind == "snow":
                drops(c, c * 1.4, b * 0.55, 3, b * 0.12, (240, 245, 255), slant=0.0, dot=True)
            else:
                bolt = [(c * 1.05, c * 1.1), (c * 0.78, c * 1.52), (c * 0.98, c * 1.52),
                        (c * 0.85, c * 1.92), (c * 1.25, c * 1.38), (c * 1.03, c * 1.38), (c * 1.18, c * 1.1)]
                d.polygon(bolt, fill=cfg.bolt_color)
                drops(c * 1.3, c * 1.35, b * 0.2, 1, b * 0.16, cfg.rain_color)
                drops(c * 0.62, c * 1.35, b * 0.2, 1, b * 0.16, cfg.rain_color)

        layer = layer.resize((px, px), Image.LANCZOS)
        img.alpha_composite(layer, (int(cx - px / 2), int(cy - px / 2)))

    # ------------------------------------------------------------------ data

    def _is_night(self, weather: WeatherData, hour: float) -> bool:
        today = weather.today
        rise = _hhmm_to_hours(today.sunrise) if today else None
        sset = _hhmm_to_hours(today.sunset) if today else None
        if rise is None or sset is None:
            return hour < 6 or hour >= 18
        return hour < rise or hour >= sset

    def _tips(self, weather: WeatherData) -> List[Tuple[str, str, RGB]]:
        """'What to bring' tips: (title, detail, accent)."""
        cfg = self.config
        tips: List[Tuple[str, str, RGB]] = []
        today = weather.today
        hourly = weather.hourly

        if hourly and hourly.hours:
            hours, probs = hourly.hours, hourly.precipitation_probs
            peak_i = max(range(len(probs)), key=lambda i: probs[i])
            peak = probs[peak_i]

            storm_hours = [h for h, c in zip(hours, hourly.weather_codes) if c >= 95]
            if storm_hours:
                tips.append(("Thunderstorms", f"around {storm_hours[0]:02d}:00", cfg.tip_storm))

            if peak >= 30:
                wet = [h for h, p in zip(hours, probs) if p >= max(30, peak * 0.6)]
                # Longest consecutive run that contains the peak
                run = [hours[peak_i]]
                for h in sorted(wet):
                    if h == run[-1] + 1:
                        run.append(h)
                for h in sorted(wet, reverse=True):
                    if h == run[0] - 1:
                        run.insert(0, h)
                mm = sum(hourly.precipitation)
                amount = f", ~{mm:.0f} mm" if mm >= 1 else ""
                tips.append(("Bring an umbrella",
                             f"{_hour_span(run)}, peak {peak}% at {hours[peak_i]:02d}:00{amount}", cfg.tip_rain))
            elif peak >= 10:
                tips.append(("Small rain chance", f"up to {peak}% at {hours[peak_i]:02d}:00", cfg.tip_neutral))
            else:
                tips.append(("Dry day", "no rain expected", cfg.tip_dry))

            feels = hourly.apparent_temperatures
            hot_i = max(range(len(feels)), key=lambda i: feels[i])
            if feels[hot_i] >= 35:
                tips.append(("Drink water", f"feels like {feels[hot_i]:.0f}° at {hours[hot_i]:02d}:00", cfg.tip_heat))
            elif min(hourly.temperatures) <= 15:
                tips.append(("Bring a jacket", f"down to {min(hourly.temperatures):.0f}°", cfg.tip_wind))

            uvs = hourly.uv_indices
            uv_i = max(range(len(uvs)), key=lambda i: uvs[i])
            if uvs[uv_i] >= 6:
                strong = [h for h, u in zip(hours, uvs) if u >= 6]
                label = "Very high UV" if uvs[uv_i] >= 8 else "Sunscreen"
                tips.append((label, f"UV {uvs[uv_i]:.0f}, {_hour_span(strong)}", cfg.tip_uv))
        elif today:
            if today.precipitation_prob >= 30:
                tips.append(("Bring an umbrella", f"{today.precipitation_prob}% chance", cfg.tip_rain))
            if today.uv_index_max >= 6:
                tips.append(("Sunscreen", f"UV {today.uv_index_max:.0f}", cfg.tip_uv))

        if weather.air_quality and weather.air_quality.aqi > 100:
            tips.append(("Wear a mask", f"AQI {weather.air_quality.aqi}", cfg.tip_air))

        if today and today.wind_speed_max >= 30:
            tips.append(("Windy", f"gusts to {today.wind_speed_max:.0f} km/h {today.wind_direction_str}", cfg.tip_wind))

        if today:
            rise, sset = _hhmm_to_hours(today.sunrise), _hhmm_to_hours(today.sunset)
            if rise is not None and sset is not None:
                length = sset - rise
                tips.append((f"Sunset {today.sunset}", f"{int(length)}h {int(round(length % 1 * 60)):02d}m of daylight",
                             cfg.tip_neutral))
        return tips

    # ------------------------------------------------------------------ today

    def generate_today_image(self, weather: WeatherData) -> io.BytesIO:
        """Generate today's weather image."""
        cfg = self.config
        s = self._s

        width = s(cfg.width)
        padding = s(20)

        # Measure the tips first: they wrap to as many rows as they need.
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        tips = self._tips(weather)
        tip_rows = self._layout_tips(probe, tips)

        hero_height = s(132)
        tips_height = len(tip_rows) * s(40) if tip_rows else 0
        chart_height = s(300) if weather.hourly else 0
        quote_height = s(64)
        footer_height = s(34)
        height = padding + hero_height + s(16) + tips_height + s(8) + chart_height + quote_height + footer_height

        img = Image.new("RGBA", (width, height), cfg.bg_color + (255,))
        draw = ImageDraw.Draw(img)

        y = padding
        self._draw_hero_header(img, draw, weather, y, hero_height)
        y += hero_height + s(16)

        y = self._draw_tips(draw, tip_rows, y)
        y += s(8)

        if weather.hourly:
            self._draw_hourly_chart(img, draw, weather, y, chart_height)
            y += chart_height

        self._draw_quote(draw, y, quote_height)
        self._draw_footer(draw, weather, height - footer_height)
        return self._finish(img)

    def _draw_hero_header(self, img, draw, weather: WeatherData, y: int, height: int) -> None:
        """Icon + temperature + stats on the left, AQI with its scale on the right."""
        cfg = self.config
        s = self._s
        padding = s(20)
        aqi_width = s(170)
        card_x = padding
        card_r = s(cfg.width) - padding - aqi_width - s(12)
        current = weather.current
        today = weather.today

        draw.rounded_rectangle([card_x, y, card_r, y + height], radius=s(16), fill=cfg.card_bg)

        night = self._is_night(weather, weather.fetched_at.hour + weather.fetched_at.minute / 60)
        self._draw_icon(img, current.weather_code, card_x + s(58), y + s(56), s(76), night=night)

        temp_font = self._get_font(50, bold=True)
        temp_text = f"{current.temperature:.0f}°"
        tx = card_x + s(108)
        draw.text((tx, y + s(56)), temp_text, fill=cfg.text_color, font=temp_font, anchor="lm")
        dx = tx + self._text_w(draw, temp_text, temp_font) + s(18)

        draw.text((dx, y + s(38)), current.weather_description, fill=cfg.text_color,
                  font=self._get_font(17, bold=True), anchor="lm")
        feels = f"Feels like {current.apparent_temperature:.0f}°"
        if today:
            feels += f"   ·   High {today.temp_max:.0f}°  Low {today.temp_min:.0f}°"
        draw.text((dx, y + s(64)), feels, fill=cfg.text_secondary, font=self._get_font(13), anchor="lm")

        # Stat row along the bottom of the card
        stats = [("Humidity", f"{current.humidity}%"),
                 ("Wind", f"{current.wind_speed:.0f} km/h {self._compass(current.wind_direction)}")]
        if today:
            stats.append(("Rain", f"{today.precipitation_prob}%" +
                          (f" · {today.precipitation_sum:.1f} mm" if today.precipitation_sum >= 0.1 else "")))
            stats.append(("UV", f"{today.uv_index_max:.0f} {today.uv_category[0].lower()}"))
        sx = card_x + s(22)
        sy = y + height - s(24)
        label_font, value_font = self._get_font(10), self._get_font(11.5, bold=True)
        for label, value in stats:
            draw.text((sx, sy), label, fill=cfg.text_muted, font=label_font, anchor="lm")
            sx += self._text_w(draw, label, label_font) + s(6)
            draw.text((sx, sy), value, fill=cfg.text_secondary, font=value_font, anchor="lm")
            sx += self._text_w(draw, value, value_font) + s(20)

        draw.text((card_r - s(18), y + s(20)), weather.location, fill=cfg.text_muted,
                  font=self._get_font(11), anchor="rm")

        # === AQI card ===
        ax = card_r + s(12)
        ar = ax + aqi_width
        aq = weather.air_quality
        if not aq:
            draw.rounded_rectangle([ax, y, ar, y + height], radius=s(16), fill=cfg.card_bg)
            draw.text(((ax + ar) // 2, y + height // 2), "AQI N/A", fill=cfg.text_secondary,
                      font=self._get_font(18, bold=True), anchor="mm")
            return

        bg, msg = self._get_aqi_style(aq.aqi)
        draw.rounded_rectangle([ax, y, ar, y + height], radius=s(16), fill=bg)
        num_font, small_bold = self._get_font(40, bold=True), self._get_font(12, bold=True)
        num = str(aq.aqi)
        nw = self._text_w(draw, num, num_font)
        lw = self._text_w(draw, "AQI", small_bold)
        nx = (ax + ar - nw - lw - s(6)) // 2
        draw.text((nx, y + s(36)), num, fill=(255, 255, 255), font=num_font, anchor="lm")
        draw.text((nx + nw + s(6), y + s(44)), "AQI", fill=(255, 255, 255), font=small_bold, anchor="lm")
        draw.text(((ax + ar) // 2, y + s(72)), msg, fill=(255, 255, 255), font=small_bold, anchor="mm")

        # Scale: six coloured segments 0-300 with a marker at today's value
        bx0, bx1, by = ax + s(16), ar - s(16), y + s(92)
        seg_edges = [0, 50, 100, 150, 200, 300]
        span = bx1 - bx0
        for i, (top, color) in enumerate(AQI_SCALE[:5]):
            lo = seg_edges[i]
            x0 = bx0 + span * lo / 300
            x1 = bx0 + span * top / 300
            draw.rectangle([x0 + (s(1) if i else 0), by, x1, by + s(5)], fill=color)
        mx = bx0 + span * min(aq.aqi, 300) / 300
        draw.polygon([(mx - s(5), by - s(7)), (mx + s(5), by - s(7)), (mx, by - s(1))], fill=(255, 255, 255))
        draw.text(((ax + ar) // 2, y + s(114)), f"PM2.5 {aq.pm2_5:.0f} · PM10 {aq.pm10:.0f} µg/m³",
                  fill=(235, 235, 235), font=self._get_font(9.5), anchor="mm")

    @staticmethod
    def _compass(deg: float) -> str:
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return directions[round((deg or 0) / 45) % 8]

    def _get_aqi_style(self, aqi: int) -> Tuple[RGB, str]:
        """Get AQI background color and status message."""
        cfg = self.config
        if aqi <= 50:
            return cfg.aqi_good, "Good"
        elif aqi <= 100:
            return cfg.aqi_moderate, "Moderate"
        elif aqi <= 150:
            return cfg.aqi_sensitive, "Unhealthy for Some"
        elif aqi <= 200:
            return cfg.aqi_unhealthy, "Unhealthy - Mask Up"
        elif aqi <= 300:
            return cfg.aqi_very_unhealthy, "Very Unhealthy"
        else:
            return cfg.aqi_hazardous, "Hazardous!"

    def _layout_tips(self, draw, tips) -> List[List[Tuple[str, str, RGB, int]]]:
        s = self._s
        max_x = s(self.config.width) - s(20)
        title_font, detail_font = self._get_font(12, bold=True), self._get_font(11)
        rows: List[List[Tuple[str, str, RGB, int]]] = []
        x = s(20)
        for title, detail, color in tips:
            w = s(26) + self._text_w(draw, title, title_font) + s(8) + self._text_w(draw, detail, detail_font) + s(12)
            if not rows or x + w > max_x:
                rows.append([])
                x = s(20)
            rows[-1].append((title, detail, color, w))
            x += w + s(8)
        return rows

    def _draw_tips(self, draw, rows, y: int) -> int:
        cfg = self.config
        s = self._s
        title_font, detail_font = self._get_font(12, bold=True), self._get_font(11)
        h = s(32)
        for row in rows:
            x = s(20)
            for title, detail, color, w in row:
                draw.rounded_rectangle([x, y, x + w, y + h], radius=s(9), fill=_mix(cfg.bg_color, color, 0.16))
                draw.ellipse([x + s(11), y + h / 2 - s(4), x + s(19), y + h / 2 + s(4)], fill=color)
                tx = x + s(26)
                draw.text((tx, y + h / 2), title, fill=_mix(color, (255, 255, 255), 0.55), font=title_font, anchor="lm")
                tx += self._text_w(draw, title, title_font) + s(8)
                draw.text((tx, y + h / 2), detail, fill=cfg.text_secondary, font=detail_font, anchor="lm")
                x += w + s(8)
            y += s(40)
        return y

    def _draw_hourly_chart(self, img, draw, weather: WeatherData, y: int, height: int) -> None:
        """Three lanes on one time axis: temperature (+ feels like), rain chance, UV.
        Each lane has its own space, so nothing covers anything else."""
        cfg = self.config
        s = self._s
        hourly: HourlyData = weather.hourly
        hours = hourly.hours
        n = len(hours)
        padding = s(20)

        left = padding + s(52)
        right = s(cfg.width) - padding - s(8)
        step = (right - left) / max(1, n - 1)

        def hx(i: float) -> float:
            return left + step * i

        # Title + legend
        draw.text((padding, y + s(12)), "Hour by hour", fill=cfg.text_color, font=self._get_font(14, bold=True),
                  anchor="lm")
        legend_font = self._get_font(10.5)
        lx = right
        for label, kind, color in [("Rain chance", "box", cfg.rain_color), ("Feels like", "dash", cfg.feels_color),
                                   ("Temp", "line", cfg.temp_color)]:
            tw = self._text_w(draw, label, legend_font)
            draw.text((lx, y + s(12)), label, fill=cfg.text_secondary, font=legend_font, anchor="rm")
            sx = lx - tw - s(22)
            if kind == "box":
                draw.rounded_rectangle([sx, y + s(8), sx + s(14), y + s(16)], radius=s(2), fill=cfg.rain_color)
            elif kind == "dash":
                draw.line([(sx, y + s(12)), (sx + s(5), y + s(12))], fill=color, width=s(2))
                draw.line([(sx + s(9), y + s(12)), (sx + s(14), y + s(12))], fill=color, width=s(2))
            else:
                draw.line([(sx, y + s(12)), (sx + s(14), y + s(12))], fill=color, width=s(3))
            lx = sx - s(18)

        icon_y = y + s(44)
        temp_top, temp_bot = y + s(74), y + s(178)
        rain_top, rain_bot = y + s(196), y + s(248)
        uv_top, uv_bot = y + s(256), y + s(270)
        axis_y = y + s(286)

        # Night shading + "now" marker go under everything
        def shade(d):
            for i, h in enumerate(hours):
                if self._is_night(weather, h + 0.5):
                    x0, x1 = max(left - step / 2, hx(i) - step / 2), min(right + step / 2, hx(i) + step / 2)
                    d.rectangle([x0, icon_y - s(18), x1, uv_bot], fill=(0, 0, 10, 70))
        self._overlay(img, shade)

        today = weather.today
        sunset = _hhmm_to_hours(today.sunset) if today else None
        if sunset is not None and hours[0] <= sunset <= hours[-1]:
            sx = hx(sunset - hours[0])
            draw.line([(sx, temp_top - s(4)), (sx, uv_bot)], fill=(90, 80, 70), width=s(1))
            draw.text((sx + s(4), temp_top - s(2)), f"sunset {today.sunset}", fill=(170, 140, 110),
                      font=self._get_font(9), anchor="lt")

        now_h = weather.fetched_at.hour + weather.fetched_at.minute / 60
        if hours[0] <= now_h <= hours[-1]:
            nx = hx(now_h - hours[0])
            for yy in range(int(temp_top - s(4)), int(temp_bot), s(6)):
                draw.line([(nx, yy), (nx, yy + s(3))], fill=(200, 205, 215), width=s(1))
            draw.text((nx, temp_top - s(6)), "now", fill=cfg.text_color, font=self._get_font(9, bold=True),
                      anchor="mb")

        # Icons every 3 hours
        for i, h in enumerate(hours):
            if h % 3 == 0:
                self._draw_icon(img, hourly.weather_codes[i], hx(i), icon_y, s(24),
                                night=self._is_night(weather, h + 0.5))

        # --- Temperature lane
        temps = hourly.temperatures
        feels = hourly.apparent_temperatures
        t_lo = min(min(temps), min(feels)) - 1
        t_hi = max(max(temps), max(feels)) + 1.5
        t_rng = max(1.0, t_hi - t_lo)

        def ty(t: float) -> float:
            return temp_bot - (t - t_lo) / t_rng * (temp_bot - temp_top)

        label_font = self._get_font(9.5)
        for k in range(3):
            val = t_lo + t_rng * k / 2
            gy = ty(val)
            draw.line([(left, gy), (right, gy)], fill=cfg.grid_color, width=s(1))
            draw.text((left - step / 2 - s(6), gy), f"{val:.0f}°", fill=cfg.text_muted, font=label_font, anchor="rm")

        temp_pts = self._smooth([(hx(i), ty(t)) for i, t in enumerate(temps)])
        feels_pts = self._smooth([(hx(i), ty(t)) for i, t in enumerate(feels)])

        # Soft fill under the temperature line, bounded by the line itself
        fill = Image.new("RGBA", img.size, (0, 0, 0, 0))
        grad = Image.new("L", (1, 256))
        for k in range(256):
            grad.putpixel((0, k), int(95 * (1 - k / 255)))
        lane_h = int(temp_bot - temp_top) + 1
        alpha = Image.new("L", img.size, 0)
        alpha.paste(grad.resize((img.width, lane_h)), (0, int(temp_top)))
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon(temp_pts + [(temp_pts[-1][0], temp_bot), (temp_pts[0][0], temp_bot)], fill=255)
        fill.paste(Image.new("RGBA", img.size, cfg.temp_color + (255,)), (0, 0), ImageChops.multiply(alpha, mask))
        img.alpha_composite(fill)

        # Feels-like dashed line, then the temperature line on top
        for k in range(0, len(feels_pts) - 1, 4):
            draw.line(feels_pts[k:k + 3], fill=cfg.feels_color, width=s(1.5))
        draw.line(temp_pts, fill=cfg.temp_color, width=s(2.5), joint="curve")

        hi_i = max(range(n), key=lambda i: temps[i])
        lo_i = min(range(n), key=lambda i: temps[i])
        value_font, value_bold = self._get_font(10), self._get_font(11, bold=True)
        for i, t in enumerate(temps):
            if i in (hi_i, lo_i) or (hours[i] % 3 == 0 and abs(i - hi_i) > 1 and abs(i - lo_i) > 1):
                px, py = hx(i), ty(t)
                r = s(3.5) if i == hi_i else s(2.5)
                draw.ellipse([px - r, py - r, px + r, py + r], fill=cfg.temp_color, outline=cfg.bg_color, width=s(1))
                font = value_bold if i == hi_i else value_font
                color = cfg.text_color if i == hi_i else cfg.text_secondary
                draw.text((px, py - s(9)), f"{t:.0f}°", fill=color, font=font, anchor="mb")

        # --- Rain lane
        draw.rounded_rectangle([left - step / 2, rain_top, right + step / 2, rain_bot], radius=s(6), fill=cfg.lane_bg)
        draw.text((left - step / 2 - s(6), (rain_top + rain_bot) / 2), "Rain", fill=cfg.text_muted, font=label_font,
                  anchor="rm")
        probs = hourly.precipitation_probs
        mm = hourly.precipitation
        bar_w = step * 0.62
        inner_top = rain_top + s(14)
        pct_font, pct_bold = self._get_font(9), self._get_font(9.5, bold=True)
        peak_i = max(range(n), key=lambda i: probs[i])
        for i, p in enumerate(probs):
            x = hx(i)
            if p <= 0:
                draw.line([(x - bar_w / 2, rain_bot - s(3)), (x + bar_w / 2, rain_bot - s(3))],
                          fill=cfg.grid_color, width=s(1))
                continue
            top = rain_bot - s(3) - (rain_bot - s(3) - inner_top) * p / 100
            color = _mix(cfg.lane_bg, cfg.rain_color, 0.35 + 0.65 * p / 100)
            draw.rounded_rectangle([x - bar_w / 2, top, x + bar_w / 2, rain_bot - s(3)], radius=s(2), fill=color)
            if mm[i] >= 0.5:  # a measurable amount: a brighter cap on the bar
                draw.rounded_rectangle([x - bar_w / 2, top, x + bar_w / 2, top + s(3)], radius=s(1),
                                       fill=(190, 225, 255))
            if p >= 10:
                draw.text((x, top - s(2)), f"{p}", fill=cfg.text_color if i == peak_i else cfg.text_secondary,
                          font=pct_bold if i == peak_i else pct_font, anchor="mb")

        # --- UV lane
        draw.text((left - step / 2 - s(6), (uv_top + uv_bot) / 2), "UV", fill=cfg.text_muted, font=label_font, anchor="rm")
        uv_font = self._get_font(8.5, bold=True)
        for i, u in enumerate(hourly.uv_indices):
            x = hx(i)
            color = self._get_uv_color(u) if u >= 0.5 else cfg.lane_bg
            if 0.5 <= u < 3:
                color = _mix(cfg.lane_bg, color, 0.7)
            draw.rounded_rectangle([x - step / 2 + s(1), uv_top, x + step / 2 - s(1), uv_bot], radius=s(3), fill=color)
            if u >= 2.5:
                draw.text((x, (uv_top + uv_bot) / 2), f"{u:.0f}", fill=(25, 25, 30), font=uv_font, anchor="mm")

        # --- Hour axis
        axis_font, axis_bold = self._get_font(9), self._get_font(9.5, bold=True)
        for i, h in enumerate(hours):
            if h % 3 == 0:
                draw.text((hx(i), axis_y), f"{h:02d}:00", fill=cfg.text_secondary, font=axis_bold, anchor="mm")
            elif n <= 20:
                draw.text((hx(i), axis_y), f"{h:02d}", fill=cfg.text_muted, font=axis_font, anchor="mm")

    def _smooth(self, pts: List[Tuple[float, float]], steps: int = 10) -> List[Tuple[float, float]]:
        """Catmull-Rom through the points, with y clamped to the neighbours so it never overshoots."""
        if len(pts) < 3:
            return pts
        out = []
        for i in range(len(pts) - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1, p2 = pts[i], pts[i + 1]
            p3 = pts[i + 2] if i + 2 < len(pts) else p2
            lo, hi = min(p1[1], p2[1]), max(p1[1], p2[1])
            for k in range(steps):
                t = k / steps
                t2, t3 = t * t, t * t * t
                x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                           + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
                yv = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                            + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
                out.append((x, min(hi, max(lo, yv))))
        out.append(pts[-1])
        return out

    def _draw_quote(self, draw, y: int, height: int) -> None:
        """Draw an inspirational quote with author."""
        cfg = self.config
        s = self._s
        quote, author = random.choice(WEATHER_QUOTES)
        cx = s(cfg.width) // 2
        draw.text((cx, y + s(24)), f"“{quote}”", fill=(180, 185, 195), font=self._get_italic_font(13), anchor="mm")
        draw.text((cx, y + s(46)), f"— {author}", fill=cfg.text_muted, font=self._get_font(10.5), anchor="mm")

    def _draw_footer(self, draw, weather: WeatherData, y: int) -> None:
        """Draw footer."""
        cfg = self.config
        s = self._s
        padding = s(20)
        footer_font = self._get_font(10)
        timestamp = weather.fetched_at.strftime("%H:%M %d/%m/%Y")
        draw.text((padding, y + s(17)), f"Data from Open-Meteo · {timestamp}", fill=cfg.text_muted,
                  font=footer_font, anchor="lm")
        draw.text((s(cfg.width) - padding, y + s(17)), "made with <3 by namesn_pe", fill=cfg.text_muted,
                  font=footer_font, anchor="rm")

    # ------------------------------------------------------------------ week

    def generate_week_image(self, weather: WeatherData) -> io.BytesIO:
        """7-day forecast: one row per day, temperatures on a shared week scale."""
        cfg = self.config
        s = self._s

        day_height = s(66)
        header_height = s(30)
        footer_height = s(34)
        days = weather.week
        width = s(cfg.width)
        height = header_height + day_height * len(days) + footer_height

        img = Image.new("RGBA", (width, height), cfg.bg_color + (255,))
        draw = ImageDraw.Draw(img)

        # Columns
        col_icon = s(34)
        col_day = s(64)
        col_tmin = s(262)       # right edge of the low label
        bar_x0, bar_x1 = s(272), s(452)
        col_tmax = s(462)
        col_rain = s(512)
        col_wind = s(618)
        col_uv = s(706)

        head_font = self._get_font(9.5, bold=True)
        hy = header_height // 2 + s(2)
        for x, label, anchor in [(col_day, "DAY", "lm"), ((bar_x0 + bar_x1) // 2, "LOW · HIGH", "mm"),
                                 (col_rain, "RAIN", "lm"), (col_wind, "WIND", "lm"), (col_uv, "UV", "lm")]:
            draw.text((x, hy), label, fill=cfg.text_muted, font=head_font, anchor=anchor)

        w_lo = min(d.temp_min for d in days) - 1
        w_hi = max(d.temp_max for d in days) + 1
        w_rng = max(1.0, w_hi - w_lo)

        def bx(t: float) -> float:
            return bar_x0 + (bar_x1 - bar_x0) * (t - w_lo) / w_rng

        day_font = self._get_font(14, bold=True)
        desc_font = self._get_font(10.5)
        val_font = self._get_font(15, bold=True)
        sub_font = self._get_font(9.5)
        temp_font = self._get_font(13, bold=True)

        y = header_height
        for i, day in enumerate(days):
            is_today = i == 0
            if is_today:
                draw.rectangle([0, y, width, y + day_height], fill=_mix(cfg.card_bg, (80, 120, 200), 0.12))
                draw.rectangle([0, y, s(4), y + day_height], fill=(110, 160, 255))
            elif i % 2 == 0:
                draw.rectangle([0, y, width, y + day_height], fill=cfg.card_bg)
            mid = y + day_height / 2

            self._draw_icon(img, day.weather_code, col_icon, mid, s(38))

            label = "Today" if is_today else DAY_NAMES[day.date.weekday()]
            draw.text((col_day, mid - s(10)), label, fill=cfg.text_color, font=day_font, anchor="lm")
            lw = self._text_w(draw, label, day_font)
            draw.text((col_day + lw + s(8), mid - s(9)), day.date.strftime("%d/%m"), fill=cfg.text_muted,
                      font=desc_font, anchor="lm")
            # An alert (very hot, heavy rain…) takes the description's place; the icon still shows the sky.
            alerts = day.is_unusual()
            if alerts:
                text = alerts[0].split(" ", 1)[1] if " " in alerts[0] else alerts[0]
                draw.text((col_day, mid + s(11)), text, fill=(255, 200, 100), font=desc_font, anchor="lm")
            else:
                draw.text((col_day, mid + s(11)), day.weather_description, fill=cfg.text_secondary,
                          font=desc_font, anchor="lm")

            # Temperature range on the shared week scale
            draw.rounded_rectangle([bar_x0, mid - s(3), bar_x1, mid + s(3)], radius=s(3), fill=cfg.grid_color)
            x0, x1 = bx(day.temp_min), bx(day.temp_max)
            self._gradient_bar(img, (x0, mid - s(3), max(x1, x0 + s(6)), mid + s(3)),
                               self._temp_to_color(day.temp_min), self._temp_to_color(day.temp_max), s(3))
            if is_today:
                cx = bx(min(max(weather.current.temperature, w_lo), w_hi))
                draw.ellipse([cx - s(5), mid - s(5), cx + s(5), mid + s(5)], fill=(255, 255, 255),
                             outline=cfg.bg_color, width=s(2))
            draw.text((col_tmin, mid), f"{day.temp_min:.0f}°", fill=cfg.text_secondary, font=temp_font, anchor="rm")
            draw.text((col_tmax, mid), f"{day.temp_max:.0f}°", fill=cfg.text_color, font=temp_font, anchor="lm")

            # Rain: chance, a small meter, and the amount
            p = day.precipitation_prob
            rain_col = cfg.rain_color if p >= 50 else cfg.text_secondary
            draw.text((col_rain, mid - s(9)), f"{p}%", fill=rain_col, font=val_font, anchor="lm")
            mx0, mx1 = col_rain + s(48), col_rain + s(88)
            draw.rounded_rectangle([mx0, mid - s(11), mx1, mid - s(7)], radius=s(2), fill=cfg.grid_color)
            if p > 0:
                draw.rounded_rectangle([mx0, mid - s(11), mx0 + (mx1 - mx0) * p / 100, mid - s(7)], radius=s(2),
                                       fill=_mix(cfg.grid_color, cfg.rain_color, 0.4 + 0.6 * p / 100))
            amount = f"{day.precipitation_sum:.1f} mm" if day.precipitation_sum >= 0.1 else "0 mm"
            draw.text((col_rain, mid + s(12)), amount, fill=cfg.text_muted, font=sub_font, anchor="lm")

            # Wind
            wind_col = cfg.tip_wind if day.wind_speed_max >= 30 else cfg.text_secondary
            draw.text((col_wind, mid - s(9)), f"{day.wind_speed_max:.0f}", fill=wind_col, font=val_font, anchor="lm")
            draw.text((col_wind, mid + s(12)), f"km/h {self._compass(day.wind_direction)}", fill=cfg.text_muted,
                      font=sub_font, anchor="lm")

            # UV pill
            uv = day.uv_index_max
            pill_col = self._get_uv_color(uv)
            draw.rounded_rectangle([col_uv, mid - s(19), col_uv + s(30), mid + s(1)], radius=s(10), fill=pill_col)
            draw.text((col_uv + s(15), mid - s(9)), f"{uv:.0f}", fill=(25, 25, 30), font=self._get_font(12, bold=True),
                      anchor="mm")
            draw.text((col_uv, mid + s(12)), day.uv_category[0], fill=cfg.text_muted, font=sub_font, anchor="lm")

            y += day_height

        self._draw_footer(draw, weather, height - footer_height)
        return self._finish(img)

    def _temp_to_color(self, temp: float) -> RGB:
        if temp <= 15:
            return (100, 150, 255)
        elif temp <= 25:
            t = (temp - 15) / 10
            return (int(100 + 155 * t), int(150 + 105 * t), int(255 - 155 * t))
        elif temp <= 35:
            t = (temp - 25) / 10
            return (255, int(255 - 155 * t), int(100 - 100 * t))
        else:
            return (255, 80, 80)

    def _get_uv_color(self, uv: float) -> RGB:
        uv = round(uv or 0)  # colour by the number that is printed
        if uv <= 2:
            return (100, 200, 100)
        elif uv <= 5:
            return (255, 200, 100)
        elif uv <= 7:
            return (255, 150, 50)
        elif uv <= 10:
            return (255, 80, 80)
        else:
            return (200, 100, 200)
