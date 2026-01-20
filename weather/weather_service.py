"""
Weather service using Open-Meteo API.
Provides weather data for HANU campus (Hanoi, Vietnam).
"""

from __future__ import annotations

import httpx
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import asyncio

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# HANU campus coordinates (Nguyen Trai, Thanh Xuan, Hanoi)
HANU_LAT = 21.0375
HANU_LON = 105.8341
LOCATION_NAME = "HANU Campus, Hanoi"

# WMO Weather interpretation codes
WMO_CODES = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Foggy", "🌫️"),
    48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌧️"),
    53: ("Moderate drizzle", "🌧️"),
    55: ("Dense drizzle", "🌧️"),
    56: ("Light freezing drizzle", "🌧️❄️"),
    57: ("Dense freezing drizzle", "🌧️❄️"),
    61: ("Slight rain", "🌧️"),
    63: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "🌧️💧"),
    66: ("Light freezing rain", "🌧️❄️"),
    67: ("Heavy freezing rain", "🌧️❄️"),
    71: ("Slight snowfall", "🌨️"),
    73: ("Moderate snowfall", "🌨️"),
    75: ("Heavy snowfall", "❄️"),
    77: ("Snow grains", "🌨️"),
    80: ("Slight rain showers", "🌦️"),
    81: ("Moderate rain showers", "🌦️"),
    82: ("Violent rain showers", "⛈️"),
    85: ("Slight snow showers", "🌨️"),
    86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with slight hail", "⛈️"),
    99: ("Thunderstorm with heavy hail", "⛈️🧊"),
}

# AQI categories
AQI_CATEGORIES = {
    (0, 50): ("Good", "🟢"),
    (51, 100): ("Moderate", "🟡"),
    (101, 150): ("Unhealthy for Sensitive Groups", "🟠"),
    (151, 200): ("Unhealthy", "🔴"),
    (201, 300): ("Very Unhealthy", "🟣"),
    (301, 500): ("Hazardous", "🟤"),
}

# UV Index categories
UV_CATEGORIES = {
    (0, 2): ("Low", "🟢"),
    (3, 5): ("Moderate", "🟡"),
    (6, 7): ("High", "🟠"),
    (8, 10): ("Very High", "🔴"),
    (11, 20): ("Extreme", "🟣"),
}


@dataclass
class DayForecast:
    date: datetime
    weather_code: int
    temp_max: float
    temp_min: float
    precipitation_prob: int
    precipitation_sum: float
    wind_speed_max: float
    wind_direction: int
    uv_index_max: float
    sunrise: str
    sunset: str

    @property
    def weather_description(self) -> str:
        return WMO_CODES.get(self.weather_code, ("Unknown", "❓"))[0]

    @property
    def weather_emoji(self) -> str:
        return WMO_CODES.get(self.weather_code, ("Unknown", "❓"))[1]

    @property
    def uv_category(self) -> tuple[str, str]:
        for (low, high), (desc, emoji) in UV_CATEGORIES.items():
            if low <= self.uv_index_max <= high:
                return (desc, emoji)
        return ("Unknown", "❓")

    @property
    def wind_direction_str(self) -> str:
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        idx = round(self.wind_direction / 22.5) % 16
        return directions[idx]

    def is_unusual(self) -> list[str]:
        """Check for unusual weather conditions worth highlighting."""
        alerts = []
        if self.temp_max >= 38:
            alerts.append(f"🔥 Extreme heat ({self.temp_max:.0f}°C)")
        elif self.temp_max >= 35:
            alerts.append(f"☀️ Very hot ({self.temp_max:.0f}°C)")
        if self.temp_min <= 10:
            alerts.append(f"🥶 Cold night ({self.temp_min:.0f}°C)")
        if self.precipitation_prob >= 80:
            alerts.append(f"🌧️ High rain chance ({self.precipitation_prob}%)")
        if self.precipitation_sum >= 50:
            alerts.append(f"💧 Heavy rainfall expected ({self.precipitation_sum:.0f}mm)")
        if self.wind_speed_max >= 50:
            alerts.append(f"💨 Strong winds ({self.wind_speed_max:.0f} km/h)")
        if self.uv_index_max >= 8:
            alerts.append(f"☀️ Very high UV ({self.uv_index_max:.0f})")
        if self.weather_code >= 95:
            alerts.append("⛈️ Thunderstorm expected")
        return alerts


@dataclass
class CurrentWeather:
    temperature: float
    apparent_temperature: float
    humidity: int
    weather_code: int
    wind_speed: float
    wind_direction: int

    @property
    def weather_description(self) -> str:
        return WMO_CODES.get(self.weather_code, ("Unknown", "❓"))[0]

    @property
    def weather_emoji(self) -> str:
        return WMO_CODES.get(self.weather_code, ("Unknown", "❓"))[1]


