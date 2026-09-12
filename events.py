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
    MAIN_MODE_CHANGED       = "main_mode_changed"       # mode="session"|"drum_sequence"|"drum_64_sequence"|"drum_4_track_sequence"|"melodic_sequence"|"chord_mode"

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
    DRUM_PAGE_DUPLICATED    = "drum_page_duplicated"    # source=int (1-based), target=int (1-based), notes=int (count copied)
    DRUM_LOOP_DOUBLED       = "drum_loop_doubled"       # old_length=float, new_length=float, notes=int
    DRUM_64_MATRIX_MODE     = "drum_64_matrix_mode"     # mode="edit"|"loop_pick"|"grid_pick"
    DRUM_4_TRACK_MATRIX_MODE = "drum_4_track_matrix_mode"  # mode="edit"|"loop_pick"|"grid_pick"
    MIDI_CAPTURED           = "midi_captured"           # ok=bool, reason=str (if not ok)

    # Melodic sequencer
    MELODIC_PAGE_SCOPED     = "melodic_page_scoped"     # start=int (1-based), end=int (1-based, inclusive)
    MELODIC_STEP_LOOP_SCOPED = "melodic_step_loop_scoped" # page=int (1-based), start_step=int (1-based), end_step=int (1-based, inclusive), label=str
    MELODIC_GRID_CHANGED    = "melodic_grid_changed"    # label=str, is_triplet=bool
    MELODIC_TRIPLET_CHANGED = "melodic_triplet_changed" # on=bool, label=str
    MELODIC_SCALE_CHANGED   = "melodic_scale_changed"   # scale_index=int, scale_name=str
    MELODIC_CHROMATIC_MODE  = "melodic_chromatic_mode"  # on=bool
    MELODIC_PREVIEW_MODE    = "melodic_preview_mode"    # on=bool
    MELODIC_DRUM_MODE       = "melodic_drum_mode"       # active=bool, count=int (used pads in the rack)
    MELODIC_DRUM_LANES      = "melodic_drum_lanes"      # first=int (1-based), last=int (1-based, inclusive), total=int
    MELODIC_LANE_VELOCITY_VIEW = "melodic_lane_velocity_view" # name=str (lane label)
    MELODIC_LANE_VELOCITY   = "melodic_lane_velocity"   # name=str, step=int (1-based), velocity=int (1..127)
    MELODIC_NAV_CHANGED     = "melodic_nav_changed"     # label=str, page=int (1-based), octave=int, semitone=int
    MELODIC_NOTES_QUANTIZED = "melodic_notes_quantized" # count=int (notes moved), scope="selected"|"clip_all", grid=str
    MELODIC_BOTTOM_RIGHT_MODE = "melodic_bottom_right_mode" # mode="pitch"|"grid"
    MELODIC_PAGE_DUPLICATED = "melodic_page_duplicated" # source=int (1-based), target=int (1-based), notes=int (count copied)
    MELODIC_LOOP_DOUBLED    = "melodic_loop_doubled"    # old_length=float, new_length=float, notes=int
    MELODIC_VELOCITY_CHANGED = "melodic_velocity_changed"   # velocity=int (1..127)

    # Chord pad mode
    CHORD_KEY_CHANGED       = "chord_key_changed"       # key_index=int (0..11), key_name=str
    CHORD_SCALE_CHANGED     = "chord_scale_changed"     # scale_index=int, scale_name=str
    CHORD_TYPE_CHANGED      = "chord_type_changed"      # type_index=int, type_name=str
    CHORD_INVERSION_CHANGED = "chord_inversion_changed" # inversion=int (0..3)
    CHORD_NAV_CHANGED       = "chord_nav_changed"       # octave=int, semitone=int, key_name=str
    # Fired on every chord-pad press. `chord_pitches` is the full diatonic
    # chord (variable length, depending on chord type), which the script
    # itself cannot play — script_forwarding is 1-1 — but an M4L companion
    # or external listener can use it to play the full harmony. The pad's
    # *audition* (single root note) goes via the AUDITION_CHANNEL pipeline,
    # independent of this event.
    CHORD_TRIGGERED         = "chord_triggered"         # degree=int (0-based), root_pitch=int, chord_pitches=tuple[int], velocity=int
    CHORD_RELEASED          = "chord_released"          # degree=int, root_pitch=int

    # Edit mode (5th stop-solo-mute sub-mode, entered via double-tap on
    # shift in session main mode). Used to delete/duplicate/move clips
    # and scenes while a modifier pad (red/green/blue) on the bottom row
    # is held.
    EDIT_MODE_CHANGED       = "edit_mode_changed"       # on=bool
    EDIT_CLIP_DELETED       = "edit_clip_deleted"       # track=int, scene=int
    EDIT_CLIP_DUPLICATED    = "edit_clip_duplicated"    # track=int, scene=int (source)
    EDIT_CLIP_MOVED         = "edit_clip_moved"         # from_track=int, from_scene=int, to_track=int, to_scene=int
    EDIT_SCENE_DELETED      = "edit_scene_deleted"      # scene=int
    EDIT_SCENE_DUPLICATED   = "edit_scene_duplicated"   # scene=int (source)
    EDIT_SCENE_MOVED        = "edit_scene_moved"        # from_scene=int, to_scene=int
    EDIT_MOVE_SOURCE_SET    = "edit_move_source_set"    # kind="clip"|"scene"
    EDIT_MOVE_CANCELLED     = "edit_move_cancelled"     # ()
    EDIT_CLIP_COLOR_CYCLED  = "edit_clip_color_cycled"  # track=int, scene=int, color_index=int
    EDIT_SCENE_COLOR_CYCLED = "edit_scene_color_cycled" # scene=int, color_index=int
    EDIT_STOP_ALL_CLIPS     = "edit_stop_all_clips"     # ()
    EDIT_UNDO               = "edit_undo"               # ()
    EDIT_REDO               = "edit_redo"               # ()

    # Track pin (Launchpad-side lock so the sequencer doesn't follow Live's
    # selected-track changes). Emitted by every sequencer component that
    # supports pinning. `mode` matches the main-mode key so the subscriber
    # can prefix the message appropriately.
    TRACK_PINNED            = "track_pinned"            # mode=str, track_name=str
    TRACK_UNPINNED          = "track_unpinned"          # mode=str

    # Errors (mode discriminates drum vs melodic)
    ERR_NEED_MIDI_SLOT      = "err_need_midi_slot"      # mode="drum"|"melodic"
    ERR_NEED_MIDI_TRACK     = "err_need_midi_track"     # mode="drum"|"melodic"
    ERR_NOT_MIDI            = "err_not_midi"            # mode="drum"|"melodic"
