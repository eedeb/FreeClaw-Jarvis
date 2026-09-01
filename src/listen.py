"""
"Hey Jarvis" — wake word + speech-to-text, tuned for the shortest possible
gap between the user finishing a sentence and Jarvis acting on it.

Three models, each chosen for that: openWakeWord's pretrained `hey_jarvis`
model scores 20ms of audio in a fraction of a millisecond, so it can run
continuously against every frame the microphone produces for the cost of a
rounding error; webrtcvad decides frame-by-frame, just as cheaply, when the
user has stopped talking, so the recording ends the instant they do rather
than after a fixed timer; faster-whisper's `tiny.en` model, run int8 on CPU,
transcribes what was said in well under a second once warm. None of this
reaches a network — everything after the microphone runs on this machine.

    ARMED ──(wake word)──► CAPTURING ──(silence)──► TRANSCRIBING ──► ARMED
      ▲                                                    │
      └──────────────────── on_transcript(text) ───────────┘

All of it happens on one worker thread, fed by a queue the audio callback
fills — PortAudio's callback has to return in microseconds, so the callback
itself never does more than a copy into that queue. `pause()`/`resume()` and
`arm()`/`disarm()` are the only calls made from other threads; they just flip
a lock-guarded flag the worker checks each frame.
"""

import queue
import threading
import time
from collections import deque

import numpy as np

from logging_setup import get_logger

logger = get_logger(__name__)

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320

# Audio kept from just before a wake word is confirmed, and stitched onto the
# front of the capture. openWakeWord can take up to ~80ms of extra audio to
# confirm a detection (see Model.predict), so without this the very start of
# whatever the user says immediately after "Hey Jarvis" would sometimes be
# clipped.
PREROLL_FRAMES = 15  # 300ms

# Endpointing. TRAILING_SILENCE_MS of no voiced frames (per webrtcvad) ends
# the capture — this is what "optimised for fastest response" mostly comes
# down to: no fixed multi-second recording window, just "stopped talking".
# MIN/MAX are safety rails: too short to be a real command, or long enough
# that something has gone wrong and the mic shouldn't stay open forever.
TRAILING_SILENCE_MS = 600
MIN_UTTERANCE_S = 0.35
MAX_UTTERANCE_S = 12.0

# openWakeWord's score crosses this to count as a detection. Its own examples
# use 0.5; lower catches more true positives at the cost of more false ones.
WAKE_THRESHOLD = 0.5

STATE_ARMED = "armed"
STATE_CAPTURING = "capturing"
STATE_TRANSCRIBING = "transcribing"
STATE_PAUSED = "paused"


