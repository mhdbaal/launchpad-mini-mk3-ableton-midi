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

    # Errors (90-99), arg1 discriminates source
    #   0 = drum, 1 = melodic
    ERR_NEED_MIDI_SLOT  = 90  # (mode_id)
    ERR_NEED_MIDI_TRACK = 91  # (mode_id)
    ERR_NOT_MIDI        = 92  # (mode_id)


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
