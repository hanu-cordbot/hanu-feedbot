"""Game music in a voice channel during live quizzes.

The tracks are synthesised here (original chiptune loops, so there is nothing to license) and cached as WAV
files under DATA_DIR/music/generated. Audio files dropped straight into DATA_DIR/music (mp3, ogg, wav, …)
replace the generated question loop, picked at random per game.

Music is a nice-to-have: every voice call here logs and gives up on failure rather than breaking the game.
"""
from __future__ import annotations

import asyncio
import logging
import random
import wave
from pathlib import Path
from typing import Optional

import discord

from . import config

log = logging.getLogger(__name__)

SR = 44100
MUSIC_DIR = config.DATA_DIR / "music"
GENERATED = MUSIC_DIR / "generated"
USER_EXTS = {".mp3", ".ogg", ".opus", ".wav", ".flac", ".m4a"}
VOLUME = 0.35
TRACK_VERSION = 1  # bump to regenerate cached tracks after changing the synth

NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def hz(name: str) -> float:
    """'A4' -> 440.0"""
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((NOTE[pitch] + 12 * (octave + 1) - 69) / 12)


# --- synth ---------------------------------------------------------------------

def _np():
    import numpy as np  # only needed when tracks are (re)generated
    return np


class Track:
    def __init__(self, seconds: float):
        np = _np()
        self.np = np
        self.buf = np.zeros(int(seconds * SR) + SR, dtype=np.float64)
        self.length = int(seconds * SR)

    def tone(self, start: float, dur: float, freq: float, vol: float, wave_: str = "square", duty: float = 0.5,
             attack: float = 0.004, release: float = 0.05, slide: float = 0.0) -> None:
        np = self.np
        n = int((dur + release) * SR)
        i0 = int(start * SR)
        t = np.arange(n) / SR
        f = freq * (1 + slide * t / max(dur, 1e-3))
        phase = np.cumsum(f) / SR % 1.0
        if wave_ == "square":
            w = np.where(phase < duty, 1.0, -1.0)
        elif wave_ == "triangle":
            w = 4 * np.abs(phase - 0.5) - 1
        elif wave_ == "saw":
            w = 2 * phase - 1
        else:
            w = np.sin(2 * np.pi * phase)
        env = np.ones(n)
        a = max(1, int(attack * SR))
        env[:a] = np.linspace(0, 1, a)
        d = int(dur * SR)
        if d < n:
            env[d:] = np.linspace(1, 0, n - d)
        self._add(i0, w * env * vol)

    def kick(self, start: float, vol: float = 0.9) -> None:
        np = self.np
        n = int(0.22 * SR)
        t = np.arange(n) / SR
        f = 45 + 110 * np.exp(-t * 28)
        w = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14)
        self._add(int(start * SR), w * vol)

    def noise(self, start: float, dur: float, vol: float, bright: bool = True) -> None:
        np = self.np
        n = int(dur * SR)
        rng = np.random.default_rng(int(start * 1000))
        w = rng.uniform(-1, 1, n)
        if bright:
            w = np.diff(w, prepend=0)  # crude high-pass: hats
        w *= np.exp(-np.arange(n) / SR * (60 if bright else 22))
        self._add(int(start * SR), w * vol)

    def _add(self, i0: int, w) -> None:
        end = min(len(self.buf), i0 + len(w))
        self.buf[i0:end] += w[: end - i0]

    def render(self, loop: bool) -> bytes:
        np = self.np
        buf = self.buf.copy()
        if loop:  # anything ringing past the end wraps to the start, so the loop is seamless
            tail = buf[self.length:]
            buf[: len(tail)] += tail
        buf = buf[: self.length]
        buf = np.tanh(buf * 1.2)
        peak = np.max(np.abs(buf)) or 1.0
        return (buf / peak * 0.85 * 32767).astype("<i2").tobytes()


