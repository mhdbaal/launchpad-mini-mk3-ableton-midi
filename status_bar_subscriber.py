from __future__ import absolute_import, print_function, unicode_literals

from .events import Event


_MODE_LABELS = {
    "session":          "Session",
    "drum_sequence":    "Drum Sequencer",
    "melodic_sequence": "Melodic Sequencer",
}

_ERR_MODE_PREFIX = {
    "drum":    "Drum Sequencer",
    "melodic": "Melodic Sequencer",
}


def _fmt_page_range(prefix, p):
    start, end = p["start"], p["end"]
    if start == end:
        return "{} page {} scoped".format(prefix, start)
    return "{} pages {}-{} scoped".format(prefix, start, end)


_FORMATTERS = {
    Event.MAIN_MODE_CHANGED:
        lambda p: "Launchpad Mini MK3: {}".format(_MODE_LABELS.get(p["mode"], p["mode"])),

    Event.SHIFT_LOCK_CHANGED:
        lambda p: "Shift {}".format("LOCKED" if p["locked"] else "unlocked"),

    Event.DRUM_PAGE_SCOPED:
        lambda p: _fmt_page_range("Drum", p),
    Event.DRUM_STEP_LOOP_SCOPED:
        lambda p: ("Drum loop: page {}, step {} ({})".format(
                       p["page"], p["start_step"], p["label"])
                   if p["start_step"] == p["end_step"]
                   else "Drum loop: page {}, steps {}-{} ({})".format(
                       p["page"], p["start_step"], p["end_step"], p["label"])),
    Event.DRUM_GRID_CHANGED:
        lambda p: "Drum grid: {}".format(p["label"]),
    Event.DRUM_TRIPLET_CHANGED:
        lambda p: "Triplet {} ({})".format("ON" if p["on"] else "OFF", p["label"]),
    Event.DRUM_VELOCITY_CHANGED:
        lambda p: "Velocity: {}".format(p["velocity"]),
    Event.DRUM_NOTE_LENGTH_CHANGED:
        lambda p: ("Length: {} step{} (page {}, step {})".format(
            p["length_steps"], "" if p["length_steps"] == 1 else "s",
            p["page"], p["anchor_step"])),
    Event.DRUM_NOTE_NUDGED:
        lambda p: "Nudge {:+.3f} beat → {:.3f}".format(p["delta_beats"], p["start_time"]),
    Event.DRUM_NOTES_QUANTIZED:
        lambda p: ("Quantize: nothing to move ({})".format(p["grid"]) if p["count"] == 0
                   else "Quantize: {} note{} {} → {}".format(
                       p["count"], "" if p["count"] == 1 else "s",
                       p["scope"], p["grid"])),
    Event.MIDI_CAPTURED:
        lambda p: ("Capture MIDI: clip created" if p["ok"]
                   else "Capture MIDI: {}".format(p.get("reason", "unavailable"))),
    Event.DRUM_BOTTOM_RIGHT_MODE:
        lambda p: "Bottom-right: {} selector".format(p["mode"]),
    Event.MELODIC_BOTTOM_RIGHT_MODE:
        lambda p: "Bottom-right: {} selector".format(p["mode"]),
    Event.DRUM_NAV_CHANGED:
        lambda p: "Drum grid {} | page {} | octave {:+d} | semitone {:+d}".format(
            p["label"], p["page"], p["octave"], p["semitone"]),

    Event.MELODIC_PAGE_SCOPED:
        lambda p: _fmt_page_range("Melodic", p),
    Event.MELODIC_STEP_LOOP_SCOPED:
        lambda p: ("Melodic loop: page {}, step {} ({})".format(
                       p["page"], p["start_step"], p["label"])
                   if p["start_step"] == p["end_step"]
                   else "Melodic loop: page {}, steps {}-{} ({})".format(
                       p["page"], p["start_step"], p["end_step"], p["label"])),
    Event.MELODIC_GRID_CHANGED:
        lambda p: "Melodic grid: {}".format(p["label"]),
    Event.MELODIC_TRIPLET_CHANGED:
        lambda p: "Triplet {} ({})".format("ON" if p["on"] else "OFF", p["label"]),
    Event.MELODIC_SCALE_CHANGED:
        lambda p: "Scale: {}".format(p["scale_name"]),
    Event.MELODIC_CHROMATIC_MODE:
        lambda p: "Chromatic {} (mode: {})".format(
            "ON" if p["on"] else "OFF",
            "chromatic" if p["on"] else "scale"),
    Event.MELODIC_PREVIEW_MODE:
        lambda p: "Melodic Sequencer: {}".format("preview" if p["on"] else "piano roll"),
    Event.MELODIC_NAV_CHANGED:
        lambda p: "Melodic grid {} | page {} | octave {:+d} | semitone {:+d}".format(
            p["label"], p["page"], p["octave"], p["semitone"]),
    Event.MELODIC_VELOCITY_CHANGED:
        lambda p: "Velocity: {}".format(p["velocity"]),
    Event.MELODIC_NOTES_QUANTIZED:
        lambda p: ("Quantize: nothing to move ({})".format(p["grid"]) if p["count"] == 0
                   else "Quantize: {} note{} {} → {}".format(
                       p["count"], "" if p["count"] == 1 else "s",
                       p["scope"], p["grid"])),

    Event.ERR_NEED_MIDI_SLOT:
        lambda p: "{}: select a MIDI clip slot".format(_ERR_MODE_PREFIX.get(p["mode"], p["mode"])),
    Event.ERR_NEED_MIDI_TRACK:
        lambda p: "{}: select a MIDI track".format(_ERR_MODE_PREFIX.get(p["mode"], p["mode"])),
    Event.ERR_NOT_MIDI:
        lambda p: "{}: selected clip is not MIDI".format(_ERR_MODE_PREFIX.get(p["mode"], p["mode"])),
}


class StatusBarSubscriber(object):
    """Translates events into strings and pushes them to Live's status bar.

    This is the single owner of every user-visible message text in the
    script. To rename a label, edit `_FORMATTERS` here; no other file
    knows about wording.
    """

    def __init__(self, show_message):
        self._show = show_message

    def __call__(self, name, payload):
        formatter = _FORMATTERS.get(name)
        if formatter is None:
            return
        try:
            self._show(formatter(payload))
        except Exception:
            # A bad payload shouldn't crash other subscribers — the bus
            # already shields us, but stay defensive on the formatter too.
            pass
