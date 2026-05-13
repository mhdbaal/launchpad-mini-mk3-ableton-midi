from __future__ import absolute_import, print_function, unicode_literals


class Event(object):
    """Semantic event names emitted by components.

    Names are arbitrary strings; only this module and the subscribers
    (status_bar_subscriber, m4l_subscriber) need to know them. Components
    import constants from here and pass payload as keyword args to
    `EventBus.emit`. Payload shapes are documented inline.

    To add a new event:
      1. add a constant here with its payload shape in a comment
      2. emit it from the relevant component
      3. add a formatter entry in status_bar_subscriber._FORMATTERS
      4. add a mapping entry in m4l_subscriber._MAPPING
    Components stay agnostic of presentation.
    """

    # Mode switches
    MAIN_MODE_CHANGED       = "main_mode_changed"       # mode="session"|"drum_sequence"|"melodic_sequence"

    # Shift state
    SHIFT_LOCK_CHANGED      = "shift_lock_changed"      # locked=bool

    # Drum sequencer
    DRUM_PAGE_SCOPED        = "drum_page_scoped"        # start=int (1-based), end=int (1-based, inclusive)
    DRUM_STEP_LOOP_SCOPED   = "drum_step_loop_scoped"   # page=int (1-based), start_step=int (1-based), end_step=int (1-based, inclusive), label=str
    DRUM_GRID_CHANGED       = "drum_grid_changed"       # label=str, is_triplet=bool
    DRUM_TRIPLET_CHANGED    = "drum_triplet_changed"    # on=bool, label=str
    DRUM_VELOCITY_CHANGED   = "drum_velocity_changed"   # velocity=int (1..127)
    DRUM_NOTE_LENGTH_CHANGED = "drum_note_length_changed" # page=int (1-based), anchor_step=int (1-based), length_steps=int, pitch=int (MIDI)
    DRUM_NOTE_NUDGED        = "drum_note_nudged"        # delta_beats=float, start_time=float (new absolute start in beats), pitch=int (MIDI)
    DRUM_NAV_CHANGED        = "drum_nav_changed"        # label=str, page=int (1-based), octave=int, semitone=int
    DRUM_NOTES_QUANTIZED    = "drum_notes_quantized"    # count=int (notes moved), scope="selected"|"pad_all", grid=str
    DRUM_BOTTOM_RIGHT_MODE  = "drum_bottom_right_mode"  # mode="loop"|"grid"
    MIDI_CAPTURED           = "midi_captured"           # ok=bool, reason=str (if not ok)

    # Melodic sequencer
    MELODIC_PAGE_SCOPED     = "melodic_page_scoped"     # start=int (1-based), end=int (1-based, inclusive)
    MELODIC_STEP_LOOP_SCOPED = "melodic_step_loop_scoped" # page=int (1-based), start_step=int (1-based), end_step=int (1-based, inclusive), label=str
    MELODIC_GRID_CHANGED    = "melodic_grid_changed"    # label=str, is_triplet=bool
    MELODIC_TRIPLET_CHANGED = "melodic_triplet_changed" # on=bool, label=str
    MELODIC_SCALE_CHANGED   = "melodic_scale_changed"   # scale_index=int, scale_name=str
    MELODIC_CHROMATIC_MODE  = "melodic_chromatic_mode"  # on=bool
    MELODIC_PREVIEW_MODE    = "melodic_preview_mode"    # on=bool
    MELODIC_NAV_CHANGED     = "melodic_nav_changed"     # label=str, page=int (1-based), octave=int, semitone=int
    MELODIC_NOTES_QUANTIZED = "melodic_notes_quantized" # count=int (notes moved), scope="selected"|"clip_all", grid=str
    MELODIC_BOTTOM_RIGHT_MODE = "melodic_bottom_right_mode" # mode="pitch"|"grid"

    # Errors (mode discriminates drum vs melodic)
    ERR_NEED_MIDI_SLOT      = "err_need_midi_slot"      # mode="drum"|"melodic"
    ERR_NEED_MIDI_TRACK     = "err_need_midi_track"     # mode="drum"|"melodic"
    ERR_NOT_MIDI            = "err_not_midi"            # mode="drum"|"melodic"
