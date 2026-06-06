# Launchpad Pro MK3 — entry point.
#
# Port layout mirrors the factory script: the Pro exposes 3 port pairs
# (1: live/remote port, 2: standalone/DIN, 3: DAW/script port). The SCRIPT
# props mark the third pair — in Live's preferences, bind the control
# surface to that pair (on Windows typically "MIDIIN3/MIDIOUT3 (LPProMK3
# MIDI)"). Wrong pair = clip grid works but Programmer-mode LEDs stay dark.
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.control_surface.capabilities import CONTROLLER_ID_KEY, NOTES_CC, PORTS_KEY, REMOTE, SCRIPT, SYNC, controller_id, inport, outport
from .device_profile import MODEL_NAME, PRODUCT_IDS, VENDOR_ID
from .launchpad_pro_mk3 import Launchpad_Pro_MK3


def get_capabilities():
    return {CONTROLLER_ID_KEY: (controller_id(vendor_id=VENDOR_ID,
                          product_ids=PRODUCT_IDS,
                          model_name=[MODEL_NAME])),

     PORTS_KEY: [
                 inport(props=[NOTES_CC, REMOTE]),
                 inport(props=[]),
                 inport(props=[NOTES_CC, SCRIPT]),
                 outport(props=[REMOTE]),
                 outport(props=[]),
                 outport(props=[NOTES_CC, SYNC, SCRIPT])]}


def create_instance(c_instance):
    return Launchpad_Pro_MK3(c_instance=c_instance)
