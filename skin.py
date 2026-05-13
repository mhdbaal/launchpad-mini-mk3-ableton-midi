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
        StepActive = Rgb.MINT  # fallback when no note can be resolved
        StepMuted = Rgb.DARK_ORANGE
        # Velocity heat-map (cold → hot). Each note's step pad uses the tier
        # whose range covers its velocity. New notes default to vel 100 →
        # `StepVelLoud`. Adjusting velocity via arrows visibly recolors the pad.
        StepVelGhost = Rgb.LIGHT_BLUE       # 1-31 (ghost / very soft)
        StepVelSoft = Rgb.MINT              # 32-63
        StepVelMedium = Rgb.AMBER           # 64-95
        StepVelLoud = Rgb.YELLOW            # 96-127
        # Highlight for a step pad currently held by the user (anchor for
        # arrow-driven velocity / nudge edits, or for length extension).
        StepHeld = Rgb.AMBER
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
            # Ternary (triplet) grid cells use a distinct color family so the
            # user can spot at a glance that the resolution is ternary, not
            # binary. PURPLE_HALF on this device renders as dark blue (see
            # `(Avoid Rgb.PURPLE_HALF...)` note in Loop above), so use PURPLE.
            GridTernary = Rgb.PURPLE
            Reset = Rgb.DARK_ORANGE
            Shift = Rgb.AMBER
            # Clip-level actions (slots 0 and 1, top of column).
            CaptureMidi = Rgb.GREEN_HALF       # dim until capturable; bright on press
            CaptureMidiReady = Rgb.GREEN       # song.can_capture_midi == True
            Quantize = Rgb.AQUA
            # Slot 6 cycle button: switches the bottom-right 4x4 between
            # loop selector (default) and grid resolution selector.
            CycleLoop = Rgb.AQUA
            CycleGrid = Rgb.ORANGE

    class MelodicSequencer(object):
        StepEmpty = Rgb.DARK_BLUE_HALF
        StepBeat = Rgb.BLUE_HALF
        StepActive = Rgb.MINT  # fallback when no note can be resolved
        # Velocity heat-map mirroring the drum sequencer tiers. Same 4 ranges
        # so users can read either sequencer the same way.
        StepVelGhost = Rgb.LIGHT_BLUE
        StepVelSoft = Rgb.MINT
        StepVelMedium = Rgb.AMBER
        StepVelLoud = Rgb.YELLOW
        # Highlight for a step pad currently held by the user (selection
        # anchor for Quantize and similar clip-action gestures).
        StepHeld = Rgb.AMBER
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
            # Step-grid resolution selectors on scene-button slots 0-3
            # (mirrors the drum sequencer convention).
            Grid = Rgb.ORANGE_HALF
            GridSelected = Rgb.WHITE
            # Ternary (triplet) grid cells use a distinct color family so the
            # user can spot at a glance that the resolution is ternary, not
            # binary. PURPLE_HALF on this device renders as dark blue (see
            # `(Avoid Rgb.PURPLE_HALF...)` note in Loop above), so use PURPLE.
            GridTernary = Rgb.PURPLE
            # Scale cycle (slot 6): bright when shift is held, dim when not
            # (the grey/disabled state is handled by the helper).
            ScaleCycle = Rgb.AQUA
            Reset = Rgb.DARK_ORANGE
            Shift = Rgb.AMBER
            # Clip-level actions on slots 5/6 when shift is NOT held.
            # When shift IS held, slots 5/6 show Chromatic/ScaleCycle instead.
            CaptureMidi = Rgb.GREEN_HALF
            CaptureMidiReady = Rgb.GREEN
            Quantize = Rgb.AQUA
            # Slot 6 cycle: switches the bottom-right 4x4 between the default
            # pitch grid and the grid resolution selector.
            CycleLoop = Rgb.AQUA
            CycleGrid = Rgb.ORANGE


# IMPORTANT: Merge with base_skin instead of redefining everything!
skin = merge_skins(base_skin, Skin(Colors))
