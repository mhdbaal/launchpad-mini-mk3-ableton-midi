# Launchpad Pro MK3 (Custom) — entry point.
#
# Installed as Launchpad_Pro_MK3_Custom, ALONGSIDE the untouched factory
# Launchpad_Pro_MK3 script — both appear in Live's Control Surface list.
#
# Port layout — the Pro exposes 3 USB MIDI interfaces (Windows names):
#   1. "LPProMK3 MIDI"          — the MIDI interface: Note/Chord/Custom
#      modes AND **Programmer mode** I/O (LED writes included). Per the
#      LP Pro MK3 Programmer's Reference, programmer-mode LEDs only work
#      through this interface.
#   2. "MIDIIN2 (LPProMK3 MIDI)" — DIN MIDI thru.
#   3. "MIDIIN3 (LPProMK3 MIDI)" — the DAW interface (what the FACTORY
#      script binds for Session mode).
# This script runs in Programmer mode, so SCRIPT marks the FIRST pair:
# bind Input/Output to "LPProMK3 MIDI". Binding MIDIIN3 = device enters
# programmer mode but stays dark (LED writes land on the DAW interface).
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.control_surface.capabilities import CONTROLLER_ID_KEY, NOTES_CC, PORTS_KEY, REMOTE, SCRIPT, SYNC, controller_id, inport, outport
from .device_profile import MODEL_NAME, PRODUCT_IDS, VENDOR_ID
from .launchpad_pro_mk3 import Launchpad_Pro_MK3


def get_capabilities():
    return {CONTROLLER_ID_KEY: (controller_id(vendor_id=VENDOR_ID,
                          product_ids=PRODUCT_IDS,
                          model_name=[MODEL_NAME])),

     PORTS_KEY: [
                 inport(props=[NOTES_CC, REMOTE, SCRIPT]),
                 inport(props=[]),
                 inport(props=[]),
                 outport(props=[NOTES_CC, SYNC, REMOTE, SCRIPT]),
                 outport(props=[]),
                 outport(props=[])]}


def create_instance(c_instance):
    return Launchpad_Pro_MK3(c_instance=c_instance)
