# Novation palette indices used by both step sequencers. The Programmer-mode
# color palette (raw integers 0-127) is part of the Launchpad firmware family —
# the same index lights the same color on Mini MK3 / Launchpad X / Pro MK3.
# Therefore these dicts live here, NOT in device_profile.py.
from __future__ import absolute_import, print_function, unicode_literals

from novation import sysex

from .device_profile import DEVICE_SYSEX_ID
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
    "DrumSequencer.NotePlaying": 21,        # GREEN (live note hitting at playhead)
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
    "DrumSequencer.Control.ShiftIdle": 14,          # AMBER_HALF (dim anchor)
    "DrumSequencer.Control.CaptureMidi": 27,        # GREEN_HALF (dim until capturable)
    "DrumSequencer.Control.CaptureMidiReady": 21,   # GREEN
    "DrumSequencer.Control.Quantize": 77,           # AQUA
    "DrumSequencer.Control.CycleLoop": 77,          # AQUA (bottom-right = loop)
    "DrumSequencer.Control.CycleGrid": 9,           # ORANGE (bottom-right = grid)
    "DrumSequencer.Control.DuplicatePage": 125,     # YELLOW_HALF (modifier idle)
    "DrumSequencer.Control.DuplicatePageHeld": 97,  # YELLOW (modifier held)
    "DrumSequencer.Control.DoubleLoop": 53,         # PURPLE (single-tap action)
    "DrumSequencer.Control.SpecialDelete": 5,            # RED
    "DrumSequencer.Control.SpecialDeleteHalf": 7,        # RED_HALF
    "DrumSequencer.Control.SpecialDuplicate": 21,        # GREEN
    "DrumSequencer.Control.SpecialDuplicateHalf": 27,    # GREEN_HALF
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


# Chord-pad mode palette. Kept in sync with skin.py's Colors.ChordPad — when
# adding a ChordPad.* color, update both. Mode-button (User button) LED is
# driven from device_profile.LED_CHORD instead of this dict; that's a CC
# write rather than a pad-color Note On, so it doesn't go through the skin.
CHORD_COLOR_VALUES = {
    "DefaultButton.Disabled": 0,
    "ChordPad.Root": 96,           # AMBER
    "ChordPad.RootDim": 14,        # AMBER_HALF
    "ChordPad.ChordTone": 41,      # BLUE
    "ChordPad.ChordToneDim": 43,   # BLUE_HALF
    "ChordPad.ScaleTone": 27,      # GREEN_HALF
    "ChordPad.ScaleToneDim": 1,    # DARK_GREY (just barely lit)
    "ChordPad.Pressed": 3,         # WHITE
    "ChordPad.Control.CaptureMidi": 27,        # GREEN_HALF (dim until capturable)
    "ChordPad.Control.CaptureMidiReady": 21,   # GREEN (capture possible)
    "ChordPad.Control.Key": 96,                # AMBER
    "ChordPad.Control.Scale": 77,              # AQUA — same as MelodicSequencer.ScaleCycle
    "ChordPad.Control.ChordType": 53,          # PURPLE — same as mode-button LED
    "ChordPad.Control.Inversion": 97,          # YELLOW
    "ChordPad.Control.Shift": 96,              # AMBER (seq-shift held feedback)
}


# Step-hold velocity selector: 16 raw palette indices forming a cool→hot ramp.
# Indices are firmware-standard (same on every Launchpad), so this tuple is
# device-agnostic. Used by both drum and melodic sequencers when rendering the
# velocity-bar overlay. Order matches the user-facing read order: index 0 in
# the tuple = level 1 (lowest), index 15 = level 16 (loudest).
VELOCITY_LEVEL_PALETTE = (
    21,  # 1  GREEN
    21,  # 2  GREEN
    21,  # 3  GREEN
    29,  # 4  MINT
    29,  # 5  MINT
    96,  # 6  AMBER
    96,  # 7  AMBER
    97,  # 8  YELLOW
    97,  # 9  YELLOW
    9,   # 10 ORANGE
    9,   # 11 ORANGE
    5,   # 12 RED
    5,   # 13 RED
    5,   # 14 RED
    5,   # 15 RED
    3,   # 16 WHITE (peak)
)
VELOCITY_LEVEL_DIM = 1  # DARK_GREY, used for pads above the current level.


