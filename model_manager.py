"""Model catalog + downloader for Auralis.

The faster-whisper library lazily downloads models from Hugging Face on first
use — which is great when it works, but a user that's offline, low on disk,
or running with antivirus interference gets a fatal exception.

This module centralises three things:

1. A catalog of known models with human-readable labels, sizes, and a short
   description of what each one is good for.
2. A cache-presence check (``is_cached``) that uses huggingface_hub's
   ``local_files_only`` snapshot lookup so we know if a model is downloaded
   BEFORE we try to instantiate WhisperModel.
3. A downloader (``download_model``) that streams progress out to a callback
   so the GUI can show a friendly progress bar.

Custom model IDs (anything not in the catalog) are accepted: ``is_cached``
still works, and ``approx_size_mb`` returns ``None`` so the GUI can prompt
"size unknown, continue?".
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


# -----------------------------------------------------------------------
# Catalog
# -----------------------------------------------------------------------

@dataclass
class ModelEntry:
    """One row in the model catalog."""
    label: str                    # Human-readable label shown in the UI.
    hf_repo: str                  # The HF repo id OR a faster-whisper alias.
    approx_size_mb: int           # Approximate on-disk size in MB.
    languages: str                # Short text e.g. "Hebrew + English (best)".
    description: str              # Two-line description.
    recommended: bool = False     # Show a "Recommended" badge.


# When a user picks a faster-whisper alias like "large-v3", the actual HF
# repo that gets downloaded is "Systran/faster-whisper-large-v3". We use the
# alias as the model_id for both the catalog and faster-whisper's constructor
# (faster-whisper does the alias-to-repo mapping internally), and we keep a
# second mapping here so we can hit huggingface_hub directly when we need
# explicit downloads or cache presence checks.

ALIAS_TO_REPO = {
    "large-v3":  "Systran/faster-whisper-large-v3",
    "large-v2":  "Systran/faster-whisper-large-v2",
    "large":     "Systran/faster-whisper-large-v2",
    "medium":    "Systran/faster-whisper-medium",
    "small":     "Systran/faster-whisper-small",
    "base":      "Systran/faster-whisper-base",
    "tiny":      "Systran/faster-whisper-tiny",
}


CATALOG: list[ModelEntry] = [
    ModelEntry(
        label="Ivrit.AI v3 turbo (Hebrew, recommended)",
        hf_repo="ivrit-ai/whisper-large-v3-turbo-ct2",
        approx_size_mb=1500,
        languages="Hebrew + English",
        description=(
            "Hebrew-tuned Whisper large-v3 turbo. Best accuracy for Hebrew "
            "university lectures. Fastest of the Hebrew models. "
            "Recommended default."
        ),
        recommended=True,
    ),
    ModelEntry(
        label="Ivrit.AI v3 (Hebrew, slower / more accurate)",
        hf_repo="ivrit-ai/whisper-large-v3-ct2",
        approx_size_mb=3000,
        languages="Hebrew + English",
        description=(
            "Hebrew-tuned Whisper large-v3 (full, not turbo). Slightly more "
            "accurate than the turbo build but 2-3× slower. Pick if you have "
            "a fast machine and a lot of patience."
        ),
    ),
    ModelEntry(
        label="Whisper large-v3 (general)",
        hf_repo="large-v3",
        approx_size_mb=3000,
        languages="Multilingual",
        description=(
            "Stock OpenAI Whisper large-v3, general purpose. Not Hebrew-tuned "
            "but supports 90+ languages. Use for English-only lectures or "
            "other languages."
        ),
    ),
    ModelEntry(
        label="Whisper medium",
        hf_repo="medium",
        approx_size_mb=1500,
        languages="Multilingual",
        description=(
            "Stock Whisper medium. Smaller, ~2× faster than large-v3, lower "
            "accuracy. Good for quick tests."
        ),
    ),
    ModelEntry(
        label="Whisper small",
        hf_repo="small",
        approx_size_mb=480,
        languages="Multilingual",
        description=(
            "Stock Whisper small. Fast, runs comfortably on most laptops, "
            "accuracy drops on Hebrew. Good for short clips."
        ),
    ),
    ModelEntry(
        label="Whisper base",
        hf_repo="base",
        approx_size_mb=140,
        languages="Multilingual",
        description="Stock Whisper base. Very fast, low accuracy.",
    ),
    ModelEntry(
        label="Whisper tiny",
        hf_repo="tiny",
        approx_size_mb=75,
        languages="Multilingual",
        description="Stock Whisper tiny. Smallest model, fastest, lowest accuracy.",
    ),
]


# Build helper dicts for quick lookups.
LABEL_TO_ENTRY = {e.label: e for e in CATALOG}
REPO_TO_ENTRY = {e.hf_repo: e for e in CATALOG}
ALL_LABELS = [e.label for e in CATALOG]


def entry_for(model_id_or_label: str) -> Optional[ModelEntry]:
    """Look up a catalog entry by either label or model_id / hf_repo."""
    if not model_id_or_label:
        return None
    if model_id_or_label in LABEL_TO_ENTRY:
        return LABEL_TO_ENTRY[model_id_or_label]
    if model_id_or_label in REPO_TO_ENTRY:
        return REPO_TO_ENTRY[model_id_or_label]
    return None


def model_id_for_label(label: str) -> str:
    """Translate a catalog label to the model_id that faster-whisper expects."""
    e = LABEL_TO_ENTRY.get(label)
    if e is not None:
        return e.hf_repo
    # Treat unknown labels as raw model IDs (custom HF repos).
    return label


def approx_size_mb(model_id: str) -> Optional[int]:
    """Return approximate on-disk size in MB, or None for unknown custom IDs."""
    e = entry_for(model_id)
    return e.approx_size_mb if e is not None else None


# -----------------------------------------------------------------------
# Cache presence
# -----------------------------------------------------------------------

def _resolve_hf_repo(model_id: str) -> str:
    """Map a faster-whisper alias (large-v3, medium...) to its HF repo id.

    For anything that already looks like 'org/name' (contains a slash) or any
    other custom string, return it unchanged.
    """
    if "/" in model_id:
        return model_id
    return ALIAS_TO_REPO.get(model_id, model_id)


def is_cached(model_id: str) -> bool:
    """Return True if the model is fully downloaded locally.

    Uses huggingface_hub's ``local_files_only`` snapshot lookup, which only
    succeeds if every file in the repo is present on disk. Returns False if
    the lookup fails for any reason (including huggingface_hub not being
    installed yet).
    """
    repo = _resolve_hf_repo(model_id)
    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError
    except Exception:
        return False
    try:
        path = snapshot_download(repo_id=repo, local_files_only=True)
        # Sanity check: a CT2 model needs at least a model.bin in there.
        p = Path(path)
        if any(p.rglob("model.bin")):
            return True
        # Some HF repos use other filenames; the snapshot succeeded so consider it good.
        return True
    except LocalEntryNotFoundError:
        return False
    except Exception:
        return False


def cache_dir_for(model_id: str) -> Optional[Path]:
    """Return the HF cache directory for the model, if it exists."""
    repo = _resolve_hf_repo(model_id)
    try:
        from huggingface_hub import snapshot_download
    except Exception:
        return None
    try:
        path = snapshot_download(repo_id=repo, local_files_only=True)
        return Path(path)
    except Exception:
        return None


def disk_size_mb(model_id: str) -> Optional[int]:
    """Actual on-disk size of the model's HF snapshot in MB, or None."""
    d = cache_dir_for(model_id)
    if d is None or not d.exists():
        return None
    total = 0
    for f in d.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except Exception:
            pass
    return int(total / (1024 * 1024))