class HotwordListener:
    """Continuous "Hey Jarvis" detection, feeding a local Whisper model.

    `on_transcript(text)` is called on the worker thread with whatever was
    heard after the wake word — never with empty or whitespace-only text.
    `on_state(state)` is optional and is called on every state transition
    (one of the STATE_* constants above), for UI feedback; exceptions from it
    are logged and otherwise ignored so a UI hiccup can't take the listener
    down.
    """

    def __init__(self, on_transcript, on_state=None, wake_model="hey_jarvis",
                 stt_model_size="tiny.en", threshold=WAKE_THRESHOLD, device=None):
        self.on_transcript = on_transcript
        self.on_state = on_state
        self.wake_model = wake_model
        self.stt_model_size = stt_model_size
        self.threshold = threshold
        self.device = device

        self._lock = threading.RLock()
        self._state = STATE_PAUSED
        self._armed_wanted = False
        self._running = False

        self._stream = None
        self._oww = None
        self._vad = None
        self._whisper = None

        self._queue = queue.Queue(maxsize=200)  # ~4s of frames; ample slack
        self._worker = None

        self._preroll = deque(maxlen=PREROLL_FRAMES)
        self._capture = []
        self._voiced_ms = 0
        self._silence_ms = 0

    # ── lifecycle ────────────────────────────────────────────

    def start(self):
        """Load the models and open the microphone. Returns True on success;
        False (logged) if there's no mic, the models can't be fetched, or the
        optional dependencies aren't installed — any of which leaves Jarvis
        exactly as usable as before, just without voice input."""
        try:
            import sounddevice as sd
        except ImportError:
            logger.warning("sounddevice isn't installed — voice input is disabled")
            return False

        if not self._load_models():
            return False

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=FRAME_SAMPLES, device=self.device,
                callback=self._on_audio)
            self._stream.start()
        except Exception as e:
            logger.warning("Could not open the microphone — voice input is disabled: %s", e)
            self._stream = None
            return False

        self._running = True
        self._worker = threading.Thread(target=self._run, name="jarvis-listen", daemon=True)
        self._worker.start()
        with self._lock:
            # Honour an arm() that arrived before start() finished loading
            # models — a caller shouldn't have to sequence the two.
            if self._armed_wanted:
                self._enter_armed()
        logger.info("Listening for 'Hey Jarvis'")
        return True

    def stop(self):
        """Shut down the microphone and worker thread. Not expected to be
        called during normal operation — only at app exit."""
        self._running = False
        with self._lock:
            self._state = STATE_PAUSED
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        try:
            self._queue.put_nowait(None)  # wake the worker so it can exit
        except queue.Full:
            pass

    def _load_models(self):
        try:
            from openwakeword.model import Model
            from openwakeword.utils import download_models
        except ImportError:
            logger.warning("openwakeword isn't installed — voice input is disabled")
            return False
        try:
            import webrtcvad
        except ImportError:
            logger.warning("webrtcvad isn't installed — voice input is disabled")
            return False
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.warning("faster-whisper isn't installed — voice input is disabled")
            return False

        try:
            download_models([self.wake_model])
            self._oww = Model(wakeword_models=[self.wake_model], inference_framework="onnx")
        except Exception as e:
            logger.warning("Could not load the '%s' wake word model: %s", self.wake_model, e)
            return False

        # Aggressiveness 2 of 0-3: leans toward not cutting speech off early,
        # which matters more here than rejecting the odd noise burst — a
        # capture that runs briefly long costs a few hundred ms of
        # transcription; one that ends mid-sentence loses words outright.
        self._vad = webrtcvad.Vad(2)

        try:
            self._whisper = WhisperModel(self.stt_model_size, device="cpu", compute_type="int8")
        except Exception as e:
            logger.warning("Could not load the '%s' speech-to-text model: %s",
                           self.stt_model_size, e)
            return False

        return True

    # ── arm/disarm (persistent intent) vs pause/resume (temporary mute) ──

    def arm(self):
        """Start (or resume) listening for the wake word."""
        with self._lock:
            self._armed_wanted = True
            if self._running and self._state == STATE_PAUSED:
                self._enter_armed()

    def disarm(self):
        """Stop listening for the wake word until arm() is called again."""
        with self._lock:
            self._armed_wanted = False
            self._enter_paused()

    def pause(self):
        """Mute without forgetting whether we're meant to be armed — for the
        brief window around a turn (see main.py's _run_turn), not a user
        choice. resume() undoes exactly this."""
        with self._lock:
            self._enter_paused()

    def resume(self):
        """Undo pause() — a no-op if disarm() was called meanwhile."""
        with self._lock:
            if self._armed_wanted:
                self._enter_armed()

    @property
    def state(self):
        with self._lock:
            return self._state

    # ── state transitions (always called with _lock held) ───

    def _enter_armed(self):
        self._reset_capture()
        self._preroll.clear()
        self._set_state(STATE_ARMED)

    def _enter_paused(self):
        self._reset_capture()
        self._preroll.clear()
        self._set_state(STATE_PAUSED)

    def _set_state(self, state):
        if state == self._state:
            return
        logger.info("Listener state: %s -> %s", self._state, state)
        self._state = state
        if self.on_state is not None:
            try:
                self.on_state(state)
            except Exception:
                logger.debug("on_state callback failed", exc_info=True)

    def _reset_capture(self):
        """Clear the in-progress capture and its endpointing counters.

        Deliberately leaves the preroll ring alone — it has to keep rolling
        all through STATE_ARMED so _on_wake_detected has something to prepend
        the instant it fires; the two _enter_* transitions above are what
        clear it, on the way in or out of being armed at all."""
        self._capture = []
        self._voiced_ms = 0
        self._silence_ms = 0

    # ── audio I/O ────────────────────────────────────────────

    def _on_audio(self, indata, frames, time_info, status):
        """PortAudio callback — runs on its own thread and must return fast.
        All it does is hand the frame to the worker; every real decision
        happens in _run()."""
        if status:
            logger.debug("Audio stream status: %s", status)
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            # The worker has fallen behind (a slow transcription, a stalled
            # thread) — drop this frame rather than block PortAudio's thread,
            # which would corrupt the stream rather than just lose 20ms.
            pass

    def _run(self):
        while self._running:
            try:
                frame_bytes = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if frame_bytes is None:
                continue
            frame = np.frombuffer(frame_bytes, dtype=np.int16)
            if len(frame) != FRAME_SAMPLES:
                continue  # a partial frame at stream start/stop; skip it

            with self._lock:
                state = self._state

            if state == STATE_ARMED:
                self._on_armed_frame(frame, frame_bytes)
            elif state == STATE_CAPTURING:
                self._on_capturing_frame(frame, frame_bytes)
            # PAUSED and TRANSCRIBING: drain and discard: nothing gets acted
            # on, but the queue must not be left to fill and start dropping
            # the calls above make on a genuinely idle stream.

    def _on_armed_frame(self, frame, frame_bytes):
        self._preroll.append(frame_bytes)
        try:
            scores = self._oww.predict(frame)
        except Exception:
            logger.exception("Wake word scoring failed")
            return
        if scores.get(self.wake_model, 0.0) >= self.threshold:
            self._on_wake_detected()

    def _on_wake_detected(self):
        logger.info("Wake word detected")
        with self._lock:
            preroll = list(self._preroll)
            self._reset_capture()
            self._capture.extend(preroll)
            self._set_state(STATE_CAPTURING)

    def _on_capturing_frame(self, frame, frame_bytes):
        self._capture.append(frame_bytes)
        try:
            voiced = self._vad.is_speech(frame_bytes, SAMPLE_RATE)
        except Exception:
            voiced = True  # fail open — better to keep listening than cut off early

        if voiced:
            self._voiced_ms += FRAME_MS
            self._silence_ms = 0
        else:
            self._silence_ms += FRAME_MS

        total_ms = len(self._capture) * FRAME_MS
        endpointed = (self._voiced_ms >= MIN_UTTERANCE_S * 1000
                     and self._silence_ms >= TRAILING_SILENCE_MS)
        timed_out = total_ms >= MAX_UTTERANCE_S * 1000

        if endpointed or timed_out:
            self._finish_capture()

    def _finish_capture(self):
        with self._lock:
            frames = self._capture
            self._reset_capture()
            self._set_state(STATE_TRANSCRIBING)

        audio = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32) / 32768.0
        text = ""
        if len(audio) >= SAMPLE_RATE * MIN_UTTERANCE_S:
            try:
                t0 = time.monotonic()
                segments, _info = self._whisper.transcribe(
                    audio, language="en", beam_size=1,
                    condition_on_previous_text=False, vad_filter=False)
                text = "".join(s.text for s in segments).strip()
                logger.info("Transcribed in %.0fms: %r", (time.monotonic() - t0) * 1000, text)
            except Exception:
                logger.exception("Transcription failed")

        with self._lock:
            # Only re-arm automatically if nothing else (a turn starting)
            # asked for a pause in the meantime.
            still_transcribing = self._state == STATE_TRANSCRIBING
        if text:
            try:
                self.on_transcript(text)
            except Exception:
                logger.exception("on_transcript callback failed")
        elif still_transcribing:
            with self._lock:
                if self._armed_wanted:
                    self._enter_armed()
