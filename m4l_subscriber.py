from __future__ import absolute_import, print_function, unicode_literals

from .events import Event
from .notification_catalog import (
    Msg,
    GRID_RESOLUTION_INDICES,
    MODE_ID_DRUM,
    MODE_ID_MELODIC,
)


_MAIN_MODE_MSG_IDS = {
    "session":          Msg.MODE_SESSION,
    "drum_sequence":    Msg.MODE_DRUM_SEQ,
    "melodic_sequence": Msg.MODE_MELODIC_SEQ,
}

_ERR_MODE_IDS = {
    "drum":    MODE_ID_DRUM,
    "melodic": MODE_ID_MELODIC,
}


def _grid_index(label):
    """Strip the trailing 't' (triplet marker) and look up the base index.
    Returns 0 if the label isn't recognized — keeps the subscriber tolerant.
    """
    base = label[:-1] if label.endswith("t") else label
    return GRID_RESOLUTION_INDICES.get(base, 0)


def _drum_page(p):
    if p["start"] == p["end"]:
        return (Msg.DRUM_PAGE_SCOPED, (p["start"],))
    return (Msg.DRUM_PAGE_RANGE, (p["start"], p["end"]))


def _melodic_page(p):
    if p["start"] == p["end"]:
        return (Msg.MELODIC_PAGE_SCOPED, (p["start"],))
    return (Msg.MELODIC_PAGE_RANGE, (p["start"], p["end"]))


_MAPPING = {
    Event.MAIN_MODE_CHANGED:
        lambda p: (_MAIN_MODE_MSG_IDS.get(p["mode"], Msg.MODE_SESSION), ()),

    Event.SHIFT_LOCK_CHANGED:
        lambda p: (Msg.SHIFT_LOCKED if p["locked"] else Msg.SHIFT_UNLOCKED, ()),

    Event.DRUM_PAGE_SCOPED:
        _drum_page,
    Event.DRUM_GRID_CHANGED:
        lambda p: (Msg.DRUM_GRID, (_grid_index(p["label"]), int(bool(p["is_triplet"])))),
    Event.DRUM_TRIPLET_CHANGED:
        lambda p: (Msg.DRUM_TRIPLET, (int(bool(p["on"])),)),
    Event.DRUM_VELOCITY_CHANGED:
        lambda p: (Msg.DRUM_VELOCITY, (p["velocity"],)),
    # Note: Msg.DRUM_BOTTOM_RIGHT (25) is now an unused wire ID — the
    # bottom-right velocity mode was removed. Catalog stays append-only.
    Event.DRUM_NAV_CHANGED:
        lambda p: (Msg.DRUM_NAV, (p["page"], p["octave"], p["semitone"])),

    Event.MELODIC_PAGE_SCOPED:
        _melodic_page,
    Event.MELODIC_GRID_CHANGED:
        lambda p: (Msg.MELODIC_GRID, (_grid_index(p["label"]), int(bool(p["is_triplet"])))),
    Event.MELODIC_TRIPLET_CHANGED:
        lambda p: (Msg.MELODIC_TRIPLET, (int(bool(p["on"])),)),
    Event.MELODIC_SCALE_CHANGED:
        lambda p: (Msg.MELODIC_SCALE, (p["scale_index"],)),
    Event.MELODIC_CHROMATIC_MODE:
        lambda p: (Msg.MELODIC_CHROMATIC, (int(bool(p["on"])),)),
    Event.MELODIC_PREVIEW_MODE:
        lambda p: (Msg.MELODIC_PREVIEW, (int(bool(p["on"])),)),
    Event.MELODIC_NAV_CHANGED:
        lambda p: (Msg.MELODIC_NAV, (p["page"], p["octave"], p["semitone"])),

    Event.ERR_NEED_MIDI_SLOT:
        lambda p: (Msg.ERR_NEED_MIDI_SLOT, (_ERR_MODE_IDS.get(p["mode"], 0),)),
    Event.ERR_NEED_MIDI_TRACK:
        lambda p: (Msg.ERR_NEED_MIDI_TRACK, (_ERR_MODE_IDS.get(p["mode"], 0),)),
    Event.ERR_NOT_MIDI:
        lambda p: (Msg.ERR_NOT_MIDI, (_ERR_MODE_IDS.get(p["mode"], 0),)),
}


class M4LSubscriber(object):
    """Translates events into (msg_id, args) and forwards to the dispatcher.

    No-ops when the dispatcher isn't ready (no device found, missing params,
    or `enabled` flag off on the device). That's the layer that makes the
    rest of the script work identically with or without an LP Notify device
    posed in the set.
    """

    def __init__(self, dispatcher):
        self._dispatcher = dispatcher

    def __call__(self, name, payload):
        if not self._dispatcher.is_ready():
            return
        mapping = _MAPPING.get(name)
        if mapping is None:
            return
        try:
            msg_id, args = mapping(payload)
        except Exception:
            return
        self._dispatcher.send(msg_id, *args)
