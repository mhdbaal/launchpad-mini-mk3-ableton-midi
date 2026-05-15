# Novation palette indices used by both step sequencers. The Programmer-mode
# color palette (raw integers 0-127) is part of the Launchpad firmware family —
# the same index lights the same color on Mini MK3 / Launchpad X / Pro MK3.
# Therefore these dicts live here, NOT in device_profile.py.
from __future__ import absolute_import, print_function, unicode_literals

from .programmer_mode import NOTE_ON_STATUS, PROGRAMMER_LED_CHANNEL


# Maps skin color names to raw Launchpad palette indices (0-127). Kept in sync
# with skin.py — when adding a new DrumSequencer.* color, update both.
DRUM_SEQUENCER_COLOR_VALUES = {
    "DefaultButton.Disabled": 0,
    "DrumSequencer.StepEmpty": 51,
    "DrumSequencer.StepBeat": 43,
    "DrumSequencer.StepActive": 29,
    "DrumSequencer.StepMuted": 84,
    # Velocity tiers (cold → hot). Kept in sync with skin.py constants.
    "DrumSequencer.StepVelGhost": 37,   # LIGHT_BLUE
    "DrumSequencer.StepVelSoft": 29,    # MINT
    "DrumSequencer.StepVelMedium": 96,  # AMBER
    "DrumSequencer.StepVelLoud": 97,    # YELLOW
    "DrumSequencer.StepHeld": 77,
    "DrumSequencer.Playhead": 21,
    "DrumSequencer.PlayheadActive": 3,
    "DrumSequencer.NoDrumRack": 7,
    "DrumSequencer.NoClip": 1,
    "DrumSequencer.NoteEmpty": 1,
    "DrumSequencer.NoteFilled": 43,
    "DrumSequencer.NoteSelected": 96,
    "DrumSequencer.Loop.Outside": 39,
    "DrumSequencer.Loop.Inside": 37,
    "DrumSequencer.Loop.Selected": 77,
    "DrumSequencer.Loop.Playhead": 21,
    "DrumSequencer.Loop.RangeEdit": 3,
    "DrumSequencer.Control.Page": 43,
    "DrumSequencer.Control.Octave": 21,
    "DrumSequencer.Control.Semitone": 29,
    "DrumSequencer.Control.Grid": 11,
    "DrumSequencer.Control.GridSelected": 3,
    "DrumSequencer.Control.Reset": 84,
    "DrumSequencer.Control.Shift": 96,
    "DrumSequencer.Control.CaptureMidi": 27,        # GREEN_HALF (dim until capturable)
    "DrumSequencer.Control.CaptureMidiReady": 21,   # GREEN
    "DrumSequencer.Control.Quantize": 77,           # AQUA
    "DrumSequencer.Control.CycleLoop": 77,          # AQUA (bottom-right = loop)
    "DrumSequencer.Control.CycleGrid": 9,           # ORANGE (bottom-right = grid)
    "DrumSequencer.Control.GridTernary": 53,        # PURPLE (ternary cells dim)
}

MELODIC_COLOR_VALUES = {
    "DefaultButton.Disabled": 0,
    "MelodicSequencer.StepEmpty": 51,
    "MelodicSequencer.StepBeat": 43,
    "MelodicSequencer.StepActive": 29,
    # Velocity tiers (in sync with skin.py). 4 ranges, cold → hot.
    "MelodicSequencer.StepVelGhost": 37,    # LIGHT_BLUE
    "MelodicSequencer.StepVelSoft": 29,     # MINT
    "MelodicSequencer.StepVelMedium": 96,   # AMBER
    "MelodicSequencer.StepVelLoud": 97,     # YELLOW
    "MelodicSequencer.Root": 96,
    "MelodicSequencer.Playhead": 21,
    "MelodicSequencer.PlayheadActive": 3,
    "MelodicSequencer.NoClip": 1,
    "MelodicSequencer.Loop.Outside": 1,
    "MelodicSequencer.Loop.Inside": 43,
    "MelodicSequencer.Loop.Selected": 96,
    "MelodicSequencer.Loop.Playhead": 21,
    "MelodicSequencer.Loop.RangeEdit": 1,
    "MelodicSequencer.Preview.Off": 41,
    "MelodicSequencer.Preview.On": 96,
    "MelodicSequencer.Control.Page": 43,
    "MelodicSequencer.Control.Octave": 21,
    "MelodicSequencer.Control.Semitone": 29,
    "MelodicSequencer.Control.Grid": 11,
    "MelodicSequencer.Control.GridSelected": 3,
    "MelodicSequencer.Control.ScaleCycle": 77,
    "MelodicSequencer.Control.Reset": 84,
    "MelodicSequencer.Control.Shift": 96,
    "MelodicSequencer.Control.CaptureMidi": 27,
    "MelodicSequencer.Control.CaptureMidiReady": 21,
    "MelodicSequencer.Control.Quantize": 77,
    "MelodicSequencer.Control.CycleLoop": 77,           # AQUA (default pitch mode)
    "MelodicSequencer.Control.CycleGrid": 9,            # ORANGE (grid resolution mode)
    "MelodicSequencer.Control.GridTernary": 53,         # PURPLE (ternary cells dim)
    "MelodicSequencer.StepHeld": 96,
}


def send_pad_color(parent, button, color, palette):
    """Light a single pad with a skin-named color in Programmer mode.

    Writes a Note On (status NOTE_ON_STATUS + PROGRAMMER_LED_CHANNEL) on the
    pad's wire-level note. Falls back to the framework's send_value path if
    the parent's raw _send_midi fails (e.g. during teardown).

    Returns (note, color_value) so callers can log the actual write — useful
    for debug counters that exist per-sequencer with its own log tag.
    """
    color_value = palette.get(color, 0)
    note = button.original_identifier()
    status = NOTE_ON_STATUS + PROGRAMMER_LED_CHANNEL
    try:
        parent._send_midi((status, note, color_value), optimized=False)
    except Exception:
        try:
            button.send_value(color_value, force=True, channel=PROGRAMMER_LED_CHANNEL)
        except Exception:
            pass
    return note, color_value