# --------------------------------------------------------------- RGB SysEx
#
# Beyond the 128-index firmware palette, Launchpads accept an explicit RGB
# value per LED:
#
#   F0h 00h 20h 29h 02h <device id> 03h  <spec> [<spec> ...]  F7h
#   <spec> = 03h <LED index> <R> <G> <B>        (0-127 per channel)
#
# Two reasons to use it over the palette:
#   - The palette only offers 4 shades per hue (indices 4n..4n+3) and they are
#     unevenly spaced, so a monotonic velocity ramp of more than ~3 steps is
#     not possible. RGB gives as many even shades of one hue as we want.
#   - Several specs ride in ONE message, so a full grid repaint is a single
#     SysEx instead of 64 Note On messages.
#
# The device id comes from the overlay's device_profile (13 Mini / 14 Pro);
# install.sh assembles the right one next to this file.
#
# NOTE: command byte 03h is shared with print-to-clip (`… 0Eh 03h <v> F7h`),
# which is a DEVICE→HOST message the Pro only sends when print-to-clip is
# enabled. Our elements never create that element, so there is no collision.
RGB_SYSEX_COMMAND_BYTE = 3
RGB_SPEC_TYPE = 3
RGB_MAX = 127
# The reference caps a message at 106 specs; a full 8x8 grid is well under.
RGB_MAX_SPECS_PER_MESSAGE = 64


# Neutral greys for everything that is NOT content. Keeping "absence" on a
# grey ramp and "presence" on the clip hue is what makes the surface readable
# at a glance: a coloured pad always means something is there.
GREY_EMPTY = (4, 4, 4)        # nothing here
GREY_DIM = (12, 12, 12)       # structural marker (beat, available option)
GREY_MID = (30, 30, 30)       # landmark (root row, ternary option)
GREY_BRIGHT = (64, 64, 64)    # playhead over empty space
RGB_WHITE = (127, 127, 127)   # "now" / selected / held
RGB_BLACK = (0, 0, 0)


def rgb_shades(color_int, levels, floor=0.10):
    """`levels` evenly-spaced shades of one colour, darkest first.

    `color_int` is a Live 0xRRGGBB value (a clip or track colour). It is first
    normalised so its brightest channel is full — otherwise an already-dark
    clip colour would scale down into indistinguishable near-black — then
    scaled from `floor` to 1.0 across the levels. Output channels are 0-127,
    the Launchpad's RGB range.
    """
    r = (color_int >> 16) & 255
    g = (color_int >> 8) & 255
    b = color_int & 255
    peak = max(r, g, b)
    if peak <= 0:
        return [(0, 0, 0)] * max(1, levels)
    r, g, b = (c * 255.0 / peak for c in (r, g, b))
    if levels <= 1:
        factors = [1.0]
    else:
        factors = [floor + (1.0 - floor) * i / (levels - 1)
                   for i in range(levels)]
    shades = []
    for f in factors:
        shades.append(tuple(
            max(0, min(RGB_MAX, int(round(c * f * RGB_MAX / 255.0))))
            for c in (r, g, b)))
    return shades


def rgb_sysex_message(device_sysex_id, specs):
    """Build one LED-lighting SysEx from `specs` = [(led_index, (r, g, b)), …]."""
    body = ()
    for index, (r, g, b) in specs:
        body += (RGB_SPEC_TYPE, index & 127,
                 max(0, min(RGB_MAX, int(r))),
                 max(0, min(RGB_MAX, int(g))),
                 max(0, min(RGB_MAX, int(b))))
    return (sysex.STD_MSG_HEADER + (device_sysex_id, RGB_SYSEX_COMMAND_BYTE)
            + body + (sysex.SYSEX_END_BYTE,))


def send_pad_rgb(parent, specs):
    """Write `specs` = [(led_index, (r, g, b)), …] in as few messages as the
    per-message cap allows. Silently no-ops if the parent can't send (teardown).
    """
    if not specs:
        return
    for start in range(0, len(specs), RGB_MAX_SPECS_PER_MESSAGE):
        chunk = specs[start:start + RGB_MAX_SPECS_PER_MESSAGE]
        try:
            parent._send_midi(rgb_sysex_message(DEVICE_SYSEX_ID, chunk),
                              optimized=False)
        except Exception:
            return


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
