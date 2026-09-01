"""
Speech output for Jarvis.

Replaces the original (missing) `modules.vocalize.coqui`. Same contract the
decompiled main_free.py expected: an awaitable `speak(text)` that blocks until
the line has finished playing, so the orb's speaking animation brackets the
audio exactly.

Synthesis is edge-tts (Microsoft's neural voices, no API key, network only);
playback is pygame.mixer. If either is unavailable the call degrades to a
no-op rather than taking the turn down with it — a silent Jarvis is still a
working Jarvis.
"""

import asyncio
import os
import tempfile
import threading
import uuid

from logging_setup import get_logger

logger = get_logger(__name__)

DEFAULT_VOICE = "en-GB-RyanNeural"

# One mixer for the process, initialised lazily so importing this module never
# grabs the sound device (and never fails on a machine with no audio output).
_mixer_lock = threading.Lock()
_mixer_ready = None


def _ensure_mixer():
    """Bring pygame.mixer up once. Returns the module, or None if unavailable."""
    global _mixer_ready
    with _mixer_lock:
        if _mixer_ready is not None:
            return _mixer_ready or None
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
            pygame.mixer.init()
            _mixer_ready = pygame
            return pygame
        except Exception as e:
            logger.warning("No audio output available, speech will be silent: %s", e)
            _mixer_ready = False
            return None


def warm_up():
    """Open the sound device ahead of time, off the critical path.

    Bringing pygame.mixer up costs a few seconds the first time. Paying that
    during startup rather than on the first reply is the difference between
    Jarvis answering promptly and appearing to hang on his opening line.
    """
    threading.Thread(target=_ensure_mixer, name="jarvis-audio-warmup",
                     daemon=True).start()


def stop():
    """Cut off whatever is currently playing. Safe to call at any time."""
    pygame = _ensure_mixer()
    if pygame is None:
        return
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass


async def speak(text, voice=None):
    """Say `text` aloud, returning once playback has finished.

    Awaited by the UI's speech task, which shows the speaking animation for
    exactly as long as this runs.
    """
    text = (text or "").strip()
    if not text:
        return

    try:
        import edge_tts
    except ImportError:
        logger.warning("edge-tts is not installed, speech is disabled")
        return

    path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.mp3")
    try:
        communicate = edge_tts.Communicate(text, voice or DEFAULT_VOICE)
        await communicate.save(path)
    except Exception as e:
        # Almost always no network — edge-tts synthesises server-side.
        logger.warning("Speech synthesis failed: %s", e)
        _cleanup(path)
        return

    try:
        await _play(path)
    finally:
        _cleanup(path)


async def _play(path):
    """Play `path` to completion without blocking the event loop."""
    pygame = _ensure_mixer()
    if pygame is None:
        return
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
    except Exception as e:
        logger.warning("Could not play synthesised speech: %s", e)
        return

    # Poll rather than block: this coroutine shares the loop with the UI's
    # widget calls, and pygame has no awaitable "finished" signal.
    try:
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.05)
    except Exception:
        pass
    finally:
        # Release the file handle so the temp file can actually be deleted on
        # Windows, where an open mixer keeps a lock on it.
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass


def _cleanup(path):
    try:
        os.remove(path)
    except OSError:
        pass


class SpeechToTextListener:
    """Placeholder for the original speech-to-text listener.

    Voice *input* is not built yet — Jarvis currently listens by keyboard. The
    class exists so the UI's start/stop listening controls have something to
    call that reports honestly instead of raising.
    """

    def __init__(self):
        self.running = False

    def start(self):
        raise NotImplementedError(
            "Voice input isn't wired up yet — type to Jarvis instead.")

    def stop(self):
        self.running = False
