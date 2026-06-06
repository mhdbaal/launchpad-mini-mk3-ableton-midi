# SHADOW __init__.py for the FACTORY Launchpad_Pro_MK3 script.
#
# Installed by install.sh (--pro) NEXT TO the factory __init__.pyc —
# Python prefers source over bytecode in the same directory, so this
# file (and ONLY this file) overrides the factory package entry point.
# Not a single byte of factory code is modified or deleted.
#
# WHY: the factory script declares the same USB ids (vendor 4661,
# product 291) as our Launchpad_Pro_MK3_Custom, so Live auto-assigned
# BOTH control surfaces on every launch — factory on the DAW port
# (MIDIIN3), custom on port 1 — and the two fought over the device
# (factory DAW-mode layouts + LED writes vs our Programmer mode; the
# factory also reacted to the DAW-port layout notifications our native
# passthrough relies on). Removing get_capabilities() disables
# AUTO-DETECTION ONLY: the factory script remains fully functional and
# can still be selected MANUALLY in the Control Surface dropdown.
#
# TO RESTORE the factory auto-detection: delete THIS file
# (__init__.py) from the installed factory folder — the original
# __init__.pyc takes over again. Full .pyc backups live in the repo
# (factory-backup/Launchpad_Pro_MK3/) and in Ableton's pristine update
# staging (.Live 12 Suite_updated/Resources/MIDI Remote Scripts/).
from __future__ import absolute_import, print_function, unicode_literals
import logging

from .launchpad_pro_mk3 import Launchpad_Pro_MK3

logger = logging.getLogger(__name__)
# Import-time trace: shows up in Log.txt when Live scans the package
# (dropdown population) — NOT proof the script is running.
logger.info("[Launchpad Pro MK3 FACTORY] package scanned (shadow __init__.py active, auto-detection disabled)")

# NOTE: no get_capabilities() here — that is the whole point. Without
# it Live cannot auto-detect/auto-assign this script; manual selection
# still works through create_instance below.


def create_instance(c_instance):
    # Instantiation trace: if this line appears in Log.txt, the factory
    # script IS running (someone selected it manually, or a stale
    # preferences slot still references it — set that slot to None).
    c_instance.log_message(
        "[Launchpad Pro MK3 FACTORY] create_instance called — factory "
        "script is RUNNING alongside the custom one; clear its Control "
        "Surface slot if this is unintended")
    return Launchpad_Pro_MK3(c_instance=c_instance)
