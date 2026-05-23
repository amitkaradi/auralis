"""Per-application audio capture on Windows via WASAPI Process Loopback.

There are three audio capture modes Auralis supports:

* "system" — capture the default speaker's loopback (entire system mix). This
  is what python-soundcard does and what every previous version of Auralis
  used. Works everywhere.

* "device" — capture loopback from a specific *named* speaker / output device
  (still the whole system mix routed to that device). Also uses python-
  soundcard. Useful when you have multiple outputs (e.g. headset vs speakers)
  and want to record only the audio going to one.

* "app" — capture audio from one specific application process. Implemented in
  this module using the Windows 10 build 20348+ Process Loopback API.
  Other apps continue playing normally; only the target app's stream is
  recorded.

Process Loopback is a relatively young Microsoft API. We wrap it via ctypes
because no widely-installed Python library covers it. If activation fails
(older Windows, locked-down endpoint, bad PID), ``ProcessLoopbackCapture``
raises ``ProcessLoopbackUnavailable`` and the caller should fall back to a
different mode.

App enumeration uses ``pycaw``, which is a pure-Python wrapper around the
WASAPI session manager. If pycaw isn't installed the audio-app picker just
shows an empty list with a hint.

Reference for the Process Loopback API:
    https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording
    https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/
        ApplicationLoopback
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional


class ProcessLoopbackUnavailable(RuntimeError):
    """Raised when per-process loopback can't be initialised."""


# -----------------------------------------------------------------------
# App enumeration via pycaw
# -----------------------------------------------------------------------

@dataclass
class AudioApp:
    """Description of an audio session currently open on the system."""
    pid: int
    name: str           # Process name, e.g. "zoom.exe".
    display_name: str   # Display name, e.g. "Zoom Meetings".
    is_active: bool     # True if the session is currently playing audio.
    peak: float = 0.0   # Peak meter value (0.0–1.0). > 0 means audio right now.


# IID for IAudioMeterInformation — used to read the per-session peak value
# (a reliable "is playing audio right now" signal that doesn't depend on the
# session state flag, which Chrome/YouTube and similar apps don't always
# update promptly).
_IID_IAudioMeterInformation = "{C02216F6-8C67-4B5B-9D00-D008E73E0064}"


def _peak_for_session(s) -> float:
    """Return the current peak meter value (0.0–1.0) for a session, or 0.0.

    Uses the underlying IAudioSessionControl's QueryInterface to obtain
    IAudioMeterInformation. Silently returns 0.0 on any failure so the caller
    can still enumerate sessions even if metering isn't supported.
    """
    try:
        import comtypes
        from ctypes import POINTER, c_float, byref
        ctl = getattr(s, "_ctl", None)
        if ctl is None:
            return 0.0
        meter_iid = comtypes.GUID(_IID_IAudioMeterInformation)
        meter = ctl.QueryInterface(comtypes.IUnknown, meter_iid)
        if meter is None:
            return 0.0
        # IAudioMeterInformation::GetPeakValue is slot 3 on the vtable
        # (after the standard IUnknown trio).
        import ctypes
        meter_ptr = ctypes.cast(meter, ctypes.c_void_p).value
        if not meter_ptr:
            return 0.0
        vtbl_ptr = ctypes.cast(meter_ptr, ctypes.POINTER(ctypes.c_void_p))[0]
        vtbl = ctypes.cast(vtbl_ptr, ctypes.POINTER(ctypes.c_void_p))
        GET_PEAK = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(c_float)
        )
        get_peak = GET_PEAK(vtbl[3])
        peak = c_float(0.0)
        hr = get_peak(meter_ptr, byref(peak))
        if hr != 0:
            return 0.0
        return float(peak.value)
    except Exception:
        return 0.0


