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
    # 64-step mode reuses MODE_DRUM_SEQ on the wire — the .amxd treats both as
    # "drum" for ambient lighting / labels. Add a dedicated wire ID later if
    # the patch needs to distinguish.
    "drum_64_sequence": Msg.MODE_DRUM_SEQ,
    # 4-track mode also reuses MODE_DRUM_SEQ on the wire — same rationale.
    "drum_4_track_sequence": Msg.MODE_DRUM_SEQ,
    "chord_mode":       Msg.MODE_CHORD,
}

_MATRIX_MODE_IDS = {
    "edit":      0,
    "loop_pick": 1,
    "grid_pick": 2,
}

_ERR_MODE_IDS = {
    "drum":    MODE_ID_DRUM,
    "melodic": MODE_ID_MELODIC,
}

# Track-pin events carry the full main-mode key (drum_sequence / melodic_sequence
# / ...). The M4L wire format only has two mode discriminators today, so collapse
# all drum variants onto MODE_ID_DRUM. Add finer-grained IDs to the catalog if a
# future .amxd needs to distinguish them.
_PIN_MODE_IDS = {
    "drum_sequence":         MODE_ID_DRUM,
    "drum_64_sequence":      MODE_ID_DRUM,
    "drum_4_track_sequence": MODE_ID_DRUM,
    "melodic_sequence":      MODE_ID_MELODIC,
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
    Event.DRUM_64_MATRIX_MODE:
        lambda p: (Msg.DRUM_64_MATRIX_MODE,
                   (_MATRIX_MODE_IDS.get(p["mode"], 0),)),
    Event.DRUM_4_TRACK_MATRIX_MODE:
        lambda p: (Msg.DRUM_4_TRACK_MATRIX_MODE,
                   (_MATRIX_MODE_IDS.get(p["mode"], 0),)),
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
    Event.MELODIC_VELOCITY_CHANGED:
        lambda p: (Msg.MELODIC_VELOCITY, (p["velocity"],)),

    Event.CHORD_KEY_CHANGED:
        lambda p: (Msg.CHORD_KEY, (p["key_index"],)),
    Event.CHORD_SCALE_CHANGED:
        lambda p: (Msg.CHORD_SCALE, (p["scale_index"],)),
    Event.CHORD_TYPE_CHANGED:
        lambda p: (Msg.CHORD_TYPE, (p["type_index"],)),
    Event.CHORD_INVERSION_CHANGED:
        lambda p: (Msg.CHORD_INVERSION, (p["inversion"],)),
    Event.CHORD_NAV_CHANGED:
        lambda p: (Msg.CHORD_NAV, (p["octave"], p["semitone"])),
    # CHORD_TRIGGERED / RELEASED are NOT mapped here — see the comment in
    # notification_catalog.py beside the CHORD_* IDs. Variable-length
    # chord_pitches don't fit the 3-arg wire format.

    Event.EDIT_MODE_CHANGED:
        lambda p: (Msg.EDIT_MODE_ON if p["on"] else Msg.EDIT_MODE_OFF, ()),
    Event.EDIT_CLIP_DELETED:
        lambda p: (Msg.EDIT_CLIP_DELETED, (p["track"], p["scene"])),
    Event.EDIT_CLIP_DUPLICATED:
        lambda p: (Msg.EDIT_CLIP_DUPLICATED, (p["track"], p["scene"])),
    # Clip move carries 4 indices, more than the wire format's 3 packed
    # ints. Send the IDs alone — the .amxd can drive UI on the event
    # itself without needing the coords. Add a dedicated wire ID if a
    # future patch needs the full from/to.
    Event.EDIT_CLIP_MOVED:
        lambda p: (Msg.EDIT_CLIP_MOVED, ()),
    Event.EDIT_SCENE_DELETED:
        lambda p: (Msg.EDIT_SCENE_DELETED, (p["scene"],)),
    Event.EDIT_SCENE_DUPLICATED:
        lambda p: (Msg.EDIT_SCENE_DUPLICATED, (p["scene"],)),
    Event.EDIT_MOVE_SOURCE_SET:
        lambda p: (Msg.EDIT_MOVE_SOURCE_SET,
                   (0 if p["kind"] == "clip" else 1,)),
    Event.EDIT_MOVE_CANCELLED:
        lambda p: (Msg.EDIT_MOVE_CANCELLED, ()),
    Event.EDIT_CLIP_COLOR_CYCLED:
        lambda p: (Msg.EDIT_CLIP_COLOR_CYCLED,
                   (p["track"], p["scene"], p["color_index"])),
    Event.EDIT_SCENE_COLOR_CYCLED:
        lambda p: (Msg.EDIT_SCENE_COLOR_CYCLED,
                   (p["scene"], p["color_index"])),
    Event.EDIT_STOP_ALL_CLIPS:
        lambda p: (Msg.EDIT_STOP_ALL_CLIPS, ()),
    Event.EDIT_UNDO:
        lambda p: (Msg.EDIT_UNDO, ()),
    Event.EDIT_REDO:
        lambda p: (Msg.EDIT_REDO, ()),

    Event.ERR_NEED_MIDI_SLOT:
        lambda p: (Msg.ERR_NEED_MIDI_SLOT, (_ERR_MODE_IDS.get(p["mode"], 0),)),
    Event.ERR_NEED_MIDI_TRACK:
        lambda p: (Msg.ERR_NEED_MIDI_TRACK, (_ERR_MODE_IDS.get(p["mode"], 0),)),
    Event.ERR_NOT_MIDI:
        lambda p: (Msg.ERR_NOT_MIDI, (_ERR_MODE_IDS.get(p["mode"], 0),)),

    Event.TRACK_PINNED:
        lambda p: (Msg.TRACK_PINNED, (_PIN_MODE_IDS.get(p["mode"], 0),)),
    Event.TRACK_UNPINNED:
        lambda p: (Msg.TRACK_UNPINNED, (_PIN_MODE_IDS.get(p["mode"], 0),)),
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
