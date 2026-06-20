"""
Auralis — a Hebrew/English lecture transcriber.

Eel + the Claude Design HTML/CSS for the UI. Python keeps all the original
audio capture, transcription, post-processing, trigger handling, and config
logic; the front-end is a browser window (Chrome/Edge in app mode) that
renders the design verbatim and talks to Python over a WebSocket bridge.

Features (unchanged from the previous build):
- Live transcription with faster-whisper (default: Ivrit.AI Hebrew turbo)
- WAV recording + automatic high-quality post-process on Stop
- Course + Category (Lectures/Exercises) organization with auto-skeleton
- Library tab with re-run, move, delete, import
- Trigger keywords -> file + clipboard for Cowork
- Dynamic vocabulary that evolves with the lecture
- Settings persisted in config.json

Run:  python auralis.py
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
import webbrowser
from dataclasses import dataclass, field, asdict
from logging.handlers import RotatingFileHandler
from pathlib import Path

import numpy as np

try:
    import soundcard as sc
except Exception:
    sc = None

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

try:
    import process_loopback as _process_loopback   # bundled module
except Exception:
    _process_loopback = None

try:
    import model_manager as _model_manager
except Exception:
    _model_manager = None

import eel


# Paths -----------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
UI_DIR = APP_DIR / "ui"
CONFIG_PATH = APP_DIR / "config.json"
TRIGGERS_DIR = APP_DIR / "triggers"
LIVE_ROOT = APP_DIR / "live_transcripts"
POST_ROOT = APP_DIR / "post_processed_transcripts"
REC_ROOT = APP_DIR / "recordings"
LOGS_DIR = APP_DIR / "logs"
for _d in (TRIGGERS_DIR, LIVE_ROOT, POST_ROOT, REC_ROOT, LOGS_DIR):
    _d.mkdir(exist_ok=True)

# Logging — rotating file in logs/auralis.log so we can debug user issues.
_log_handler = RotatingFileHandler(
    LOGS_DIR / "auralis.log", maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
)
_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s  %(levelname)-7s  %(name)s:  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
log = logging.getLogger("auralis")
log.info("=" * 60)
log.info("Auralis v%s starting (Eel UI)", "1.1.1")

SAMPLE_RATE = 16_000
CHUNK_SECONDS = 30.0
CONTEXT_SECONDS_FOR_TRIGGER = 120
APP_NAME = "Auralis"
APP_VERSION = "1.1.1"
APP_BUILD_DATE = "2026-05-20"
APP_TAGLINE = "Listen. Transcribe. Study."
APP_AUTHOR = "Amit"
APP_LICENSE = "MIT"

MODEL_PRESETS = {
    "Ivrit.AI v3 turbo  (Hebrew, recommended)": "ivrit-ai/whisper-large-v3-turbo-ct2",
    "Ivrit.AI v3        (Hebrew, slower)":       "ivrit-ai/whisper-large-v3-ct2",
    "Whisper large-v3   (slow, accurate)":      "large-v3",
    "Whisper medium":                            "medium",
    "Whisper small":                             "small",
    "Whisper base":                              "base",
    "Whisper tiny":                              "tiny",
}
MODEL_LABELS = list(MODEL_PRESETS.keys())
CATEGORIES = ["Lectures", "Exercises"]


# File-system helpers ---------------------------------------------------

def _safe_course_name(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"[^\w\-֐-׿ ]+", "", s, flags=re.UNICODE)
    s = s.replace(" ", "_")
    return s or "default"


def _course_subdir(root: Path, course: str, category: str = "") -> Path:
    d = root / _safe_course_name(course)
    if category:
        d = d / _safe_course_name(category)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_course_skeleton(course: str) -> None:
    for root in (REC_ROOT, LIVE_ROOT, POST_ROOT):
        for cat in CATEGORIES:
            (root / _safe_course_name(course) / _safe_course_name(cat)).mkdir(
                parents=True, exist_ok=True
            )


# Stopwords for dynamic vocab -------------------------------------------

HEBREW_STOPWORDS = {
    "אני","אתה","את","הוא","היא","אנחנו","אתם","הן","הם",
    "של","על","אם","כי","מה","אבל","גם","רק","יש","אין","או",
    "לא","כן","אז","כל","כמו","אחד","אחת","אנו","זה","זאת","אלה",
    "הזה","הזאת","כאן","שם","פה","עכשיו","אחר","אחרי","לפני",
    "להיות","יהיה","היה","הייתה","עוד","כבר","באמת","מאוד","ש",
    "כדי","אולי","עכשו","תמיד","פעם","טוב","רע","יותר","פחות",
    "אפשר","אומר","אומרת","אומרים","צריך","צריכה","צריכים",
    "באופן","למשל","כדוגמה","במקום",
}
ENGLISH_STOPWORDS = {
    "the","is","at","which","on","and","a","an","of","to","in",
    "for","with","as","by","this","that","i","you","he","she","it","we","they",
    "but","or","so","not","all","any","be","are","was","were","have","has","had",
    "do","does","did","will","would","can","could","should","may","might","must",
    "from","up","down","out","about","into","through","during","before","after",
    "above","below","between","under","again","then","than","very","just","more",
    "less","no","yes","ok","okay","now","here","there","if","when","what","who",
    "how","why","where","some","such","only","also","really",
}
WORD_RE = re.compile(r"[\w']+", flags=re.UNICODE)


class DynamicVocabExtractor:
    def __init__(self, top_n: int = 30, history_minutes: int = 20,
                 update_interval_minutes: int = 10):
        self.top_n = top_n
        self.history_minutes = history_minutes
        self.update_interval_minutes = update_interval_minutes
        self.history: list = []
        self.last_update_time: float = 0.0
        self.current_terms: list = []

    def add_segment(self, ts: float, text: str):
        self.history.append((ts, text))
        cutoff = ts - (self.history_minutes * 60.0)
        self.history = [(t, x) for (t, x) in self.history if t >= cutoff]

    def should_update(self, now_ts: float) -> bool:
        if self.last_update_time == 0.0:
            return any(t >= 2 * 60 for t, _ in self.history)
        return (now_ts - self.last_update_time) >= self.update_interval_minutes * 60

    def recompute(self, now_ts: float) -> list:
        from collections import Counter
        counter: Counter = Counter()
        for _, text in self.history:
            for w in WORD_RE.findall(text):
                w = w.strip("'_")
                if len(w) < 3:
                    continue
                wl = w.lower()
                if wl in HEBREW_STOPWORDS or wl in ENGLISH_STOPWORDS:
                    continue
                if wl.isdigit():
                    continue
                counter[w] += 1
        ranked = [w for w, c in counter.most_common(self.top_n * 2) if c >= 2]
        self.current_terms = ranked[: self.top_n]
        self.last_update_time = now_ts
        return self.current_terms


# Config ----------------------------------------------------------------

@dataclass
class AppConfig:
    language: str = "he"
    whisper_model_label: str = MODEL_LABELS[0]
    compute_type: str = "int8"
    triggers: list = field(default_factory=lambda: ["kahoot", "surprise test", "quiz", "מבחן פתע"])
    meeting_prompt: str = (
        "A trigger keyword was detected during a university lecture. "
        "Read the transcript context and respond with whatever is most "
        "useful right now. Keep it under 150 words."
    )
    initial_prompt: str = (
        "הרצאה באוניברסיטה במדעי החשמל. אופטואלקטרוניקה, פוטונים, "
        "דיודות, מוליכים למחצה, אורך גל, אנרגיית פס, פוריה, מערכת לינארית."
    )
    cooldown_seconds: int = 30
    output_device_name: str = ""
    # Audio capture mode:
    #   "system" — default speaker loopback (whole system mix)
    #   "device" — named speaker loopback (output_device_name)
    #   "app"    — specific process via WASAPI Process Loopback API
    audio_capture_mode: str = "system"
    output_app_pid: int = 0
    output_app_name: str = ""
    postprocess_enabled: bool = True
    save_audio: bool = True
    save_live_transcript_enabled: bool = True
    # Library view mode for the recordings list ("list" | "cards")
    library_view_mode: str = "list"
    courses: list = field(default_factory=lambda: [
        "General",
        "מיקרו מעבדים ושפת אסמבלר",
        "תהליכי ייצור במיקרואלקטרוניקה",
        "אופטואלקטרוניקה התקנים ומערכות",
        "התקני ננו-אלקטרוניקה",
        "מעגלים משולבים ספרתיים",
        "מבוא ללייזרים",
    ])
    current_course: str = "אופטואלקטרוניקה התקנים ומערכות"
    current_category: str = "Lectures"
    auto_stop_silence_minutes: int = 20
    silence_rms_threshold: float = 0.005
    dark_mode: bool = True
    first_run: bool = True
    dynamic_vocab_enabled: bool = True
    dynamic_vocab_interval_minutes: int = 10
    dynamic_vocab_history_minutes: int = 20
    dynamic_vocab_top_n: int = 30

    @property
    def whisper_model_id(self) -> str:
        return MODEL_PRESETS.get(self.whisper_model_label, "large-v3")

    @classmethod
    def load(cls):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                cfg = cls()
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
                if cfg.current_course not in cfg.courses:
                    cfg.courses.insert(0, cfg.current_course)
                return cfg
            except Exception:
                pass
        return cls()

    def save(self):
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# Audio capture ---------------------------------------------------------

class AudioCaptureThread(threading.Thread):
    """Capture loop. Three modes:
      "system" — default speaker loopback (whole system mix)
      "device" — named speaker loopback (device_name)
      "app"    — specific process via WASAPI Process Loopback API
    """
    def __init__(self, audio_queue, device_name, stop_event, wav_path=None,
                 silence_rms_threshold=0.005, capture_mode="system",
                 app_pid=0, app_name="", level_callback=None):
        super().__init__(daemon=True)
        self.audio_queue = audio_queue
        self.device_name = device_name
        self.stop_event = stop_event
        self.wav_path = wav_path
        self.wav_file = None
        self.error = None
        self.silence_rms_threshold = silence_rms_threshold
        self.last_sound_ts = time.time()
        self.capture_mode = capture_mode or "system"
        self.app_pid = int(app_pid or 0)
        self.app_name = app_name or ""
        # level_callback(rms_float) is invoked from this thread for each chunk
        # so the UI can render a live waveform / VU meter.
        self.level_callback = level_callback

    def run(self):
        if self.wav_path is not None:
            try:
                self.wav_path.parent.mkdir(parents=True, exist_ok=True)
                self.wav_file = wave.open(str(self.wav_path), "wb")
                self.wav_file.setnchannels(1)
                self.wav_file.setsampwidth(2)
                self.wav_file.setframerate(SAMPLE_RATE)
            except Exception as e:
                self.wav_file = None
                self.error = "Could not open WAV file: " + str(e)
        try:
            if self.capture_mode == "app" and _process_loopback is not None and self.app_pid:
                self._run_app_loopback()
            else:
                self._run_speaker_loopback()
        finally:
            if self.wav_file is not None:
                try:
                    self.wav_file.close()
                except Exception:
                    pass
                self.wav_file = None

    def _publish_chunk(self, mono):
        """Common path for both capture modes — push to queue, write to WAV,
        update silence timestamp, notify level callback."""
        self.audio_queue.put(mono)
        if self.wav_file is not None:
            try:
                clipped = np.clip(mono, -1.0, 1.0)
                int16 = (clipped * 32767.0).astype(np.int16)
                self.wav_file.writeframes(int16.tobytes())
            except Exception:
                pass
        try:
            rms = float(np.sqrt(np.mean(mono ** 2)))
            if rms >= self.silence_rms_threshold:
                self.last_sound_ts = time.time()
            if self.level_callback is not None:
                self.level_callback(rms)
        except Exception:
            pass

    def _run_speaker_loopback(self):
        if sc is None:
            self.error = "soundcard package not installed."
            return
        try:
            speaker = self._resolve_speaker()
            loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        except Exception as e:
            self.error = "Could not open loopback: " + str(e)
            return
        frames_per_chunk = int(SAMPLE_RATE * CHUNK_SECONDS)
        try:
            with loopback.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=4096) as rec:
                while not self.stop_event.is_set():
                    data = rec.record(numframes=frames_per_chunk)
                    if self.stop_event.is_set():
                        break
                    if data.ndim > 1:
                        data = data.mean(axis=1)
                    self._publish_chunk(data.astype(np.float32))
        except Exception as e:
            if not self.stop_event.is_set():
                self.error = "Recording error: " + str(e)

    def _run_app_loopback(self):
        """Per-process audio capture via the bundled process_loopback module."""
        try:
            cap = _process_loopback.ProcessLoopbackCapture(
                pid=self.app_pid, sample_rate=SAMPLE_RATE)
        except Exception as e:
            self.error = "App capture failed (" + str(e) + ") — falling back to system."
            self._run_speaker_loopback()
            return
        frames_per_chunk = int(SAMPLE_RATE * CHUNK_SECONDS)
        try:
            cap.start()
            buf = np.zeros(0, dtype=np.float32)
            while not self.stop_event.is_set():
                more = cap.read(frames_per_chunk)
                if more is None or len(more) == 0:
                    time.sleep(0.05)
                    continue
                if more.ndim > 1:
                    more = more.mean(axis=1)
                buf = np.concatenate([buf, more.astype(np.float32)])
                while len(buf) >= frames_per_chunk and not self.stop_event.is_set():
                    chunk = buf[:frames_per_chunk]
                    buf = buf[frames_per_chunk:]
                    self._publish_chunk(chunk)
        except Exception as e:
            if not self.stop_event.is_set():
                self.error = "App recording error: " + str(e)
        finally:
            try:
                cap.stop()
            except Exception:
                pass

    def _resolve_speaker(self):
        if self.capture_mode == "device" and self.device_name:
            for s in sc.all_speakers():
                if self.device_name.lower() in s.name.lower():
                    return s
        return sc.default_speaker()


@dataclass
class TranscriptSegment:
    timestamp: float
    text: str
    language: str


class TranscriptionThread(threading.Thread):
    def __init__(self, audio_queue, text_queue, cfg, stop_event, start_time):
        super().__init__(daemon=True)
        self.audio_queue = audio_queue
        self.text_queue = text_queue
        self.cfg = cfg
        self.stop_event = stop_event
        self.start_time = start_time
        self.error = None
        self.model = None
        self._tail = ""
        self.vocab = DynamicVocabExtractor(
            top_n=getattr(cfg, "dynamic_vocab_top_n", 30),
            history_minutes=getattr(cfg, "dynamic_vocab_history_minutes", 20),
            update_interval_minutes=getattr(cfg, "dynamic_vocab_interval_minutes", 10),
        )
        self.dynamic_prompt = ""

    def run(self):
        if WhisperModel is None:
            self.error = "faster-whisper not installed."
            self.text_queue.put(("error", self.error))
            return
        model_id = self.cfg.whisper_model_id
        try:
            self.text_queue.put(("status", "Loading model '" + model_id + "'..."))
            self.model = WhisperModel(model_id, device="auto", compute_type=self.cfg.compute_type)
            self.text_queue.put(("status", "Model loaded. Listening..."))
        except Exception as e:
            self.error = "Failed to load model: " + str(e)
            self.text_queue.put(("error", self.error))
            return
        while not self.stop_event.is_set():
            try:
                audio = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self.stop_event.is_set():
                break
            try:
                lang = None if self.cfg.language == "auto" else self.cfg.language
                parts = []
                if (self.cfg.initial_prompt or "").strip():
                    parts.append(self.cfg.initial_prompt.strip())
                if getattr(self.cfg, "dynamic_vocab_enabled", True) and self.dynamic_prompt:
                    parts.append(self.dynamic_prompt)
                if self._tail:
                    parts.append(self._tail)
                initial = " ".join(parts).strip() or None
                segments, info = self.model.transcribe(
                    audio, language=lang, vad_filter=False, beam_size=5,
                    condition_on_previous_text=True, initial_prompt=initial,
                    temperature=[0.0, 0.2, 0.4],
                )
                ts = time.time() - self.start_time
                pieces = [s.text.strip() for s in segments if s.text.strip()]
                if pieces:
                    text = " ".join(pieces)
                    self._tail = (self._tail + " " + text)[-400:].strip()
                    if getattr(self.cfg, "dynamic_vocab_enabled", True):
                        self.vocab.add_segment(ts, text)
                        if self.vocab.should_update(ts):
                            terms = self.vocab.recompute(ts)
                            self.dynamic_prompt = ", ".join(terms)
                            self.text_queue.put(("vocab", terms))
                    self.text_queue.put(("segment", TranscriptSegment(ts, text, info.language)))
            except Exception as e:
                # Race during shutdown: model.transcribe() can raise when the
                # audio queue dries up mid-call after stop_event fires. Those
                # are expected and shouldn't surface as a user-visible error
                # (it was the source of the sticky "Whisper error" pill).
                if self.stop_event.is_set():
                    log.debug("Transcription exception during shutdown: %s", e)
                else:
                    self.text_queue.put(("error", "Transcription error: " + str(e)))


class PostProcessThread(threading.Thread):
    def __init__(self, wav_path: Path, out_path: Path, cfg, status_cb, done_cb=None,
                 progress_cb=None, cancel_event=None):
        super().__init__(daemon=False)
        self.wav_path = wav_path
        self.out_path = out_path
        self.cfg = cfg
        self.status_cb = status_cb
        self.done_cb = done_cb
        self.progress_cb = progress_cb
        self.cancel_event = cancel_event

    def _cancelled(self):
        return self.cancel_event is not None and self.cancel_event.is_set()

    def run(self):
        success = False
        try:
            if WhisperModel is None:
                self.status_cb("Post-process error: faster-whisper not installed.")
                return
            if not self.wav_path.exists() or self.wav_path.stat().st_size < 1024:
                self.status_cb("Post-process skipped: no audio captured.")
                return
            model_id = self.cfg.whisper_model_id
            try:
                self.status_cb("Post-processing: loading model '" + model_id + "'...")
                if self.progress_cb: self.progress_cb(5)
                if self._cancelled(): return
                model = WhisperModel(model_id, device="auto", compute_type=self.cfg.compute_type)
                if self.progress_cb: self.progress_cb(15)
            except Exception as e:
                self.status_cb("Post-process error: " + str(e))
                return
            try:
                self.status_cb("Post-processing: transcribing full audio...")
                lang = None if self.cfg.language == "auto" else self.cfg.language
                initial = (self.cfg.initial_prompt or "").strip() or None
                segments, info = model.transcribe(
                    str(self.wav_path), language=lang, vad_filter=True, beam_size=10,
                    condition_on_previous_text=True, initial_prompt=initial,
                    temperature=[0.0, 0.2, 0.4, 0.6, 0.8],
                )
                # Estimate total length from the wav header so we can map
                # segment.end → progress percentage as we iterate.
                try:
                    total_s = _wav_duration_seconds(self.wav_path) or 1.0
                except Exception:
                    total_s = 1.0
                lines = []
                for seg in segments:
                    if self._cancelled():
                        self.status_cb("Post-process cancelled by user.")
                        return
                    start = float(seg.start or 0.0)
                    end = float(seg.end or start)
                    m, s = divmod(int(start), 60)
                    h, m = divmod(m, 60)
                    stamp = "{:d}:{:02d}:{:02d}".format(h, m, s) if h else "{:02d}:{:02d}".format(m, s)
                    t = (seg.text or "").strip()
                    if t:
                        lines.append("[" + stamp + "] " + t)
                    if self.progress_cb:
                        # 15% loading + 80% transcribe + 5% write
                        pct = 15 + int(80 * min(1.0, end / total_s))
                        self.progress_cb(pct)
                if self._cancelled():
                    return
                self.out_path.parent.mkdir(parents=True, exist_ok=True)
                header = (
                    "# Post-processed transcript\n"
                    "# Source: " + str(self.wav_path) + "\n"
                    "# Model: " + model_id + "\n"
                    "# Language: " + str(info.language) + "\n\n"
                )
                self.out_path.write_text(header + "\n".join(lines), encoding="utf-8")
                self.status_cb("Post-processed transcript saved: " + str(self.out_path))
                if self.progress_cb: self.progress_cb(100)
                success = True
            except Exception as e:
                self.status_cb("Post-process error during transcribe: " + str(e))
        finally:
            if self.done_cb:
                try:
                    self.done_cb(self.wav_path, success)
                except Exception:
                    pass


# Trigger handler -------------------------------------------------------

def _slug(s):
    out = "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")[:30]
    return out or "trigger"


class TriggerHandler:
    def __init__(self, cfg, clipboard_setter):
        self.cfg = cfg
        self.clipboard_setter = clipboard_setter
        self.last_fire = {}
        self.recent = []

    def add_segment(self, seg):
        self.recent.append(seg)
        cutoff = seg.timestamp - CONTEXT_SECONDS_FOR_TRIGGER
        self.recent = [s for s in self.recent if s.timestamp >= cutoff]
        low = seg.text.lower()
        now = time.time()
        for trig in self.cfg.triggers:
            t = trig.strip()
            if not t:
                continue
            if t.lower() in low:
                if now - self.last_fire.get(t, 0.0) >= self.cfg.cooldown_seconds:
                    self.last_fire[t] = now
                    return t
        return None

    def emit_trigger(self, trigger, seg):
        ts_human = time.strftime("%Y-%m-%d %H:%M:%S")
        ts_file = time.strftime("%Y%m%d_%H%M%S")
        ctx = "\n".join("[" + str(int(s.timestamp)) + "s] " + s.text for s in self.recent)
        payload = (
            "# Trigger fired: '" + trigger + "'\n"
            "# When: " + ts_human + "\n"
            "# Meeting prompt:\n\n" + self.cfg.meeting_prompt + "\n\n"
            "---\n\n# Recent transcript context:\n\n" + ctx + "\n"
        )
        fname = TRIGGERS_DIR / ("trigger_" + ts_file + "_" + _slug(trigger) + ".txt")
        fname.write_text(payload, encoding="utf-8")
        (TRIGGERS_DIR / "latest.txt").write_text(payload, encoding="utf-8")
        try:
            self.clipboard_setter(payload)
        except Exception:
            pass
        return {
            "trigger": trigger,
            "timestamp": seg.timestamp,
            "ts_human": ts_human,
            "preview": (seg.text[:200]),
            "path": str(fname),
        }


# Utilities -------------------------------------------------------------

def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "{:.1f} {}".format(n, unit)
        n /= 1024
    return "{:.1f} TB".format(n)


def _wav_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def _format_duration(secs: float) -> str:
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "{:d}:{:02d}:{:02d}".format(h, m, s)
    return "{:02d}:{:02d}".format(m, s)


def _set_clipboard(text):
    """Cross-platform clipboard write that doesn't need a Tk root.

    Windows → `clip` (UTF-16 LE).
    macOS   → `pbcopy` (UTF-8).
    Linux   → tries `xclip`, then `xsel`. Silent no-op if neither installed.
    """
    try:
        if sys.platform.startswith("win"):
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-16le"))
        elif sys.platform == "darwin":
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"))
        else:
            for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "-b", "-i"]):
                try:
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                    proc.communicate(input=text.encode("utf-8"))
                    return
                except FileNotFoundError:
                    continue
    except Exception:
        pass


def _open_path(path):
    """Open `path` in the OS default application. Cross-platform."""
    p = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception:
        pass


def _reveal_in_folder(path):
    """Show `path` in the OS file manager with the file pre-selected."""
    p = Path(path)
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(p)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p.parent)])
    except Exception:
        try:
            _open_path(p.parent)
        except Exception:
            pass


# Back-compat alias: some older call sites still import this name.
_set_windows_clipboard = _set_clipboard


def _find_companion(wav, root, course, category="", suffix=".txt"):
    """Best-effort match: find the live/post transcript that goes with `wav`."""
    m = re.search(r"(\d{8}_\d{6})", wav.name)
    if not m:
        return None
    ts = m.group(1)
    candidates = []
    if course and category:
        candidates.append(root / _safe_course_name(course) / _safe_course_name(category) / ("transcript_" + ts + suffix))
    if course:
        candidates.append(root / _safe_course_name(course) / ("transcript_" + ts + suffix))
    candidates.append(root / ("transcript_" + ts + suffix))
    for c in candidates:
        if c.exists():
            return c
    search_dirs = [root]
    if course:
        cd = root / _safe_course_name(course)
        search_dirs.append(cd)
        if category:
            search_dirs.append(cd / _safe_course_name(category))
        for sub in (cd.iterdir() if cd.exists() else []):
            if sub.is_dir():
                search_dirs.append(sub)
    for d in search_dirs:
        if not d.exists():
            continue
        for f in d.glob("*" + ts + "*"):
            if suffix == ".txt" and "_postprocessed.txt" not in f.name and f.suffix == ".txt":
                return f
            if suffix == "_postprocessed.txt" and f.name.endswith(suffix):
                return f
    return None


def _scan_library(in_progress_set=None):
    """Walk REC_ROOT and return [{course, category, wavs:[...]}, ...] grouped
    by course. Each wav dict contains path, name, size, duration_seconds,
    has_live, has_post, mtime, is_polishing."""
    by_course = {}
    if REC_ROOT.exists():
        for d in sorted(REC_ROOT.iterdir()):
            if not d.is_dir():
                continue
            course = d.name
            entry = {"course": course, "categories": {}, "total_recordings": 0,
                     "total_duration_s": 0.0}
            direct = sorted(d.glob("*.wav"))
            if direct:
                entry["categories"][""] = []
                for w in direct:
                    info = _wav_info(w, course, "", in_progress_set)
                    entry["categories"][""].append(info)
                    entry["total_recordings"] += 1
                    entry["total_duration_s"] += info["duration_seconds"]
            for sd in sorted([sd for sd in d.iterdir() if sd.is_dir()]):
                cat = sd.name
                items = []
                for w in sorted(sd.glob("*.wav")):
                    info = _wav_info(w, course, cat, in_progress_set)
                    items.append(info)
                    entry["total_recordings"] += 1
                    entry["total_duration_s"] += info["duration_seconds"]
                entry["categories"][cat] = items
            by_course[course] = entry
    loose = sorted(REC_ROOT.glob("*.wav"))
    if loose:
        entry = {"course": "", "categories": {"": []},
                 "total_recordings": 0, "total_duration_s": 0.0}
        for w in loose:
            info = _wav_info(w, "", "", in_progress_set)
            entry["categories"][""].append(info)
            entry["total_recordings"] += 1
            entry["total_duration_s"] += info["duration_seconds"]
        by_course[""] = entry
    return list(by_course.values())


def _wav_info(wav: Path, course: str, category: str, in_progress_set=None):
    try:
        dur = _wav_duration_seconds(wav)
    except Exception:
        dur = 0.0
    try:
        size = wav.stat().st_size
        mtime = wav.stat().st_mtime
    except Exception:
        size, mtime = 0, 0.0
    live = _find_companion(wav, LIVE_ROOT, course, category, suffix=".txt")
    post = _find_companion(wav, POST_ROOT, course, category, suffix="_postprocessed.txt")
    is_polishing = bool(in_progress_set and str(wav) in in_progress_set)
    return {
        "path": str(wav),
        "name": wav.name,
        "course": course,
        "category": category,
        "size_bytes": int(size),
        "size_human": _human_size(int(size)),
        "duration_seconds": float(dur),
        "duration_human": _format_duration(dur),
        "mtime_epoch": float(mtime),
        "mtime_human": time.strftime("%a · %b %d", time.localtime(mtime)),
        "mtime_short": time.strftime("%H:%M", time.localtime(mtime)),
        "has_live": live is not None,
        "live_path": str(live) if live else "",
        "has_post": post is not None,
        "post_path": str(post) if post else "",
        "is_polishing": is_polishing,
        # `warn` is the "no post-processed copy yet — run polish to recover" hint.
        "warn": ("" if (post or is_polishing) else
                 ("No post-processed copy yet — run polish to recover." if live else "")),
    }


# =====================================================================
# Eel app — the Python ↔ JS bridge
# =====================================================================

class AuralisApp:
    """Holds runtime state and exposes @eel.expose'd methods.

    Note: instance methods can't be decorated with @eel.expose directly. We
    expose them at module-import time by binding to module-level functions
    that delegate to the singleton instance.
    """

    def __init__(self):
        self.cfg = AppConfig.load()
        # Recording state
        self.audio_queue = queue.Queue(maxsize=50)
        self.text_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.audio_thread = None
        self.transcribe_thread = None
        self.trigger_handler = None
        self.recording_start = None
        self.is_recording = False
        self.all_segments = []
        self.recording_wav_path = None
        self.recording_ts_file = ""
        self.postprocess_thread = None
        self.postprocess_cancel = threading.Event()
        self._polish_progress = 0   # 0-100, set by PostProcessThread
        self._polish_wav_path = None
        self.in_progress_wavs: set = set()
        # Cached static lookups
        self._devices_cache: list = []
        self._audio_apps_cache: list = []
        self._cfg_last_saved_ts = time.time()
        self._whisper_status = "ready"  # "loading" | "ready" | "error"
        # Throttle for audio-level pushes (don't flood the websocket).
        self._last_level_push_ts = 0.0
        self._refresh_devices_internal()
        self._refresh_apps_internal()
        # Ensure course skeleton for every configured course.
        for c in self.cfg.courses:
            try:
                _ensure_course_skeleton(c)
            except Exception:
                pass
        log.info("AuralisApp initialized; %d courses; dark=%s",
                 len(self.cfg.courses), self.cfg.dark_mode)

    # ---- state snapshot for the UI ------------------------------------

    def get_state(self):
        """Single payload used by the JS App on mount and after refreshes."""
        return {
            "config": asdict(self.cfg),
            "model_labels": MODEL_LABELS,
            "categories": CATEGORIES,
            "devices": self._devices_cache,
            "audio_apps": self._audio_apps_cache,
            "courses": self.cfg.courses,
            "library": _scan_library(self.in_progress_wavs),
            "recording": self._recording_blob(),
            "transcript_segments": [],
            "triggers": [],
            "dyn_vocab": [],
            "audio_level": 0.0,
            "whisper_status": self._whisper_status,
            "app_dir": str(APP_DIR),
            "version": APP_VERSION,
            "build_date": APP_BUILD_DATE,
            "is_first_run": bool(self.cfg.first_run),
            "config_last_saved_ts": self._cfg_last_saved_ts,
        }

    def _recording_blob(self):
        rec = {
            "is_recording": self.is_recording,
            "polishing": (self.postprocess_thread is not None
                          and self.postprocess_thread.is_alive()),
            "elapsed_seconds": 0,
            "recording_start_ts": self.recording_start,
            "polish_progress": self._polish_progress,
            "polish_path": (str(self._polish_wav_path)
                            if self._polish_wav_path else None),
            "polishing_paths": list(self.in_progress_wavs),
        }
        if self.is_recording and self.recording_start is not None:
            rec["elapsed_seconds"] = int(time.time() - self.recording_start)
        return rec

    # ---- push helpers -------------------------------------------------

    def _push(self, name, *args):
        try:
            fn = getattr(eel, name, None)
            if fn is None:
                log.warning("push %s: no JS handler registered", name)
                return
            fn(*args)
        except Exception as e:
            log.warning("push %s failed: %s", name, e)

    def push_state_patch(self, patch):
        self._push("push_state_patch", patch)

    def push_toast(self, title, body="", action=None, action_cmd=None,
                   action_path=None, icon="✓", variant="good", duration_ms=6000):
        self._push("push_toast", {
            "title": title, "body": body, "action": action,
            "actionCmd": action_cmd, "actionPath": action_path,
            "icon": icon, "variant": variant, "durationMs": duration_ms,
        })

    # ---- recording ----------------------------------------------------

    def start_recording(self, course, category):
        if sc is None or WhisperModel is None:
            return {"ok": False, "error": "Missing dependencies — run setup_and_run.bat first."}
        if self.is_recording:
            return {"ok": False, "error": "Already recording."}
        # Persist the chosen course/category so config reflects current pick.
        self.cfg.current_course = course or self.cfg.current_course
        self.cfg.current_category = category or self.cfg.current_category
        self.cfg.save()
        self.stop_event.clear()
        self._drain_queues()
        self.all_segments = []
        course = self.cfg.current_course or "General"
        category = self.cfg.current_category or CATEGORIES[0]
        _ensure_course_skeleton(course)
        ts_file = time.strftime("%Y%m%d_%H%M%S")
        self.recording_ts_file = ts_file
        self.recording_wav_path = None
        if self.cfg.save_audio or self.cfg.postprocess_enabled:
            self.recording_wav_path = _course_subdir(REC_ROOT, course, category) / ("lecture_" + ts_file + ".wav")
        self.recording_start = time.time()
        self.trigger_handler = TriggerHandler(self.cfg, _set_windows_clipboard)
        self.audio_thread = AudioCaptureThread(
            self.audio_queue, self.cfg.output_device_name,
            self.stop_event, wav_path=self.recording_wav_path,
            silence_rms_threshold=getattr(self.cfg, "silence_rms_threshold", 0.005),
            capture_mode=getattr(self.cfg, "audio_capture_mode", "system"),
            app_pid=getattr(self.cfg, "output_app_pid", 0),
            app_name=getattr(self.cfg, "output_app_name", ""),
            level_callback=self._on_audio_level,
        )
        self.transcribe_thread = TranscriptionThread(
            self.audio_queue, self.text_queue,
            self.cfg, self.stop_event, self.recording_start)
        self._set_whisper_status("loading")
        self.audio_thread.start()
        self.transcribe_thread.start()
        self.is_recording = True
        log.info("Recording started: course=%s category=%s",
                 self.cfg.current_course, self.cfg.current_category)
        self.push_state_patch({
            "recording": self._recording_blob(),
            "transcript_segments": [],
            "triggers": [],
            "dyn_vocab": [],
        })
        self.push_toast(title="Recording started",
                        body=course + " / " + category + " — press S to stop",
                        icon="●", variant="accent", duration_ms=3500)
        return {"ok": True}

    def _on_audio_level(self, level):
        """Throttled audio-level push so the JS waveform stays smooth without
        flooding the websocket. ~20 updates per second is plenty."""
        now = time.time()
        if now - self._last_level_push_ts < 0.05:
            return
        self._last_level_push_ts = now
        try:
            self._push("push_audio_level", float(level))
        except Exception:
            pass

    def _set_whisper_status(self, status):
        if status != self._whisper_status:
            self._whisper_status = status
            self.push_state_patch({"whisper_status": status})

    def stop_recording(self):
        if not self.is_recording:
            return {"ok": False, "error": "Not recording."}
        self.stop_event.set()
        self.is_recording = False
        log.info("Recording stopped — joining threads")
        threading.Thread(target=self._finalize_stop, daemon=True).start()
        self.push_state_patch({"recording": self._recording_blob()})
        self.push_toast(title="Recording stopped",
                        body="Saving transcript…", icon="■",
                        variant="good", duration_ms=2500)
        return {"ok": True}

    def _finalize_stop(self):
        for th in (self.audio_thread, self.transcribe_thread):
            if th is not None:
                th.join(timeout=4.0)
        self.audio_thread = None
        self.transcribe_thread = None
        self._drain_queues()
        # The transcription model is loaded and ready for the next session —
        # clear any stale "loading" / "error" state so the hero pill and the
        # Start button both come back to a usable state.
        self._set_whisper_status("ready")
        course = self.cfg.current_course or "General"
        category = self.cfg.current_category or CATEGORIES[0]
        ts = self.recording_ts_file or time.strftime("%Y%m%d_%H%M%S")
        live_path = None
        if self.cfg.save_live_transcript_enabled and self.all_segments:
            try:
                live_dir = _course_subdir(LIVE_ROOT, course, category)
                live_path = live_dir / ("transcript_" + ts + ".txt")
                live_path.write_text(self._format_transcript(), encoding="utf-8")
            except Exception as e:
                log.exception("save live transcript failed: %s", e)
        if live_path:
            self.push_toast(title="Live transcript saved",
                            body=str(live_path),
                            action="Show in folder",
                            action_cmd="reveal",
                            action_path=str(live_path),
                            icon="✓", variant="good")
        if (self.cfg.postprocess_enabled and self.recording_wav_path is not None
                and self.recording_wav_path.exists()):
            try:
                out_dir = _course_subdir(POST_ROOT, course, category)
                out = out_dir / ("transcript_" + ts + "_postprocessed.txt")
                self.in_progress_wavs.add(str(self.recording_wav_path))
                self._polish_wav_path = self.recording_wav_path
                self._polish_progress = 0
                self.postprocess_cancel.clear()
                self.postprocess_thread = PostProcessThread(
                    self.recording_wav_path, out, self.cfg,
                    self._post_status, done_cb=self._pp_done_cb,
                    progress_cb=self._on_polish_progress,
                    cancel_event=self.postprocess_cancel)
                self.postprocess_thread.start()
                self.push_state_patch({"recording": self._recording_blob()})
            except Exception as e:
                log.exception("postprocess kickoff failed: %s", e)
        self._push("push_library_changed")

    def _on_polish_progress(self, pct):
        self._polish_progress = max(0, min(100, int(pct)))
        self._push("push_polish_progress", self._polish_progress)

    def cancel_polish(self):
        """User pressed Cancel polish — signal the PostProcessThread to abort
        and clear in-progress state. The thread checks the cancel event."""
        if self.postprocess_thread is None or not self.postprocess_thread.is_alive():
            return {"ok": False, "error": "No polish in progress."}
        self.postprocess_cancel.set()
        return {"ok": True}

    def save_transcript_now(self):
        if not self.all_segments:
            return {"ok": False, "error": "Nothing to save yet."}
        course = self.cfg.current_course or "General"
        category = self.cfg.current_category or CATEGORIES[0]
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_dir = _course_subdir(LIVE_ROOT, course, category)
        out = out_dir / ("transcript_" + ts + ".txt")
        out.write_text(self._format_transcript(), encoding="utf-8")
        self.push_toast(title="Transcript saved", body=str(out),
                        action="Show in folder", action_cmd="reveal",
                        action_path=str(out))
        return {"ok": True, "path": str(out)}

    def _format_transcript(self):
        lines = []
        for s in self.all_segments:
            m, sec = divmod(int(s.timestamp), 60)
            lines.append("[{:02d}:{:02d}] ({}) {}".format(m, sec, s.language, s.text))
        return "\n".join(lines)

    def _post_status(self, msg):
        log.info("postprocess: %s", msg)

    def _pp_done_cb(self, wav_path: Path, success: bool):
        self.in_progress_wavs.discard(str(wav_path))
        # Reset polish progress so the drain loop stops ticking and so the
        # next polish starts from 0.
        self._polish_progress = 0
        if str(self._polish_wav_path) == str(wav_path):
            self._polish_wav_path = None
        self._push("push_library_changed")
        self.push_state_patch({"recording": self._recording_blob()})
        if success:
            m = re.search(r"(\d{8}_\d{6})", Path(wav_path).name)
            ts = m.group(1) if m else ""
            post_path = None
            if ts:
                for c in POST_ROOT.rglob("transcript_" + ts + "_postprocessed.txt"):
                    post_path = c
                    break
            self.push_toast(title="Post-processed transcript saved",
                            body=str(post_path) if post_path else "",
                            action="Show in folder" if post_path else None,
                            action_cmd="reveal" if post_path else None,
                            action_path=str(post_path) if post_path else None,
                            icon="✨", variant="accent")

    def recopy_last_trigger(self):
        latest = TRIGGERS_DIR / "latest.txt"
        if not latest.exists():
            return {"ok": False, "error": "No trigger has fired this session."}
        _set_windows_clipboard(latest.read_text(encoding="utf-8"))
        self.push_toast(title="Last trigger copied", body="",
                        icon="✓", variant="good", duration_ms=3000)
        return {"ok": True}

    def force_vocab_refresh(self):
        if self.transcribe_thread is None or self.transcribe_thread.vocab is None:
            return {"ok": False, "error": "Start a recording first."}
        ts = time.time() - (self.recording_start or time.time())
        terms = self.transcribe_thread.vocab.recompute(ts)
        self.transcribe_thread.dynamic_prompt = ", ".join(terms)
        self.push_state_patch({"dyn_vocab": terms})
        return {"ok": True, "terms": terms}

    def _drain_queues(self):
        for q in (self.audio_queue, self.text_queue):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    # ---- course / library ops ----------------------------------------

    def new_course(self, name):
        name = (name or "").strip()
        if not name or name in self.cfg.courses:
            return {"ok": False, "error": "Empty or duplicate course name."}
        self.cfg.courses.append(name)
        self.cfg.current_course = name
        self.cfg.save()
        _ensure_course_skeleton(name)
        self._push("push_library_changed")
        self.push_state_patch({"courses": self.cfg.courses,
                               "config": asdict(self.cfg)})
        return {"ok": True}

    def delete_recording(self, path):
        try:
            p = Path(path)
            if not p.exists():
                return {"ok": False, "error": "File not found."}
            m = re.search(r"(\d{8}_\d{6})", p.name)
            if m:
                ts = m.group(1)
                for root in (LIVE_ROOT, POST_ROOT):
                    for f in root.rglob("*" + ts + "*"):
                        try:
                            f.unlink()
                        except Exception:
                            pass
            p.unlink()
            self._push("push_library_changed")
            self.push_state_patch({"library": _scan_library(self.in_progress_wavs)})
            return {"ok": True}
        except Exception as e:
            log.exception("delete failed")
            return {"ok": False, "error": str(e)}

    def move_recording(self, path, target_course):
        try:
            wav = Path(path)
            target = (target_course or "").strip()
            if target not in self.cfg.courses:
                self.cfg.courses.append(target)
            new = _course_subdir(REC_ROOT, target) / wav.name
            shutil.move(str(wav), str(new))
            self.cfg.save()
            self._push("push_library_changed")
            self.push_state_patch({"library": _scan_library(),
                                   "courses": self.cfg.courses})
            return {"ok": True, "new_path": str(new)}
        except Exception as e:
            log.exception("move failed")
            return {"ok": False, "error": str(e)}

    def rename_recording(self, path, new_name):
        """Rename a WAV (and its sibling transcripts) in place. `new_name` may
        omit the .wav suffix — we add it. Hidden/system suffixes are stripped."""
        try:
            wav = Path(path)
            if not wav.exists():
                return {"ok": False, "error": "File not found."}
            stem = (new_name or "").strip()
            if not stem:
                return {"ok": False, "error": "Empty name."}
            if not stem.lower().endswith(".wav"):
                stem += ".wav"
            new_wav = wav.with_name(stem)
            if new_wav.exists() and new_wav != wav:
                return {"ok": False, "error": "A file with that name already exists."}
            wav.rename(new_wav)
            # Best-effort: also rename matching transcripts so the row still
            # shows Live/Polished pills.
            m = re.search(r"(\d{8}_\d{6})", wav.name)
            if m:
                ts = m.group(1)
                m2 = re.search(r"(\d{8}_\d{6})", new_wav.name)
                new_ts = m2.group(1) if m2 else ts
                if new_ts != ts:
                    for root in (LIVE_ROOT, POST_ROOT):
                        for f in root.rglob("*" + ts + "*"):
                            try:
                                f.rename(f.with_name(f.name.replace(ts, new_ts)))
                            except Exception:
                                pass
            self._push("push_library_changed")
            self.push_state_patch({"library": _scan_library(self.in_progress_wavs)})
            return {"ok": True, "new_path": str(new_wav)}
        except Exception as e:
            log.exception("rename failed")
            return {"ok": False, "error": str(e)}

    def rerun_postprocess(self, path):
        try:
            wav = Path(path)
            if not wav.exists():
                return {"ok": False, "error": "WAV missing."}
            # Best-effort course/category recovery from path layout
            rel = wav.relative_to(REC_ROOT) if str(wav).startswith(str(REC_ROOT)) else None
            course = ""; category = ""
            if rel is not None and len(rel.parts) >= 2:
                course = rel.parts[0]
                if len(rel.parts) >= 3:
                    category = rel.parts[1]
            out_dir = _course_subdir(POST_ROOT, course, category) if course else POST_ROOT
            m = re.search(r"(\d{8}_\d{6})", wav.name)
            ts = m.group(1) if m else time.strftime("%Y%m%d_%H%M%S")
            out = out_dir / ("transcript_" + ts + "_postprocessed.txt")
            self.in_progress_wavs.add(str(wav))
            self._push("push_library_changed")
            self.postprocess_thread = PostProcessThread(
                wav, out, self.cfg, self._post_status, done_cb=self._pp_done_cb)
            self.postprocess_thread.start()
            return {"ok": True}
        except Exception as e:
            log.exception("rerun failed")
            return {"ok": False, "error": str(e)}

    def open_path(self, path):
        try:
            _open_path(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reveal_in_folder(self, path):
        try:
            _reveal_in_folder(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_config(self, partial):
        try:
            partial = partial or {}
            allowed = set(asdict(self.cfg).keys())
            for k, v in partial.items():
                if k in allowed:
                    setattr(self.cfg, k, v)
            self.cfg.save()
            self._cfg_last_saved_ts = time.time()
            self.push_state_patch({"config": asdict(self.cfg),
                                   "config_last_saved_ts": self._cfg_last_saved_ts})
            return {"ok": True}
        except Exception as e:
            log.exception("save_config failed")
            return {"ok": False, "error": str(e)}

    def restore_defaults(self):
        """Reset config.json to factory defaults, preserving dark_mode +
        first_run so we don't surprise the user or re-show onboarding.
        Recordings on disk are untouched."""
        try:
            keep_dark = self.cfg.dark_mode
            new_cfg = AppConfig()
            new_cfg.dark_mode = keep_dark
            new_cfg.first_run = False
            new_cfg.save()
            self.cfg = new_cfg
            self._cfg_last_saved_ts = time.time()
            for c in self.cfg.courses:
                try: _ensure_course_skeleton(c)
                except Exception: pass
            self.push_state_patch({"config": asdict(self.cfg),
                                   "courses": self.cfg.courses,
                                   "library": _scan_library(self.in_progress_wavs),
                                   "config_last_saved_ts": self._cfg_last_saved_ts})
            self.push_toast(title="Settings restored to defaults",
                            icon="✓", variant="good", duration_ms=4000)
            return {"ok": True}
        except Exception as e:
            log.exception("restore_defaults failed")
            return {"ok": False, "error": str(e)}

    def reset_session(self):
        """Clear in-memory vocab/triggers from a previous session — without
        touching disk. Useful when the recorded data is stale."""
        self.all_segments = []
        if self.transcribe_thread is not None and self.transcribe_thread.vocab is not None:
            self.transcribe_thread.vocab.history = []
            self.transcribe_thread.vocab.last_update_time = 0.0
            self.transcribe_thread.vocab.current_terms = []
            self.transcribe_thread.dynamic_prompt = ""
        if self.trigger_handler is not None:
            self.trigger_handler.last_fire = {}
            self.trigger_handler.recent = []
        self.push_state_patch({"transcript_segments": [], "triggers": [], "dyn_vocab": []})
        self.push_toast(title="Session reset", icon="✓", variant="good", duration_ms=2500)
        return {"ok": True}

    def refresh_devices(self):
        self._refresh_devices_internal()
        self.push_state_patch({"devices": self._devices_cache})
        return self._devices_cache

    def _refresh_devices_internal(self):
        names = []
        try:
            if sc is not None:
                names = [s.name for s in sc.all_speakers()]
        except Exception as e:
            log.warning("refresh_devices: %s", e)
        self._devices_cache = names

    def refresh_apps(self):
        self._refresh_apps_internal()
        self.push_state_patch({"audio_apps": self._audio_apps_cache})
        return self._audio_apps_cache

    def _refresh_apps_internal(self):
        """Enumerate processes currently producing audio via pycaw."""
        apps = []
        try:
            from pycaw.pycaw import AudioUtilities
            sessions = AudioUtilities.GetAllSessions()
            seen = set()
            for s in sessions:
                proc = getattr(s, "Process", None)
                if proc is None: continue
                try:
                    name = proc.name()
                except Exception:
                    continue
                if not name: continue
                pid = int(getattr(proc, "pid", 0) or 0)
                active = False
                try:
                    # SimpleAudioVolume might tell us if currently playing
                    sav = s.SimpleAudioVolume
                    if sav and getattr(sav, "GetMute", lambda: False)() is False:
                        active = True
                except Exception:
                    pass
                key = (name.lower(), pid)
                if key in seen: continue
                seen.add(key)
                apps.append({"name": name, "pid": pid, "playing": active})
        except Exception as e:
            log.debug("refresh_apps: %s", e)
        self._audio_apps_cache = apps

    def audio_sessions_count(self):
        """Active render sessions, surfaced as a small pill in Settings."""
        try:
            return sum(1 for a in self._audio_apps_cache if a.get("playing"))
        except Exception:
            return 0

    def set_theme(self, dark):
        self.cfg.dark_mode = bool(dark)
        self.cfg.save()
        self._cfg_last_saved_ts = time.time()
        self.push_state_patch({"config": asdict(self.cfg),
                               "config_last_saved_ts": self._cfg_last_saved_ts})
        return {"ok": True}

    def apply_model(self, label):
        self.cfg.whisper_model_label = label
        self.cfg.save()
        self._cfg_last_saved_ts = time.time()
        self.push_state_patch({"config": asdict(self.cfg),
                               "config_last_saved_ts": self._cfg_last_saved_ts})
        return {"ok": True}

    def get_model_status(self, label=None):
        """Return whether the given model id (or current) is downloaded, and
        an approximate cache size on disk in MB. Used by the Settings model
        picker for the 'Downloaded · 1.5 GB' pill."""
        label = label or self.cfg.whisper_model_label
        repo = MODEL_PRESETS.get(label, label)
        try:
            from huggingface_hub import scan_cache_dir
            cache = scan_cache_dir()
            for r in cache.repos:
                if repo.lower() in r.repo_id.lower() or repo.lower() in r.repo_path.lower():
                    return {"downloaded": True,
                            "size_mb": int(r.size_on_disk / 1024 / 1024),
                            "repo": r.repo_id}
        except Exception:
            pass
        # Builtin Whisper alias (e.g. "large-v3") — assume cached if Whisper
        # has been run at least once on it; can't reliably introspect.
        return {"downloaded": False, "size_mb": 0, "repo": repo}

    def setup_checklist(self):
        """Return a list of items the Setup-checklist modal renders."""
        items = []
        # Model downloaded
        ms = self.get_model_status()
        items.append({
            "label": "Whisper model downloaded",
            "ok": ms.get("downloaded", False),
            "detail": ms.get("repo", "") + (" · {} MB".format(ms["size_mb"]) if ms.get("size_mb") else ""),
        })
        # Audio target picked
        if self.cfg.audio_capture_mode == "app":
            ok = bool(self.cfg.output_app_name and self.cfg.output_app_pid)
            items.append({"label": "Audio source: specific app",
                          "ok": ok, "detail": self.cfg.output_app_name or "—"})
        elif self.cfg.audio_capture_mode == "device":
            ok = bool(self.cfg.output_device_name)
            items.append({"label": "Audio source: output device",
                          "ok": ok, "detail": self.cfg.output_device_name or "—"})
        else:
            items.append({"label": "Audio source: whole system",
                          "ok": True, "detail": "Default speaker"})
        # At least one course
        items.append({"label": "At least one course exists",
                      "ok": len(self.cfg.courses) > 0,
                      "detail": "{} course(s)".format(len(self.cfg.courses))})
        # Disk space (rough)
        try:
            import shutil as _sh
            free_gb = _sh.disk_usage(str(APP_DIR)).free / (1024**3)
            items.append({"label": "Disk space > 1 GB",
                          "ok": free_gb > 1.0,
                          "detail": "{:.1f} GB free".format(free_gb)})
        except Exception:
            pass
        return items

    def dismiss_onboarding(self):
        self.cfg.first_run = False
        self.cfg.save()
        return {"ok": True}

    def show_about(self):
        """Return data the About modal renders. The toast version remains as
        a fallback for callers that want a quick acknowledgement."""
        return {
            "version": APP_VERSION,
            "build_date": APP_BUILD_DATE,
            "tagline": APP_TAGLINE,
            "author": APP_AUTHOR,
            "license": APP_LICENSE,
            "credits": [
                {"name": "OpenAI Whisper / faster-whisper", "url": "https://github.com/SYSTRAN/faster-whisper"},
                {"name": "Ivrit.AI Hebrew fine-tunes",      "url": "https://ivrit.ai"},
                {"name": "python-soundcard",                "url": "https://github.com/bastibe/SoundCard"},
                {"name": "Inter font",                      "url": "https://rsms.me/inter"},
                {"name": "Heebo font",                      "url": "https://fonts.google.com/specimen/Heebo"},
            ],
        }

    # ---- background drain --------------------------------------------

    def start_drain_loop(self):
        """Pump the transcription text_queue into JS push events. Runs in a
        background thread for the lifetime of the process."""
        t = threading.Thread(target=self._drain_loop, daemon=True)
        t.start()

    def _drain_loop(self):
        last_tick = 0.0
        while True:
            try:
                item = self.text_queue.get(timeout=0.25)
            except queue.Empty:
                item = None
            # Always tick recording_state at most ~4×/second so the timer in
            # the UI keeps moving even while segments are streaming in.
            now = time.time()
            if (self.is_recording or self._polish_progress) and now - last_tick > 0.25:
                last_tick = now
                self._push("push_recording_state", self._recording_blob())
            # Silence watchdog — auto-stop if quiet long enough.
            if self.is_recording and self.audio_thread is not None:
                cutoff = self.cfg.auto_stop_silence_minutes
                if cutoff and cutoff > 0:
                    idle = time.time() - self.audio_thread.last_sound_ts
                    if idle >= cutoff * 60:
                        log.info("Auto-stop after %s min of silence", cutoff)
                        self.stop_recording()
            if item is None:
                continue
            try:
                kind = item[0]
                if kind == "segment":
                    seg = item[1]
                    self.all_segments.append(seg)
                    payload = {
                        "timestamp": seg.timestamp,
                        "ts_human": _format_duration(seg.timestamp),
                        "text": seg.text,
                        "language": seg.language,
                    }
                    self._push("push_transcript_segment", payload)
                    # Trigger detection
                    if self.trigger_handler is not None:
                        hit = self.trigger_handler.add_segment(seg)
                        if hit:
                            t_payload = self.trigger_handler.emit_trigger(hit, seg)
                            self._push("push_trigger", t_payload)
                            self.push_toast(
                                title="Trigger fired: " + hit,
                                body="Copied recent context to clipboard.",
                                icon="⚡", variant="accent", duration_ms=4000)
                elif kind == "vocab":
                    self._push("push_dyn_vocab", item[1])
                elif kind == "status":
                    msg = str(item[1])
                    self._push("push_status", msg)
                    if "Loading model" in msg:
                        self._set_whisper_status("loading")
                    elif "Model loaded" in msg or "Listening" in msg:
                        self._set_whisper_status("ready")
                elif kind == "error":
                    self._set_whisper_status("error")
                    self.push_toast(title="Error", body=str(item[1]),
                                    icon="!", variant="warn", duration_ms=8000)
            except Exception as e:
                log.exception("drain loop error: %s", e)


# ---------------- Eel registration ----------------
# Eel needs module-level functions to expose; bind to the singleton.

_app = AuralisApp()

@eel.expose
def get_state():                return _app.get_state()
@eel.expose
def start_recording(c, k):      return _app.start_recording(c, k)
@eel.expose
def stop_recording():           return _app.stop_recording()
@eel.expose
def save_transcript_now():      return _app.save_transcript_now()
@eel.expose
def recopy_last_trigger():      return _app.recopy_last_trigger()
@eel.expose
def force_vocab_refresh():      return _app.force_vocab_refresh()
@eel.expose
def new_course(name):           return _app.new_course(name)
@eel.expose
def delete_recording(path):     return _app.delete_recording(path)
@eel.expose
def move_recording(p, target):  return _app.move_recording(p, target)
@eel.expose
def rerun_postprocess(path):    return _app.rerun_postprocess(path)
@eel.expose
def open_path(path):            return _app.open_path(path)
@eel.expose
def reveal_in_folder(path):     return _app.reveal_in_folder(path)
@eel.expose
def save_config(partial):       return _app.save_config(partial)
@eel.expose
def refresh_devices():          return _app.refresh_devices()
@eel.expose
def set_theme(dark):            return _app.set_theme(dark)
@eel.expose
def apply_model(label):         return _app.apply_model(label)
@eel.expose
def dismiss_onboarding():       return _app.dismiss_onboarding()
@eel.expose
def show_about():               return _app.show_about()
@eel.expose
def restore_defaults():         return _app.restore_defaults()
@eel.expose
def reset_session():            return _app.reset_session()
@eel.expose
def refresh_apps():             return _app.refresh_apps()
@eel.expose
def audio_sessions_count():     return _app.audio_sessions_count()
@eel.expose
def cancel_polish():            return _app.cancel_polish()
@eel.expose
def setup_checklist():          return _app.setup_checklist()
@eel.expose
def get_model_status(label=None): return _app.get_model_status(label)
@eel.expose
def rename_recording(path, new_name): return _app.rename_recording(path, new_name)
@eel.expose
def import_wav():
    # File pickers from a browser don't reach the file system; use a backend
    # picker via tkinter.filedialog (no Tk window needed).
    try:
        import tkinter as tk_mod
        from tkinter import filedialog as fd
        root = tk_mod.Tk(); root.withdraw()
        path = fd.askopenfilename(title="Pick a WAV",
                                   filetypes=[("WAV", "*.wav")])
        root.destroy()
        if not path:
            return {"ok": False, "error": "Cancelled"}
        target = _app.cfg.current_course
        dst = _course_subdir(REC_ROOT, target) / Path(path).name
        shutil.copy2(path, dst)
        _app._push("push_library_changed")
        return {"ok": True, "new_path": str(dst)}
    except Exception as e:
        log.exception("import failed")
        return {"ok": False, "error": str(e)}


def main():
    # Start background queue drain loop.
    _app.start_drain_loop()
    # Initialize eel pointing at the UI folder. We have to add '.jsx' to the
    # allowed_extensions list — Eel's default skips .jsx, which means the
    # eel.expose(fn, 'name') stubs in app.jsx were invisible to Python's
    # source parser, so no JS-side push handlers ever got registered.
    eel.init(str(UI_DIR),
             allowed_extensions=['.js', '.jsx', '.html', '.txt',
                                 '.htm', '.xhtml', '.vue'])
    # Register a /wav?path=... route so the in-app <audio> player can stream
    # WAV files that live OUTSIDE the ui/ folder. Restrict to REC_ROOT so we
    # never serve arbitrary disk files.
    try:
        import bottle as _bottle
        @eel.btl.route('/wav')
        def _serve_wav():
            from urllib.parse import unquote
            raw = _bottle.request.query.path or ''
            try:
                p = Path(unquote(raw)).resolve()
            except Exception:
                return _bottle.HTTPResponse(status=400, body="bad path")
            try:
                p.relative_to(REC_ROOT.resolve())
            except Exception:
                return _bottle.HTTPResponse(status=403, body="not under recordings/")
            if not p.exists() or not p.is_file():
                return _bottle.HTTPResponse(status=404, body="not found")
            return _bottle.static_file(p.name, root=str(p.parent), mimetype='audio/wav')
    except Exception as e:
        log.warning("could not register /wav route: %s", e)
    # Default size matches the original Tk window.
    size = (1240, 820)
    # Try Chrome app-mode first (looks like a native window — no tab bar,
    # no URL bar). Fall back to Edge if Chrome isn't installed, then to the
    # user's default browser as a last resort.
    # Optional: pass AURALIS_DEBUG=1 to enable Chrome DevTools on port 9222.
    extra_cmd = []
    if os.environ.get("AURALIS_DEBUG"):
        extra_cmd = ["--remote-debugging-port=9222"]
        log.info("AURALIS_DEBUG: Chrome DevTools on http://localhost:9222")
    for mode in ("chrome", "edge", "default"):
        try:
            log.info("Starting eel in mode=%s", mode)
            eel.start("index.html", size=size, port=0, mode=mode,
                      block=True, suppress_error=True,
                      cmdline_args=extra_cmd)
            return
        except (SystemExit, KeyboardInterrupt):
            log.info("Auralis shutting down")
            _app.stop_event.set()
            return
        except Exception as e:
            log.warning("Eel mode=%s failed (%s); trying next mode", mode, e)
    raise SystemExit("No supported browser found (Chrome / Edge).")


if __name__ == "__main__":
    main()