CHORDS = {
    "Am": ["A2", "C4", "E4", "A4"], "F": ["F2", "A3", "C4", "F4"], "C": ["C3", "E4", "G4", "C5"],
    "G": ["G2", "B3", "D4", "G4"], "Dm": ["D3", "D4", "F4", "A4"], "E": ["E2", "G#3", "B3", "E4"],
    "Cmaj7": ["C3", "E4", "G4", "B4"], "Am7": ["A2", "C4", "E4", "G4"], "Dm7": ["D3", "F4", "A4", "C5"],
    "G7": ["G2", "B3", "D4", "F4"],
}


def question_loop() -> Track:
    """Driving 132 bpm loop, Am F C G twice with a busier second half."""
    bpm, bars = 132, 16
    beat = 60 / bpm
    tr = Track(bars * 4 * beat)
    prog = ["Am", "F", "C", "G"] * 2 + ["Am", "F", "C", "G", "Dm", "F", "E", "E"]
    rng = random.Random(7)
    for bar, chord in enumerate(prog):
        notes = CHORDS[chord]
        t0 = bar * 4 * beat
        root = hz(notes[0])
        for k in range(8):  # bass: eighths, octave jump on the offbeats
            f = root * (2 if k % 2 else 1)
            tr.tone(t0 + k * beat / 2, beat / 2 * 0.8, f, 0.22, "square", duty=0.25)
        arp = [hz(n) * 2 for n in notes[1:]] + [hz(notes[2]) * 4]
        for k in range(16):  # arpeggio: sixteenths up and down
            idx = [0, 1, 2, 3, 2, 1][k % 6]
            tr.tone(t0 + k * beat / 4, beat / 4 * 0.6, arp[idx], 0.05 if bar < 8 else 0.07, "square", duty=0.125)
        for k in range(4):  # drums
            tr.kick(t0 + k * beat, 0.8)
            if k % 2:
                tr.noise(t0 + k * beat, 0.16, 0.35, bright=False)
        for k in range(8):
            tr.noise(t0 + k * beat / 2 + (beat / 4 if bar >= 8 else 0), 0.05, 0.12)
        if bar >= 8:  # lead melody on chord tones in the second half
            pattern = [0, 1.5, 2, 3] if bar % 2 == 0 else [0, 0.5, 1, 2.5]
            for p in pattern:
                n = rng.choice(notes[1:])
                tr.tone(t0 + p * beat, beat * 0.45, hz(n) * 2, 0.08, "square", duty=0.5, release=0.08)
    return tr


def lobby_loop() -> Track:
    """Relaxed 100 bpm loop for the answer screens."""
    bpm, bars = 100, 8
    beat = 60 / bpm
    tr = Track(bars * 4 * beat)
    prog = ["Cmaj7", "Am7", "Dm7", "G7"] * 2
    for bar, chord in enumerate(prog):
        notes = CHORDS[chord]
        t0 = bar * 4 * beat
        for n in notes[1:]:
            tr.tone(t0, 4 * beat * 0.95, hz(n), 0.07, "triangle", attack=0.08, release=0.3)
        for k in (0, 1.5, 2, 3.5):
            tr.tone(t0 + k * beat, beat * 0.4, hz(notes[0]), 0.18, "triangle")
        for k in range(8):
            tr.noise(t0 + k * beat / 2, 0.04, 0.07 if k % 2 else 0.04)
        tr.kick(t0, 0.5)
        tr.kick(t0 + 2.5 * beat, 0.4)
    return tr


def reveal_sting() -> Track:
    tr = Track(1.4)
    for i, n in enumerate(["C5", "E5", "G5", "C6"]):
        tr.tone(i * 0.08, 0.5 - i * 0.05, hz(n), 0.18, "square", duty=0.25, release=0.4)
    tr.tone(0.32, 0.6, hz("C4"), 0.2, "triangle", release=0.4)
    return tr


def fanfare() -> Track:
    tr = Track(4.0)
    seq = [(0.0, "G4", 0.18), (0.2, "G4", 0.12), (0.35, "G4", 0.12), (0.5, "C5", 0.5), (1.1, "A4", 0.3),
           (1.45, "B4", 0.3), (1.8, "C5", 1.4)]
    for t, n, d in seq:
        for mult, vol in ((1, 0.14), (1.5, 0.07), (0.5, 0.12)):
            tr.tone(t, d, hz(n) * mult, vol, "saw", attack=0.01, release=0.15)
    for t in (0.0, 0.5, 1.1, 1.45, 1.8):
        tr.kick(t, 0.8)
    tr.noise(1.8, 1.2, 0.18, bright=True)
    return tr


