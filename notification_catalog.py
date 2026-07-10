from __future__ import absolute_import, print_function, unicode_literals


class Msg(object):
    """Wire protocol shared with the LP Notify Max for Live device.

    The .amxd patch's lookup table is indexed by these integer IDs. The
    contract is append-only: never renumber an existing ID, never reuse
    a freed ID. Adding new messages → append, with a comment documenting
    the arg signature.

    Args are signed integers in the range -128..127 (live.numbox in the
    device). String labels (scale name, "Drum"/"Melodic", etc.) live in
    secondary lookup tables INSIDE the Max patch — they are never sent
    over the wire.
    """

    # Mode switches (0-9)
    MODE_SESSION        = 0
    MODE_DRUM_SEQ       = 1
    MODE_MELODIC_SEQ    = 2
    MODE_CHORD          = 3

    # Shift state (10-19)
    SHIFT_LOCKED        = 10  # ()
    SHIFT_UNLOCKED      = 11  # ()

    # Drum sequencer (20-29)
    DRUM_PAGE_SCOPED    = 20  # (page_1based)
    DRUM_PAGE_RANGE     = 21  # (start_1based, end_1based_inclusive)
    DRUM_GRID           = 22  # (resolution_index, is_triplet)
    DRUM_TRIPLET        = 23  # (on)
    DRUM_VELOCITY       = 24  # (velocity)
    DRUM_BOTTOM_RIGHT   = 25  # (mode_index: 0=loop, 1=velocity)
    DRUM_NAV            = 26  # (page_1based, octave, semitone)

    # Melodic sequencer (30-39)
    MELODIC_PAGE_SCOPED = 30  # (page_1based)
    MELODIC_PAGE_RANGE  = 31  # (start_1based, end_1based_inclusive)
    MELODIC_GRID        = 32  # (resolution_index, is_triplet)
    MELODIC_TRIPLET     = 33  # (on)
    MELODIC_SCALE       = 34  # (scale_index)
    MELODIC_CHROMATIC   = 35  # (on)
    MELODIC_PREVIEW     = 36  # (on)
    MELODIC_NAV         = 37  # (page_1based, octave, semitone)
    MELODIC_VELOCITY    = 38  # (velocity)

    # Drum 64-step sequencer (40-49)
    DRUM_64_MATRIX_MODE = 40  # (mode_index: 0=edit, 1=loop_pick, 2=grid_pick)
    DRUM_4_TRACK_MATRIX_MODE = 41  # (mode_index: 0=edit, 1=loop_pick, 2=grid_pick)

    # Chord pad mode (50-59). CHORD_TRIGGERED/RELEASED are NOT on the wire —
    # chord_pitches is variable-length and the dispatcher only carries
    # 3 packed integer args. If a future LP Chord M4L companion needs the
    # full chord, the layout itself must be reconstructed from the *static*
    # (key, scale, type, inversion) state echoed by these IDs.
    CHORD_KEY           = 50  # (key_index 0..11)
    CHORD_SCALE         = 51  # (scale_index)
    CHORD_TYPE          = 52  # (type_index)
    CHORD_INVERSION     = 53  # (inversion 0..3)
    CHORD_NAV           = 54  # (octave, semitone)

    # Edit mode (60-79). Reached via double-tap on shift in session main
    # mode; clip/scene presses while holding the red/green/blue modifier
    # pad delete/duplicate/move the target. Track and scene indices in
    # the payload are 0-based — the .amxd patch is responsible for any
    # 1-based formatting.
    EDIT_MODE_ON          = 60  # ()
    EDIT_MODE_OFF         = 61  # ()
    EDIT_CLIP_DELETED     = 62  # (track, scene)
    EDIT_CLIP_DUPLICATED  = 63  # (track, scene)
    EDIT_CLIP_MOVED       = 64  # arg-packed; the .amxd reads from the
                                # 'from_track/from_scene/to_track/to_scene'
                                # secondary params if it needs all 4 values.
                                # The wire ID alone fires the visual cue.
    EDIT_SCENE_DELETED    = 65  # (scene)
    EDIT_SCENE_DUPLICATED = 66  # (scene)
    EDIT_MOVE_SOURCE_SET  = 67  # (kind: 0=clip, 1=scene)
    EDIT_MOVE_CANCELLED   = 68  # ()
    EDIT_CLIP_COLOR_CYCLED  = 69  # (track, scene, color_index)
    EDIT_SCENE_COLOR_CYCLED = 70  # (scene, color_index)
    EDIT_STOP_ALL_CLIPS     = 71  # ()
    EDIT_UNDO               = 72  # ()
    EDIT_REDO               = 73  # ()

    # Errors (90-99), arg1 discriminates source
    #   0 = drum, 1 = melodic
    ERR_NEED_MIDI_SLOT  = 90  # (mode_id)
    ERR_NEED_MIDI_TRACK = 91  # (mode_id)
    ERR_NOT_MIDI        = 92  # (mode_id)

    # Track pin (100-109). `mode_id` discriminates which sequencer's pin
    # changed (same MODE_ID_* values as the error block above). The track
    # name itself never goes over the wire — the .amxd can read the
    # currently-pinned name from a secondary string param if needed.
    TRACK_PINNED   = 100  # (mode_id)
    TRACK_UNPINNED = 101  # (mode_id)


# Grid resolution index for DRUM_GRID / MELODIC_GRID. The .amxd's secondary
# lookup table maps these integers to strings (e.g. 0 -> "1/32"). Kept here
# as the single source so the M4L subscriber can pack the right value.
GRID_RESOLUTION_INDICES = {
    "1/32": 0,
    "1/16": 1,
    "1/8":  2,
    "1/4":  3,
}


# Mode discriminator for the shared error messages.
MODE_ID_DRUM    = 0
MODE_ID_MELODIC = 1
