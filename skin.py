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

    class Transport(object):
        PlayOff = Rgb.GREEN_HALF
        PlayOn = Rgb.GREEN
        RecordOff = Rgb.RED_HALF
        RecordOn = Rgb.RED

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
            # Cyan/aqua family — visually orthogonal to Note (blue/amber)
            # and to Step (deep blue / mint), so the bottom-right loop
            # selector cannot be confused with the bottom-left drum pads
            # or with the step grid above.
            # (Avoid Rgb.PURPLE_HALF — it maps to palette 55 which is
            # actually a dark BLUE on the Launchpad, not a dim purple.)
            Outside = Rgb.LIGHT_BLUE_HALF
            Inside = Rgb.LIGHT_BLUE
            Selected = Rgb.AQUA
            Playhead = Rgb.GREEN
            RangeEdit = Rgb.WHITE

        class Control(object):
            Page = Rgb.BLUE_HALF
            Octave = Rgb.GREEN_HALF
            Semitone = Rgb.MINT
            # Step-grid resolution selectors (drum sequencer side-row slots 2-5).
            Grid = Rgb.ORANGE_HALF
            GridSelected = Rgb.WHITE
            Reset = Rgb.DARK_ORANGE
            Shift = Rgb.AMBER
            # Bottom-right cycle indicator: shows current mode of the 4x4 quadrant.
            CycleLoop = Rgb.AQUA  # quadrant currently in loop mode
            CycleVelocity = Rgb.YELLOW  # quadrant currently in velocity mode

        class Velocity(object):
            # Bottom-right 4x4 when in velocity mode (16 velocity levels).
            Cell = Rgb.DARK_YELLOW_HALF
            Selected = Rgb.YELLOW

    class MelodicSequencer(object):
        StepEmpty = Rgb.DARK_BLUE_HALF
        StepBeat = Rgb.BLUE_HALF
        StepActive = Rgb.MINT
        Root = Rgb.AMBER
        Playhead = Rgb.GREEN
        PlayheadActive = Rgb.WHITE
        NoClip = Rgb.DARK_GREY

        class Preview(object):
            Off = Rgb.GREEN_HALF
            On = Rgb.AMBER

        class Loop(object):
            Outside = Rgb.DARK_GREY
            Inside = Rgb.BLUE_HALF
            Selected = Rgb.AMBER
            Playhead = Rgb.GREEN
            RangeEdit = Rgb.WHITE_HALF

        class Control(object):
            Page = Rgb.BLUE_HALF
            Octave = Rgb.GREEN_HALF
            Semitone = Rgb.MINT
            Reset = Rgb.DARK_ORANGE
            Shift = Rgb.AMBER


# IMPORTANT: Merge with base_skin instead of redefining everything!
skin = merge_skins(base_skin, Skin(Colors))
