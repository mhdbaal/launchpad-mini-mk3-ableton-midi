# Launchpad Mini MK3 Skin - Based on 12.0.1 with select mode added
from __future__ import absolute_import, print_function, unicode_literals
from builtins import object
from ableton.v2.control_surface import Skin, merge_skins
from ableton.v2.control_surface.elements import Color
from novation.colors import Rgb
from novation.skin import skin as base_skin


class Colors(object):

    class Mode(object):

        class Session(object):
            Launch = Color((Rgb.PALE_GREEN_HALF.midi_value, Rgb.WHITE_HALF.midi_value))
            Overview = Color((Rgb.BLUE.midi_value, Rgb.WHITE_HALF.midi_value))

    # NEW: Color for select mode
    class Mixer(object):
        TrackSelected = Rgb.AQUA

    class DrumSequencer(object):
        StepEmpty = Rgb.DARK_BLUE_HALF
        StepBeat = Rgb.BLUE_HALF
        StepActive = Rgb.MINT
        StepMuted = Rgb.DARK_ORANGE
        Playhead = Rgb.GREEN
        PlayheadActive = Rgb.WHITE
        Disabled = Rgb.BLACK
        NoDrumRack = Rgb.RED_HALF
        NoClip = Rgb.DARK_GREY
        NoteEmpty = Rgb.DARK_GREY
        NoteFilled = Rgb.BLUE_HALF
        NoteSelected = Rgb.AMBER

        class Loop(object):
            Outside = Rgb.DARK_GREY
            Inside = Rgb.BLUE_HALF
            Selected = Rgb.AMBER
            Playhead = Rgb.GREEN
            RangeEdit = Rgb.WHITE_HALF


# IMPORTANT: Merge with base_skin instead of redefining everything!
skin = merge_skins(base_skin, Skin(Colors))