# -----------------------------------------------------------------------
# Downloader
# -----------------------------------------------------------------------

@dataclass
class DownloadProgress:
    """Snapshot of an in-flight model download."""
    model_id: str
    total_bytes: int = 0
    downloaded_bytes: int = 0
    current_file: str = ""
    done: bool = False
    error: str = ""

    @property
    def pct(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, (self.downloaded_bytes / self.total_bytes) * 100.0)


def download_model(
    model_id: str,
    progress_cb: Callable[[DownloadProgress], None],
    cancel_event: Optional[threading.Event] = None,
) -> DownloadProgress:
    """Download a model from Hugging Face with progress callbacks.

    Calls ``progress_cb`` periodically with the current ``DownloadProgress``.
    Returns the final progress object — check ``.done`` and ``.error``.

    On network failure or other exception, ``.error`` is populated and the
    function returns normally (does not raise).
    """
    prog = DownloadProgress(model_id=model_id)
    repo = _resolve_hf_repo(model_id)

    try:
        from huggingface_hub import hf_hub_download, HfApi
    except Exception as e:
        prog.error = (
            "huggingface_hub is not installed. Run setup_and_run.bat to install "
            "dependencies. (" + str(e) + ")"
        )
        progress_cb(prog)
        return prog

    # First pass: list files in the repo and total up sizes.
    try:
        api = HfApi()
        files = api.list_repo_files(repo_id=repo)
    except Exception as e:
        prog.error = "Could not reach Hugging Face: " + str(e)
        progress_cb(prog)
        return prog

    # Keep only files we actually need to run inference. CT2 / Whisper repos
    # have everything important under model.bin + config + tokenizer + vocab.
    wanted_suffixes = (
        ".bin", ".json", ".txt", ".model", ".vocab", ".tiktoken", ".spm",
    )
    files = [f for f in files if f.lower().endswith(wanted_suffixes)]

    # Pre-fetch each file's size via the HF API to get accurate progress.
    sizes: dict[str, int] = {}
    total = 0
    for f in files:
        try:
            info = api.get_paths_info(repo_id=repo, paths=[f])
            if info and hasattr(info[0], "size") and info[0].size:
                sizes[f] = int(info[0].size)
                total += sizes[f]
        except Exception:
            sizes[f] = 0
    prog.total_bytes = total or 1
    progress_cb(prog)

    downloaded = 0
    for f in files:
        if cancel_event is not None and cancel_event.is_set():
            prog.error = "Download cancelled."
            progress_cb(prog)
            return prog
        prog.current_file = f
        progress_cb(prog)
        try:
            hf_hub_download(repo_id=repo, filename=f)
        except Exception as e:
            prog.error = "Failed to download " + f + ": " + str(e)
            progress_cb(prog)
            return prog
        downloaded += sizes.get(f, 0)
        prog.downloaded_bytes = downloaded
        progress_cb(prog)

    prog.done = True
    prog.downloaded_bytes = prog.total_bytes
    progress_cb(prog)
    return prog


def remove_model(model_id: str) -> bool:
    """Delete a downloaded model from the HF cache. Returns True on success."""
    d = cache_dir_for(model_id)
    if d is None:
        return False
    # snapshot_download returns the snapshot dir; we want the parent repo dir,
    # which contains snapshots/, blobs/, refs/.
    repo_dir = d.parent.parent if d.parent.name == "snapshots" else d
    try:
        shutil.rmtree(repo_dir, ignore_errors=True)
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------
# Friendly summaries for the UI
# -----------------------------------------------------------------------

def describe(model_id: str) -> str:
    """Return a friendly one-paragraph description of the model."""
    e = entry_for(model_id)
    if e is not None:
        size_str = "~{:,} MB".format(e.approx_size_mb)
        return e.description + "  (" + size_str + ", " + e.languages + ")"
    return "Custom Hugging Face model: " + model_id + ". Size unknown until first download."


def label_for(model_id: str) -> str:
    """Return the catalog label for a known model, or the raw ID otherwise."""
    e = entry_for(model_id)
    return e.label if e is not None else model_id
