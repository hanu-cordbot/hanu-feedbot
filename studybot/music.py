"""Game music in a voice channel during live quizzes.

The tracks are synthesised here (original chiptune loops, so there is nothing to license) and cached as WAV
files under DATA_DIR/music/generated: six question loops in different styles and two calmer lobby loops.
Each question plays the next loop in a shuffled rotation. Audio files dropped straight into DATA_DIR/music
(mp3, ogg, wav, …) join that rotation.

Music is a nice-to-have: every voice call here logs and gives up on failure rather than breaking the game.
"""
from __future__ import annotations

import asyncio
import logging
import random
import wave
from dataclasses import dataclass, field
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
TRACK_VERSION = 3  # bump to regenerate cached tracks after changing the synth

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

    def render(self, loop: bool, rms: Optional[float] = None) -> bytes:
        """16-bit PCM. With `rms`, levelled to that loudness so tracks in a rotation match."""
        np = self.np
        buf = self.buf.copy()
        if loop:  # anything ringing past the end wraps to the start, so the loop is seamless
            tail = buf[self.length:]
            buf[: len(tail)] += tail
        buf = buf[: self.length]
        buf = np.tanh(buf * 1.2)
        peak = np.max(np.abs(buf)) or 1.0
        buf = buf / peak * 0.85
        if rms:
            buf *= rms / (np.sqrt(np.mean(buf ** 2)) or 1.0)
            buf /= max(1.0, np.max(np.abs(buf)) / 0.95)
        return (buf * 32767).astype("<i2").tobytes()


CHORDS = {
    "Am": ["A2", "C4", "E4", "A4"], "F": ["F2", "A3", "C4", "F4"], "C": ["C3", "E4", "G4", "C5"],
    "G": ["G2", "B3", "D4", "G4"], "Dm": ["D3", "D4", "F4", "A4"], "E": ["E2", "G#3", "B3", "E4"],
    "Em": ["E2", "G3", "B3", "E4"], "D": ["D3", "F#3", "A3", "D4"], "Bm": ["B2", "D4", "F#4", "B4"],
    "Cmaj7": ["C3", "E4", "G4", "B4"], "Am7": ["A2", "C4", "E4", "G4"], "Dm7": ["D3", "F4", "A4", "C5"],
    "G7": ["G2", "B3", "D4", "F4"], "Fmaj7": ["F2", "A3", "C4", "E4"], "Em7": ["E2", "G3", "B3", "D4"],
}


@dataclass
class Style:
    """One question loop. Patterns are sixteenth-note steps within a bar (0-15)."""
    bpm: int
    prog: list[str]                                   # one chord per bar
    bass: list[tuple[int, int, int]]                  # (step, length in steps, octave multiplier)
    bass_wave: str = "square"
    bass_duty: float = 0.25
    bass_vol: float = 0.22
    arp: Optional[list[int]] = None                   # chord-tone index per step, repeating
    arp_every: int = 1                                # play the arp on every Nth step
    arp_wave: str = "square"
    arp_duty: float = 0.125
    arp_vol: float = 0.05
    stabs: list[int] = field(default_factory=list)    # short chord hits
    stab_wave: str = "square"
    pad: bool = False                                 # sustained chord under everything
    kick: list[int] = field(default_factory=lambda: [0, 4, 8, 12])
    snare: list[int] = field(default_factory=lambda: [4, 12])
    hats: list[int] = field(default_factory=lambda: [0, 2, 4, 6, 8, 10, 12, 14])
    hat_vol: float = 0.12
    lead_from: Optional[int] = None                   # bar where the melody comes in
    lead_rhythm: list[list[tuple[float, float]]] = field(
        default_factory=lambda: [[(0, 2), (6, 2), (8, 4), (12, 2)], [(0, 2), (2, 2), (4, 4), (10, 4)]])
    lead_wave: str = "square"
    lead_vol: float = 0.08
    seed: int = 7
    build: bool = True                                # second half gets louder arps and offbeat hats


