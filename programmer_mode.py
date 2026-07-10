# Novation Programmer-mode MIDI conventions shared across the Launchpad family
# (Mini MK3, X, Pro MK3). These values come from the wire protocol, not from
# any one device's firmware quirks — moving to another Launchpad does NOT
# change them. Device-specific bytes live in device_profile.py.
from __future__ import absolute_import, print_function, unicode_literals

# MIDI status bytes (channel-less).
NOTE_ON_STATUS = 144   # 0x90
MIDI_CC_STATUS = 176   # 0xB0

# Channel used for LED writes while the device is in Programmer mode. The
# firmware listens on channel 0 for pad-color Note On / mode-button CC.
PROGRAMMER_LED_CHANNEL = 0

# Channel used when the script translates pad presses to audition notes that
# Live will forward to the selected track. The translated pitches collide on
# Live's MIDI forwarding registry (keyed by (channel, identifier)) with the
# original_identifier of OTHER pads in the same matrix — putting audition on
# a distinct channel makes those keys disjoint. Channel 1 also doubles as the
# feedback channel so drum-rack LED hints round-trip back to the same pads.
AUDITION_CHANNEL = 1
