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

        # Mode selector: shown on scene buttons 0-4 (top to bottom) while
        # the User button is held. The active mode renders bright; the
        # others render half. Tapping the active mode returns to session;
        # tapping any other mode switches to it.
        class Selector(object):
            Drum          = Rgb.AMBER
            DrumDim       = Rgb.AMBER_HALF
            Drum64        = Rgb.ORANGE
            Drum64Dim     = Rgb.ORANGE_HALF
            Drum4Track    = Rgb.YELLOW
            Drum4TrackDim = Rgb.YELLOW_HALF
            Melodic       = Rgb.BLUE
            MelodicDim    = Rgb.BLUE_HALF
            # PURPLE_HALF renders as dark blue on this device — use VIOLET
            # (palette 52, immediately next to PURPLE 53) as a dim variant.
            Chord         = Rgb.PURPLE
            ChordDim      = Rgb.VIOLET

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
        # Drum pad on the bottom-left selector flashes GREEN when a note
        # of its pitch is firing at the current playhead. Overrides the
        # selected/filled/empty render so live activity is visible at a
        # glance, even on the selected pad. (Tried WHITE / palette 3 but
        # it renders as a dim grey on Mini MK3 — GREEN pops better.)
        NotePlaying = Rgb.GREEN

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
            # Dim variant rendered on slot 5 when shift is NOT held — gives the
            # user a permanent visual anchor for the modifier button location.
            ShiftIdle = Rgb.AMBER_HALF
            # Clip-level actions (slots 0 and 1, top of column).
            CaptureMidi = Rgb.GREEN_HALF       # dim until capturable; bright on press
            CaptureMidiReady = Rgb.GREEN       # song.can_capture_midi == True
            Quantize = Rgb.AQUA
            # Slot 2: Duplicate Page modifier. Hold + tap page = copy.
            DuplicatePage = Rgb.YELLOW_HALF
            DuplicatePageHeld = Rgb.YELLOW
            # Slot 3: Double Loop action. Single tap doubles + duplicates.
            DoubleLoop = Rgb.PURPLE
            # Slot 6: Special Shift cycle button. Tap cycles delete/dup;
            # hold = armed action mode. Idle uses *Half (current mode at
            # a glance); held / source-armed cell uses the bright variant.
            SpecialDelete = Rgb.RED
            SpecialDeleteHalf = Rgb.RED_HALF
            SpecialDuplicate = Rgb.GREEN
            SpecialDuplicateHalf = Rgb.GREEN_HALF
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

    class EditMode(object):
        # 5th "stop-solo-mute" sub-mode, entered via double-tap on the
        # shift button while in session main mode. The bottom row of the
        # 8x8 grid becomes a row of modifier pads:
        #   slot 0 = Delete       (red)    — modifier
        #   slot 1 = Duplicate    (green)  — modifier
        #   slot 2 = Move         (blue)   — modifier
        #   slot 3 = Color Cycle  (yellow) — modifier
        #   slot 4 = Stop All     (orange) — single-tap action
        #   slot 5-6 = inert (dim)
        #   slot 7 = Undo         (white)  — single tap; +shift = redo
        # Each pad lives in two visual states: available (half) and held
        # (full). Held = the user is currently pressing it; any clip or
        # scene press while held triggers the corresponding action.
        Delete           = Rgb.RED_HALF
        DeleteHeld       = Rgb.RED
        Duplicate        = Rgb.GREEN_HALF
        DuplicateHeld    = Rgb.GREEN
        Move             = Rgb.BLUE_HALF
        MoveHeld         = Rgb.BLUE
        # Once a move source is captured (1st tap), the move pad turns
        # WHITE to signal "waiting for destination". Releasing Blue
        # before the 2nd tap cancels and the pad goes back to MoveHeld.
        MoveArmed        = Rgb.WHITE
        # Color Cycle (slot 3): held + tap clip/scene cycles its
        # color_index. Yellow to read distinctly from RGB modifiers.
        ColorCycle       = Rgb.YELLOW_HALF
        ColorCycleHeld   = Rgb.YELLOW
        # Stop All Clips (slot 4): single tap fires song.stop_all_clips().
        # DARK_ORANGE so it doesn't collide with Delete's red and reads
        # as a "global / careful" action.
        StopAll          = Rgb.DARK_ORANGE
        # Undo (slot 7): single tap undoes, tap-while-shift-held redoes.
        # WHITE_HALF: neutral / system-action coloring.
        Undo             = Rgb.WHITE_HALF
        # Slots 5-6 of the bottom row are inert while edit mode is on —
        # render them dim so the row reads as "owned by edit mode" but
        # the user can tell those pads do nothing.
        Dim              = Rgb.DARK_GREY
        # LED color of the shift button (scene_launch_buttons_raw[7])
        # while edit mode is active. WHITE so it stands out from the
        # mixer-tinted select/stop/solo/mute colors.
        Cycle          = Rgb.WHITE

    class ChordPad(object):
        # Each pad in the 8x8 chord grid maps to one MIDI note (column =
        # scale degree, row = octave shift). Three flavors of pad,
        # chosen by where the degree falls in the diatonic triad of the
        # tonic (I, iii, V — the harmonic backbone):
        #   - Root      : degrees 0 and 7 (I and I-up-octave). AMBER.
        #   - ChordTone : degrees 2 and 4 (iii, V). BLUE.
        #   - ScaleTone : every other in-scale degree. GREEN_HALF.
        # Each gets a *Dim variant for rows other than the default
        # octave anchor (DEFAULT_ROW in chord_pad_mode.py). Flat names
        # ("RootDim", not "Root.Dim") because Skin treats each dot in a
        # color name as a class navigation — see MelodicSequencer
        # above for the same convention (Grid vs GridSelected).
        Root = Rgb.AMBER
        RootDim = Rgb.AMBER_HALF
        ChordTone = Rgb.BLUE
        ChordToneDim = Rgb.BLUE_HALF
        ScaleTone = Rgb.GREEN_HALF
        ScaleToneDim = Rgb.DARK_GREY
        Pressed = Rgb.WHITE
        # Mode-button LED while in chord_mode (User button cycle color).
        # PURPLE to read distinctly from session (green), drum (amber),
        # and melodic (blue).
        Active = Rgb.PURPLE

        class Control(object):
            # Capture MIDI (dim until capturable). Matches the other modes.
            CaptureMidi = Rgb.GREEN_HALF
            CaptureMidiReady = Rgb.GREEN
            Key = Rgb.AMBER
            Scale = Rgb.AQUA
            ChordType = Rgb.PURPLE
            Inversion = Rgb.YELLOW
            # Sequencer-shift modifier feedback on slot 5 (parent-owned).
            Shift = Rgb.AMBER


# IMPORTANT: Merge with base_skin instead of redefining everything!
skin = merge_skins(base_skin, Skin(Colors))
