# ======================================================================
# DEVICE PROFILE — Novation Launchpad Mini MK3
#
# To port this script to another Launchpad (Launchpad X, Pro MK3, …):
# REPLACE THIS FILE WHOLESALE. Nothing else in the repo embeds device-
# specific MIDI bytes, USB IDs, or button assignments.
#
# Companion device-agnostic seams:
#   - programmer_mode.py : Novation-wide Programmer-mode conventions
#                          (Note On / CC status, LED channel, audition channel)
#   - palette.py         : raw 0-127 Launchpad palette + skin-name → index dicts
#   - sysex_ids.py       : Mini-MK3-specific family + model identity bytes
# ======================================================================
from __future__ import absolute_import, print_function, unicode_literals

from . import sysex_ids as _ids


# ------------------------------------------------------------------ Identity
# USB descriptor matched in __init__.py::get_capabilities. Different on
# Launchpad X and Pro MK3.
VENDOR_ID = 4661
PRODUCT_IDS = [275]
MODEL_NAME = "Launchpad Mini MK3"

# Re-exports under generic names. Call sites that don't need to spell out
# "Mini MK3" can import these instead, making them ready for a future fork.
DEVICE_FAMILY_CODE = _ids.LP_MINI_MK3_FAMILY_CODE  # (19, 1)
DEVICE_SYSEX_ID = _ids.LP_MINI_MK3_ID              # 13

# ----------------------------------------------------- SysEx firmware commands
# Bytes used in `_send_launchpad_sysex` after STD_MSG_HEADER + DEVICE_SYSEX_ID.
# Programmer-mode entry / external feedback / sleep — Mini-MK3-specific syntax.
PROGRAMMER_MODE_COMMAND_BYTE = 14
PROGRAMMER_MODE_ON = 1
PROGRAMMER_MODE_OFF = 0
LED_FEEDBACK_COMMAND_BYTE = 10
INTERNAL_FEEDBACK_OFF = 0
EXTERNAL_FEEDBACK_ON = 1
SLEEP_COMMAND_BYTE = 9
SLEEP_OFF = 1

# ----------------------------------------------- Mode/arrow button CC numbers
# CC values that the device firmware emits on press and accepts as LED writes
# in Programmer mode. Read by `_set_mode_button_lights` and the value-listener
# wiring in `_create_components`.
SESSION_BUTTON_CC = 95
DRUMS_BUTTON_CC = 96
KEYS_BUTTON_CC = 97
USER_BUTTON_CC = 98
UP_BUTTON_CC = 91
DOWN_BUTTON_CC = 92
LEFT_BUTTON_CC = 93
RIGHT_BUTTON_CC = 94

# --------------------------------- Mode/arrow button LED palette indices (0-127)
# Raw Novation palette indices. The palette numbers are shared with other
# Launchpads (the firmware speaks the same Programmer-mode color table), so
# only the choices below are "Mini-MK3-specific" in the sense of "this UI
# uses these colors" — the indices themselves are portable.
LED_OFF = 0
LED_SESSION = 21
LED_SESSION_DIM = 27        # GREEN_HALF — "session button is available, press to switch"
LED_SEQUENCER = 96          # AMBER — drum sequencer indicator on User button
LED_MELODIC = 41            # MELODIC sequencer indicator on User button
LED_ARROW_OCTAVE = 27       # GREEN_HALF, matches Control.Octave skin
LED_ARROW_SEMITONE = 29     # MINT, matches Control.Semitone skin
