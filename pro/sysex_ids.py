# Launchpad Pro MK3 SysEx identity + firmware layout bytes.
# Values lifted from the decompiled factory script
# (midi-remote-scripts/Launchpad_Pro_MK3/sysex_ids.py).
from __future__ import absolute_import, print_function, unicode_literals

LP_PRO_MK3_FAMILY_CODE = (35, 1)
LP_PRO_MK3_ID = 14

# Firmware layout selectors — 3-byte tuples (layout, page, 0) per the
# Programmer's Reference "Selecting layouts" table. Full layout list:
#   0 Session (DAW mode only) · 1 Fader · 2 Chord · 3 Custom Mode ·
#   4 Note/Drum · 5 Scale Settings · 6 Sequencer Settings ·
#   7 Sequencer Steps · 8 Seq Velocity · 9 Seq Pattern Settings ·
#   10 Seq Probability · 11 Seq Mutation · 12 Seq Micro Step ·
#   13 Seq Projects · 14 Seq Patterns · 15 Seq Tempo · 16 Seq Swing ·
#   17 Programmer Mode · 18 Settings Menu · 19 Custom Mode Settings
SESSION_LAYOUT_BYTES = (0, 0, 0)
CHORD_LAYOUT_BYTES = (2, 0, 0)
CUSTOM_LAYOUT_BYTES = (3, 0, 0)
NOTE_LAYOUT_BYTES = (4, 0, 0)
SEQUENCER_STEPS_LAYOUT_BYTES = (7, 0, 0)
FADER_LAYOUT_BYTE = 1
SCALE_LAYOUT_BYTES = (1, )
DRUM_LAYOUT_BYTES = (2, )