@dataclass
class AirQuality:
    aqi: int
    pm2_5: float
    pm10: float

    @property
    def category(self) -> tuple[str, str]:
        for (low, high), (desc, emoji) in AQI_CATEGORIES.items():
            if low <= self.aqi <= high:
                return (desc, emoji)
        return ("Unknown", "❓")


@dataclass
class HourlyData:
    """Hourly weather data for charts."""
    hours: list[int]  # Hour of day (0-23)
    temperatures: list[float]
    apparent_temperatures: list[float]
    precipitation_probs: list[int]
    precipitation: list[float]
    wind_speeds: list[float]
    uv_indices: list[float]
    weather_codes: list[int]


@dataclass
class WeatherData:
    location: str
    current: CurrentWeather
    today: DayForecast
    week: list[DayForecast]
    hourly: Optional[HourlyData]
    air_quality: Optional[AirQuality]
    fetched_at: datetime


async def fetch_weather() -> WeatherData:
    """Fetch weather data from Open-Meteo API."""

    # Weather forecast API
    weather_url = "https://api.open-meteo.com/v1/forecast"
    weather_params = {
        "latitude": HANU_LAT,
        "longitude": HANU_LON,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m",
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,wind_speed_10m,uv_index,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max,wind_direction_10m_dominant,uv_index_max,sunrise,sunset",
        "timezone": "Asia/Ho_Chi_Minh",
        "forecast_days": 7,
    }

    # Air quality API
    aqi_url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    aqi_params = {
        "latitude": HANU_LAT,
        "longitude": HANU_LON,
        "current": "us_aqi,pm2_5,pm10",
        "timezone": "Asia/Ho_Chi_Minh",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch both APIs concurrently
        weather_resp, aqi_resp = await asyncio.gather(
            client.get(weather_url, params=weather_params),
            client.get(aqi_url, params=aqi_params),
            return_exceptions=True
        )

        # Parse weather data
        if isinstance(weather_resp, Exception):
            raise weather_resp
        weather_resp.raise_for_status()
        weather_data = weather_resp.json()

        # Parse current weather
        current = weather_data["current"]
        current_weather = CurrentWeather(
            temperature=current["temperature_2m"],
            apparent_temperature=current["apparent_temperature"],
            humidity=current["relative_humidity_2m"],
            weather_code=current["weather_code"],
            wind_speed=current["wind_speed_10m"],
            wind_direction=current["wind_direction_10m"],
        )

        # Parse daily forecasts
        daily = weather_data["daily"]
        forecasts = []
        for i in range(len(daily["time"])):
            forecast = DayForecast(
                date=datetime.fromisoformat(daily["time"][i]),
                weather_code=daily["weather_code"][i],
                temp_max=daily["temperature_2m_max"][i],
                temp_min=daily["temperature_2m_min"][i],
                precipitation_prob=daily["precipitation_probability_max"][i] or 0,
                precipitation_sum=daily["precipitation_sum"][i] or 0,
                wind_speed_max=daily["wind_speed_10m_max"][i],
                wind_direction=daily["wind_direction_10m_dominant"][i],
                uv_index_max=daily["uv_index_max"][i],
                sunrise=daily["sunrise"][i].split("T")[1] if daily["sunrise"][i] else "N/A",
                sunset=daily["sunset"][i].split("T")[1] if daily["sunset"][i] else "N/A",
            )
            forecasts.append(forecast)

        # Parse air quality (may fail, that's ok)
        air_quality = None
        if not isinstance(aqi_resp, Exception):
            try:
                aqi_resp.raise_for_status()
                aqi_data = aqi_resp.json()
                aqi_current = aqi_data.get("current", {})
                if aqi_current.get("us_aqi") is not None:
                    air_quality = AirQuality(
                        aqi=int(aqi_current["us_aqi"]),
                        pm2_5=aqi_current.get("pm2_5", 0) or 0,
                        pm10=aqi_current.get("pm10", 0) or 0,
                    )
            except Exception:
                pass  # Air quality is optional

        # Parse hourly data (today only, 5am to 11pm for useful display)
        hourly_data = None
        try:
            hourly = weather_data.get("hourly", {})
            if hourly.get("time"):
                # Get today's date in Vietnam timezone (matches API timezone)
                vietnam_tz = ZoneInfo("Asia/Ho_Chi_Minh")
                today_str = datetime.now(vietnam_tz).strftime("%Y-%m-%d")

                # Filter to today's hours (5am to 11pm = indices 5-23)
                hours = []
                temps = []
                apparent_temps = []
                precip_probs = []
                precip = []
                winds = []
                uvs = []
                codes = []

                for i, time_str in enumerate(hourly["time"]):
                    if time_str.startswith(today_str):
                        hour = int(time_str.split("T")[1].split(":")[0])
                        if 5 <= hour <= 23:  # 5am to 11pm
                            hours.append(hour)
                            temps.append(hourly["temperature_2m"][i] or 0)
                            apparent_temps.append(hourly["apparent_temperature"][i] or 0)
                            precip_probs.append(hourly["precipitation_probability"][i] or 0)
                            precip.append(hourly["precipitation"][i] or 0)
                            winds.append(hourly["wind_speed_10m"][i] or 0)
                            uvs.append(hourly["uv_index"][i] or 0)
                            codes.append(hourly["weather_code"][i] or 0)

                if hours:
                    hourly_data = HourlyData(
                        hours=hours,
                        temperatures=temps,
                        apparent_temperatures=apparent_temps,
                        precipitation_probs=precip_probs,
                        precipitation=precip,
                        wind_speeds=winds,
                        uv_indices=uvs,
                        weather_codes=codes,
                    )
        except Exception:
            pass  # Hourly is optional

        return WeatherData(
            location=LOCATION_NAME,
            current=current_weather,
            today=forecasts[0] if forecasts else None,
            week=forecasts,
            hourly=hourly_data,
            air_quality=air_quality,
            fetched_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
        )


def generate_title(weather: WeatherData) -> str:
    """Generate a catchy title highlighting unusual conditions."""
    today = weather.today
    alerts = today.is_unusual() if today else []

    # Pick the most important alert for the title
    if alerts:
        return f"Weather Alert: {alerts[0].split(' ', 1)[1] if ' ' in alerts[0] else alerts[0]}"

    # Default title based on weather
    emoji = today.weather_emoji if today else "🌤️"
    desc = today.weather_description if today else "Weather"
    return f"{emoji} {desc} in Hanoi"


def format_today_embed_content(weather: WeatherData) -> str:
    """Format today's weather for embed."""
    today = weather.today
    current = weather.current

    lines = []

    # Current conditions
    lines.append(f"### Right Now")
    lines.append(f"{current.weather_emoji} **{current.weather_description}**")
    lines.append(f"🌡️ {current.temperature:.1f}°C (feels like {current.apparent_temperature:.1f}°C)")
    lines.append(f"💧 Humidity: {current.humidity}%")
    lines.append(f"💨 Wind: {current.wind_speed:.0f} km/h")
    lines.append("")

    # Today's forecast
    if today:
        lines.append(f"### Today's Forecast")
        lines.append(f"🌡️ High: **{today.temp_max:.0f}°C** | Low: **{today.temp_min:.0f}°C**")
        lines.append(f"🌧️ Rain chance: {today.precipitation_prob}%")
        if today.precipitation_sum > 0:
            lines.append(f"💧 Expected rainfall: {today.precipitation_sum:.1f}mm")
        lines.append(f"💨 Wind: up to {today.wind_speed_max:.0f} km/h {today.wind_direction_str}")

        uv_desc, uv_emoji = today.uv_category
        lines.append(f"☀️ UV Index: {today.uv_index_max:.0f} ({uv_emoji} {uv_desc})")
        lines.append(f"🌅 Sunrise: {today.sunrise} | 🌇 Sunset: {today.sunset}")

    # Air quality
    if weather.air_quality:
        aqi = weather.air_quality
        cat_desc, cat_emoji = aqi.category
        lines.append("")
        lines.append(f"### Air Quality")
        lines.append(f"{cat_emoji} AQI: **{aqi.aqi}** ({cat_desc})")
        lines.append(f"PM2.5: {aqi.pm2_5:.1f} µg/m³ | PM10: {aqi.pm10:.1f} µg/m³")

    # Alerts
    if today:
        alerts = today.is_unusual()
        if alerts:
            lines.append("")
            lines.append("### ⚠️ Weather Alerts")
            for alert in alerts:
                lines.append(f"• {alert}")

    return "\n".join(lines)


def format_week_forecast(weather: WeatherData) -> str:
    """Format weekly forecast."""
    lines = []

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for day in weather.week[1:]:  # Skip today
        day_name = day_names[day.date.weekday()]
        date_str = day.date.strftime("%d/%m")

        rain_icon = "💧" if day.precipitation_prob >= 50 else ""

        line = (
            f"**{day_name} {date_str}** {day.weather_emoji} "
            f"{day.temp_max:.0f}°/{day.temp_min:.0f}° "
            f"{rain_icon}{day.precipitation_prob}%"
        )
        lines.append(line)

        # Add alerts for this day
        alerts = day.is_unusual()
        if alerts:
            for alert in alerts[:2]:  # Limit to 2 alerts per day
                lines.append(f"  ↳ {alert}")

    return "\n".join(lines)
