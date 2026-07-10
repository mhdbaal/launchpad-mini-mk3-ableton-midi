from __future__ import absolute_import, print_function, unicode_literals

from ableton.v2.base import liveobj_valid


DEVICE_NAME = "LP Notify"

# Parameter names expected on the Max for Live device. The .amxd must expose
# each `live.numbox` / `live.toggle` with these "Long Name" values via the
# Inspector → Parameter Visibility (Stored Only or Automation). The script
# resolves them by name match on `device.parameters[i].name`.
PARAM_MSG_ID  = "msg_id"
PARAM_ARG1    = "arg1"
PARAM_ARG2    = "arg2"
PARAM_ARG3    = "arg3"
PARAM_SEQ     = "seq"
PARAM_ENABLED = "enabled"

_REQUIRED_PARAMS = (PARAM_MSG_ID, PARAM_ARG1, PARAM_ARG2, PARAM_ARG3, PARAM_SEQ)


class NotificationDispatcher(object):
    """Locates the LP Notify Max for Live device on any track and writes
    parameters on it to push notification events.

    Discovery scans all regular tracks + return tracks + master at startup
    and refreshes on add/remove/rename. First device matching `DEVICE_NAME`
    wins; subsequent ones are ignored (with a warning).

    `is_ready()` is True only when the device is bound AND every required
    parameter resolves. Otherwise `send()` is a no-op — the rest of the
    script (status bar fallback) keeps working unchanged.
    """

    def __init__(self, song, logger=None):
        self._song = song
        self._logger = logger
        self._device = None
        self._params = {}  # name -> parameter ref
        self._seq = 0

        # Listener bookkeeping. Stored as (subject, listener_callable) tuples
        # so we can detach each one in disconnect().
        self._track_devices_listeners = []   # [(track, listener)]
        self._device_name_listener = None    # (device, listener)
        self._tracks_listener = self._on_tracks_changed
        self._return_tracks_listener = self._on_tracks_changed

        self._attach_song_listeners()
        self._scan()

    # ---- public API -----------------------------------------------------

    def is_ready(self):
        if not liveobj_valid(self._device):
            return False
        return all(name in self._params for name in _REQUIRED_PARAMS)

    def send(self, msg_id, arg1=0, arg2=0, arg3=0):
        if not self.is_ready():
            return
        if not self._enabled_flag():
            return
        # Write args before bumping seq so the live.observer on `seq` sees
        # consistent values when it fires on the Max side.
        self._set(PARAM_MSG_ID, msg_id)
        self._set(PARAM_ARG1, arg1)
        self._set(PARAM_ARG2, arg2)
        self._set(PARAM_ARG3, arg3)
        self._seq = (self._seq + 1) & 0x7F
        self._set(PARAM_SEQ, self._seq)

    def disconnect(self):
        """Detach every Live listener so the script can be reloaded cleanly."""
        self._detach_device()
        self._detach_track_device_listeners()
        try:
            self._song.remove_tracks_listener(self._tracks_listener)
        except Exception:
            pass
        try:
            self._song.remove_return_tracks_listener(self._return_tracks_listener)
        except Exception:
            pass

    # ---- internals: scanning & binding ---------------------------------

    def _all_tracks(self):
        tracks = []
        try:
            tracks.extend(self._song.tracks)
        except Exception:
            pass
        try:
            tracks.extend(self._song.return_tracks)
        except Exception:
            pass
        try:
            master = self._song.master_track
            if liveobj_valid(master):
                tracks.append(master)
        except Exception:
            pass
        return tracks

    def _scan(self):
        """Re-attach per-track device listeners and find the first matching device."""
        self._detach_track_device_listeners()
        found = None
        duplicate_count = 0
        for track in self._all_tracks():
            self._attach_track_devices_listener(track)
            if found is None:
                match = self._find_device_in_track(track)
                if match is not None:
                    found = match
            else:
                if self._find_device_in_track(track) is not None:
                    duplicate_count += 1

        if duplicate_count > 0:
            self._log("warning: {} additional '{}' device(s) ignored".format(
                duplicate_count, DEVICE_NAME))

        if found is self._device:
            return
        self._bind_device(found)

    def _find_device_in_track(self, track):
        if not liveobj_valid(track):
            return None
        try:
            devices = track.devices
        except Exception:
            return None
        for device in devices:
            if liveobj_valid(device) and getattr(device, "name", None) == DEVICE_NAME:
                return device
        return None

    def _bind_device(self, device):
        self._detach_device()
        self._params = {}
        self._device = device
        if device is None:
            self._log("notification device lost")
            return
        self._attach_device_name_listener(device)
        # Resolve parameter refs by name.
        bound = []
        missing = []
        try:
            parameters = device.parameters
        except Exception:
            parameters = []
        wanted = set(_REQUIRED_PARAMS) | {PARAM_ENABLED}
        for param in parameters:
            try:
                pname = param.name
            except Exception:
                continue
            if pname in wanted:
                self._params[pname] = param
                bound.append(pname)
        for required in _REQUIRED_PARAMS:
            if required not in self._params:
                missing.append(required)
        track_name = self._device_track_name(device)
        if missing:
            self._log("notification device found on track '{}' "
                      "but missing parameters: {}".format(track_name, missing))
        else:
            self._log("notification device found on track '{}' "
                      "(bound: {})".format(track_name, bound))

    def _device_track_name(self, device):
        try:
            chain = device.canonical_parent
            if liveobj_valid(chain):
                track = chain.canonical_parent
                if liveobj_valid(track):
                    return getattr(track, "name", "<?>")
        except Exception:
            pass
        return "<unknown>"

    # ---- internals: listeners ------------------------------------------

    def _attach_song_listeners(self):
        try:
            self._song.add_tracks_listener(self._tracks_listener)
        except Exception:
            pass
        try:
            self._song.add_return_tracks_listener(self._return_tracks_listener)
        except Exception:
            pass

    def _attach_track_devices_listener(self, track):
        if not liveobj_valid(track):
            return
        listener = self._make_track_devices_listener(track)
        try:
            track.add_devices_listener(listener)
            self._track_devices_listeners.append((track, listener))
        except Exception:
            pass

    def _make_track_devices_listener(self, track):
        def listener():
            self._on_track_devices_changed(track)
        return listener

    def _detach_track_device_listeners(self):
        for track, listener in self._track_devices_listeners:
            try:
                track.remove_devices_listener(listener)
            except Exception:
                pass
        self._track_devices_listeners = []

    def _attach_device_name_listener(self, device):
        listener = self._on_device_name_changed
        try:
            device.add_name_listener(listener)
            self._device_name_listener = (device, listener)
        except Exception:
            self._device_name_listener = None

    def _detach_device(self):
        if self._device_name_listener is not None:
            device, listener = self._device_name_listener
            try:
                device.remove_name_listener(listener)
            except Exception:
                pass
            self._device_name_listener = None
        self._device = None
        self._params = {}

    def _on_tracks_changed(self):
        self._scan()

    def _on_track_devices_changed(self, track):
        # Don't try to be clever — a device add/remove anywhere can change
        # which "LP Notify" wins (or whether the bound one was removed).
        self._scan()

    def _on_device_name_changed(self):
        # User renamed the bound device away from DEVICE_NAME → it stops
        # being a match. Also catches renames TO DEVICE_NAME on something
        # we'd already passed over.
        self._scan()

    # ---- internals: parameter writes -----------------------------------

    def _set(self, name, value):
        param = self._params.get(name)
        if param is None:
            return
        try:
            v = float(value)
            try:
                v = max(param.min, min(param.max, v))
            except Exception:
                pass
            param.value = v
        except Exception:
            pass

    def _enabled_flag(self):
        param = self._params.get(PARAM_ENABLED)
        if param is None:
            return True  # absent param = treat as enabled by default
        try:
            return float(param.value) >= 0.5
        except Exception:
            return True

    def _log(self, message):
        if self._logger is not None:
            try:
                self._logger("[NotificationDispatcher] {}".format(message))
            except Exception:
                pass