TRACKS = {"question": (question_loop, True), "lobby": (lobby_loop, True), "reveal": (reveal_sting, False),
          "fanfare": (fanfare, False)}


def ensure_tracks(directory: Path = GENERATED) -> dict[str, Path]:
    """Writes any missing generated track. Takes a few seconds the first time, then it's cached."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, (make, loop) in TRACKS.items():
        path = directory / f"{name}-v{TRACK_VERSION}.wav"
        if not path.exists():
            pcm = make().render(loop)
            tmp = path.with_suffix(".tmp")
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(pcm)
            tmp.replace(path)
        paths[name] = path
    return paths


def user_tracks(directory: Path = MUSIC_DIR) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in USER_EXTS)


def voice_available() -> bool:
    try:
        import nacl  # noqa: F401
        import davey  # noqa: F401
    except ImportError:
        return False
    return discord.opus.is_loaded() or _load_opus()


def _load_opus() -> bool:
    for name in ("libopus.so.0", "libopus.so", "opus"):
        try:
            discord.opus.load_opus(name)
            return True
        except OSError:
            continue
    return False


# --- playback ------------------------------------------------------------------

class GameMusic:
    """One per live game. join → cue("question") / cue("reveal") … → finale()."""

    def __init__(self):
        self.vc: Optional[discord.VoiceClient] = None
        self.paths: dict[str, Path] = {}
        self.question_track: Optional[Path] = None
        self.generation = 0  # bumps on every cue, so a stopped track's "then" can't override a newer cue

    async def join(self, channel: discord.VoiceChannel) -> Optional[str]:
        """Connects; returns a short problem description instead of raising."""
        if not voice_available():
            return "voice support isn't installed on the bot (PyNaCl, davey, libopus)"
        me = channel.guild.me
        perms = channel.permissions_for(me)
        if not (perms.connect and perms.speak):
            return f"I need **Connect** and **Speak** in {channel.mention}"
        if channel.guild.voice_client is not None:
            return "I'm already playing music for another game in this server"
        try:
            self.paths = await asyncio.to_thread(ensure_tracks)
            mine = user_tracks()
            self.question_track = random.choice(mine) if mine else self.paths["question"]
            self.vc = await channel.connect(self_deaf=True, timeout=15)
        except Exception as exc:  # noqa: BLE001 - music must never break the game
            log.exception("Couldn't join voice")
            self.vc = None
            return f"couldn't join voice ({type(exc).__name__})"
        return None

    def cue(self, name: str, then: Optional[str] = None) -> None:
        """Switches track now. `then` follows a one-shot track (e.g. the reveal sting, then the lobby loop)."""
        vc = self.vc
        if not vc or not vc.is_connected():
            return
        path = self.question_track if name == "question" else self.paths.get(name)
        if not path:
            return
        loop = TRACKS.get(name, (None, True))[1] if name != "question" else True
        try:
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(str(path), before_options="-stream_loop -1" if loop else ""), volume=VOLUME
            )
            if vc.is_playing() or vc.is_paused():
                vc.stop()
            self.generation += 1
            after = None
            if then:
                loop_ = vc.client.loop
                mine = self.generation

                def after(err, name=then):  # runs on the audio thread
                    if err is None:
                        loop_.call_soon_threadsafe(lambda: self.generation == mine and self.cue(name))
            vc.play(source, after=after)
        except Exception:  # noqa: BLE001
            log.exception("Couldn't play %s", name)

    async def finale(self) -> None:
        """Plays the fanfare, then leaves the channel."""
        if not self.vc:
            return
        self.cue("fanfare")
        await asyncio.sleep(4.5)
        await self.leave()

    async def leave(self) -> None:
        vc, self.vc = self.vc, None
        if vc and vc.is_connected():
            try:
                vc.stop()
                await vc.disconnect(force=True)
            except Exception:  # noqa: BLE001
                log.exception("Couldn't leave voice")
