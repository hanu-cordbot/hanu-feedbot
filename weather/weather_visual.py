"""
Weather Visual Generator for QLDT Bot.
Creates weather images with a "glanceability" focused design.
Prioritizes: AQI & Rain (immediate) > Hourly temp (short term) > 7-day (long term)
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple, List

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    PIL_AVAILABLE = False

from .weather_service import WeatherData, WMO_CODES, HourlyData

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


@dataclass
class WeatherVisualConfig:
    """Configuration for weather visuals."""
    dark_mode: bool = True
    width: int = 800

    # Dark mode colors
    bg_color: Tuple[int, int, int] = (24, 26, 31)
    card_bg: Tuple[int, int, int] = (36, 39, 46)
    text_color: Tuple[int, int, int] = (255, 255, 255)
    text_secondary: Tuple[int, int, int] = (170, 175, 185)
    text_muted: Tuple[int, int, int] = (120, 125, 135)

    # AQI colors
    aqi_good: Tuple[int, int, int] = (30, 75, 40)
    aqi_moderate: Tuple[int, int, int] = (115, 95, 25)
    aqi_sensitive: Tuple[int, int, int] = (160, 75, 30)
    aqi_unhealthy: Tuple[int, int, int] = (145, 40, 40)
    aqi_very_unhealthy: Tuple[int, int, int] = (105, 40, 105)
    aqi_hazardous: Tuple[int, int, int] = (90, 30, 30)

    # Chart colors
    temp_color: Tuple[int, int, int] = (255, 120, 100)
    rain_color: Tuple[int, int, int] = (80, 160, 255)

    # Grid
    grid_color: Tuple[int, int, int] = (50, 54, 62)

    # Badge colors
    badge_neutral: Tuple[int, int, int] = (55, 60, 70)
    badge_wind_storm: Tuple[int, int, int] = (70, 130, 180)
    badge_uv: Tuple[int, int, int] = (180, 130, 40)
    badge_storm: Tuple[int, int, int] = (180, 80, 80)
    badge_rain: Tuple[int, int, int] = (60, 120, 200)


class WeatherVisualGenerator:
    """Generates weather images with glanceability-focused design."""

    def __init__(self, config: Optional[WeatherVisualConfig] = None):
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is required for weather visuals")
        self.config = config or WeatherVisualConfig()

    def _get_font(self, size: int, bold: bool = False) -> "ImageFont.FreeTypeFont":
        """Get a font at the specified size."""
        font_names = [
            "seguisb.ttf" if bold else "segoeui.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            "Arial Bold.ttf" if bold else "Arial.ttf",
        ]
        for font_name in font_names:
            try:
                return ImageFont.truetype(font_name, size)
            except (OSError, IOError):
                continue
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _get_italic_font(self, size: int) -> "ImageFont.FreeTypeFont":
        """Get an italic font for quotes."""
        font_names = ["segoeuii.ttf", "segoeui.ttf", "DejaVuSans-Oblique.ttf", "georgia.ttf"]
        for font_name in font_names:
            try:
                return ImageFont.truetype(font_name, size)
            except (OSError, IOError):
                continue
        return self._get_font(size, bold=False)

    def generate_today_image(self, weather: WeatherData) -> io.BytesIO:
        """Generate today's weather image."""
        cfg = self.config

        # Calculate dimensions
        hero_height = 120
        badges_height = 50
        chart_height = 220
        quote_height = 70
        footer_height = 35
        padding = 20

        height = hero_height + badges_height + chart_height + quote_height + footer_height + padding * 3

        img = Image.new('RGBA', (cfg.width, height), cfg.bg_color + (255,))
        draw = ImageDraw.Draw(img, 'RGBA')

        current_y = padding

        # Hero header
        current_y = self._draw_hero_header(draw, weather, current_y, hero_height)
        current_y += 15

        # Condition badges
        current_y = self._draw_condition_badges(draw, weather, current_y, badges_height)
        current_y += 10

        # Chart (full 24h)
        if weather.hourly:
            current_y = self._draw_combined_chart(draw, img, weather, current_y, chart_height)
        current_y += 15

        # Quote
        current_y = self._draw_quote(draw, current_y, quote_height)

        # Footer
        self._draw_footer(draw, weather, height - footer_height)

        # Convert to RGB
        rgb_img = Image.new('RGB', img.size, cfg.bg_color)
        rgb_img.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)

        output = io.BytesIO()
        rgb_img.save(output, format='PNG', optimize=True)
        output.seek(0)
        return output

    def _draw_hero_header(self, draw, weather: WeatherData, y: int, height: int) -> int:
        """Draw split hero header - temp+desc spanning left, AQI on right."""
        cfg = self.config
        padding = 20

        # AQI card is fixed width on right
        aqi_width = 160
        weather_width = cfg.width - aqi_width - padding * 3

        # === LEFT: Weather Card (spans most of width) ===
        weather_card_x = padding
        draw.rounded_rectangle(
            [weather_card_x, y, weather_card_x + weather_width, y + height],
            radius=16,
            fill=cfg.card_bg
        )

        # Big temperature on left
        temp_font = self._get_font(52, bold=True)
        temp_text = f"{weather.current.temperature:.0f}°C"
        draw.text((weather_card_x + 25, y + 25), temp_text, fill=cfg.text_color, font=temp_font)

        # Get temp text width for positioning desc to the right
        try:
            bbox = draw.textbbox((0, 0), temp_text, font=temp_font)
            temp_width = bbox[2] - bbox[0]
        except:
            temp_width = 100

        # Description and location to the RIGHT of temperature
        desc_x = weather_card_x + 45 + temp_width
        desc_font = self._get_font(16)
        loc_font = self._get_font(13)

        # Weather description
        desc_text = weather.current.weather_description
        draw.text((desc_x, y + 25), desc_text, fill=cfg.text_secondary, font=desc_font)

        # Feels like
        feels_text = f"Feels like {weather.current.apparent_temperature:.0f}°C"
        draw.text((desc_x, y + 50), feels_text, fill=cfg.text_secondary, font=desc_font)

        # Location - at far right of weather card
        loc_text = weather.location
        try:
            bbox = draw.textbbox((0, 0), loc_text, font=loc_font)
            loc_width = bbox[2] - bbox[0]
        except:
            loc_width = 120
        loc_x = weather_card_x + weather_width - loc_width - 20
        draw.text((loc_x, y + 80), loc_text, fill=cfg.text_muted, font=loc_font)

        # === RIGHT: AQI Card ===
        aqi_card_x = weather_card_x + weather_width + padding

        if weather.air_quality:
            aqi = weather.air_quality.aqi
            aqi_bg, aqi_msg = self._get_aqi_style(aqi)
        else:
            aqi = None
            aqi_bg = cfg.card_bg
            aqi_msg = "No data"

        draw.rounded_rectangle(
            [aqi_card_x, y, aqi_card_x + aqi_width, y + height],
            radius=16,
            fill=aqi_bg
        )

        if aqi is not None:
            aqi_font = self._get_font(44, bold=True)
            aqi_text = str(aqi)
            try:
                bbox = draw.textbbox((0, 0), aqi_text, font=aqi_font)
                text_width = bbox[2] - bbox[0]
            except:
                text_width = 50
            aqi_x = aqi_card_x + (aqi_width - text_width - 35) // 2
            draw.text((aqi_x, y + 12), aqi_text, fill=(255, 255, 255), font=aqi_font)

            label_font = self._get_font(14, bold=True)
            draw.text((aqi_x + text_width + 6, y + 32), "AQI", fill=(255, 255, 255), font=label_font)

            msg_font = self._get_font(13, bold=True)
            try:
                bbox = draw.textbbox((0, 0), aqi_msg, font=msg_font)
                msg_width = bbox[2] - bbox[0]
            except:
                msg_width = 80
            msg_x = aqi_card_x + (aqi_width - msg_width) // 2
            draw.text((msg_x, y + 65), aqi_msg, fill=(255, 255, 255), font=msg_font)

            if weather.air_quality:
                pm_font = self._get_font(11)
                pm_text = f"PM2.5: {weather.air_quality.pm2_5:.0f} µg/m³"
                try:
                    bbox = draw.textbbox((0, 0), pm_text, font=pm_font)
                    pm_width = bbox[2] - bbox[0]
                except:
                    pm_width = 70
                pm_x = aqi_card_x + (aqi_width - pm_width) // 2
                draw.text((pm_x, y + 90), pm_text, fill=(255, 255, 255, 200), font=pm_font)
        else:
            na_font = self._get_font(18, bold=True)
            draw.text((aqi_card_x + 25, y + 45), "AQI N/A", fill=cfg.text_secondary, font=na_font)

        return y + height

    def _get_aqi_style(self, aqi: int) -> Tuple[Tuple[int, int, int], str]:
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

    def _draw_condition_badges(self, draw, weather: WeatherData, y: int, height: int) -> int:
        """Draw condition badges."""
        cfg = self.config
        padding = 20

        badges = []
        today = weather.today
        max_rain = max(weather.hourly.precipitation_probs) if weather.hourly else 0

        if today:
            # Storm
            if today.weather_code >= 95:
                badges.append(("Storm Alert", cfg.badge_storm, "Thunderstorm"))

            # Rain badge - show with different style based on amount
            if max_rain >= 50:
                badges.append(("Rain Likely", cfg.badge_rain, f"{max_rain}%"))
            elif max_rain >= 10:
                badges.append(("Chance of Rain", cfg.badge_neutral, f"{max_rain}%"))
            # < 10% handled by striped tile in chart

            # Wind
            if today.wind_speed_max >= 40:
                badges.append(("High Wind", cfg.badge_wind_storm, f"{today.wind_speed_max:.0f} km/h"))
            elif today.wind_speed_max >= 15:
                badges.append(("Breezy", cfg.badge_neutral, f"{today.wind_speed_max:.0f} km/h"))

            # UV
            if today.uv_index_max >= 8:
                badges.append(("Extreme UV", cfg.badge_uv, f"Index {today.uv_index_max:.0f}"))
            elif today.uv_index_max >= 6:
                badges.append(("High UV", cfg.badge_uv, f"Index {today.uv_index_max:.0f}"))

            # Sunrise/sunset
            badges.append((f"Sunrise {today.sunrise}", cfg.badge_neutral, f"Sunset {today.sunset}"))

        if not badges:
            return y

        badge_font = self._get_font(12, bold=True)
        detail_font = self._get_font(11)

        badge_x = padding
        badge_height = 32
        badge_y = y + (height - badge_height) // 2

        for label, color, detail in badges:
            try:
                label_bbox = draw.textbbox((0, 0), label, font=badge_font)
                detail_bbox = draw.textbbox((0, 0), detail, font=detail_font)
                label_width = label_bbox[2] - label_bbox[0]
                detail_width = detail_bbox[2] - detail_bbox[0]
            except:
                label_width = len(label) * 8
                detail_width = len(detail) * 7

            badge_width = label_width + detail_width + 30

            if badge_x + badge_width > cfg.width - padding:
                break

            draw.rounded_rectangle(
                [badge_x, badge_y, badge_x + badge_width, badge_y + badge_height],
                radius=8,
                fill=color
            )
            draw.text((badge_x + 10, badge_y + 8), label, fill=(255, 255, 255), font=badge_font)
            draw.text((badge_x + 15 + label_width, badge_y + 9), detail, fill=(255, 255, 255, 200), font=detail_font)

            badge_x += badge_width + 10

        return y + height

    def _draw_combined_chart(self, draw, img, weather: WeatherData, y: int, height: int) -> int:
        """Draw combined chart with full 24h, temp numbers above markers."""
        cfg = self.config
        hourly = weather.hourly
        padding = 20

        chart_left = padding + 35
        chart_right = cfg.width - padding - 10
        chart_top = y + 55  # More space for temp labels above
        chart_bottom = y + height - 30
        chart_width = chart_right - chart_left
        chart_height = chart_bottom - chart_top

        # Build full 24h data (pad missing hours with interpolation)
        temps_24h = [None] * 24
        rains_24h = [0] * 24

        if hourly:
            for i, hour in enumerate(hourly.hours):
                if 0 <= hour < 24:
                    temps_24h[hour] = hourly.temperatures[i]
                    rains_24h[hour] = hourly.precipitation_probs[i]

        # Fill missing temps with interpolation or nearest
        for i in range(24):
            if temps_24h[i] is None:
                # Find nearest valid temp
                for offset in range(1, 24):
                    if i - offset >= 0 and temps_24h[i - offset] is not None:
                        temps_24h[i] = temps_24h[i - offset]
                        break
                    if i + offset < 24 and temps_24h[i + offset] is not None:
                        temps_24h[i] = temps_24h[i + offset]
                        break

        # Fallback
        temps_24h = [t if t is not None else 20 for t in temps_24h]

        max_rain = max(rains_24h)
        has_significant_rain = max_rain >= 10

        # Title and legend area
        title_font = self._get_font(14, bold=True)
        legend_font = self._get_font(11)

        draw.text((padding, y + 10), "Today's Forecast", fill=cfg.text_color, font=title_font)

        # Legends on right side - Rain tile next to Temp
        legend_right = cfg.width - padding

        # Temperature legend (rightmost)
        temp_legend_x = legend_right - 50
        draw.rectangle([temp_legend_x, y + 12, temp_legend_x + 10, y + 18], fill=cfg.temp_color)
        draw.text((temp_legend_x + 14, y + 9), "Temp", fill=cfg.text_secondary, font=legend_font)

        # Rain tile next to Temp legend
        rain_tile_w = 85
        rain_tile_h = 18
        rain_tile_x = temp_legend_x - rain_tile_w - 15
        rain_tile_y = y + 8

        if has_significant_rain:
            # Solid colored rain indicator
            draw.rounded_rectangle(
                [rain_tile_x, rain_tile_y, rain_tile_x + rain_tile_w, rain_tile_y + rain_tile_h],
                radius=4,
                fill=cfg.rain_color
            )
            rain_text = f"Rain {max_rain}%"
            draw.text((rain_tile_x + 10, rain_tile_y + 2), rain_text, fill=(255, 255, 255), font=legend_font)
        else:
            # Striped tile for < 10% rain - create stripe pattern
            # Draw base
            draw.rounded_rectangle(
                [rain_tile_x, rain_tile_y, rain_tile_x + rain_tile_w, rain_tile_y + rain_tile_h],
                radius=4,
                fill=(45, 50, 58)
            )
            # Draw diagonal stripes using a clipping approach
            stripe_color = (70, 75, 85)
            for i in range(-rain_tile_h, rain_tile_w + rain_tile_h, 5):
                x1 = rain_tile_x + i
                y1 = rain_tile_y
                x2 = rain_tile_x + i + rain_tile_h
                y2 = rain_tile_y + rain_tile_h
                # Clip to tile bounds
                if x1 < rain_tile_x:
                    y1 = rain_tile_y + (rain_tile_x - x1)
                    x1 = rain_tile_x
                if x2 > rain_tile_x + rain_tile_w:
                    y2 = rain_tile_y + rain_tile_h - (x2 - rain_tile_x - rain_tile_w)
                    x2 = rain_tile_x + rain_tile_w
                if y1 < rain_tile_y + rain_tile_h and y2 > rain_tile_y:
                    draw.line([(x1, y1), (x2, y2)], fill=stripe_color, width=2)
            rain_text = "Rain <10%"
            try:
                bbox = draw.textbbox((0, 0), rain_text, font=legend_font)
                tw = bbox[2] - bbox[0]
            except:
                tw = 55
            draw.text((rain_tile_x + (rain_tile_w - tw) // 2, rain_tile_y + 2), rain_text, fill=cfg.text_secondary, font=legend_font)

        # Calculate temp range with padding
        temp_min = min(temps_24h) - 2
        temp_max = max(temps_24h) + 4
        temp_range = temp_max - temp_min if temp_max > temp_min else 1

        label_font = self._get_font(10)
        temp_label_font = self._get_font(9)

        # Draw grid lines
        for i in range(5):
            grid_y = chart_top + (chart_height * i / 4)
            draw.line([(chart_left, grid_y), (chart_right, grid_y)], fill=cfg.grid_color, width=1)
            temp_val = temp_max - (temp_range * i / 4)
            draw.text((padding, grid_y - 6), f"{temp_val:.0f}°", fill=cfg.text_muted, font=label_font)

        # Draw rain bars if significant
        if has_significant_rain:
            bar_width = max(4, chart_width // 24 - 2)
            for i, rain in enumerate(rains_24h):
                if rain > 0:
                    x = chart_left + (chart_width * i / 23)
                    bar_h = (rain / 100) * chart_height
                    bar_top_y = chart_bottom - bar_h
                    for bar_y_pos in range(int(bar_top_y), int(chart_bottom)):
                        progress = (bar_y_pos - bar_top_y) / bar_h if bar_h > 0 else 0
                        alpha = int(80 * (1 - progress * 0.5))
                        draw.line([(x - bar_width//2, bar_y_pos), (x + bar_width//2, bar_y_pos)],
                                 fill=cfg.rain_color + (alpha,), width=1)

        # Draw temperature line and points
        temp_points = []
        for i, temp in enumerate(temps_24h):
            x = chart_left + (chart_width * i / 23)
            y_val = chart_bottom - ((temp - temp_min) / temp_range * chart_height)
            temp_points.append((x, y_val, temp))

        # Gradient fill under line
        if len(temp_points) >= 2:
            min_y = min(p[1] for p in temp_points)
            for fill_y in range(int(min_y), int(chart_bottom)):
                alpha = int(20 * (1 - (fill_y - chart_top) / chart_height))
                draw.line([(chart_left, fill_y), (chart_right, fill_y)], fill=cfg.temp_color + (alpha,), width=1)

        # Draw line
        if len(temp_points) >= 2:
            line_points = [(p[0], p[1]) for p in temp_points]
            draw.line(line_points, fill=cfg.temp_color, width=2)

        # Draw points and temp labels every 3 hours
        for i, (px, py, temp) in enumerate(temp_points):
            # Draw point
            draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=cfg.temp_color)
            draw.ellipse([px - 1.5, py - 1.5, px + 1.5, py + 1.5], fill=(255, 255, 255))

            # Temperature label above point every 3 hours
            if i % 3 == 0:
                temp_text = f"{temp:.0f}°"
                try:
                    bbox = draw.textbbox((0, 0), temp_text, font=temp_label_font)
                    tw = bbox[2] - bbox[0]
                except:
                    tw = 15
                draw.text((px - tw // 2, py - 18), temp_text, fill=cfg.text_secondary, font=temp_label_font)

        # Hour labels
        for i in range(0, 24, 3):
            x = chart_left + (chart_width * i / 23)
            hour_text = f"{i:02d}:00"
            try:
                bbox = draw.textbbox((0, 0), hour_text, font=label_font)
                tw = bbox[2] - bbox[0]
            except:
                tw = 25
            draw.text((x - tw // 2, chart_bottom + 8), hour_text, fill=cfg.text_secondary, font=label_font)

        return y + height

    def _draw_quote(self, draw, y: int, height: int) -> int:
        """Draw an inspirational quote with author."""
        cfg = self.config
        padding = 20

        quote, author = random.choice(WEATHER_QUOTES)

        quote_font = self._get_italic_font(14)
        author_font = self._get_font(11)

        quote_color = (180, 185, 195)
        author_color = cfg.text_muted

        quote_text = f'"{quote}"'
        try:
            bbox = draw.textbbox((0, 0), quote_text, font=quote_font)
            quote_width = bbox[2] - bbox[0]
        except:
            quote_width = len(quote_text) * 7

        max_width = cfg.width - padding * 4
        quote_x = (cfg.width - min(quote_width, max_width)) // 2
        quote_y = y + 15

        draw.text((quote_x, quote_y), quote_text, fill=quote_color, font=quote_font)

        author_text = f"— {author}"
        try:
            bbox = draw.textbbox((0, 0), author_text, font=author_font)
            author_width = bbox[2] - bbox[0]
        except:
            author_width = len(author_text) * 6

        author_x = (cfg.width - author_width) // 2
        author_y = quote_y + 25

        draw.text((author_x, author_y), author_text, fill=author_color, font=author_font)

        return y + height

    def _draw_footer(self, draw, weather: WeatherData, y: int):
        """Draw footer."""
        cfg = self.config
        padding = 20

        timestamp = weather.fetched_at.strftime("%H:%M %d/%m/%Y")
        footer_font = self._get_font(10)

        left_text = f"Data from Open-Meteo · {timestamp}"
        draw.text((padding, y + 12), left_text, fill=cfg.text_muted, font=footer_font)

        right_text = "made with <3 by namesn_pe"
        try:
            bbox = draw.textbbox((0, 0), right_text, font=footer_font)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = 130
        draw.text((cfg.width - padding - text_width, y + 12), right_text, fill=cfg.text_muted, font=footer_font)

    def generate_week_image(self, weather: WeatherData) -> io.BytesIO:
        """Generate 7-day forecast - full width tiles, no header."""
        cfg = self.config

        padding = 0  # Full width
        day_height = 65
        footer_height = 30

        num_days = len(weather.week)
        height = day_height * num_days + footer_height

        img = Image.new('RGB', (cfg.width, height), cfg.bg_color)
        draw = ImageDraw.Draw(img)

        day_font = self._get_font(14, bold=True)
        temp_font = self._get_font(16, bold=True)
        label_font = self._get_font(11)

        current_y = 0
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        # Layout positions - spread across full width
        col_day = 15
        col_temp = 160
        temp_bar_width = 220
        col_rain = col_temp + temp_bar_width + 50
        col_wind = col_rain + 80
        col_uv = col_wind + 80
        col_alert = cfg.width - 40

        for i, day in enumerate(weather.week):
            # Full width alternating rows
            if i % 2 == 0:
                draw.rectangle([0, current_y, cfg.width, current_y + day_height], fill=cfg.card_bg)

            # Day name and date
            day_name = day_names[day.date.weekday()]
            date_str = day.date.strftime("%d/%m")
            is_today = i == 0

            day_label = f"{day_name} {date_str}" + (" (Today)" if is_today else "")
            draw.text((col_day, current_y + 12), day_label, fill=cfg.text_color, font=day_font)

            # Weather description
            draw.text((col_day, current_y + 35), day.weather_description, fill=cfg.text_secondary, font=label_font)

            # Temperature bar - wider
            self._draw_temp_bar(draw, day.temp_min, day.temp_max, col_temp, current_y + 15, temp_bar_width, 28, temp_font, label_font)

            # Rain
            rain_color = cfg.rain_color if day.precipitation_prob >= 50 else cfg.text_secondary
            draw.text((col_rain, current_y + 18), f"{day.precipitation_prob}%", fill=rain_color, font=temp_font)
            draw.text((col_rain, current_y + 40), "rain", fill=cfg.text_muted, font=label_font)

            # Wind
            wind_color = cfg.badge_wind_storm if day.wind_speed_max >= 30 else cfg.text_secondary
            draw.text((col_wind, current_y + 18), f"{day.wind_speed_max:.0f}", fill=wind_color, font=temp_font)
            draw.text((col_wind, current_y + 40), "km/h", fill=cfg.text_muted, font=label_font)

            # UV
            uv_color = self._get_uv_color(day.uv_index_max)
            draw.text((col_uv, current_y + 18), f"{day.uv_index_max:.0f}", fill=uv_color, font=temp_font)
            draw.text((col_uv, current_y + 40), "UV", fill=cfg.text_muted, font=label_font)

            # Alert at far right
            alerts = day.is_unusual()
            if alerts:
                draw.text((col_alert, current_y + 22), "!", fill=(255, 200, 100), font=temp_font)

            current_y += day_height

        # Compact footer
        self._draw_footer(draw, weather, height - footer_height)

        output = io.BytesIO()
        img.save(output, format='PNG', optimize=True)
        output.seek(0)
        return output

    def _draw_temp_bar(self, draw, temp_min: float, temp_max: float,
                       x: int, y: int, width: int, height: int,
                       temp_font, label_font):
        """Draw a temperature range bar."""
        cfg = self.config

        global_min = 10
        global_max = 40
        global_range = global_max - global_min

        bar_y = y + 8
        bar_height = 8

        min_pos = max(0, (temp_min - global_min) / global_range)
        max_pos = min(1, (temp_max - global_min) / global_range)

        draw.rounded_rectangle([x, bar_y, x + width, bar_y + bar_height], radius=4, fill=cfg.grid_color)

        bar_start = x + int(width * min_pos)
        bar_end = x + int(width * max_pos)
        end_color = self._temp_to_color(temp_max)

        draw.rounded_rectangle([bar_start, bar_y, bar_end, bar_y + bar_height], radius=4, fill=end_color)

        draw.text((bar_start - 25, bar_y - 2), f"{temp_min:.0f}°", fill=cfg.text_secondary, font=label_font)
        draw.text((bar_end + 5, bar_y - 2), f"{temp_max:.0f}°", fill=cfg.text_color, font=label_font)

    def _temp_to_color(self, temp: float) -> Tuple[int, int, int]:
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

    def _get_uv_color(self, uv: float) -> Tuple[int, int, int]:
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