# Common audio-producing apps. Used as a fallback enumeration source for the
# cases where pycaw doesn't expose a session (Chrome with site isolation,
# sandboxed UWP apps, etc.). Lowercase exe basenames, mapped to display
# labels so the picker reads cleanly.
_KNOWN_AUDIO_APPS = {
    "chrome.exe":        "Google Chrome",
    "msedge.exe":        "Microsoft Edge",
    "firefox.exe":       "Mozilla Firefox",
    "brave.exe":         "Brave Browser",
    "opera.exe":         "Opera",
    "arc.exe":           "Arc",
    "zoom.exe":          "Zoom",
    "teams.exe":         "Microsoft Teams",
    "ms-teams.exe":      "Microsoft Teams",
    "skype.exe":         "Skype",
    "discord.exe":       "Discord",
    "slack.exe":         "Slack",
    "vlc.exe":           "VLC",
    "spotify.exe":       "Spotify",
    "wmplayer.exe":      "Windows Media Player",
    "potplayer.exe":     "PotPlayer",
    "obs64.exe":         "OBS Studio",
    "obs32.exe":         "OBS Studio",
    "audacity.exe":      "Audacity",
    "winamp.exe":        "Winamp",
    "itunes.exe":        "iTunes",
    "applemusic.exe":    "Apple Music",
    "music.ui.exe":      "Microsoft Groove",
    "googleplaymusic.exe": "Google Play Music",
}


def _list_known_running_apps() -> list[AudioApp]:
    """psutil-based fallback: list common audio-producing apps that are
    currently running, regardless of whether they've opened an audio session.

    Returns an empty list if psutil isn't available. is_active is always
    False here — these are "could play audio" candidates, not "currently
    playing". The UI shows them alongside pycaw's active results so users
    can pick them before audio starts.
    """
    try:
        import psutil
    except Exception:
        return []
    out: list[AudioApp] = []
    seen_pids: set[int] = set()
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                info = proc.info
                pid = int(info.get("pid") or 0)
                name = (info.get("name") or "").lower()
                if not pid or not name:
                    continue
                if name not in _KNOWN_AUDIO_APPS:
                    continue
                # One entry per process name (Chrome has many — pick the
                # parent, which is usually the lowest PID for that name).
                key = name
                if key in seen_pids:
                    continue
                seen_pids.add(key)
                out.append(AudioApp(
                    pid=pid,
                    name=name,
                    display_name=_KNOWN_AUDIO_APPS[name],
                    is_active=False,
                    peak=0.0,
                ))
            except Exception:
                continue
    except Exception:
        return []
    return out


def list_audio_apps(active_only: bool = False) -> list[AudioApp]:
    """Enumerate audio-producing apps on the system.

    Combines two sources:

    1. **pycaw audio sessions** — apps that have opened an audio stream.
       For each session we report both the pycaw state flag AND the per-
       session peak meter value; either signal triggers ``is_active``.
       This is the authoritative path and gives us live "playing now"
       badges.

    2. **psutil running processes** — a curated list of common audio-
       producing apps (browsers, Zoom/Teams, Spotify, VLC, …). This catches
       apps that pycaw misses (Chrome with site isolation, sandboxed UWP
       apps, etc.) so the user can still pick them.

    Results are de-duplicated by process name. If pycaw already returned
    Chrome, the psutil pass won't add a second entry.

    ``active_only=True`` keeps only apps with the active flag set (legacy
    callers); default returns everything so the UI can sort/badge.

    Always returns a list — never raises — so the UI stays responsive even
    if both data sources fail.
    """
    out: list[AudioApp] = []
    pycaw_apps: list[AudioApp] = []

    # ---- Source 1: pycaw audio sessions ----
    try:
        from pycaw.pycaw import AudioUtilities
        try:
            from pycaw.constants import AudioSessionState
            ACTIVE_STATE = int(getattr(AudioSessionState, "Active", 1))
        except Exception:
            ACTIVE_STATE = 1
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception as e:
            log_lazy("GetAllSessions failed: %s", e)
            sessions = []

        seen_pids: set[int] = set()
        for s in sessions:
            try:
                proc = s.Process
                if proc is None:
                    continue
                try:
                    pid = int(proc.pid)
                except Exception:
                    continue
                if pid in seen_pids:
                    continue
                seen_pids.add(pid)
                name = ""
                try:
                    name = proc.name() if hasattr(proc, "name") else ""
                except Exception:
                    name = ""
                display = s.DisplayName or name
                if display.lower().endswith(".exe"):
                    display = display[:-4]
                if display.startswith("@") or not display:
                    display = name or ("PID " + str(pid))
                state_active = False
                try:
                    state_active = (int(s.State) == ACTIVE_STATE)
                except Exception:
                    pass
                peak = _peak_for_session(s)
                is_active = state_active or peak > 0.0001
                pycaw_apps.append(AudioApp(
                    pid=pid,
                    name=name or "",
                    display_name=display or name or ("PID " + str(pid)),
                    is_active=is_active,
                    peak=peak,
                ))
            except Exception:
                continue
        log_lazy("pycaw enumerated %d session(s), %d active",
                 len(pycaw_apps),
                 sum(1 for a in pycaw_apps if a.is_active))
    except Exception as e:
        log_lazy("pycaw import failed: %s", e)

    out.extend(pycaw_apps)
    seen_names = {a.name.lower() for a in out if a.name}

    # ---- Source 2: psutil fallback for known audio apps ----
    fallback = _list_known_running_apps()
    added = 0
    for a in fallback:
        if a.name.lower() in seen_names:
            continue
        out.append(a)
        seen_names.add(a.name.lower())
        added += 1
    if added:
        log_lazy("psutil fallback added %d app(s) not seen by pycaw", added)

    if active_only:
        out = [a for a in out if a.is_active]

    # Sort: actively playing first (peak desc), then alphabetical.
    out.sort(key=lambda a: (not a.is_active, -a.peak, a.display_name.lower()))
    return out


