# ======================================================================
# DEVICE PROFILE — Novation Launchpad Pro MK3
#
# Same contract as mini/device_profile.py: nothing else in the package
# embeds device-specific MIDI bytes, USB IDs, or button assignments.
# Replace this file wholesale to port to another Launchpad.
#
# Companion device-agnostic seams:
#   - programmer_mode.py : Novation-wide Programmer-mode conventions
#                          (Note On / CC status, LED channel, audition channel)
#   - palette.py         : raw 0-127 Launchpad palette + skin-name → index dicts
#   - sysex_ids.py       : Pro-MK3-specific family + model identity bytes
# ======================================================================
from __future__ import absolute_import, print_function, unicode_literals

from . import sysex_ids as _ids


# ------------------------------------------------------------------ Identity
# USB descriptor matched in __init__.py::get_capabilities.
VENDOR_ID = 4661
PRODUCT_IDS = [291]
MODEL_NAME = "Launchpad Pro MK3"

DEVICE_FAMILY_CODE = _ids.LP_PRO_MK3_FAMILY_CODE  # (35, 1)
DEVICE_SYSEX_ID = _ids.LP_PRO_MK3_ID              # 14

# ----------------------------------------------------- SysEx firmware commands
# Bytes used in `_send_launchpad_sysex` after STD_MSG_HEADER + DEVICE_SYSEX_ID.
# Programmer-mode entry per the LP Pro MK3 Programmer's Reference:
#   F0 00 20 29 02 0E 0E <mode> F7   (<mode> 1 = programmer, 0 = live)
# — same command byte 14 as the Mini MK3 / X, only the device id differs.
PROGRAMMER_MODE_COMMAND_BYTE = 14
PROGRAMMER_MODE_ON = 1
PROGRAMMER_MODE_OFF = 0
# Feedback + sleep follow the Mini's Novation convention. TO VALIDATE on
# hardware — if the Pro firmware ignores these commands they are harmless
# no-ops (the script works without them; they only tune LED echo/sleep).
LED_FEEDBACK_COMMAND_BYTE = 10
INTERNAL_FEEDBACK_OFF = 0
EXTERNAL_FEEDBACK_ON = 1
SLEEP_COMMAND_BYTE = 9
SLEEP_OFF = 1

# --------------------------------------------------------- Button CC numbers
# CC values the firmware emits on press and accepts as LED writes (CC ch 0)
# in Programmer mode. Layout (decimal grid coords, pads are notes 11-88):
#   top row     : 91 ◄, 92 ►, 93 Session, 94 Note, 95 Chord, 96 Custom,
#                 97 Sequencer, 98 Projects
#   left column : 90 Shift, 80 ▲, 70 ▼, 60 Clear, 50 Duplicate, 40 Quantise,
#                 30 Fixed Length, 20 Play, 10 Record
#   below grid  : 101-108 track select row, then 1-8 function row
#                 (1 Record Arm, 2 Mute, 3 Solo, 4 Volume, 5 Pan, 6 Sends,
#                  7 Device, 8 Stop Clip)
#   right column: 89..19 scene launch (identical to the Mini)
SESSION_BUTTON_CC = 93
NOTE_BUTTON_CC = 94
CHORD_BUTTON_CC = 95
CUSTOM_BUTTON_CC = 96
SEQUENCER_BUTTON_CC = 97
PROJECTS_BUTTON_CC = 98
UP_BUTTON_CC = 80
DOWN_BUTTON_CC = 70
LEFT_BUTTON_CC = 91
RIGHT_BUTTON_CC = 92
SHIFT_BUTTON_CC = 90
CLEAR_BUTTON_CC = 60
DUPLICATE_BUTTON_CC = 50
QUANTIZE_BUTTON_CC = 40
FIXED_LENGTH_BUTTON_CC = 30
PLAY_BUTTON_CC = 20
RECORD_BUTTON_CC = 10
RECORD_ARM_BUTTON_CC = 1
MUTE_BUTTON_CC = 2
SOLO_BUTTON_CC = 3
VOLUME_BUTTON_CC = 4
PAN_BUTTON_CC = 5
SENDS_BUTTON_CC = 6
DEVICE_BUTTON_CC = 7
STOP_CLIP_BUTTON_CC = 8
TRACK_SELECT_FIRST_CC = 101  # 101-108, left → right

# Buttons deliberately inert in v1 — swallowed by the background layer,
# LEDs kept dark. Reserved for future features (faders need the DAW-mode
# fader layout; Custom/Projects/Fixed Length unassigned).
INERT_BUTTON_CCS = (
    CHORD_BUTTON_CC,
    CUSTOM_BUTTON_CC,
    PROJECTS_BUTTON_CC,
    FIXED_LENGTH_BUTTON_CC,
    VOLUME_BUTTON_CC,
    PAN_BUTTON_CC,
    SENDS_BUTTON_CC,
    DEVICE_BUTTON_CC,
)

# --------------------------------- Button LED palette indices (0-127, shared
# firmware color table across the Launchpad family — only the CHOICES below
# are Pro-specific UI decisions). Tune on hardware if a shade reads wrong.
LED_OFF = 0
LED_SESSION = 21            # GREEN — session main mode active
LED_SESSION_DIM = 27        # GREEN_HALF — "session reachable, press to switch"
LED_SESSION_PINNED = 37     # BLUE — active sequencer pinned to a track
LED_SEQUENCER = 96          # AMBER — drum sequencer active (Sequencer button)
LED_MELODIC = 41            # BLUE-ISH — melodic sequencer active (Note button)
LED_CHORD = 53              # PURPLE — chord mode (future, Chord button)
LED_MODE_IDLE = 1           # dim grey — mode button available but inactive
LED_ARROW_OCTAVE = 27       # GREEN_HALF, matches Control.Octave skin
LED_ARROW_SEMITONE = 29     # MINT, matches Control.Semitone skin
# Modifier buttons (left column) — idle dim, bright while held.
LED_SHIFT_IDLE = 1
LED_SHIFT_HELD = 3          # WHITE
LED_CLEAR_IDLE = 7          # RED_HALF
LED_CLEAR_HELD = 5          # RED
LED_DUPLICATE_IDLE = 27     # GREEN_HALF
LED_DUPLICATE_HELD = 21     # GREEN
LED_QUANTIZE_IDLE = 15      # YELLOW_HALF
# Mixer function row (CC 1/2/3/8) — idle dim, bright when its row mode is on.
LED_ARM_IDLE = 7
LED_ARM_ACTIVE = 5
LED_MUTE_IDLE = 11          # AMBER_HALF
LED_MUTE_ACTIVE = 9         # AMBER
LED_SOLO_IDLE = 39          # BLUE_HALF
LED_SOLO_ACTIVE = 37        # BLUE
LED_STOP_IDLE = 1
LED_STOP_ACTIVE = 3