def groove(st: Style) -> Track:
    beat = 60 / st.bpm
    step = beat / 4
    bars = len(st.prog)
    tr = Track(bars * 4 * beat)
    rng = random.Random(st.seed)
    for bar, chord in enumerate(st.prog):
        notes = CHORDS[chord]
        t0 = bar * 4 * beat
        late = st.build and bar >= bars // 2
        root = hz(notes[0])
        for k, length, mult in st.bass:
            tr.tone(t0 + k * step, length * step * 0.85, root * mult, st.bass_vol, st.bass_wave, duty=st.bass_duty)
        if st.pad:
            for n in notes[1:]:
                tr.tone(t0, 16 * step * 0.97, hz(n), 0.05, "triangle", attack=0.15, release=0.4)
        if st.arp:
            tones = [hz(n) * 2 for n in notes[1:]] + [hz(notes[2]) * 4]
            for k in range(0, 16, st.arp_every):
                idx = st.arp[(k // st.arp_every) % len(st.arp)] % len(tones)
                tr.tone(t0 + k * step, step * st.arp_every * 0.6, tones[idx], st.arp_vol * (1.4 if late else 1),
                        st.arp_wave, duty=st.arp_duty)
        for k in st.stabs:
            for n in notes[1:]:
                tr.tone(t0 + k * step, step * 1.2, hz(n) * 2, 0.045, st.stab_wave, duty=0.5, release=0.06)
        for k in st.kick:
            tr.kick(t0 + k * step, 0.8)
        for k in st.snare:
            tr.noise(t0 + k * step, 0.16, 0.33, bright=False)
        for k in st.hats:
            tr.noise(t0 + k * step, 0.05, st.hat_vol)
        if late:  # build-up: extra offbeat hats
            for k in range(1, 16, 2):
                tr.noise(t0 + k * step, 0.03, st.hat_vol * 0.5)
        if st.lead_from is not None and bar >= st.lead_from:
            for start, length in st.lead_rhythm[bar % len(st.lead_rhythm)]:
                n = rng.choice(notes[1:])
                tr.tone(t0 + start * step, length * step * 0.9, hz(n) * 2, st.lead_vol, st.lead_wave, duty=0.5,
                        release=0.08)
    return tr


EIGHTHS_OCTAVE = [(k, 2, 2 if k % 4 else 1) for k in range(0, 16, 2)]
STYLES = {
    # The original: driving minor loop, melody in the second half.
    "drive": Style(132, ["Am", "F", "C", "G"] * 2 + ["Am", "F", "C", "G", "Dm", "F", "E", "E"],
                   EIGHTHS_OCTAVE, arp=[0, 1, 2, 3, 2, 1], lead_from=8),
    # Fast 8-bit: sixteenth bass, busy arps, melody early.
    "arcade": Style(150, ["Em", "C", "G", "D"] * 4, [(k, 1, 2 if k % 2 else 1) for k in range(16)],
                    bass_duty=0.5, bass_vol=0.16, arp=[0, 2, 1, 3], arp_duty=0.25,
                    hats=[2, 6, 10, 14], lead_from=4, seed=11,
                    lead_rhythm=[[(0, 1), (1, 1), (2, 2), (4, 2), (6, 1), (7, 1), (8, 4), (12, 4)],
                                 [(0, 3), (3, 3), (6, 2), (8, 2), (10, 2), (12, 4)]]),
    # Happy major bounce with offbeat chord stabs.
    "bounce": Style(118, ["C", "Am", "F", "G"] * 4, [(0, 3, 1), (6, 2, 1), (8, 3, 2), (14, 2, 1)],
                    bass_wave="triangle", bass_vol=0.28, stabs=[2, 6, 10, 14], kick=[0, 8, 10],
                    lead_from=8, lead_wave="triangle", lead_vol=0.12, seed=3),
    # Funky seventh chords, syncopated bass, sixteenth hats.
    "groove": Style(104, ["Dm7", "G7", "Cmaj7", "Am7"] * 4, [(0, 2, 1), (3, 1, 2), (6, 2, 1), (8, 1, 1), (11, 2, 2),
                                                               (14, 2, 1)],
                    bass_duty=0.5, stabs=[3, 7, 10], stab_wave="triangle", kick=[0, 6, 8],
                    hats=list(range(16)), hat_vol=0.07, build=False),
    # Tense ticking clock: pulsing bass, rising arp, sparse drums.
    "tension": Style(140, ["Am", "Am", "F", "E"] * 4, [(k, 2, 1) for k in range(0, 16, 2)], bass_duty=0.5,
                     bass_vol=0.18, arp=[0, 1, 2, 3], arp_duty=0.25, kick=[0, 8], snare=[12],
                     hats=list(range(16)), hat_vol=0.06, build=False, lead_from=12, seed=5),
    # Spacey: soft pads, slow arps, gentle melody.
    "space": Style(124, ["Fmaj7", "Em7", "Dm7", "Cmaj7"] * 4, [(0, 6, 1), (8, 6, 1)], bass_wave="sine",
                   bass_vol=0.3, pad=True, arp=[0, 1, 2, 3, 2, 1], arp_every=2, arp_wave="triangle", arp_vol=0.06,
                   kick=[0, 8], hats=[4, 12], hat_vol=0.08, lead_from=8, lead_wave="triangle", lead_vol=0.1,
                   lead_rhythm=[[(0, 6), (8, 8)], [(0, 4), (4, 4), (8, 8)]], seed=9),
}


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


def lobby_lofi() -> Track:
    """Slow, soft loop: pads and a lazy beat."""
    beat = 60 / 86
    bars = 8
    tr = Track(bars * 4 * beat)
    for bar, chord in enumerate(["Fmaj7", "Em7", "Dm7", "Cmaj7"] * 2):
        notes = CHORDS[chord]
        t0 = bar * 4 * beat
        for n in notes[1:]:
            tr.tone(t0, 4 * beat * 0.97, hz(n), 0.06, "triangle", attack=0.2, release=0.4)
        tr.tone(t0, beat * 1.5, hz(notes[0]), 0.25, "sine")
        tr.tone(t0 + 2.5 * beat, beat, hz(notes[0]), 0.2, "sine")
        tr.kick(t0, 0.45)
        tr.kick(t0 + 2.75 * beat, 0.35)
        tr.noise(t0 + 2 * beat, 0.2, 0.18, bright=False)
        for k in range(8):
            tr.noise(t0 + k * beat / 2 + (0.03 if k % 2 else 0), 0.04, 0.05)
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


TRACKS = {f"q_{name}": ((lambda st=st: groove(st)), True) for name, st in STYLES.items()}
TRACKS.update({"lobby": (lobby_loop, True), "lobby_lofi": (lobby_lofi, True), "reveal": (reveal_sting, False),
               "fanfare": (fanfare, False)})
QUESTION_TRACKS = [k for k in TRACKS if k.startswith("q_")]
LEVELS = {"q_": 0.22, "lobby": 0.15}  # target loudness (RMS) so switching tracks doesn't jump in volume
LOBBY_TRACKS = ["lobby", "lobby_lofi"]


def ensure_tracks(directory: Path = GENERATED) -> dict[str, Path]:
    """Writes any missing generated track. Takes a few seconds the first time, then it's cached."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, (make, loop) in TRACKS.items():
        path = directory / f"{name}-v{TRACK_VERSION}.wav"
        if not path.exists():
            pcm = make().render(loop, rms=LEVELS.get(name[:2]) or LEVELS.get(name.split("_")[0]))
            tmp = path.with_suffix(".tmp")
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(pcm)
            tmp.replace(path)
        paths[name] = path
    for old in directory.glob("*.wav"):  # tracks from an older synth version, or removed styles
        if old not in paths.values():
            old.unlink(missing_ok=True)
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
        self.rotation: list[Path] = []  # question loops, played in turn: one per question
        self.turn = 0
        self.lobby_turn = 0
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
            self.rotation = user_tracks() + [self.paths[k] for k in QUESTION_TRACKS]
            random.shuffle(self.rotation)
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
        path = self.pick(name)
        if not path:
            return
        loop = TRACKS.get(name, (None, True))[1] if name not in ("question", "lobby") else True
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

    def pick(self, name: str) -> Optional[Path]:
        """'question' and 'lobby' cycle through their tracks; anything else is one named track."""
        if name == "question":
            if not self.rotation:
                return None
            self.turn += 1
            return self.rotation[(self.turn - 1) % len(self.rotation)]
        if name == "lobby":
            self.lobby_turn += 1
            return self.paths.get(LOBBY_TRACKS[(self.lobby_turn - 1) % len(LOBBY_TRACKS)])
        return self.paths.get(name)

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
