"""
core/audio_devices.py — pick which microphone and which speakers JINX uses.

WHY
    Both audio streams in main.py were opened without a `device=` argument, so
    they always took whatever the operating system called "default". On a laptop
    with a built-in mic, a webcam mic and a headset that is a coin toss — and on
    Windows the default *moves on its own* the moment you plug a headset in.
    "JINX can't hear me" almost always means "JINX is listening to the
    monitor's microphone".

WHY NAMES, NOT INDICES
    sounddevice identifies devices by integer index, and those indices shift
    whenever a device appears or disappears. Storing index 3 means that after
    unplugging a USB interface the saved setting silently points at something
    else. We store the device *name* and resolve it to an index at open time.

WHY THIS IS CACHED
    `sd.query_devices()` talks to the host audio API and can take a few hundred
    milliseconds on a Windows machine with many endpoints. The JINX LV release learned this
    lesson the expensive way — a 2.1-second `openwakeword` import on the Qt
    thread made the settings drawer look like it was broken. So the list is
    fetched once on a background thread at startup and served from cache.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

# The label shown for "let the OS decide", and the value stored in config for
# it. Empty string, so an untouched install and a deliberately-default install
# are the same thing — nothing changes for anyone who never opens the picker.
DEFAULT_LABEL = "System default"
DEFAULT_VALUE = ""

_cache: dict[str, list[str]] | None = None
_cache_lock = threading.Lock()
_selection_lock = threading.RLock()
_prefetch_lock = threading.Lock()
_prefetching = False

# Which host API each direction settled on, so resolve() opens the same endpoint
# the picker listed. Filled in by _query().
_chosen_api: dict = {"input": None, "output": None}


# ── Why the raw list is unusable, and what is filtered out ───────────────────
#
# `sd.query_devices()` returns one entry per (device × host API), not one per
# device. Measured on a normal Windows machine: 41 entries for what the Windows
# sound settings show as 4 microphones and 4 speakers. The same Realtek
# microphone appears four times — once each under MME, DirectSound, WASAPI and
# WDM-KS — and none of the four is labelled to say which is which.
#
# Handing that to a person is not a choice, it is a quiz. So the list is reduced
# the way the operating system's own settings panel does it:
#
#   1. ONE host API per direction — chosen by measurement, not by reasoning.
#      See the preference note below.
#   2. No pseudo-devices. "Microsoft Sound Mapper", "Primary Sound Driver",
#      ALSA's "default"/"sysdefault"/"dmix" are aliases for "whatever the OS
#      picks" — which is precisely the "System default" entry already at the top
#      of the list. Offering them again as if they were hardware is noise.
#   3. No zero-channel or unnamed entries (WASAPI reports one of each).
#   4. Deduplicated by name.
#
# Nothing is hidden that a person could actually want: the same hardware is
# still there, listed once, under the name their operating system uses for it.

# ── Preference order, which is only a starting point ─────────────────────────
#
# Two earlier versions of this file were wrong in the same way: they decided
# which host API to use by reasoning about it instead of measuring it.
#
#   v1 ranked APIs by how clean their device names were and picked WASAPI.
#      WASAPI in shared mode does not resample — the hardware runs at 48 kHz,
#      this app streams 16 kHz in and 24 kHz out, and every open failed with
#      "Invalid sample rate". The picker looked right and did nothing.
#
#   v2 added a rate check and picked DirectSound, which passes that check on
#      both sides. PortAudio's DirectSound *output* is a silent sink: the
#      stream opens, every write returns success in ~0 ms, and nothing is ever
#      heard. Same failure, one layer deeper.
#
# So this list is a preference, not a promise. Which API actually gets used is
# decided below by _usable() (open it for real) and _transport_works() (does
# audio actually move), per direction. On this platform that lands on
# DirectSound for the microphone and MME for the speakers — a split that no
# amount of reasoning would have produced.
_PREFERRED_APIS = {
    "Windows": ("directsound", "mme", "wasapi"),
    # macOS has only Core Audio, so there is nothing to disambiguate.
    "Darwin":  ("core audio",),
    # PulseAudio/PipeWire present one clean endpoint per device; raw ALSA
    # presents dozens of routing permutations of the same card.
    "Linux":   ("pulse", "pipewire", "jack", "alsa"),
}

# ── "It opens" is not "it works" ─────────────────────────────────────────────
#
# Opening a stream successfully proves nothing. Measured, writing 2.0 s of audio:
#
#     device=None (MME)                    2.02 s   consumed in real time
#     DirectSound, any output device       0.00 s   swallowed instantly
#
# No flag or capability field reports this. The only thing that separates a real
# sink from a fake one is whether it consumes audio at the rate audio is
# consumed at — so that is what gets measured, once per host API per direction,
# on the background thread at startup, using silence.
#
# Each direction is probed **the way main.py actually uses it**. That is not a
# detail: DirectSound input passes a callback stream and fails a blocking read,
# so an earlier version of this probe rejected a microphone that works perfectly
# in the app. Probe the mode you ship, not the mode that is easier to write.
_PROBE_SECONDS = {"output": 0.6, "input": 0.35}

# Cache includes endpoint identity, direction and rate; endpoints can disagree
# even when they use the same host API.
_probe_results: dict = {}


def _transport_works(idx: int, kind: str, api_key) -> bool:
    """Does this host API actually move audio, or only pretend to?

    Probed once per API per direction and cached. Output writes silence, so the
    probe is inaudible; input reads and discards."""
    cache_key = (api_key, kind, idx, _RATES.get(kind, 16000))
    if cache_key in _probe_results:
        return _probe_results[cache_key]

    ok = False
    st = None
    try:
        import sounddevice as sd
        rate = _RATES.get(kind, 16000)
        secs = _PROBE_SECONDS.get(kind, 0.5)

        # Each direction is probed the way main.py actually uses it. That is not
        # a detail: DirectSound input passes a callback stream and fails a
        # blocking read, so probing the wrong mode rejected a microphone that
        # works perfectly in the app.
        if kind == "output":
            # main.py writes with stream.write() — a real sink is rate-limited
            # by the hardware clock, a fake one swallows the buffer instantly.
            st = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16",
                                    blocksize=1024, device=idx)
            st.start()
            t0 = time.monotonic()
            st.write(bytes(int(rate * secs) * 2))   # silence — inaudible
            st.stop()  # Include draining buffered output, not only write().
            elapsed = time.monotonic() - t0
            ok = elapsed > secs * 0.5
            if not ok:
                print(f"[Audio] output: host API reports success but moves no "
                      f"audio ({elapsed*1000:.0f} ms for {secs*1000:.0f} ms) "
                      f"— skipping it")
        else:
            # main.py reads through a callback — count what arrives.
            frames = [0]

            def _cb(indata, n, *_a):
                frames[0] += n

            st = sd.InputStream(samplerate=rate, channels=1, dtype="int16",
                                blocksize=1024, device=idx, callback=_cb)
            st.start()
            time.sleep(secs)
            st.stop()
            ok = frames[0] > rate * secs * 0.3
            if not ok:
                print(f"[Audio] input: host API delivered {frames[0]} frames in "
                      f"{secs*1000:.0f} ms — skipping it")
    except Exception as e:
        print(f"[Audio] {kind} transport probe failed: {e}")
        ok = False
    finally:
        _close_stream(st)

    _probe_results[cache_key] = ok
    return ok


def _close_stream(stream):
    if stream is None:
        return
    try:
        stream.stop()
    except Exception:
        pass
    try:
        stream.close()
    except Exception:
        pass


class SerializedOutput:
    """Let pending blocking writes finish before the stream is closed."""
    def __init__(self, stream):
        self._stream = stream
        self._io_lock = threading.RLock()
        self._closed = False

    @property
    def latency(self):
        return self._stream.latency

    def write(self, data):
        with self._io_lock:
            if self._closed:
                raise RuntimeError('Audio output is closed')
            return self._stream.write(data)

    def stop(self):
        with self._io_lock:
            if not self._closed:
                self._stream.stop()

    def close(self):
        with self._io_lock:
            if not self._closed:
                self._closed = True
                _close_stream(self._stream)


def _display_name(name: str, devices) -> str:
    """MME truncates device names to 31 characters, so the API that actually
    carries the audio may not be the one that can spell. If another host API
    knows a longer name that starts with this one, show that instead — the user
    reads 'Realtek HD Audio 2nd output (Realtek(R) Audio)' while the stream runs
    on the endpoint called 'Realtek HD Audio 2nd output (Re'."""
    if len(name) < 30:
        return name
    best = name
    for dev in devices:
        other = (dev.get("name") or "").strip()
        if len(other) > len(best) and other.startswith(name):
            best = other
    return best

# The rates the app opens its streams at. Defaults match main.py; main.py calls
# configure() at startup with its own constants so the two can never drift apart
# and silently reintroduce the bug above.
_RATES = {"input": 16000, "output": 24000}


def configure(input_rate: int, output_rate: int) -> None:
    """Tell this module the sample rates the audio streams will use, so the
    picker can rule out devices that cannot be opened at them.

    Drops the cached list/probes if rates changed. Reapplying the same rates
    preserves the early background enumeration."""
    global _cache
    rates = {'input': int(input_rate), 'output': int(output_rate)}
    if any(rate <= 0 for rate in rates.values()):
        raise ValueError('Audio sample rates must be positive')
    with _selection_lock:
        if rates == _RATES:
            return
        _RATES.update(rates)
        _probe_results.clear()
        _chosen_api.update(input=None, output=None)
        with _cache_lock:
            _cache = None


def _usable(idx: int, kind: str) -> bool:
    """Can this device actually be opened at the rate we need?

    Deliberately opens a real stream rather than asking
    `check_output_settings`, because that function lies: it passed for an MME
    endpoint that then failed to open with "The specified format is not
    supported or cannot be translated" [MME error 32]. Opening and immediately
    closing costs milliseconds and is the only answer that holds."""
    st = None
    try:
        import sounddevice as sd
        rate = _RATES.get(kind, 16000)
        if kind == "input":
            st = sd.InputStream(samplerate=rate, channels=1, dtype="int16",
                                blocksize=1024, device=idx,
                                callback=lambda *_a: None)
        else:
            st = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16",
                                    blocksize=1024, device=idx)
        st.start()
        return True
    except Exception:
        return False
    finally:
        _close_stream(st)

# Aliases for "the default device" and internal routing endpoints. Matched
# case-insensitively as substrings against the device name.
_PSEUDO_DEVICES = (
    "sound mapper",        # Windows MME
    "primary sound",       # Windows DirectSound ("Primary Sound Capture Driver")
    "sysdefault",          # ALSA
    "default",             # ALSA / PulseAudio alias
    "dmix", "dsnoop",      # ALSA software mixing plugins
    "surround",            # ALSA channel-layout permutations of one card
    "samplerate", "speexrate", "upmix", "vdownmix", "null",
    "mapeador de som", "driver de som primário", "driver de captura de som primário",
)


def _is_pseudo(name: str) -> bool:
    low = _fold(name)
    return any(_fold(tok) in low for tok in _PSEUDO_DEVICES)


def _query() -> dict[str, list[str]]:
    with _selection_lock:
        return _query_devices()


def _query_devices() -> dict[str, list[str]]:
    """Return {'input': [names...], 'output': [names...]}. Never raises.

    Only real, selectable devices — see the note above."""
    out: dict[str, list[str]] = {"input": [], "output": []}
    try:
        import platform
        import sounddevice as sd

        devices = list(sd.query_devices())
        try:
            apis = [a.get("name", "") for a in sd.query_hostapis()]
        except Exception:
            apis = []

        preferred = _PREFERRED_APIS.get(platform.system(), ())

        def _collect(api_filter, kind) -> list[tuple[int, str]]:
            """(index, name) for named, non-pseudo devices on one side that can
            be opened at the rate that side runs at."""
            chan = "max_input_channels" if kind == "input" else "max_output_channels"
            found, seen = [], set()
            for idx, dev in enumerate(devices):
                name = (dev.get("name") or "").strip()
                if not name or _is_pseudo(name) or name in seen:
                    continue
                if dev.get(chan, 0) <= 0:
                    continue
                if api_filter is not None:
                    api_index = dev.get('hostapi', -1)
                    api = apis[api_index].lower() if 0 <= api_index < len(apis) else ''
                    if api_filter not in api:
                        continue
                if not _usable(idx, kind):
                    continue
                seen.add(name)
                found.append((idx, name))
            return found

        # Each direction picks its own host API. They are genuinely different
        # problems — on Windows the microphone works on DirectSound while the
        # speakers only work on MME — and a single global choice cannot be right
        # for both.
        for kind in ("input", "output"):
            _chosen_api[kind] = None
            for api_filter in list(preferred) + [None]:
                found = _collect(api_filter, kind)
                if not found:
                    continue
                # Probe every physical endpoint independently, on this worker.
                verified = [(idx, name) for idx, name in found
                            if _transport_works(idx, kind, (api_filter, kind, name))]
                if not verified:
                    continue
                _chosen_api[kind] = api_filter
                out[kind] = [_display_name(n, devices) for _i, n in verified]
                break
            if out[kind]:
                print(f"[Audio] {kind}: using "
                      f"{_chosen_api[kind] or 'any host API'} "
                      f"({len(out[kind])} devices)")
        return out

    except Exception as e:
        print(f"[Audio] Device enumeration failed: {e}")
    return out


def prefetch() -> None:
    """Warm the cache on a background thread. Called once at startup so the
    settings drawer never pays for enumeration on the Qt thread."""
    global _prefetching
    with _prefetch_lock:
        if _prefetching:
            return
        _prefetching = True
    def _work():
        global _prefetching
        try:
            inputs, outputs = list_devices('input'), list_devices('output')
            print(f'[Audio] {len(inputs)} input / {len(outputs)} output devices found')
        finally:
            with _prefetch_lock:
                _prefetching = False
    try:
        threading.Thread(target=_work, daemon=True, name="audio-devices").start()
    except Exception:
        with _prefetch_lock:
            _prefetching = False
        raise


def list_devices(kind: str, refresh: bool = False) -> list[str]:
    """Device names for 'input' or 'output'. Falls back to a synchronous query
    if the prefetch has not landed yet — correctness over the cache."""
    global _cache
    if kind not in ('input', 'output'):
        raise ValueError('Invalid audio direction')
    with _selection_lock:
        with _cache_lock:
            cached = None if refresh else _cache
        if cached is None:
            if refresh:
                _probe_results.clear()
            cached = _query()
            with _cache_lock:
                _cache = cached
    return list(cached.get(kind, []))


class AudioDeviceUnavailable(RuntimeError):
    pass


def resolve(name: str, kind: str, *, refresh=False, exclude=()):
    """Resolve default and named settings to a transport-verified physical ID.

    Missing named devices fall back to the OS default physical endpoint on a
    working host API. Never silently return an unverified device=None.
    """
    if kind not in ('input', 'output'):
        raise ValueError('Invalid audio direction')
    import platform
    import sounddevice as sd
    with _selection_lock:
        list_devices(kind, refresh=refresh)
        devices = list(sd.query_devices())
        apis = [a.get('name', '').lower() for a in sd.query_hostapis()]
        chan = 'max_input_channels' if kind == 'input' else 'max_output_channels'
        excluded = set(exclude)
        wanted = (name or '').strip()
        if wanted == DEFAULT_LABEL:
            wanted = ''
        requested = wanted
        if not wanted:
            try:
                index = int(sd.default.device[0 if kind == 'input' else 1])
                if index >= 0 and not _is_pseudo(devices[index]['name']):
                    wanted = _display_name(devices[index]['name'], devices)
            except (IndexError, TypeError, ValueError, KeyError):
                pass
        chosen = _chosen_api.get(kind)
        order = ([chosen] if chosen is not None else []) + [
            api for api in _PREFERRED_APIS.get(platform.system(), ()) if api != chosen] + [None]
        checked = set()

        def candidates(api_filter):
            rows = []
            for idx, dev in enumerate(devices):
                actual_name = (dev.get('name') or '').strip()
                api_idx = dev.get('hostapi', -1)
                api = apis[api_idx] if 0 <= api_idx < len(apis) else ''
                if (idx in excluded or dev.get(chan, 0) <= 0 or not actual_name
                        or _is_pseudo(actual_name) or (api_filter is not None and api_filter not in api)):
                    continue
                rows.append((idx, actual_name, _display_name(actual_name, devices), api))
            return rows

        def verified_match(target):
            for api_filter in order:
                rows = candidates(api_filter)
                exact = [r for r in rows if _fold(r[1]) == _fold(target) or _fold(r[2]) == _fold(target)] if target else rows
                partial = [r for r in rows if target and min(len(_fold(r[1])), len(_fold(target))) >= 16
                           and (_fold(r[1]).startswith(_fold(target)[:24]) or _fold(target).startswith(_fold(r[1])[:24]))]
                # Never guess between two similarly-named physical endpoints.
                matches = exact or (partial if len(partial) == 1 else [])
                for idx, actual_name, display_name, api in matches:
                    if idx in checked:
                        continue
                    checked.add(idx)
                    if _transport_works(idx, kind, (api_filter, kind, actual_name)):
                        print(f'[Audio] {kind} resolved: {display_name} [{api}] index={idx}')
                        return idx
            return None

        index = verified_match(wanted)
        if index is not None:
            return index
        if requested:
            print(f'[Audio] Saved {kind} endpoint unavailable; trying a verified default')
            return resolve('', kind, exclude=excluded)
        # The former default may have been unplugged; use a remaining verified
        # physical endpoint, preserving the chosen host-API preference.
        index = verified_match('')
        if index is not None:
            return index
        raise AudioDeviceUnavailable(f'Nenhum dispositivo de {kind} com transporte de áudio verificado')


# ─────────────────────────────────────────────────────────────────────────────
#  The one question automation cannot answer: is it hearing YOU?
# ─────────────────────────────────────────────────────────────────────────────
#
# Everything above decides whether a device can be OPENED and whether it moves
# audio, and it does that with silence so it can run at startup without anyone
# noticing. That is not the same question as "is my microphone picking up my
# voice", and it never will be: a muted mic, a level slider at zero, a headset
# boom pointing at the ceiling and a privacy shutter all pass every automated
# probe in this file and deliver nothing but a flat line.
#
# Only a person can answer that, by speaking. These two functions are what a
# TEST button in the settings panel calls — measure what actually arrives, and
# play something the user can confirm they heard.
#
# This began life as `ses_testi.py`, a loose script in the project root that
# nobody would ever find. It is here because the moment somebody needs it is
# the moment they have opened AUDIO DEVICES wondering why JINX cannot hear
# them.

# Below this peak, nothing usable arrived; below the second, speech is present
# but so quiet that recognition will struggle. Both are int16 sample values,
# taken from the levels a normal speaking voice produces at arm's length.
_SILENT_PEAK = 100
_QUIET_PEAK = 1500


def measure_input(name: str, seconds: float = 3.0, on_level=None) -> dict:
    """Record from one microphone and report what actually arrived.

    -> {"ok", "peak", "level", "verdict"} — `level` is 0.0-1.0 for a meter,
    `verdict` a short English sentence for the panel. Never raises: a device
    that cannot be opened is a result, not an exception, because the user is
    standing in front of the panel waiting for an answer either way.

    `on_level(0.0-1.0)` is called as the audio arrives, roughly twenty times a
    second, so the caller can move a meter WHILE the user is speaking.

    THE METER IS NOT DECORATION.
        The first version recorded for three seconds and then printed a
        verdict. Reported as "I saw no sign of anything, no level, no
        movement" — which is exactly right: three seconds of a static label
        reading "Speak now" is indistinguishable from a test that has hung.
        A person needs to see the thing respond to their voice to believe it
        is listening, and that is the entire point of the button.
    """
    peak_seen = [0]
    try:
        import numpy as np
        import sounddevice as sd
        idx = resolve(name, "input")

        rate = _RATES.get("input", 16000)

        def _cb(indata, _frames, _t, _status):
            samples = np.frombuffer(indata, dtype='int16').astype(np.int32)
            block = int(np.abs(samples).max()) if samples.size else 0
            if block > peak_seen[0]:
                peak_seen[0] = block
            if on_level is not None:
                try:
                    on_level(min(1.0, block / 12000.0))
                except Exception:
                    pass

        stream = sd.RawInputStream(samplerate=rate, channels=1, dtype="int16",
                                   blocksize=int(rate / 20), device=idx,
                                   callback=_cb)
        with stream:
            time.sleep(max(0.5, float(seconds)))
        peak = peak_seen[0]
    except Exception as e:
        return {"ok": False, "peak": 0, "level": 0.0,
                "verdict": f"Não foi possível abrir este microfone: {e}"}

    if peak < _SILENT_PEAK:
        verdict = ("Nenhum sinal recebido. O microfone pode estar mudo, com o "
                   "nível zerado ou não ser o dispositivo usado para falar.")
    elif peak < _QUIET_PEAK:
        verdict = ("Sinal muito baixo. O reconhecimento de fala pode falhar — "
                   "aumente o nível de entrada nas configurações de som do sistema.")
    else:
        verdict = "Sinal de áudio detectado. Confirme a transcrição falando com o JINX."

    return {"ok": peak >= _QUIET_PEAK, "peak": peak,
            "level": min(1.0, peak / 12000.0), "verdict": verdict}


def play_tone(name: str, seconds: float = 0.6) -> dict:
    """Play a short tone through one output so the user can confirm they hear it.

    -> {"ok", "verdict"}. There is no way to check this from software — the
    silent-sink probe above proves audio was CONSUMED, not that a speaker made
    a sound — so the answer comes from the person, and this only makes the
    sound for them to answer about.
    """
    stream = None
    try:
        import numpy as np
        import sounddevice as sd
        idx = resolve(name, "output")

        rate = _RATES.get("output", 24000)
        seconds = max(.2, min(2.0, float(seconds)))
        t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
        # 660 Hz, well inside every speaker's range and unmistakable against
        # room noise. Quiet enough not to startle somebody wearing headphones.
        tone = (np.sin(2 * np.pi * 660 * t) * 6000).astype(np.int16)
        ramp = min(len(tone) // 2, int(rate * .01))
        if ramp:
            tone[:ramp] = (tone[:ramp] * np.linspace(0, 1, ramp)).astype(np.int16)
            tone[-ramp:] = (tone[-ramp:] * np.linspace(1, 0, ramp)).astype(np.int16)
        stream = sd.RawOutputStream(samplerate=rate, channels=1, dtype='int16', blocksize=1024, device=idx)
        stream.start()
        stream.write(tone.tobytes())
        stream.stop()
    except Exception as e:
        return {"ok": False, "verdict": f"Não foi possível reproduzir o som neste dispositivo: {e}"}
    finally:
        _close_stream(stream)
    return {"ok": True, "heard_verified": False, "device_index": idx,
            "verdict": "Tom enviado à saída validada. Você conseguiu ouvi-lo?"}


# ─────────────────────────────────────────────────────────────────────────────
#  Output volume, so the panel can set it where the device is chosen
# ─────────────────────────────────────────────────────────────────────────────
#
# Choosing "Realtek(R) Audio" in this panel and then finding it far too quiet
# means going to the system sound settings, finding the same endpoint again and
# moving a slider there — reported as exactly that annoyance. The volume
# belongs beside the device it applies to.
#
# These delegate to actions/computer_settings, which already owns the
# per-platform volume plumbing and had a real bug in it (see
# _win_endpoint_volume there). One implementation, not two.

def _endpoint_for(name: str):
    """The Windows volume interface for ONE named output, or None.

    WHY THIS IS NOT JUST THE DEFAULT DEVICE
        The first version set the system's default endpoint, so moving the
        slider in this panel changed the volume of whichever output Windows
        happened to consider default — not the one chosen two lines above it.

        That is wrong in a way that matters to how people actually use this:
        somebody puts the assistant on their speakers and keeps everything else
        in their headphones, and a slider labelled with one device silently
        moving the other is worse than having no slider.

        It also explains a complaint that looked separate. The selected output
        here was sitting at 10% while the default endpoint was at 100% — so the
        assistant was almost inaudible, and the slider "fixed" it by turning up
        something the user could not hear either.

    Matching is by the name Windows itself reports, which is the same string
    sounddevice lists, folded so case and punctuation cannot separate them.
    """
    if _platform_is() != "Windows" or not name:
        return None
    try:
        from pycaw.pycaw import AudioUtilities
        wanted = _fold(name)
        if not wanted:
            return None

        # Collect first, decide after. An earlier version returned the first
        # candidate that matched on a PREFIX, which meant a loosely-similar
        # name could win over the exact one simply by coming first in the
        # enumeration — and the slider then moved a device the user had not
        # chosen. Exact wins, always; the prefix pass exists only because MME
        # truncates long names to 31 characters.
        exact, partial = None, None
        for dev in AudioUtilities.GetAllDevices():
            # ONLY ACTIVE ENDPOINTS, AND THIS IS NOT A TIDINESS FILTER.
            #
            # Windows keeps a record of hardware that is no longer here, and it
            # keeps the SAME FRIENDLY NAME. Measured on this machine, two
            # devices answered to "Hoparlör (Realtek(R) Audio)": one
            # NotPresent sitting at 100%, and the real one, Active, at 10%.
            # Matching by name alone returned whichever came first — so the
            # panel read 100% for a speaker that was actually at 10%, and
            # setting it moved a device that does not exist.
            try:
                if str(getattr(dev, "state", "")) != "AudioDeviceState.Active":
                    continue
            except Exception:
                continue
            try:
                # Reading this property activates a COM interface and raises
                # for devices that are unplugged or disabled — normal, and not
                # worth a line in the log for each one.
                endpoint = dev.EndpointVolume
            except Exception:
                continue
            if endpoint is None:
                continue
            try:
                friendly = _fold(getattr(dev, "FriendlyName", "") or "")
            except Exception:
                continue
            if not friendly:
                continue
            if friendly == wanted:
                exact = endpoint
                break
            if partial is None and (friendly.startswith(wanted[:24])
                                    or wanted.startswith(friendly[:24])):
                partial = endpoint
        return exact or partial
    except Exception as e:
        print(f"[Audio] per-device volume unavailable: {e}")
    return None


def _platform_is() -> str:
    import platform
    return platform.system()


def _fold(text: str) -> str:
    """Same reduction core/appidentity uses for application names — imported
    lazily so this module keeps working if that one is ever absent."""
    try:
        from core.appidentity import fold
        return fold(text)
    except Exception:
        return "".join(c for c in str(text or "").lower() if c.isalnum())


def get_output_volume(name: str = "") -> Optional[int]:
    """Volume 0-100 of ONE output, or of the system default when unnamed.

    None where the platform will not report it — macOS and Linux have no
    per-device volume through this plumbing, so a name there falls back to the
    master level rather than silently answering about the wrong device.
    """
    endpoint = _endpoint_for(name)
    if endpoint is not None:
        try:
            return max(0, min(100, round(
                endpoint.GetMasterVolumeLevelScalar() * 100)))
        except Exception as e:
            print(f"[Audio] could not read '{name}' volume: {e}")
    try:
        from actions.computer_settings import volume_get
        return volume_get()
    except Exception as e:
        print(f"[Audio] could not read the output volume: {e}")
        return None


def set_output_volume(percent: int, name: str = "") -> bool:
    """Set ONE output's volume 0-100. -> did it take.

    Falls back to the system master only when the named device cannot be
    reached, and says so, because silently moving a different device's volume
    is the bug this function exists to fix.
    """
    percent = max(0, min(100, int(percent)))
    endpoint = _endpoint_for(name)
    if endpoint is not None:
        try:
            endpoint.SetMasterVolumeLevelScalar(percent / 100.0, None)
            if percent > 0 and endpoint.GetMute():
                endpoint.SetMute(0, None)
            actual = round(endpoint.GetMasterVolumeLevelScalar() * 100)
            return abs(actual - percent) <= 3 and (percent == 0 or not endpoint.GetMute())
        except Exception as e:
            print(f"[Audio] could not set '{name}' volume: {e}")
    if name:
        print(f"[Audio] '{name}' has no separate volume control here — "
              f"setting the system level instead.")
    try:
        from actions.computer_settings import volume_set, volume_get
        volume_set(percent)
        now = volume_get()
        return now is not None and abs(now - percent) <= 3
    except Exception as e:
        print(f"[Audio] could not set the output volume: {e}")
        return False