# Lightweight logger — process_loopback is imported very early and we don't
# want to pull in the Auralis logger if it isn't set up yet.
def log_lazy(msg: str, *args):
    try:
        import logging
        logging.getLogger("auralis").warning(msg, *args)
    except Exception:
        pass


# -----------------------------------------------------------------------
# Process Loopback via ctypes
# -----------------------------------------------------------------------
#
# The Windows API does roughly:
#
#   1. ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
#                                  IID_IAudioClient,
#                                  &AUDIOCLIENT_ACTIVATION_PARAMS{
#                                      ActivationType = LoopbackTarget,
#                                      ProcessLoopbackParams = {
#                                          TargetProcessId = <pid>,
#                                          ProcessLoopbackMode = IncludeTargetProcessTree,
#                                      },
#                                  },
#                                  callback, &completionHandler)
#   2. The callback receives an IActivateAudioInterfaceAsyncOperation.
#   3. GetActivateResult() gives us the IAudioClient.
#   4. IAudioClient->Initialize(SHARED, LOOPBACK, ...).
#   5. IAudioClient->GetService(IAudioCaptureClient).
#   6. IAudioClient->Start(); then read frames in a loop.
#
# This is many hundreds of lines if written from scratch. We use ``comtypes``
# to dynamically build COM interfaces, which keeps the binding compact.

VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK = (
    "VAD\\Process_Loopback"
)

# AUDIOCLIENT_ACTIVATION_TYPE
AUDIOCLIENT_ACTIVATION_TYPE_DEFAULT = 0
AUDIOCLIENT_ACTIVATION_TYPE_LOOPBACK = 1

# PROCESS_LOOPBACK_MODE
PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0
PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE = 1

# Audio client share / stream flags.
AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000

REFTIMES_PER_SEC = 10_000_000

# WAVE_FORMAT_IEEE_FLOAT — we want float32 PCM.
WAVE_FORMAT_IEEE_FLOAT = 0x0003


class AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS(ctypes.Structure):
    _fields_ = [
        ("TargetProcessId", wt.DWORD),
        ("ProcessLoopbackMode", ctypes.c_int),
    ]


class AUDIOCLIENT_ACTIVATION_PARAMS(ctypes.Structure):
    _fields_ = [
        ("ActivationType", ctypes.c_int),
        ("ProcessLoopbackParams", AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS),
    ]


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wt.WORD),
        ("nChannels", wt.WORD),
        ("nSamplesPerSec", wt.DWORD),
        ("nAvgBytesPerSec", wt.DWORD),
        ("nBlockAlign", wt.WORD),
        ("wBitsPerSample", wt.WORD),
        ("cbSize", wt.WORD),
    ]


class _CompletionHandler:
    """Holds the activation result so the calling thread can grab it."""

    def __init__(self):
        self.event = threading.Event()
        self.client = None
        self.hr = 0


class ProcessLoopbackCapture:
    """Capture float32 PCM audio from a single Windows process.

    Usage::

        cap = ProcessLoopbackCapture(pid=1234, samplerate=16000)
        cap.start()
        while running:
            chunk = cap.read(numframes=16000)   # 1 second
            ...
        cap.stop()

    ``read`` returns a numpy float32 mono array. If multiple channels are
    captured natively, they are downmixed to mono.

    On any failure the constructor or ``start()`` raises
    ``ProcessLoopbackUnavailable``.
    """

    def __init__(self, pid: int, samplerate: int = 16000):
        if sys.platform != "win32":
            raise ProcessLoopbackUnavailable("Process loopback is Windows-only.")
        self.pid = int(pid)
        self.samplerate = int(samplerate)
        self._client = None              # IAudioClient
        self._capture = None             # IAudioCaptureClient
        self._wfx = None                 # WAVEFORMATEX
        self._native_channels = 0
        self._native_samplerate = 0
        self._buf_lock = threading.Lock()
        self._buf = bytearray()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._init()

    # ---------- setup / teardown ----------

    def _init(self):
        try:
            import comtypes
            from comtypes import GUID, COMMETHOD, IUnknown, HRESULT
            from comtypes.client import GetModule
        except Exception as e:
            raise ProcessLoopbackUnavailable(
                "comtypes not installed: " + str(e)
            )

        try:
            ole32 = ctypes.windll.ole32
            mmdevapi = ctypes.windll.mmdevapi
        except Exception as e:
            raise ProcessLoopbackUnavailable("Cannot load mmdevapi.dll: " + str(e))

        # CoInitialize (multi-threaded) — required before any COM call from
        # this thread. Safe to call multiple times.
        try:
            comtypes.CoInitializeEx(0x0)
        except Exception:
            pass

        # GUIDs we need.
        IID_IAudioClient = comtypes.GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
        IID_IAudioCaptureClient = comtypes.GUID(
            "{C8ADBD64-E71E-48a0-A4DE-185C395CD317}"
        )
        IID_IActivateAudioInterfaceCompletionHandler = comtypes.GUID(
            "{41D949AB-9862-444A-80F6-C261334DA5EB}"
        )

        # Build the activation params.
        params = AUDIOCLIENT_ACTIVATION_PARAMS()
        params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_LOOPBACK
        params.ProcessLoopbackParams.TargetProcessId = self.pid
        params.ProcessLoopbackParams.ProcessLoopbackMode = (
            PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE
        )

        # PROPVARIANT wrapper around the params blob — required by
        # ActivateAudioInterfaceAsync. We build a minimal blob: VT_BLOB type,
        # cbSize, pBlobData.
        class BLOB(ctypes.Structure):
            _fields_ = [("cbSize", wt.ULONG), ("pBlobData", ctypes.c_void_p)]

        class PROPVARIANT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("blob", BLOB)]
            _anonymous_ = ("u",)
            _fields_ = [
                ("vt", wt.USHORT),
                ("wReserved1", wt.WORD),
                ("wReserved2", wt.WORD),
                ("wReserved3", wt.WORD),
                ("u", _U),
            ]

        VT_BLOB = 0x41
        pv = PROPVARIANT()
        pv.vt = VT_BLOB
        pv.blob.cbSize = ctypes.sizeof(params)
        # Hold a reference so the buffer survives until the call returns.
        self._params_ref = params
        pv.blob.pBlobData = ctypes.cast(
            ctypes.pointer(params), ctypes.c_void_p
        ).value

        # ActivateAudioInterfaceAsync prototype.
        ActivateAudioInterfaceAsync = mmdevapi.ActivateAudioInterfaceAsync
        ActivateAudioInterfaceAsync.argtypes = [
            wt.LPCWSTR,                   # deviceInterfacePath
            ctypes.c_void_p,              # REFIID *riid (IID_IAudioClient)
            ctypes.c_void_p,              # PROPVARIANT *activationParams
            ctypes.c_void_p,              # IActivateAudioInterfaceCompletionHandler *
            ctypes.c_void_p,              # IActivateAudioInterfaceAsyncOperation **
        ]
        ActivateAudioInterfaceAsync.restype = ctypes.HRESULT

        # ------------------------------------------------------------------
        # Build a tiny COM completion-handler in-process. We do this by
        # constructing a vtable manually. The handler has one method:
        #   STDMETHODIMP ActivateCompleted(IActivateAudioInterfaceAsyncOperation *op)
        # plus the standard IUnknown trio (QueryInterface / AddRef / Release).
        # ------------------------------------------------------------------

        IID_IUnknown = comtypes.GUID("{00000000-0000-0000-C000-000000000046}")

        QI_TYPE = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )
        ADDREF_TYPE = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        RELEASE_TYPE = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        COMPLETED_TYPE = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p
        )

        done = threading.Event()
        result_ref = {"client": None, "hr": 0}

        def qi(this, riid_ptr, ppv):
            if not ppv:
                return -2147467261  # E_POINTER
            # Cast to GUID for comparison.
            riid = comtypes.GUID.from_address(riid_ptr) if riid_ptr else None
            if riid is not None and (
                riid == IID_IUnknown
                or riid == IID_IActivateAudioInterfaceCompletionHandler
            ):
                ctypes.cast(
                    ppv, ctypes.POINTER(ctypes.c_void_p)
                )[0] = this
                return 0
            ctypes.cast(ppv, ctypes.POINTER(ctypes.c_void_p))[0] = 0
            return -2147467262  # E_NOINTERFACE

        def addref(this):
            return 1

        def release(this):
            return 1

        def completed(this, op_ptr):
            # Call op->GetActivateResult(&hr, &punk) via its vtable.
            try:
                pp = ctypes.cast(op_ptr, ctypes.POINTER(ctypes.c_void_p))
                vtbl = ctypes.cast(pp[0], ctypes.POINTER(ctypes.c_void_p))
                # slot 0..2 = IUnknown, slot 3 = GetActivateResult.
                GET_ACTIVATE_RESULT = ctypes.WINFUNCTYPE(
                    ctypes.HRESULT,
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_int),
                    ctypes.POINTER(ctypes.c_void_p),
                )
                fn = GET_ACTIVATE_RESULT(vtbl[3])
                hr = ctypes.c_int(0)
                punk = ctypes.c_void_p(0)
                fn(op_ptr, ctypes.byref(hr), ctypes.byref(punk))
                result_ref["hr"] = int(hr.value)
                result_ref["client"] = int(punk.value or 0)
            except Exception as e:
                result_ref["hr"] = -1
                result_ref["error"] = str(e)
            done.set()
            return 0

        # Pin the function refs so they don't get GC'd while COM holds them.
        self._qi = QI_TYPE(qi)
        self._addref = ADDREF_TYPE(addref)
        self._release = RELEASE_TYPE(release)
        self._completed = COMPLETED_TYPE(completed)

        VTBL_TYPE = ctypes.c_void_p * 4
        self._vtbl = VTBL_TYPE(
            ctypes.cast(self._qi, ctypes.c_void_p).value,
            ctypes.cast(self._addref, ctypes.c_void_p).value,
            ctypes.cast(self._release, ctypes.c_void_p).value,
            ctypes.cast(self._completed, ctypes.c_void_p).value,
        )

        # IActivateAudioInterfaceCompletionHandler is laid out as a pointer to
        # a vtable. We allocate the "object" as a c_void_p that points to the
        # vtable.
        self._handler_obj = ctypes.c_void_p(
            ctypes.cast(self._vtbl, ctypes.c_void_p).value
        )

        # Now kick off the activation.
        op = ctypes.c_void_p(0)
        hr = ActivateAudioInterfaceAsync(
            VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
            ctypes.byref(IID_IAudioClient),
            ctypes.byref(pv),
            ctypes.byref(self._handler_obj),
            ctypes.byref(op),
        )
        if hr != 0:
            raise ProcessLoopbackUnavailable(
                "ActivateAudioInterfaceAsync HRESULT 0x{:08X}".format(hr & 0xFFFFFFFF)
            )

        # Wait up to 5 seconds for completion.
        if not done.wait(timeout=5.0):
            raise ProcessLoopbackUnavailable("Activation timed out.")

        if result_ref["hr"] != 0 or not result_ref["client"]:
            err = result_ref.get("error") or "HRESULT 0x{:08X}".format(
                result_ref["hr"] & 0xFFFFFFFF
            )
            raise ProcessLoopbackUnavailable("Activation failed: " + err)

        self._client_ptr = result_ref["client"]

        # We now have an IAudioClient pointer. Initialize it.
        # IAudioClient vtable (after IUnknown 0..2):
        #   3 Initialize(ShareMode, StreamFlags, hnsBufferDuration, hnsPeriod, *fmt, *sessionGuid)
        #   4 GetBufferSize(out)
        #   5 GetStreamLatency(out)
        #   6 GetCurrentPadding(out)
        #   7 IsFormatSupported
        #   8 GetMixFormat(out)
        #   9 GetDevicePeriod
        #  10 Start
        #  11 Stop
        #  12 Reset
        #  13 SetEventHandle
        #  14 GetService(riid, **out)

        vtbl_ptr = ctypes.cast(
            self._client_ptr, ctypes.POINTER(ctypes.c_void_p)
        )[0]
        vtbl = ctypes.cast(vtbl_ptr, ctypes.POINTER(ctypes.c_void_p))

        GET_MIX_FORMAT = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )
        get_mix_format = GET_MIX_FORMAT(vtbl[8])

        wfx_ptr = ctypes.c_void_p(0)
        hr = get_mix_format(self._client_ptr, ctypes.byref(wfx_ptr))
        if hr != 0:
            raise ProcessLoopbackUnavailable(
                "GetMixFormat HRESULT 0x{:08X}".format(hr & 0xFFFFFFFF)
            )

        # Force a float32 format we control rather than using the system mix.
        wfx = WAVEFORMATEX()
        wfx.wFormatTag = WAVE_FORMAT_IEEE_FLOAT
        wfx.nChannels = 2
        wfx.nSamplesPerSec = self.samplerate
        wfx.wBitsPerSample = 32
        wfx.nBlockAlign = wfx.nChannels * wfx.wBitsPerSample // 8
        wfx.nAvgBytesPerSec = wfx.nSamplesPerSec * wfx.nBlockAlign
        wfx.cbSize = 0
        self._wfx = wfx
        self._native_channels = 2
        self._native_samplerate = self.samplerate

        INITIALIZE = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p,
            ctypes.c_int,                    # ShareMode
            ctypes.c_uint,                   # StreamFlags
            ctypes.c_longlong,               # hnsBufferDuration
            ctypes.c_longlong,               # hnsPeriod
            ctypes.c_void_p,                 # *pFormat
            ctypes.c_void_p,                 # *AudioSessionGuid
        )
        initialize = INITIALIZE(vtbl[3])

        # 2-second buffer.
        hr = initialize(
            self._client_ptr,
            AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_LOOPBACK,
            int(2 * REFTIMES_PER_SEC),
            0,
            ctypes.cast(ctypes.pointer(wfx), ctypes.c_void_p),
            None,
        )
        if hr != 0:
            raise ProcessLoopbackUnavailable(
                "IAudioClient::Initialize HRESULT 0x{:08X}".format(hr & 0xFFFFFFFF)
            )

        # GetService(IID_IAudioCaptureClient, &capture).
        GET_SERVICE = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        )
        get_service = GET_SERVICE(vtbl[14])
        cap_ptr = ctypes.c_void_p(0)
        hr = get_service(
            self._client_ptr,
            ctypes.byref(IID_IAudioCaptureClient),
            ctypes.byref(cap_ptr),
        )
        if hr != 0:
            raise ProcessLoopbackUnavailable(
                "GetService(IAudioCaptureClient) HRESULT 0x{:08X}".format(
                    hr & 0xFFFFFFFF
                )
            )
        self._capture_ptr = cap_ptr.value
        self._client_vtbl = vtbl

    # ---------- public API ----------

    def start(self):
        if self._thread is not None:
            return
        START = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)
        hr = START(self._client_vtbl[10])(self._client_ptr)
        if hr != 0:
            raise ProcessLoopbackUnavailable(
                "IAudioClient::Start HRESULT 0x{:08X}".format(hr & 0xFFFFFFFF)
            )
        self._stop.clear()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        try:
            STOP = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)
            STOP(self._client_vtbl[11])(self._client_ptr)
        except Exception:
            pass

    def read(self, numframes: int, timeout: float = 5.0):
        """Block up to ``timeout`` seconds for ``numframes`` mono float32 samples."""
        import numpy as np
        bytes_per_frame_mono = 4   # float32
        want = numframes * bytes_per_frame_mono
        deadline = time.time() + timeout
        while True:
            with self._buf_lock:
                if len(self._buf) >= want:
                    chunk = bytes(self._buf[:want])
                    del self._buf[:want]
                    arr = np.frombuffer(chunk, dtype=np.float32)
                    return arr
            if self._stop.is_set() or time.time() >= deadline:
                # Return whatever we have, zero-padded.
                with self._buf_lock:
                    have = bytes(self._buf)
                    self._buf.clear()
                arr = np.frombuffer(have, dtype=np.float32)
                if len(arr) < numframes:
                    pad = np.zeros(numframes - len(arr), dtype=np.float32)
                    arr = np.concatenate([arr, pad])
                return arr[:numframes]
            time.sleep(0.02)

    # ---------- internals ----------

    def _pump(self):
        import numpy as np
        GET_NEXT_PACKET_SIZE = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)
        )
        GET_BUFFER = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),     # **pData
            ctypes.POINTER(ctypes.c_uint32),     # *numFrames
            ctypes.POINTER(ctypes.c_uint32),     # *dwFlags
            ctypes.POINTER(ctypes.c_uint64),     # *qpcPosition
            ctypes.POINTER(ctypes.c_uint64),     # *DevicePosition
        )
        RELEASE_BUFFER = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_uint32
        )

        cap_vtbl = ctypes.cast(
            ctypes.cast(
                self._capture_ptr, ctypes.POINTER(ctypes.c_void_p)
            )[0],
            ctypes.POINTER(ctypes.c_void_p),
        )
        get_next_size = GET_NEXT_PACKET_SIZE(cap_vtbl[3])
        get_buffer = GET_BUFFER(cap_vtbl[4])
        release_buffer = RELEASE_BUFFER(cap_vtbl[5])

        channels = self._native_channels

        while not self._stop.is_set():
            packet_size = ctypes.c_uint32(0)
            hr = get_next_size(self._capture_ptr, ctypes.byref(packet_size))
            if hr != 0:
                time.sleep(0.01)
                continue
            if packet_size.value == 0:
                time.sleep(0.005)
                continue
            data_ptr = ctypes.c_void_p(0)
            num_frames = ctypes.c_uint32(0)
            flags = ctypes.c_uint32(0)
            qpc = ctypes.c_uint64(0)
            devpos = ctypes.c_uint64(0)
            hr = get_buffer(
                self._capture_ptr,
                ctypes.byref(data_ptr),
                ctypes.byref(num_frames),
                ctypes.byref(flags),
                ctypes.byref(qpc),
                ctypes.byref(devpos),
            )
            if hr != 0 or num_frames.value == 0 or not data_ptr.value:
                try:
                    release_buffer(self._capture_ptr, num_frames.value)
                except Exception:
                    pass
                continue
            # AUDCLNT_BUFFERFLAGS_SILENT = 0x2
            silent = bool(flags.value & 0x2)
            count = num_frames.value
            byte_len = count * channels * 4   # float32
            buf = (ctypes.c_byte * byte_len).from_address(data_ptr.value)
            if silent:
                pcm = np.zeros(count * channels, dtype=np.float32)
            else:
                pcm = np.frombuffer(bytes(buf), dtype=np.float32).copy()
            release_buffer(self._capture_ptr, count)

            if channels > 1:
                pcm = pcm.reshape(-1, channels).mean(axis=1)
            with self._buf_lock:
                self._buf.extend(pcm.astype(np.float32).tobytes())


def is_supported() -> bool:
    """Best-effort check that Process Loopback is available on this machine.

    Doesn't actually capture; just tries to load the relevant DLLs and
    confirms we're on a Windows build new enough to have the API.
    """
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.mmdevapi
    except Exception:
        return False
    try:
        ver = sys.getwindowsversion()
    except Exception:
        return False
    # Windows 10, build 20348 (Server 2022 / Win11 lineage) added the API.
    # We accept any Windows 10 1903+ and let activation succeed-or-fail at
    # runtime since the build check is unreliable on older Python.
    if ver.major < 10:
        return False
    return True
