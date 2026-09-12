from __future__ import absolute_import, print_function, unicode_literals

import Live
import time

from ableton.v2.base import listens, liveobj_valid, task
from ableton.v2.control_surface import Component
from ableton.v2.control_surface.input_control_element import ScriptForwarding

from .events import Event
from .device_profile import SUPPORTS_RGB_LEDS
from .palette import (
    GREY_BRIGHT,
    GREY_DIM,
    GREY_EMPTY,
    GREY_MID,
    MELODIC_COLOR_VALUES,
    RGB_BLACK,
    RGB_WHITE,
    VELOCITY_LEVEL_DIM,
    VELOCITY_LEVEL_PALETTE,
    rgb_shades,
    send_pad_color,
    send_pad_rgb,
)
from .programmer_mode import (
    AUDITION_CHANNEL,
    NOTE_ON_STATUS,
    PROGRAMMER_LED_CHANNEL,
)


STEPS_PER_PAGE = 8
# Step and page lengths are per-instance (self._step_length, self._page_length)
# so the user can switch the step-grid resolution (1/4 .. 1/32) at runtime.
DEFAULT_VELOCITY = 100
DEFAULT_CLIP_PAGES = 8
DOUBLE_TAP_SECONDS = 0.35
BASE_PITCH = 60
MIN_PITCH_OFFSET = -60
MAX_PITCH_OFFSET = 60
PREVIEW_TOGGLE_X = 7
# Row 0 is dual-purpose:
#   - shift NOT held: regular pitch row (degree = 7 - 0 = 7 = octave above root)
#   - shift held    : page selector (x=0..6) + preview toggle (x=7)
# Pitch rows span 0..7 (8 rows), with the root at y=7 and the octave at y=0.
# degree = 7 - y for y in 0..7. With 7 scale notes per octave, degree 7 wraps
# to scale[0] + one octave, so row 0 ends up exactly one octave above row 7.
PREVIEW_TOGGLE_Y = 0
PITCH_ROW_MIN = 0
PITCH_ROW_MAX = 7

# Drum-lane mode: when the selected track carries a Drum Rack, the 8 pitch
# rows stop being a scale and become 8 simultaneous drum lanes — one row per
# drum pad that actually has a device loaded. Same drum-keyboard convention
# as the rest of the codebase: the LOWEST pitch sits on the bottom row
# (y = PITCH_ROW_MAX), the highest on y = 0. Racks with more than 8 used
# pads are scrolled with the octave arrows (a "bank" = DRUM_LANES pads);
# the semitone arrows move the window one pad at a time.
DRUM_LANES = 8

# Lane velocity view: hold a scene button to turn the whole grid into the
# velocity profile of that row. Columns = the 8 steps of the current page,
# rows = 8 velocity levels read bottom-up (grid row 7 = level 1). Velocity is
# `level * LANE_VELOCITY_STEP`, clamped to 127 (level 8 → 127).
#
# Why the scene column: the scene button sits physically at the end of its
# row, so "scene i edits row i" needs no learning. Why 8 levels and not the
# 16 of the step-hold overlay: there are only 8 rows. The two tools split the
# work — this one shapes a whole lane at a glance, the step-hold overlay
# fine-tunes a single note.
#
# MINI CAVEAT: scene 7 is the device shift / stop-solo-mute, owned by the top
# level and untouched by the sequencers, so row 7's lane view is unreachable
# there (use the step-hold overlay for that row). All 8 work on the Pro, where
# shift is a dedicated button.
LANE_VELOCITY_LEVELS = 8
LANE_VELOCITY_STEP = 16

# Push-style note shading: a note's pad takes the CLIP's colour, and velocity
# picks one of NOTE_SHADE_LEVELS evenly-spaced shades of that single hue.
# Everything that is not a note (empty steps, beat markers, playhead, loop,
# held highlight) deliberately stays OUTSIDE the hue on skin colours, so a
# lit pad always means "there is a note here".
#
# This needs the RGB SysEx path (`palette.send_pad_rgb`) — the firmware
# palette only carries 4 unevenly-spaced shades per hue. Set RGB_NOTE_SHADES
# to False to fall back to the old 4-tier skin colours (StepVelGhost/Soft/
# Medium/Loud) if a device turns out not to accept RGB colour specs.
# On devices that accept RGB colour specs (Pro MK3 — the Mini overlay sets
# SUPPORTS_RGB_LEDS False and keeps palette rendering until its script moves
# to its own project), the WHOLE melodic surface follows one rule set:
#
#   clip hue, shaded  = content / chosen value  (note velocity, loop inside,
#                                                current page, selected grid)
#   grey              = nothing / available     (empty step, beat marker,
#                                                unselected option)
#   white             = "now" / held / anchor   (playhead, held cell, range
#                                                anchor)
#
# Consequence worth stating: a coloured pad ALWAYS means something is there.
# Nothing structural borrows the hue.
RGB_NOTE_SHADES = True
NOTE_SHADE_LEVELS = 8
# Floor of the shade ramp. Low enough that a ghost note reads as "barely
# there", high enough that it is still visibly the clip's hue and not black.
NOTE_SHADE_FLOOR = 0.12
DEFAULT_CLIP_COLOR = 0x00FF00  # fallback hue when the clip has no usable colour
MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)

# Curated scale list cycled via slot 6 (SCALE_CYCLE_SLOT). Each entry is a
# (name, intervals) pair. Intervals are semitones from the root, expressed
# as offsets (0..11). Length is variable — pentatonic/blues have fewer than
# 7 notes per octave, so a row whose `degree` modulo len(scale) lands past
# the last index wraps into the next octave just like the diatonic case.
MELODIC_SCALES = (
    ("Major",            (0, 2, 4, 5, 7, 9, 11)),
    ("Minor",            (0, 2, 3, 5, 7, 8, 10)),
    ("Dorian",           (0, 2, 3, 5, 7, 9, 10)),
    ("Mixolydian",       (0, 2, 4, 5, 7, 9, 10)),
    ("Lydian",           (0, 2, 4, 6, 7, 9, 11)),
    ("Phrygian",         (0, 1, 3, 5, 7, 8, 10)),
    ("Locrian",          (0, 1, 3, 5, 6, 8, 10)),
    ("Harmonic Minor",   (0, 2, 3, 5, 7, 8, 11)),
    ("Melodic Minor",    (0, 2, 3, 5, 7, 9, 11)),
    ("Pentatonic Major", (0, 2, 4, 7, 9)),
    ("Pentatonic Minor", (0, 3, 5, 7, 10)),
    ("Blues",            (0, 3, 5, 6, 7, 10)),
)
DEFAULT_SCALE_INDEX = 0  # Major

# Step-grid resolutions. Same 16-cell table as the drum sequencer, laid out
# across the bottom-right 4x4 of the grid when slot 6 is in "grid" mode:
#   Row 0 (binary):   1/4    1/8    1/16   1/32
#   Row 1 (binary):   1/64   1/128  1/256  1/512
#   Row 2 (ternary):  1/4t   1/8t   1/16t  1/32t   ← distinct color
#   Row 3 (ternary):  1/64t  1/128t 1/256t 1/512t
TRIPLET_FACTOR = 2.0 / 3.0
GRID_OPTIONS = (
    (1.0,                "1/4"),
    (0.5,                "1/8"),
    (0.25,               "1/16"),
    (0.125,              "1/32"),
    (0.0625,             "1/64"),
    (0.03125,            "1/128"),
    (0.015625,           "1/256"),
    (0.0078125,          "1/512"),
    (1.0     * TRIPLET_FACTOR, "1/4t"),
    (0.5     * TRIPLET_FACTOR, "1/8t"),
    (0.25    * TRIPLET_FACTOR, "1/16t"),
    (0.125   * TRIPLET_FACTOR, "1/32t"),
    (0.0625  * TRIPLET_FACTOR, "1/64t"),
    (0.03125 * TRIPLET_FACTOR, "1/128t"),
    (0.015625 * TRIPLET_FACTOR, "1/256t"),
    (0.0078125 * TRIPLET_FACTOR, "1/512t"),
)
TERNARY_FIRST_INDEX = 8
DEFAULT_GRID_INDEX = 2  # 1/16
VELOCITY_TIER_BOUNDARIES = (31, 63, 95)
# Step-hold velocity selector: 16 levels overlaid on the bottom 2 rows
# (y=6 and y=7) while at least one cell with a note is held. Level → MIDI
# velocity mapping is `level * 8` clamped to 1..127 (level 16 → 127).
VELOCITY_MIN = 1
VELOCITY_MAX = 127
VELOCITY_OVERLAY_LEVELS = 16
VELOCITY_OVERLAY_ROW_BOTTOM = 7  # levels 1..8
VELOCITY_OVERLAY_ROW_TOP = 6     # levels 9..16
# Hold delay before the velocity overlay arms — short enough to feel
# responsive when the user genuinely wants to edit velocity, long enough
# that brief taps for note toggling don't briefly flash the bar.
VELOCITY_OVERLAY_HOLD_DELAY = 0.25

# Scene-button slot indices in melodic_sequence mode (top → bottom):
#     0: Capture MIDI (shift NOT held) / Chromatic toggle (shift held)
#     1: Quantize Selected (shift NOT held) / Scale cycle (shift held)
#   2-5: free / disabled
#     6: cycle button — bottom-right 4x4 mode: pitch ↔ grid
#     7: device shift
CAPTURE_SLOT = 0
QUANTIZE_SLOT = 1
CHROMATIC_SLOT = CAPTURE_SLOT      # same physical slot, dual-purpose by shift state
SCALE_CYCLE_SLOT = QUANTIZE_SLOT   # same physical slot, dual-purpose
SHIFT_SLOT = 5                     # sequencer shift modifier (parent-owned)
CYCLE_SLOT = 6

# Bottom-right 4x4 modes. Cycled by slot 6. Default = "pitch" (the 4x4 stays
# part of the pitch grid). "grid" repurposes it as a grid resolution selector.
BOTTOM_RIGHT_MODE_PITCH = "pitch"
BOTTOM_RIGHT_MODE_GRID = "grid"

DEFAULT_STEP_LENGTH = GRID_OPTIONS[DEFAULT_GRID_INDEX][0]  # 1/16

class MelodicStepSequencerComponent(Component):
    """Launchpad95-style melodic step sequencer: 7 pitch rows + 1 page row."""

    def __init__(self, event_bus=None, *a, **k):
        super(MelodicStepSequencerComponent, self).__init__(*a, **k)
        self._event_bus = event_bus
        self._grid_matrix = None
        self._clip = None
        self._clip_slot = None
        self._notes = []
        self._page_index = 0
        self._step_length = DEFAULT_STEP_LENGTH
        self._page_length = self._step_length * STEPS_PER_PAGE
        # "Build-out" flag: True only while editing a clip we just created in
        # this session. Auto-extends the loop while True, no-op otherwise.
        # Same semantics as in the drum sequencer.
        self._clip_just_created = False
        # Device shift (scene_launch_buttons_raw[7]) acts as a modifier: while
        # held, the grid-resolution slots 0-3 are active; otherwise greyed.
        self._device_shift_held = False
        # Parent's User button — held = mode selector active, gate scene
        # listener + LED writes (parent paints those slots itself).
        self._user_mode_button = None
        self._loop_press_points = []
        self._loop_range_active = False
        # Step-grid loop range picker — active while device shift is held.
        # Rows 1..7 of the grid double as a sub-page loop selector: only the
        # X coordinate matters; pressing 2 columns scopes the loop on that
        # step range within the current page.
        self._step_loop_press_points = []
        self._step_loop_range_active = False
        self._last_page_tap = (-1, 0)
        self._held_grid_buttons = set()
        # Cells currently held by the user that contain a note (selection
        # anchor for Quantize / future per-note gestures). Maps
        # (x, y) -> (step, pitch, original_start_time). Populated on press,
        # popped on release. None for cells held on empty positions.
        self._held_note_cells = {}
        # (x, y) pairs whose release should NOT toggle the note (consumed by
        # a clip-level gesture, e.g., Quantize). Discarded on release.
        self._consumed_note_cells = set()
        self._preview_mode = False
        self._pitch_offset = 0
        # Drum-lane mode (see DRUM_LANES). `_drum_group_device` is the rack on
        # the selected track, or None for a normal melodic track.
        # `_drum_lane_offset` indexes the used-pad list for the BOTTOM row.
        self._drum_group_device = None
        self._drum_lane_offset = 0
        # Lane velocity view — index of the held scene button (= grid row), or
        # None. `_armed` gates on the hold delay so a quick tap still performs
        # the slot's own action (cycle / capture / quantize) without flashing
        # the view.
        self._lane_velocity_scene = None
        self._lane_velocity_armed = False
        # Cached shade ramp for the current clip colour, darkest first, and the
        # colour it was built from (so we only rebuild when the colour moves).
        # Shade ramps keyed by level count, rebuilt when the clip colour moves.
        self._shade_ramps = {}
        self._note_shade_source = None
        # Open RGB batch: while not None, every RGB write appends here and the
        # whole refresh goes out as one SysEx instead of ~80 messages.
        # `_rgb_batch_depth` makes begin/flush re-entrant so an inner pass
        # (pitch grid, loop row, scene column) joins the outer batch.
        self._rgb_batch = None
        self._rgb_batch_depth = 0
        # Cached result of _scan_used_drum_pads — the LED path reads this.
        self._used_pads = []
        self._control_buttons = ()
        self._control_button_listeners = []
        # Scene-button slot assignments. Defaults are the Mini MK3 layout
        # (module constants); device wiring can remap or disable (None)
        # individual slots via configure_slots(). Chromatic/Capture share a
        # physical slot, as do ScaleCycle/Quantize (dual-purpose by shift).
        self._chromatic_slot = CHROMATIC_SLOT
        self._scale_cycle_slot = SCALE_CYCLE_SLOT
        self._cycle_slot = CYCLE_SLOT
        self._shift_slot = SHIFT_SLOT
        # When True (Pro MK3), the dual-purpose slots act directly:
        # chromatic toggle and scale cycle no longer need shift held,
        # because Capture/Quantize live on dedicated buttons instead of
        # sharing these slots.
        self._direct_slot_actions = False
        self._grid_option_index = DEFAULT_GRID_INDEX
        # Bottom-right 4x4 mode: "pitch" (default — those cells are pitch
        # rows) or "grid" (resolution selector). Cycled via the slot 6 cycle
        # button. Pitch state isn't lost when toggling — it's just hidden.
        self._bottom_right_mode = BOTTOM_RIGHT_MODE_PITCH
        # Pitch-grid mode: False = scale-based (8 rows = 1 octave of the scale),
        # True = chromatic (each row = 1 semitone above the row below). Toggled
        # by CHROMATIC_SLOT while shift is held.
        self._chromatic_mode = False
        # Active scale index into MELODIC_SCALES, cycled by SCALE_CYCLE_SLOT.
        # The previously hardcoded "song.scale_name contains Minor" heuristic
        # is replaced by an explicit, user-controllable list.
        self._scale_index = DEFAULT_SCALE_INDEX
        self._playhead = None
        self._led_debug_count = 0
        self._delayed_update_task = self._tasks.add(task.sequence(task.wait(0.1), task.run(self.update)))
        self._delayed_update_task.kill()
        # Velocity overlay arming: a cell must be held continuously for
        # VELOCITY_OVERLAY_HOLD_DELAY seconds before the bar appears. The
        # task is restarted on every press; the release path disarms when
        # the held set empties.
        self._velocity_overlay_armed = False
        self._lane_velocity_arm_task = self._tasks.add(
            task.sequence(task.wait(VELOCITY_OVERLAY_HOLD_DELAY),
                          task.run(self._arm_lane_velocity)))
        self._lane_velocity_arm_task.kill()
        self._velocity_overlay_arm_task = self._tasks.add(
            task.sequence(task.wait(VELOCITY_OVERLAY_HOLD_DELAY),
                          task.run(self._arm_velocity_overlay)))
        self._velocity_overlay_arm_task.kill()
        self._on_detail_clip_changed.subject = self.song.view
        self._on_selected_track_changed.subject = self.song.view
        self._on_can_capture_midi_changed.subject = self.song

    def disconnect(self):
        self.set_control_buttons(None)
        self.set_grid_matrix(None)
        self._set_clip(None)
        # Drop the rack subscription before teardown.
        self._on_selected_drum_pad_changed.subject = None
        self._drum_group_device = None
        self._used_pads = []
        super(MelodicStepSequencerComponent, self).disconnect()

    def set_control_buttons(self, buttons):
        if self._control_buttons:
            for button, listener in self._control_button_listeners:
                try:
                    button.remove_value_listener(listener)
                except Exception:
                    pass
        self._control_buttons = tuple(buttons) if buttons is not None else ()
        self._control_button_listeners = []
        for index, button in enumerate(self._control_buttons):
            listener = self._make_control_button_listener(index)
            button.add_value_listener(listener)
            self._control_button_listeners.append((button, listener))
        self._update_control_leds()

    def set_grid_matrix(self, matrix):
        if matrix != self._grid_matrix:
            if self._grid_matrix is not None:
                self._grid_matrix.remove_value_listener(self._on_grid_matrix_value)
                self._clear_audition_translations()
            self._grid_matrix = matrix
            if self._grid_matrix is not None:
                self._grid_matrix.add_value_listener(self._on_grid_matrix_value)
            self._request_midi_map_rebuild()
            self._log("grid matrix set: {}x{}".format(matrix.width(), matrix.height()) if matrix is not None else "grid matrix cleared")
            self.update()

    def set_enabled(self, enabled):
        super(MelodicStepSequencerComponent, self).set_enabled(enabled)
        self._log("enabled: {}".format(enabled))
        if enabled:
            self._led_debug_count = 0
            self._clear_audition_translations()
            self._refresh_targets()
            self._delayed_update_task.restart()
            self._update_control_leds()
        else:
            self._delayed_update_task.kill()
            self._playhead = None
            self._held_grid_buttons = set()
            self._held_note_cells = {}
            self._consumed_note_cells = set()
            self._disarm_velocity_overlay()
            self._disarm_lane_velocity()
            self._preview_mode = False
            # Leaving sequencer mode ends "build-out": the next session treats
            # the clip's loop as sacred again.
            self._clip_just_created = False
            self._turn_grid_off()
            self._clear_audition_translations()
            self._turn_control_buttons_off()

    def update(self):
        super(MelodicStepSequencerComponent, self).update()
        if not self.is_enabled():
            return
        # One batch around the three passes: a full refresh is a single SysEx.
        self._begin_rgb_batch()
        try:
            self._update_pitch_leds()
            self._update_loop_leds()
            self._update_control_leds()
        finally:
            self._flush_rgb_batch()

    @listens("detail_clip")
    def _on_detail_clip_changed(self):
        if self.is_enabled():
            # The clip may have moved to another track — re-resolve the rack
            # too, not just the clip.
            self._refresh_targets()

    @listens("selected_track")
    def _on_selected_track_changed(self):
        if self.is_enabled():
            self._refresh_targets()

    @listens("selected_drum_pad")
    def _on_selected_drum_pad_changed(self):
        """Live's rack selection moved. Repaint the lane anchor, and take the
        opportunity to refresh the used-pad cache — loading a sound into an
        empty pad usually goes through selecting it."""
        if self.is_enabled():
            self._rescan_drum_pads()
            self.update()

    @listens("color")
    def _on_clip_color_changed(self):
        """Recolouring a clip in Live restyles the whole sequencer."""
        self._shade_ramps = {}
        self._note_shade_source = None
        if self.is_enabled():
            self.update()

    @listens("can_capture_midi")
    def _on_can_capture_midi_changed(self):
        if self.is_enabled():
            self._update_control_leds()

    @listens("notes")
    def _on_clip_notes_changed(self):
        if self.is_enabled():
            self._refresh_notes()
            self.update()

    @listens("playing_position")
    def _on_playing_position_changed(self):
        if self.is_enabled():
            if liveobj_valid(self._clip) and self._clip.is_playing and self.song.is_playing:
                self._playhead = self._clip.playing_position
            else:
                self._playhead = None
            self._update_pitch_leds()
            self._update_loop_leds()

    @listens("playing_status")
    def _on_playing_status_changed(self):
        self._on_playing_position_changed()

    @listens("loop_start")
    def _on_loop_changed(self):
        if self.is_enabled():
            self._update_loop_leds()
            # Rows 1..7 show the loop backdrop while shift is held — refresh
            # them so external loop changes are reflected immediately.
            if self._device_shift_held:
                self._update_pitch_leds()

    @listens("loop_end")
    def _on_loop_end_changed(self):
        self._on_loop_changed()

    # --- Drum-lane detection -------------------------------------------

    def _target_track(self):
        """Track whose rack drives the lanes.

        The clip comes from `song.view.detail_clip`, which does NOT have to
        live on `song.view.selected_track` — Live keeps the detail clip open
        when you select another track. Resolving the rack from the selected
        track while editing someone else's clip is how the sequencer ended up
        writing scale pitches (C/D/F) into a drum clip. Follow the clip first,
        fall back to the selected track when there is no clip yet."""
        clip = self._clip
        if liveobj_valid(clip):
            try:
                # clip → clip slot → track
                slot = clip.canonical_parent
                track = slot.canonical_parent if slot is not None else None
                if liveobj_valid(track):
                    return track
            except Exception:
                pass
        return self.song.view.selected_track

    def _refresh_targets(self):
        """Resolve the Drum Rack for the target track, then the clip.

        Called wherever the selected track, the detail clip, or the rack's
        contents can have changed. Switching racks resets the lane window —
        pad indices from the previous rack mean nothing in the new one."""
        was_drum = self._drum_lane_mode()
        self._resolve_clip()
        track = self._target_track()
        drum_group = self._find_drum_group_device(track)
        self._log("target track: {}, drum group: {}".format(
            getattr(track, "name", "<none>"),
            getattr(drum_group, "name", "<none>")))
        if drum_group != self._drum_group_device:
            self._drum_group_device = drum_group
            self._on_selected_drum_pad_changed.subject = (
                drum_group.view if liveobj_valid(drum_group) else None)
            self._drum_lane_offset = 0
            # Row → pitch just changed meaning; drop in-flight cell state so a
            # release can't write a note on a lane that no longer exists.
            self._held_grid_buttons = set()
            self._held_note_cells = {}
            self._consumed_note_cells = set()
        self._rescan_drum_pads()
        self._log("drum lanes: {} used pad(s)".format(len(self._used_pads)))
        is_drum = self._drum_lane_mode()
        if is_drum != was_drum:
            self._emit(Event.MELODIC_DRUM_MODE,
                       active=is_drum,
                       count=len(self._used_pads))
            if self._preview_mode:
                self._update_audition_translations()
        self.update()

    def _find_drum_group_device(self, track):
        if not liveobj_valid(track):
            return None
        for device in track.devices:
            drum_group = self._find_drum_group_device_in_device(device)
            if liveobj_valid(drum_group):
                return drum_group
        return None

    def _find_drum_group_device_in_device(self, device):
        if not liveobj_valid(device):
            return None
        if getattr(device, "can_have_drum_pads", False):
            return device
        if getattr(device, "can_have_chains", False):
            for chain in device.chains:
                for nested_device in chain.devices:
                    nested = self._find_drum_group_device_in_device(nested_device)
                    if liveobj_valid(nested):
                        return nested
        return None

    def _scan_used_drum_pads(self):
        """Drum pads that actually have a device loaded, lowest pitch first.
        This is the whole point of the mode: rows map to *used* pads, so an
        808 kit with 9 sounds fills 8 rows instead of scattering them across
        a chromatic keyboard.

        Walks all 128 rack pads — call it from `_rescan_drum_pads`, never from
        the LED path (`_update_pitch_leds` resolves a pitch per row and a
        color per cell, so a scan per call would be ~10k iterations on every
        playhead tick)."""
        if not liveobj_valid(self._drum_group_device):
            return []
        used = []
        for pad in self._drum_group_device.drum_pads:
            if liveobj_valid(pad) and getattr(pad, "chains", None):
                if len(pad.chains) > 0:
                    used.append(pad)
        used.sort(key=lambda p: p.note)
        return used

    def _rescan_drum_pads(self):
        """Refresh the used-pad cache. Cheap enough to call on any event that
        can change the rack's contents (track change, clip change, pad
        selection, mode enable); everything else reads the cache."""
        self._used_pads = self._scan_used_drum_pads()

    def _used_drum_pads(self):
        """Cached view of the rack — see `_rescan_drum_pads`."""
        return self._used_pads

    def _drum_lane_mode(self):
        return liveobj_valid(self._drum_group_device) and bool(self._used_pads)

    def _visible_drum_pads(self):
        """Up to DRUM_LANES pads for the current window. Index 0 = bottom row
        (y = PITCH_ROW_MAX). Shorter than DRUM_LANES when the rack has fewer
        used pads than rows — the extra rows render dead."""
        used = self._used_drum_pads()
        start = self._clamped_lane_offset(len(used))
        return used[start:start + DRUM_LANES]

    def _clamped_lane_offset(self, total=None):
        if total is None:
            total = len(self._used_drum_pads())
        return max(0, min(self._drum_lane_offset, max(0, total - DRUM_LANES)))

    def _selected_drum_pad_note(self):
        """Note of the pad Live currently has selected in the rack, or None.
        Used as the lane anchor (renders in the Root color)."""
        if not liveobj_valid(self._drum_group_device):
            return None
        try:
            pad = self._drum_group_device.view.selected_drum_pad
        except Exception:
            return None
        return pad.note if liveobj_valid(pad) else None

    def _scroll_drum_lanes(self, delta):
        total = len(self._used_drum_pads())
        current = self._clamped_lane_offset(total)
        limit = max(0, total - DRUM_LANES)
        target = max(0, min(current + delta, limit))
        if target == current:
            return
        self._drum_lane_offset = target
        # The window moved: cells now mean different pitches.
        self._held_grid_buttons = set()
        self._held_note_cells = {}
        self._consumed_note_cells = set()
        if self._preview_mode:
            self._update_audition_translations()
        visible = self._visible_drum_pads()
        self._emit(Event.MELODIC_DRUM_LANES,
                   first=(target + 1),
                   last=(target + len(visible)),
                   total=total)
        self.update()

    def _resolve_clip(self):
        """Clip resolution without the repaint — `_refresh_targets` needs the
        clip settled before it can work out which track's rack to read, and
        painting in between would render one frame from a stale lane cache."""
        clip_slot = self._selected_clip_slot()
        clip = None
        detail_clip = self.song.view.detail_clip
        if liveobj_valid(detail_clip) and detail_clip.is_midi_clip:
            clip = detail_clip
        elif clip_slot is not None and clip_slot.has_clip and clip_slot.clip.is_midi_clip:
            clip = clip_slot.clip
        self._clip_slot = clip_slot
        self._set_clip(clip)

    def _refresh_clip(self):
        self._resolve_clip()
        self.update()

    def _set_clip(self, clip):
        if clip != self._clip:
            self._clip = clip
            self._on_clip_notes_changed.subject = clip
            self._on_playing_position_changed.subject = clip
            self._on_playing_status_changed.subject = clip
            self._on_loop_changed.subject = clip
            self._on_loop_end_changed.subject = clip
            self._on_clip_color_changed.subject = clip
            # A new clip means a new hue — drop the cached shade ramp.
            self._shade_ramps = {}
            self._note_shade_source = None
            # Different clip — drop "just created" state. _ensure_clip's
            # create path re-sets it after this call when relevant.
            self._clip_just_created = False
        self._refresh_notes()

    def _selected_clip_slot(self):
        slot = self.song.view.highlighted_clip_slot
        return slot if slot is not None else None

    def _ensure_clip(self):
        if liveobj_valid(self._clip) and self._clip.is_midi_clip:
            return True
        slot = self._selected_clip_slot()
        if slot is None:
            self._emit(Event.ERR_NEED_MIDI_SLOT, mode="melodic")
            return False
        if slot.has_clip:
            if slot.clip.is_midi_clip:
                self.song.view.detail_clip = slot.clip
                self._set_clip(slot.clip)
                return True
            self._emit(Event.ERR_NOT_MIDI, mode="melodic")
            return False
        if not self._selected_track_can_hold_midi():
            self._emit(Event.ERR_NEED_MIDI_TRACK, mode="melodic")
            return False
        try:
            slot.create_clip(self._page_length * DEFAULT_CLIP_PAGES)
            self.song.view.detail_clip = slot.clip
            self._clip_slot = slot
            self._set_clip(slot.clip)
            # Mark as just-created so the initial note adds + page navigation
            # are allowed to auto-extend the loop during build-out.
            self._clip_just_created = True
            # Push-2 style: firing the newly-created slot starts playback
            # immediately so the user hears their first note without manually
            # hitting play.
            try:
                slot.fire()
                self._log("fired newly-created clip")
            except Exception as exc:
                self._log("clip fire failed: {}".format(exc))
            return True
        except RuntimeError:
            return False

    def _refresh_notes(self):
        if liveobj_valid(self._clip):
            loop_end = max(self._clip.loop_end, self._page_length * DEFAULT_CLIP_PAGES)
            self._notes = list(self._clip.get_notes_extended(from_time=0,
              from_pitch=0,
              time_span=loop_end,
              pitch_span=128))
        else:
            self._notes = []

    def _on_grid_matrix_value(self, value, x, y, is_momentary):
        if not self.is_enabled():
            return
        # Lane velocity view owns the whole grid while a scene is held. Press
        # sets the velocity; release is a no-op (the bar must not ghost-toggle).
        if self._lane_velocity_active():
            if value:
                self._handle_lane_velocity_press(x, y)
            return
        if y == PREVIEW_TOGGLE_Y and self._device_shift_held:
            # Top row in shift-active state = page selector + preview toggle.
            if x == PREVIEW_TOGGLE_X:
                if value:
                    self._toggle_preview_mode()
                return
            self._handle_loop_press(x, bool(value))
            return
        # Shift-gated: rows 1..7 become a sub-page step-range picker. Only X
        # matters (Y is ignored). This overrides preview mode and the grid
        # cycle mode: while shift is held the grid is a loop picker, period.
        # Fires on press AND release for the single-tap-vs-range distinction.
        if self._device_shift_held and PITCH_ROW_MIN <= y <= PITCH_ROW_MAX:
            self._handle_step_loop_press(x, bool(value))
            return
        # Step-hold velocity selector: once a cell has been held past the
        # arm delay, the bottom two rows (y=6, y=7) become a 16-level
        # velocity bar. Wins over both pitch toggling and the bottom-right
        # grid-resolution selector. Press = apply velocity; release of a
        # bar-tap is a no-op. Release of a cell that was ALREADY held
        # before the overlay armed falls through to the pitch handler
        # below so held tracking gets cleaned up.
        if self._velocity_overlay_should_show() and y in (
                VELOCITY_OVERLAY_ROW_TOP, VELOCITY_OVERLAY_ROW_BOTTOM):
            if value:
                level = self._velocity_overlay_cell_to_level(x, y)
                if level is not None:
                    self._apply_velocity_from_selector(level)
                return
            if (x, y) not in self._held_grid_buttons:
                return
            # else fall through to the pitch release path
        # Bottom-right 4x4 in "grid" mode = resolution selector (overrides
        # pitch). Routed before the pitch path; shift gestures above already
        # returned, so this is "no shift" by elimination.
        if (self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID
                and y >= 4 and x >= 4):
            index = (y - 4) * 4 + (x - 4)
            self._handle_grid_cell_press(index, bool(value))
            return
        # Otherwise (shift not held) treat as a pitch row. Preview mode keeps
        # auditioning the pad; we still track press/release for the "selection
        # via hold" gesture used by clip actions (Quantize) — but we don't
        # toggle a note in preview mode (the pad is for playing, not editing).
        pitch = self._pitch_for_row(y)
        if pitch is None:
            # Drum-lane mode, row past the end of the rack — dead cell.
            # Bail on both edges: a dead row is never tracked on press, so
            # there is nothing for a release to undo either.
            return
        step = self._page_index * STEPS_PER_PAGE + x
        if not value:
            # Release. Ignore if we never recorded the press (stray edge).
            if (x, y) not in self._held_grid_buttons:
                return
            self._held_grid_buttons.discard((x, y))
            self._held_note_cells.pop((x, y), None)
            consumed = (x, y) in self._consumed_note_cells
            self._consumed_note_cells.discard((x, y))
            if not self._held_grid_buttons:
                self._disarm_velocity_overlay()
            self.update()  # repaint to drop StepHeld
            if consumed or self._preview_mode:
                return
            if self._ensure_clip():
                self._toggle_note(step, pitch)
            return
        # Press path — dedupe sustained MIDI events.
        if (x, y) in self._held_grid_buttons:
            return
        self._held_grid_buttons.add((x, y))
        # Restart the velocity-overlay arm timer on every press. Brief
        # taps disarm via the release path before the timer fires.
        self._velocity_overlay_arm_task.restart()
        self._log("grid pressed: {},{} pitch={} step={}".format(x, y, pitch, step))
        # Record selection if the pad maps to an existing note. The toggle
        # itself happens on release (see above) — pressing the pad is the
        # start of a potential clip-action gesture (Quantize).
        note = self._find_note_at_step_pitch(step, pitch)
        if note is not None:
            self._held_note_cells[(x, y)] = (step, pitch, note.start_time)
        self.update()  # repaint to show StepHeld

    def _handle_grid_cell_press(self, index, pressed):
        """Cell press in the bottom-right 4x4 while in 'grid' mode. Selects
        the corresponding entry from `GRID_OPTIONS`."""
        if not pressed:
            return
        self._set_grid_option(index)

    def _grid_cell_color(self, index):
        """LED color for a grid-resolution cell in the bottom-right 4x4 while
        in 'grid' mode. Currently-selected cell is bright (WHITE). Binary
        cells (0..7) = ORANGE_HALF. Ternary cells (8..15) = PURPLE to flag
        them at a glance."""
        if self._rgb_leds():
            if not 0 <= index < len(GRID_OPTIONS):
                return RGB_BLACK
            if index == self._grid_option_index:
                return self._shade(NOTE_SHADE_LEVELS)
            # Ternary options sit one grey brighter than binary ones — the
            # hue is reserved for the chosen value, so the binary/ternary
            # distinction moves onto the grey ramp.
            return GREY_MID if index >= TERNARY_FIRST_INDEX else GREY_DIM
        if not 0 <= index < len(GRID_OPTIONS):
            return "DefaultButton.Disabled"
        if index == self._grid_option_index:
            return "MelodicSequencer.Control.GridSelected"
        if index >= TERNARY_FIRST_INDEX:
            return "MelodicSequencer.Control.GridTernary"
        return "MelodicSequencer.Control.Grid"

    def _handle_loop_press(self, index, pressed):
        if pressed:
            if index not in self._loop_press_points:
                self._loop_press_points.append(index)
            if len(self._loop_press_points) >= 2:
                start = min(self._loop_press_points)
                end = max(self._loop_press_points) + 1
                self._set_loop_pages(start, end)
                self._loop_range_active = True
                self._emit(Event.MELODIC_PAGE_SCOPED, start=start + 1, end=end)
            self._update_loop_leds()
        else:
            was_range_active = self._loop_range_active
            if index in self._loop_press_points:
                self._loop_press_points.remove(index)
            if was_range_active:
                if not self._loop_press_points:
                    self._loop_range_active = False
                self.update()
                return
            if self._is_page_double_tap(index):
                self._scope_page(index)
            else:
                self._page_index = index
                if self._ensure_clip():
                    self._select_page(index)
            self.update()

    def _handle_step_loop_press(self, step, pressed):
        """Sub-page loop scoping on the X axis of the grid while shift is held.
        Mirror of `_handle_loop_press` but operating on step columns within the
        currently-viewed page. Single tap = loop on that 1 step;
        hold + press another = scope on [min..max+1]."""
        if pressed:
            if step not in self._step_loop_press_points:
                self._step_loop_press_points.append(step)
            self._log("step loop pressed: {}".format(step))
            if len(self._step_loop_press_points) >= 2:
                start = min(self._step_loop_press_points)
                end = max(self._step_loop_press_points) + 1
                self._set_step_loop_in_current_page(start, end)
                self._step_loop_range_active = True
                self._emit(Event.MELODIC_STEP_LOOP_SCOPED,
                           page=self._page_index + 1,
                           start_step=start + 1,
                           end_step=end,
                           label=self._current_grid_label())
            self._update_pitch_leds()
        else:
            # Guard: ignore stray releases when no matching anchor was
            # registered (e.g., user pressed step without shift then engaged
            # shift before release — we don't want to scope a phantom loop).
            if step not in self._step_loop_press_points and not self._step_loop_range_active:
                return
            was_range_active = self._step_loop_range_active
            if step in self._step_loop_press_points:
                self._step_loop_press_points.remove(step)
            if was_range_active:
                if not self._step_loop_press_points:
                    self._step_loop_range_active = False
                self._update_pitch_leds()
                return
            self._set_step_loop_in_current_page(step, step + 1)
            self._emit(Event.MELODIC_STEP_LOOP_SCOPED,
                       page=self._page_index + 1,
                       start_step=step + 1,
                       end_step=step + 1,
                       label=self._current_grid_label())
            self._update_pitch_leds()

    def _set_step_loop_in_current_page(self, start_step, end_step):
        if self._ensure_clip():
            page_start = self._page_index * self._page_length
            self._set_clip_loop(page_start + start_step * self._step_length,
                                page_start + end_step * self._step_length)
            self._clip_just_created = False

    def _toggle_note(self, step, pitch):
        start = step * self._step_length
        if self._step_has_pitch(step, pitch):
            self._clip.remove_notes_extended(from_time=start,
              from_pitch=pitch,
              time_span=self._step_length,
              pitch_span=1)
            self._log("note removed: pitch={} start={}".format(pitch, start))
        else:
            note = Live.Clip.MidiNoteSpecification(pitch=pitch,
              start_time=start,
              duration=self._step_length,
              velocity=DEFAULT_VELOCITY,
              mute=False)
            self._clip.add_new_notes((note,))
            self._clip.deselect_all_notes()
            self._ensure_loop_contains_time(start + self._step_length)
            self._log("note added: pitch={} start={}".format(pitch, start))
        self._refresh_notes()
        self.update()

    def _step_has_pitch(self, step, pitch):
        start = step * self._step_length
        end = start + self._step_length
        for note in self._notes:
            if note.pitch == pitch and start <= note.start_time < end:
                return True
        return False

    def _set_loop_pages(self, start_page, end_page):
        if self._ensure_clip():
            self._page_index = start_page
            self._set_clip_loop(start_page * self._page_length, end_page * self._page_length)
            self._clip_just_created = False

    def _scope_page(self, page):
        if self._ensure_clip():
            self._page_index = page
            self._set_clip_loop(page * self._page_length, (page + 1) * self._page_length)
            self._clip_just_created = False
            self._emit(Event.MELODIC_PAGE_SCOPED, start=page + 1, end=page + 1)

    def _is_page_double_tap(self, page):
        now = time.time()
        last_page, last_time = self._last_page_tap
        self._last_page_tap = (page, now)
        return last_page == page and now - last_time <= DOUBLE_TAP_SECONDS

    def _select_page(self, page):
        if liveobj_valid(self._clip):
            self._ensure_loop_contains_time((page + 1) * self._page_length)

    def _ensure_loop_contains_time(self, end_time):
        # Auto-extension is gated by `_clip_just_created`. Once the user has
        # established a loop or opened an existing clip, the loop is sacred —
        # notes added past loop_end are still written but the loop stays put.
        if not liveobj_valid(self._clip):
            return
        if not self._clip_just_created:
            return
        if end_time > self._clip.loop_end:
            self._set_clip_loop(self._clip.loop_start, end_time)

    def _set_clip_loop(self, start, end):
        if not liveobj_valid(self._clip):
            return
        if start >= self._clip.loop_end:
            self._clip.loop_end = end
            self._clip.loop_start = start
        else:
            self._clip.loop_start = start
            self._clip.loop_end = end
        self._clip.start_marker = start
        self._clip.end_marker = end

    def _pitch_for_row(self, y):
        # Drum-lane mode wins over both scale modes: one row per used drum
        # pad, lowest at the bottom. Returns None for rows past the end of
        # the rack — callers render those dead and ignore presses.
        if self._drum_lane_mode():
            pads = self._visible_drum_pads()
            index = PITCH_ROW_MAX - y
            if 0 <= index < len(pads):
                return pads[index].note
            return None
        # Two modes:
        #   - scale (default): 8 rows = 1 octave of the current scale.
        #     `degree = PITCH_ROW_MAX - y` puts the root at y=7 (degree 0) and
        #     wraps via the scale array for higher rows; degree 7 lands on
        #     `scale[0] + 12` = octave above root.
        #   - chromatic: each row = 1 semitone. y=7 = root, y=6 = root+1, etc.
        #     Lets the user move existing notes by exactly one row when the
        #     semitone arrows are pressed.
        root = self._root_pitch()
        if self._chromatic_mode:
            return root + (PITCH_ROW_MAX - y)
        scale = self._current_scale()
        degree = PITCH_ROW_MAX - y
        return root + scale[degree % len(scale)] + 12 * int(degree / len(scale))

    def _current_scale(self):
        return MELODIC_SCALES[self._scale_index][1]

    def _current_scale_name(self):
        return MELODIC_SCALES[self._scale_index][0]

    def _root_pitch(self):
        root_note = getattr(self.song, "root_note", 0) or 0
        return BASE_PITCH + int(root_note) + self._pitch_offset

    def _update_pitch_leds(self):
        """Repaint the grid. The whole pass rides in one RGB batch so a full
        refresh costs a single SysEx instead of 64 Note On messages."""
        if self._grid_matrix is None:
            return
        self._begin_rgb_batch()
        try:
            self._paint_pitch_leds()
        finally:
            self._flush_rgb_batch()

    def _paint_pitch_leds(self):
        # When shift is held: row 0 is the page selector (owned by
        # _update_loop_leds), and rows 1..7 become a step range picker
        # backdrop — each column lit Inside/Outside per the clip loop in the
        # current page (Y ignored, all rows in a column share the same color).
        # _update_loop_leds keeps owning row 0; we cover rows 1..7 here.
        # When shift is NOT held: every row 0..7 is a pitch row, except that
        # the bottom-right 4x4 may be overridden when the slot 6 cycle is in
        # "grid" mode (each of those cells displays a grid-resolution option).
        if self._lane_velocity_active():
            self._render_lane_velocity()
            return
        if self._device_shift_held:
            for y in range(PITCH_ROW_MIN + 1, PITCH_ROW_MAX + 1):
                for x in range(8):
                    self._set_grid_light(x, y, self._step_loop_color(x))
            return
        overlay_active = self._velocity_overlay_should_show()
        grid_mode = self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID
        for y in range(PITCH_ROW_MIN, PITCH_ROW_MAX + 1):
            # Velocity overlay claims rows 6 and 7 (full width) — skip the
            # pitch render for those rows so writes don't fight. Overlay
            # writes happen after the loop below.
            if overlay_active and y in (
                    VELOCITY_OVERLAY_ROW_TOP, VELOCITY_OVERLAY_ROW_BOTTOM):
                continue
            pitch = self._pitch_for_row(y)
            if pitch is None:
                dead = RGB_BLACK if self._rgb_leds() else "DefaultButton.Disabled"
                for x in range(8):
                    self._set_grid_light(x, y, dead)
                continue
            for x in range(8):
                if grid_mode and y >= 4 and x >= 4:
                    index = (y - 4) * 4 + (x - 4)
                    self._set_grid_light(x, y, self._grid_cell_color(index))
                    continue
                step = self._page_index * STEPS_PER_PAGE + x
                self._set_grid_light(x, y, self._pitch_color(step, pitch, x))
        if overlay_active:
            self._render_velocity_overlay()

    def _step_loop_color(self, step):
        if self._rgb_leds():
            return self._step_loop_rgb(step)
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return "MelodicSequencer.NoClip"
        if step in self._step_loop_press_points:
            return "MelodicSequencer.Loop.RangeEdit"
        abs_step = self._page_index * STEPS_PER_PAGE + step
        if self._playhead_is_on_step(abs_step):
            return "MelodicSequencer.Loop.Playhead"
        if liveobj_valid(self._clip):
            time = abs_step * self._step_length
            if self._clip.loop_start <= time < self._clip.loop_end:
                return "MelodicSequencer.Loop.Inside"
        return "MelodicSequencer.Loop.Outside"

    def _step_loop_rgb(self, step):
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return GREY_EMPTY
        if step in self._step_loop_press_points:
            return RGB_WHITE
        abs_step = self._page_index * STEPS_PER_PAGE + step
        if self._playhead_is_on_step(abs_step):
            return RGB_WHITE
        if liveobj_valid(self._clip):
            time = abs_step * self._step_length
            if self._clip.loop_start <= time < self._clip.loop_end:
                # Mid shade: the loop is content, but it must not compete with
                # the notes drawn on top of it in the normal view.
                return self._shade(3)
        return GREY_EMPTY

    def _pitch_color(self, step, pitch, x):
        if self._rgb_leds():
            return self._pitch_rgb(step, pitch, x)
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return "MelodicSequencer.NoClip"
        color = "MelodicSequencer.StepBeat" if x == 0 or x == 4 else "MelodicSequencer.StepEmpty"
        if self._drum_lane_mode():
            # No scale root here — anchor on the pad Live has selected in the
            # rack, so the user can tell which lane is which at a glance.
            if pitch == self._selected_drum_pad_note():
                color = "MelodicSequencer.Root"
        elif pitch % 12 == self._root_pitch() % 12:
            color = "MelodicSequencer.Root"
        note = self._find_note_at_step_pitch(step, pitch)
        if note is not None:
            color = self._velocity_color_for(int(note.velocity))
        # Held cell highlight overrides velocity color; playhead still wins.
        if self._is_cell_held(step, pitch):
            color = "MelodicSequencer.StepHeld"
        if self._playhead_is_on_step(step):
            color = "MelodicSequencer.PlayheadActive" if note is not None else "MelodicSequencer.Playhead"
        return color

    def _pitch_rgb(self, step, pitch, x):
        """Step-grid cell under the hue/grey/white rule set. Precedence, most
        specific first: playhead, held, note, anchor row, beat marker, empty."""
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return GREY_EMPTY
        note = self._find_note_at_step_pitch(step, pitch)
        if self._playhead_is_on_step(step):
            # Over a note the playhead goes full white; over empty space it is
            # only a bright grey, so the column reads as "here" without
            # pretending there is content.
            return RGB_WHITE if note is not None else GREY_BRIGHT
        if self._is_cell_held(step, pitch):
            return RGB_WHITE
        if note is not None:
            return self._shade_for_velocity(note.velocity)
        if self._is_anchor_pitch(pitch):
            return GREY_MID
        return GREY_DIM if x in (0, 4) else GREY_EMPTY

    def _find_note_at_step_pitch(self, step, pitch):
        start = step * self._step_length
        end = start + self._step_length
        for note in self._notes:
            if note.pitch == pitch and start <= note.start_time < end:
                return note
        return None

    def _is_cell_held(self, step, pitch):
        for cell_info in self._held_note_cells.values():
            if cell_info[0] == step and cell_info[1] == pitch:
                return True
        return False

    def _velocity_color_for(self, velocity):
        """Same 4-tier classification as the drum sequencer."""
        if velocity <= VELOCITY_TIER_BOUNDARIES[0]:
            return "MelodicSequencer.StepVelGhost"
        if velocity <= VELOCITY_TIER_BOUNDARIES[1]:
            return "MelodicSequencer.StepVelSoft"
        if velocity <= VELOCITY_TIER_BOUNDARIES[2]:
            return "MelodicSequencer.StepVelMedium"
        return "MelodicSequencer.StepVelLoud"

    def _update_loop_leds(self):
        if self._grid_matrix is None:
            return
        # Top row only renders the page selector when shift is active. When
        # shift isn't held/locked, row 0 is a normal pitch row and is rendered
        # by _update_pitch_leds (which always iterates the full 0..7 range).
        if not self._device_shift_held or self._lane_velocity_active():
            return
        for x in range(8):
            self._set_grid_light(x, PREVIEW_TOGGLE_Y, self._loop_color(x))

    def _loop_color(self, index):
        if self._rgb_leds():
            return self._loop_rgb(index)
        if index == PREVIEW_TOGGLE_X:
            return "MelodicSequencer.Preview.On" if self._preview_mode else "MelodicSequencer.Preview.Off"
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return "MelodicSequencer.NoClip"
        if index in self._loop_press_points:
            return "MelodicSequencer.Loop.RangeEdit"
        if self._playhead_is_on_page(index):
            return "MelodicSequencer.Loop.Playhead"
        if index == self._page_index:
            return "MelodicSequencer.Loop.Selected"
        if liveobj_valid(self._clip):
            start = index * self._page_length
            if self._clip.loop_start <= start < self._clip.loop_end:
                return "MelodicSequencer.Loop.Inside"
        return "MelodicSequencer.Loop.Outside"

    def _loop_rgb(self, index):
        if index == PREVIEW_TOGGLE_X:
            return self._shade(NOTE_SHADE_LEVELS) if self._preview_mode else GREY_DIM
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return GREY_EMPTY
        if index in self._loop_press_points:
            return RGB_WHITE
        if self._playhead_is_on_page(index):
            return RGB_WHITE
        if index == self._page_index:
            return self._shade(NOTE_SHADE_LEVELS)
        if liveobj_valid(self._clip):
            start = index * self._page_length
            if self._clip.loop_start <= start < self._clip.loop_end:
                return self._shade(3)
        return GREY_EMPTY

    def _playhead_is_on_step(self, step):
        if self._playhead is None:
            return False
        start = step * self._step_length
        return start <= self._playhead < start + self._step_length

    def _playhead_is_on_page(self, page):
        if self._playhead is None:
            return False
        start = page * self._page_length
        return start <= self._playhead < start + self._page_length

    def _clear_audition_translations(self):
        if self._grid_matrix is None:
            return
        for y in range(8):
            for x in range(8):
                button = self._get_grid_button(x, y)
                if button is not None:
                    button.use_default_message()
                    button.script_forwarding = ScriptForwarding.exclusive
        self._request_midi_map_rebuild()

    def _toggle_preview_mode(self):
        self._preview_mode = not self._preview_mode
        self._held_grid_buttons = set()
        if self._preview_mode:
            self._update_audition_translations()
        else:
            self._clear_audition_translations()
        self._emit(Event.MELODIC_PREVIEW_MODE, on=self._preview_mode)
        self.update()

    def _update_audition_translations(self):
        if self._grid_matrix is None or not self.is_enabled():
            return
        # Audition on AUDITION_CHANNEL (=1, not 0). Translated pitches collide
        # on the forwarding registry with original_identifier values of OTHER
        # pads in the matrix when both sit on channel 0; using a distinct
        # channel makes (channel, identifier) keys disjoint. Same fix as
        # drum_step_sequencer.py.
        # First reset every pad so a previous translation can't leak (e.g.,
        # row 0 was previously translated as a pitch row, but the user just
        # held shift and we want it to act as the page selector now).
        for y in range(8):
            for x in range(8):
                button = self._get_grid_button(x, y)
                if button is not None:
                    button.use_default_message()
                    button.script_forwarding = ScriptForwarding.exclusive
        # When the device shift is active, the entire grid becomes a loop-edit
        # surface (row 0 = page selector, rows 1..7 = step range picker) — no
        # row should audition, otherwise pressing a loop pad would play a
        # rogue note on the track. Drop every translation in that case.
        if self._device_shift_held:
            self._request_midi_map_rebuild()
            return
        for y in range(PITCH_ROW_MIN, PITCH_ROW_MAX + 1):
            pitch = self._pitch_for_row(y)
            if pitch is None:
                continue
            for x in range(8):
                button = self._get_grid_button(x, y)
                if button is not None:
                    button.set_identifier(pitch)
                    button.set_channel(AUDITION_CHANNEL)
                    button.script_forwarding = ScriptForwarding.non_consuming
        self._request_midi_map_rebuild()

    # --- Lane velocity view (hold a scene button) -----------------------

    def _lane_velocity_active(self):
        """True while the view owns the grid. Shift wins over it — shift turns
        the whole grid into a loop picker, and two surfaces cannot share it."""
        return self._lane_velocity_armed and not self._device_shift_held

    def _arm_lane_velocity(self):
        if not self.is_enabled() or self._lane_velocity_scene is None:
            return
        if self._device_shift_held or self._lane_velocity_armed:
            return
        self._lane_velocity_armed = True
        # Holding a scene means "look at this lane", not "keep editing steps":
        # drop step state so a stale release can't toggle a note underneath.
        self._held_grid_buttons = set()
        self._held_note_cells = {}
        self._consumed_note_cells = set()
        self._disarm_velocity_overlay()
        self._emit(Event.MELODIC_LANE_VELOCITY_VIEW,
                   name=self._lane_name(self._lane_velocity_scene))
        self.update()

    def _disarm_lane_velocity(self):
        self._lane_velocity_arm_task.kill()
        self._lane_velocity_scene = None
        if self._lane_velocity_armed:
            self._lane_velocity_armed = False
            if self.is_enabled():
                self.update()

    def _lane_name(self, y):
        """Human label for a row: the drum pad's name on a rack, otherwise the
        note name. Used for the status bar only."""
        pitch = self._pitch_for_row(y)
        if pitch is None:
            return "empty"
        if self._drum_lane_mode():
            for pad in self._used_pads:
                if pad.note == pitch:
                    name = getattr(pad, "name", None)
                    if name:
                        return name
                    break
        names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        return "{}{}".format(names[pitch % 12], int(pitch / 12) - 2)

    def _lane_velocity_cell_to_level(self, y):
        """Grid row → level 1..8, read bottom-up (row 7 = level 1)."""
        if not PITCH_ROW_MIN <= y <= PITCH_ROW_MAX:
            return None
        return PITCH_ROW_MAX - y + 1

    def _velocity_for_lane_level(self, level):
        return max(VELOCITY_MIN,
                   min(VELOCITY_MAX, level * LANE_VELOCITY_STEP))

    def _lane_level_for_velocity(self, velocity):
        """Inverse, rounding up so any audible note lights at least level 1."""
        return max(1, min(LANE_VELOCITY_LEVELS,
                          -(-int(velocity) // LANE_VELOCITY_STEP)))

    def _handle_lane_velocity_press(self, x, y):
        """Tap at a height: set that step's velocity, or create the note at
        that velocity when the step is empty (same Push-style behaviour as the
        step-hold overlay)."""
        row = self._lane_velocity_scene
        if row is None:
            return
        pitch = self._pitch_for_row(row)
        if pitch is None:
            return
        level = self._lane_velocity_cell_to_level(y)
        if level is None or not self._ensure_clip():
            return
        velocity = self._velocity_for_lane_level(level)
        step = self._page_index * STEPS_PER_PAGE + x
        note = self._find_note_at_step_pitch(step, pitch)
        if note is None:
            start = step * self._step_length
            self._clip.add_new_notes((Live.Clip.MidiNoteSpecification(
                pitch=pitch, start_time=start, duration=self._step_length,
                velocity=velocity, mute=False),))
            self._clip.deselect_all_notes()
            self._ensure_loop_contains_time(start + self._step_length)
        elif int(note.velocity) != velocity:
            self._replace_note_at(note, velocity=velocity)
        else:
            return
        self._refresh_notes()
        self._emit(Event.MELODIC_LANE_VELOCITY,
                   name=self._lane_name(row), step=(x + 1), velocity=velocity)
        self.update()

    def _render_lane_velocity(self):
        """Paint the velocity profile of the held lane: one column per step of
        the current page, a bar growing from the bottom."""
        row = self._lane_velocity_scene
        pitch = self._pitch_for_row(row) if row is not None else None
        for x in range(8):
            note = None
            if pitch is not None:
                step = self._page_index * STEPS_PER_PAGE + x
                note = self._find_note_at_step_pitch(step, pitch)
            current = (self._lane_level_for_velocity(note.velocity)
                       if note is not None else 0)
            for y in range(PITCH_ROW_MIN, PITCH_ROW_MAX + 1):
                level = self._lane_velocity_cell_to_level(y)
                if pitch is None:
                    self._set_grid_light(
                        x, y, RGB_BLACK if self._rgb_leds()
                        else "DefaultButton.Disabled")
                    continue
                if level <= current:
                    if self._rgb_leds():
                        # Same clip-hue ramp as the step grid, so a bar height
                        # and a note's shade read as the same scale.
                        self._set_grid_light_rgb(
                            x, y, self._note_shade_ramp()[level - 1])
                        continue
                    # Palette fallback: 8 levels over a 16-entry ramp, every
                    # second entry so the full colour range is still used.
                    self._set_grid_light_palette(
                        x, y, VELOCITY_LEVEL_PALETTE[level * 2 - 1])
                elif self._rgb_leds():
                    self._set_grid_light(x, y, GREY_EMPTY)
                else:
                    self._set_grid_light_palette(x, y, VELOCITY_LEVEL_DIM)

    def _make_control_button_listener(self, index):
        def listener(value):
            self._on_control_button_value(index, value)
        return listener

    def set_user_mode_button(self, button):
        self._user_mode_button = button

    def _is_main_mode_selector_held(self):
        return (self._user_mode_button is not None
                and self._user_mode_button.is_pressed())

    def _on_control_button_value(self, index, value):
        if not self.is_enabled():
            return
        if self._is_main_mode_selector_held():
            # Parent's mode selector owns the scene column — drop any lane
            # view we were arming so it can't fire behind the selector.
            self._disarm_lane_velocity()
            return
        if value:
            # Press only arms the lane view; the slot's own action now fires on
            # RELEASE, so hold and tap can share the same button. The arm delay
            # means a quick tap never flashes the view.
            self._lane_velocity_scene = index
            self._lane_velocity_arm_task.restart()
            return
        was_armed = self._lane_velocity_armed
        self._disarm_lane_velocity()
        if was_armed:
            # The hold was a lane view — releasing just closes it.
            return
        self._perform_control_button_action(index)

    def _perform_control_button_action(self, index):
        if index == self._chromatic_slot:
            # Dual-purpose slot: chromatic toggle when shift held (or when
            # the device exposes direct slots), Capture MIDI otherwise.
            # Chromatic/scale mean nothing on a drum rack — the rows are pads.
            if self._direct_slot_actions or self._device_shift_held:
                if not self._drum_lane_mode():
                    self._toggle_chromatic_mode()
            else:
                self._capture_midi()
        elif index == self._scale_cycle_slot:
            # Dual-purpose slot: scale cycle / Quantize.
            if self._direct_slot_actions or self._device_shift_held:
                if not self._drum_lane_mode():
                    self._cycle_scale(1)
            else:
                self._quantize_selected()
        elif index == self._cycle_slot:
            self._toggle_bottom_right_mode()
        # Unassigned slots are free; slot 7 is the device shift (untouched).

    def adjust_pitch_offset(self, delta):
        """Public: shift the pitch row range by `delta` semitones.

        Called from the parent control surface when the user presses the top
        arrow buttons in melodic_sequence main mode.
        """
        if self.is_enabled():
            self._adjust_pitch_offset(delta)

    def nav_page(self, delta):
        """Public: navigate the visible page by `delta` (typically ±1).
        Bound to the ← / → top arrows in melodic_sequence main mode.
        Clamps to [0, last_page] where last_page is derived from
        `clip.loop_end / page_length`. No-op when no clip is open."""
        if not self.is_enabled() or not liveobj_valid(self._clip):
            return
        max_idx = self._last_page_index()
        target = max(0, min(self._page_index + delta, max_idx))
        if target == self._page_index:
            return
        self._page_index = target
        self._emit(Event.MELODIC_PAGE_SCOPED,
                   start=target + 1, end=target + 1)
        self.update()

    # ---- public API for device-specific wiring -------------------------
    # The Mini reaches these actions through scene-button slots; the Pro
    # MK3 wiring calls them directly from dedicated hardware buttons.

    def configure_slots(self, **overrides):
        """Remap or disable scene-button slot assignments.

        Keys: chromatic, scale_cycle, cycle, shift. Values: slot index 0-7,
        or None to disable the slot. Defaults are the Mini MK3 layout
        (module constants).
        """
        for key, value in overrides.items():
            attr = "_{}_slot".format(key)
            if not hasattr(self, attr):
                raise ValueError("unknown slot key: {}".format(key))
            setattr(self, attr, value)
        if self.is_enabled():
            self._update_control_leds()

    def set_direct_slot_actions(self, direct):
        """When True (Pro MK3), the dual-purpose slots act directly —
        chromatic toggle / scale cycle without holding shift — because
        Capture/Quantize live on dedicated buttons."""
        self._direct_slot_actions = bool(direct)
        if self.is_enabled():
            self._update_control_leds()

    def capture_midi(self):
        """Public: trigger Capture MIDI (same path as the capture slot)."""
        if self.is_enabled():
            self._capture_midi()

    def quantize_selected(self):
        """Public: quantize the current selection (held cells, else all
        notes in the clip)."""
        if self.is_enabled():
            self._quantize_selected()

    def toggle_bottom_right_mode(self):
        """Public: cycle the bottom-right 4x4 (pitch ↔ grid resolution)."""
        if self.is_enabled():
            self._toggle_bottom_right_mode()

    def _set_grid_option(self, index):
        """Pick a grid resolution from `GRID_OPTIONS` (0..15)."""
        if not 0 <= index < len(GRID_OPTIONS):
            return
        if index == self._grid_option_index:
            return
        self._grid_option_index = index
        self._recompute_grid()
        label = self._current_grid_label()
        self._emit(Event.MELODIC_GRID_CHANGED,
                   label=label,
                   is_triplet=label.endswith("t"))

    def _recompute_grid(self):
        self._step_length = GRID_OPTIONS[self._grid_option_index][0]
        self._page_length = self._step_length * STEPS_PER_PAGE
        self._page_index = min(self._page_index, DEFAULT_CLIP_PAGES - 1)
        self._refresh_notes()
        self.update()

    def _current_grid_label(self):
        return GRID_OPTIONS[self._grid_option_index][1]

    def _cycle_color(self):
        grid_mode = self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID
        if self._rgb_leds():
            # Hue while the 4x4 is showing resolutions (a chosen state), grey
            # while it is the plain pitch grid.
            return self._shade(NOTE_SHADE_LEVELS) if grid_mode else GREY_DIM
        return ("MelodicSequencer.Control.CycleGrid" if grid_mode
                else "MelodicSequencer.Control.CycleLoop")

    def _toggle_bottom_right_mode(self):
        """Cycle the bottom-right 4x4 between pitch (default) and grid
        (resolution selector). Pitch state isn't lost; it's just hidden while
        in grid mode. Drops any in-flight grid-press dedup for cells whose
        meaning is about to flip."""
        if self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID:
            self._bottom_right_mode = BOTTOM_RIGHT_MODE_PITCH
        else:
            self._bottom_right_mode = BOTTOM_RIGHT_MODE_GRID
        self._log("bottom-right mode: {}".format(self._bottom_right_mode))
        # Clear any held / consumed state on bottom-right cells — their
        # press handler is about to switch (pitch toggle ↔ resolution select).
        self._held_grid_buttons = {coord for coord in self._held_grid_buttons
                                   if not (coord[0] >= 4 and coord[1] >= 4)}
        self._held_note_cells = {k: v for k, v in self._held_note_cells.items()
                                 if not (k[0] >= 4 and k[1] >= 4)}
        self._consumed_note_cells = {coord for coord in self._consumed_note_cells
                                     if not (coord[0] >= 4 and coord[1] >= 4)}
        self._emit(Event.MELODIC_BOTTOM_RIGHT_MODE,
                   mode=self._bottom_right_mode)
        self.update()

    def _cycle_scale(self, delta=1):
        """Advance the scale by `delta` (default forward). Existing notes
        keep their absolute pitches; the row→pitch mapping changes so notes
        outside the new scale become invisible in scale mode. No effect in
        chromatic mode (scale isn't used for rendering)."""
        self._scale_index = (self._scale_index + delta) % len(MELODIC_SCALES)
        if self._preview_mode:
            self._update_audition_translations()
        self._refresh_notes()
        self.update()
        self._emit(Event.MELODIC_SCALE_CHANGED,
                   scale_index=self._scale_index,
                   scale_name=self._current_scale_name())

    def _toggle_chromatic_mode(self):
        """Toggle the pitch-grid mode (scale ↔ chromatic). Notes keep their
        absolute pitches; only the row→pitch mapping changes."""
        self._chromatic_mode = not self._chromatic_mode
        if self._preview_mode:
            self._update_audition_translations()
        self._refresh_notes()
        self.update()
        self._emit(Event.MELODIC_CHROMATIC_MODE, on=self._chromatic_mode)

    def _chromatic_color(self):
        # Dual-purpose slot. Shift held (or direct slots) → chromatic
        # toggle. Otherwise → Capture MIDI (bright when capturable, dim
        # otherwise).
        rgb = self._rgb_leds()
        if self._direct_slot_actions or self._device_shift_held:
            if self._drum_lane_mode():
                # Chromatic means nothing on a rack — the rows are pads.
                return RGB_BLACK if rgb else "DefaultButton.Disabled"
            if rgb:
                return (self._shade(NOTE_SHADE_LEVELS) if self._chromatic_mode
                        else GREY_DIM)
            return ("MelodicSequencer.Control.GridSelected"
                    if self._chromatic_mode
                    else "MelodicSequencer.Control.Grid")
        ready = getattr(self.song, "can_capture_midi", False)
        if rgb:
            return self._shade(NOTE_SHADE_LEVELS) if ready else GREY_DIM
        if ready:
            return "MelodicSequencer.Control.CaptureMidiReady"
        return "MelodicSequencer.Control.CaptureMidi"

    def _scale_or_quantize_color(self):
        """Dual-purpose slot: scale cycle (shift held, or direct slots) /
        Quantize otherwise. Encapsulates both LED states in one helper to
        keep `_update_control_leds` compact."""
        rgb = self._rgb_leds()
        if self._direct_slot_actions or self._device_shift_held:
            if self._drum_lane_mode():
                return RGB_BLACK if rgb else "DefaultButton.Disabled"
            # Always available, never "chosen" — it stays on the grey ramp.
            return GREY_MID if rgb else "MelodicSequencer.Control.ScaleCycle"
        return GREY_MID if rgb else "MelodicSequencer.Control.Quantize"

    def _capture_midi(self):
        """Post-capture: re-resolve the clip, re-arm the build-out gate,
        and jump to the page where the captured content ends so the user
        sees the new notes immediately."""
        song = self.song
        if not getattr(song, "can_capture_midi", False):
            self._emit(Event.MIDI_CAPTURED, ok=False, reason="nothing to capture")
            return
        try:
            song.capture_midi()
        except Exception as exc:
            self._log("capture_midi failed: {}".format(exc))
            self._emit(Event.MIDI_CAPTURED, ok=False, reason=str(exc))
            return
        self._refresh_clip()
        if liveobj_valid(self._clip):
            self._clip_just_created = True
            self._page_index = self._last_page_index()
        self.update()
        self._emit(Event.MIDI_CAPTURED, ok=True, reason="")

    def _last_page_index(self):
        if not liveobj_valid(self._clip) or self._page_length <= 0:
            return 0
        loop_end = max(0.0, float(self._clip.loop_end))
        if loop_end <= 0:
            return 0
        idx = int((loop_end - 1e-6) / self._page_length)
        return max(0, idx)

    def _quantize_selected(self):
        """Quantize notes to the current step grid. If any pitch cells are
        held with notes, only those notes are moved. Otherwise quantizes every
        note in the clip (melodic doesn't have a per-pad concept). 100% pull
        to grid. Held cells are marked consumed so their release doesn't
        toggle the (now-moved) notes back off."""
        if not liveobj_valid(self._clip):
            return
        grid = self._step_length
        if grid <= 0:
            return
        held = list(self._held_note_cells.items())
        if held:
            scope = "selected"
            targets = []
            for cell, (step, pitch, start) in held:
                note = self._find_note_at_step_pitch(step, pitch)
                if note is not None:
                    targets.append((cell, note))
        else:
            scope = "clip_all"
            targets = [(None, n) for n in self._notes]
        moved = 0
        for cell, note in targets:
            new_start = round(note.start_time / grid) * grid
            if abs(new_start - note.start_time) <= 1e-6:
                continue
            self._replace_note_at(note, start_time=new_start)
            if cell is not None:
                # Update tracked start so the LED + future gestures see the
                # new position. The pad coords (x, y) don't change.
                step, pitch, _ = self._held_note_cells[cell]
                self._held_note_cells[cell] = (
                    int(round(new_start / grid)), pitch, new_start)
            moved += 1
        for cell, _ in held:
            self._consumed_note_cells.add(cell)
        self._emit(Event.MELODIC_NOTES_QUANTIZED,
                   count=moved,
                   scope=scope,
                   grid=self._current_grid_label())
        self.update()

    def _velocity_overlay_should_show(self):
        if self._lane_velocity_active():
            return False
        """Overlay is active once the hold-arm task has fired AND device
        shift is NOT held (shift gestures keep priority for rows 1..7).
        The arm fires when a cell has been held continuously for
        VELOCITY_OVERLAY_HOLD_DELAY — brief taps for note toggling don't
        flash the bar."""
        return self._velocity_overlay_armed and not self._device_shift_held

    def _arm_velocity_overlay(self):
        """Promote the current hold into a velocity-edit gesture. Bails
        if the user already released or shift is now held."""
        if not self.is_enabled():
            return
        if self._device_shift_held:
            return
        if not self._held_grid_buttons:
            return
        if self._velocity_overlay_armed:
            return
        self._velocity_overlay_armed = True
        self.update()

    def _disarm_velocity_overlay(self):
        """Kill the pending arm task and clear the armed flag."""
        self._velocity_overlay_arm_task.kill()
        if self._velocity_overlay_armed:
            self._velocity_overlay_armed = False
            if self.is_enabled():
                self.update()

    def _velocity_overlay_cell_to_level(self, x, y):
        """Cell (x in 0..7, y in {6, 7}) → level 1..16. Bottom row (y=7) =
        levels 1..8; top row (y=6) = levels 9..16. None if out of range."""
        if not 0 <= x <= 7:
            return None
        if y == VELOCITY_OVERLAY_ROW_BOTTOM:
            return x + 1
        if y == VELOCITY_OVERLAY_ROW_TOP:
            return x + 9
        return None

    def _velocity_for_level(self, level):
        return max(VELOCITY_MIN, min(VELOCITY_MAX, level * 8))

    def _level_for_velocity(self, velocity):
        return max(1, min(VELOCITY_OVERLAY_LEVELS, (int(velocity) + 7) // 8))

    def _current_held_velocity(self):
        """Velocity of the most-recently held note. Falls back to
        DEFAULT_VELOCITY if no held cell currently resolves to a note."""
        for _, cell_info in reversed(list(self._held_note_cells.items())):
            if cell_info is None:
                continue
            step, pitch, _ = cell_info
            note = self._find_note_at_step_pitch(step, pitch)
            if note is not None:
                return int(note.velocity)
        return DEFAULT_VELOCITY

    def _render_velocity_overlay(self):
        """Write the 16-pad velocity bar into y=6 and y=7 (8 cells per row)."""
        current = self._level_for_velocity(self._current_held_velocity())
        for level in range(1, VELOCITY_OVERLAY_LEVELS + 1):
            if level <= 8:
                x = level - 1
                y = VELOCITY_OVERLAY_ROW_BOTTOM
            else:
                x = level - 9
                y = VELOCITY_OVERLAY_ROW_TOP
            if self._rgb_leds():
                self._set_grid_light(
                    x, y,
                    self._shade(level, VELOCITY_OVERLAY_LEVELS)
                    if level <= current else GREY_EMPTY)
                continue
            palette = (VELOCITY_LEVEL_PALETTE[level - 1] if level <= current
                       else VELOCITY_LEVEL_DIM)
            self._set_grid_light_palette(x, y, palette)

    def _apply_velocity_from_selector(self, level):
        """Set every held note's velocity to `level`'s value, OR create new
        notes for held cells that sit on empty positions. Iterates the full
        held set (`_held_grid_buttons`) rather than just cells-with-notes so
        empty-cell creation works Push-style. Marks held cells consumed so
        their release doesn't toggle. Emits MELODIC_VELOCITY_CHANGED once."""
        if not self.is_enabled() or not self._ensure_clip():
            return
        velocity = self._velocity_for_level(level)
        new_notes = []
        modified = False
        for (x, y) in list(self._held_grid_buttons):
            pitch = self._pitch_for_row(y)
            if pitch is None:
                continue
            step = self._page_index * STEPS_PER_PAGE + x
            note = self._find_note_at_step_pitch(step, pitch)
            if note is None:
                # Empty held cell → create a note at this level's
                # velocity. Track it in _held_note_cells so subsequent bar
                # taps adjust the same note.
                start = step * self._step_length
                new_notes.append(Live.Clip.MidiNoteSpecification(
                    pitch=pitch, start_time=start,
                    duration=self._step_length, velocity=velocity, mute=False))
                self._held_note_cells[(x, y)] = (step, pitch, start)
                self._consumed_note_cells.add((x, y))
                self._ensure_loop_contains_time(start + self._step_length)
                modified = True
                continue
            if int(note.velocity) != velocity:
                self._replace_note_at(note, velocity=velocity)
                modified = True
            # Refresh the tracked start in case _replace_note_at moved it
            # (it shouldn't here, but defensive — and cover cells that
            # were held but never recorded in _held_note_cells because
            # the press path saw an empty cell at the time).
            self._held_note_cells[(x, y)] = (step, pitch, note.start_time)
            self._consumed_note_cells.add((x, y))
        if new_notes:
            self._clip.add_new_notes(tuple(new_notes))
            self._clip.deselect_all_notes()
            self._refresh_notes()
        if modified:
            self._emit(Event.MELODIC_VELOCITY_CHANGED, velocity=velocity)
        self.update()

    def _replace_note_at(self, note, **changes):
        """Remove a note (matched by start_time + pitch within a tight window)
        and re-add with attribute overrides. Mirrors the drum sequencer's
        helper but uses a melodic-tight window since notes here are quantized
        to step boundaries by default."""
        window = max(self._step_length / 8.0, 1e-4)
        self._clip.remove_notes_extended(from_time=note.start_time,
            from_pitch=note.pitch,
            time_span=window,
            pitch_span=1)
        new = Live.Clip.MidiNoteSpecification(
            pitch=note.pitch,
            start_time=changes.get("start_time", note.start_time),
            duration=changes.get("duration", note.duration),
            velocity=changes.get("velocity", note.velocity),
            mute=changes.get("mute", note.mute))
        self._clip.add_new_notes((new,))
        self._clip.deselect_all_notes()
        self._refresh_notes()

    def set_device_shift_held(self, pressed):
        """Notify of device shift (scene_launch_buttons_raw[7]) press/release.
        Gates the control-row grid slots, the top-row page selector, the
        rows 1..7 step-loop range picker, AND the audition translation. When
        shift is held the whole grid is a loop-edit surface (no audition), so
        we re-install the audition map to drop ALL pitch-row translations."""
        pressed = bool(pressed)
        if pressed == self._device_shift_held:
            return
        self._device_shift_held = pressed
        # Drop any in-flight grid-press dedup state — row 0 just changed
        # meaning (pitch vs page selector), so old held entries are stale.
        self._held_grid_buttons = set()
        # Held note-cells (selection anchors for clip actions) are tied to
        # the pitch-row meaning of the grid; both directions of shift
        # transition invalidate them.
        self._held_note_cells = {}
        self._consumed_note_cells = set()
        self._disarm_velocity_overlay()
        # Drop step-loop press anchors so a held step pad can't leak across
        # a shift transition. The scoped loop itself stays put.
        if not pressed:
            self._step_loop_press_points = []
            self._step_loop_range_active = False
        if pressed:
            self._disarm_lane_velocity()
        if self.is_enabled():
            if self._preview_mode:
                self._update_audition_translations()
            self.update()

    def _adjust_pitch_offset(self, delta):
        # Drum-lane mode has no transposition — the rows ARE the rack. Reuse
        # the same arrows to scroll the pad window: octave arrows (±12) move
        # a full bank of DRUM_LANES pads, semitone arrows (±1) move one pad.
        if self._drum_lane_mode():
            if delta == 0:
                return
            step = DRUM_LANES if abs(delta) >= 12 else 1
            self._scroll_drum_lanes(step if delta > 0 else -step)
            return
        self._set_pitch_offset(self._pitch_offset + delta)

    def _set_pitch_offset(self, offset):
        self._pitch_offset = max(MIN_PITCH_OFFSET, min(MAX_PITCH_OFFSET, offset))
        if self._preview_mode:
            self._update_audition_translations()
        self._show_navigation_message()
        self.update()

    def _show_navigation_message(self):
        octave = int(self._pitch_offset / 12)
        semitone = self._pitch_offset - octave * 12
        self._emit(Event.MELODIC_NAV_CHANGED,
                   label=self._current_grid_label(),
                   page=self._page_index + 1,
                   octave=octave,
                   semitone=semitone)

    def _update_control_leds(self):
        if not self._control_buttons:
            return
        if self._is_main_mode_selector_held():
            return
        # Default (Mini MK3) slot layout: 0 = Capture / Chromatic (dual via
        # shift), 1 = Quantize / Scale cycle, 2-4 = free (grid resolutions
        # moved to the bottom-right 4x4 in "grid" mode), 5 = sequencer
        # shift (relocated from slot 7), 6 = cycle (pitch ↔ grid), 7 =
        # RESERVED (was device shift; now session-only). Actual positions
        # come from the configure_slots() assignments; unassigned (or
        # None, i.e. disabled) slots stay dark.
        off = RGB_BLACK if self._rgb_leds() else "DefaultButton.Disabled"
        if self._rgb_leds():
            shift_color = RGB_WHITE if self._device_shift_held else off
        else:
            shift_color = ("MelodicSequencer.Control.Shift"
                           if self._device_shift_held else off)
        colors = [off] * len(self._control_buttons)

        def assign(slot, color):
            if slot is not None and 0 <= slot < len(colors):
                colors[slot] = color

        assign(self._chromatic_slot, self._chromatic_color())
        assign(self._scale_cycle_slot, self._scale_or_quantize_color())
        assign(self._shift_slot, shift_color)
        assign(self._cycle_slot, self._cycle_color())
        # The lane whose velocity view is up takes over its own slot's colour.
        if self._lane_velocity_active():
            assign(self._lane_velocity_scene,
                   RGB_WHITE if self._rgb_leds()
                   else "MelodicSequencer.LaneVelocity")
        for index, button in enumerate(self._control_buttons):
            self._set_control_light(
                button, colors[index] if self.is_enabled() else off)

    def _set_control_light(self, button, color):
        """Scene-button write. In Programmer mode a button's LED index is its
        CC number, so the RGB colour-spec path addresses it exactly like a pad;
        skin names still go through the framework."""
        if isinstance(color, tuple):
            try:
                index = button.original_identifier()
            except Exception:
                return
            self._write_rgb(index, color)
            return
        try:
            button.set_light(color)
        except Exception:
            pass

    def _turn_control_buttons_off(self):
        off = RGB_BLACK if self._rgb_leds() else "DefaultButton.Disabled"
        for button in self._control_buttons:
            self._set_control_light(button, off)

    def _selected_track_can_hold_midi(self):
        track = self.song.view.selected_track
        return liveobj_valid(track) and getattr(track, "has_midi_input", True)

    def _turn_grid_off(self):
        if self._grid_matrix is None:
            return
        off = RGB_BLACK if self._rgb_leds() else "DefaultButton.Disabled"
        self._begin_rgb_batch()
        try:
            for y in range(8):
                for x in range(8):
                    self._set_grid_light(x, y, off)
        finally:
            self._flush_rgb_batch()

    def _set_grid_light(self, x, y, color):
        """Accepts a skin colour NAME or an (r, g, b) triple. Every colour
        helper returns a triple on RGB devices and a name otherwise, so this
        one dispatch keeps all call sites unchanged."""
        if isinstance(color, tuple):
            self._set_grid_light_rgb(x, y, color)
            return
        button = self._get_grid_button(x, y)
        if button is not None:
            self._send_programmer_pad_color(button, color)

    def _set_grid_light_palette(self, x, y, palette_value):
        """Same as `_set_grid_light` but takes a raw Launchpad palette index
        (0-127) instead of a skin color name. Used by the velocity overlay,
        which paints the bottom 2 rows from a 16-entry gradient rather than
        a skin map."""
        button = self._get_grid_button(x, y)
        if button is None:
            return
        try:
            note = button.original_identifier()
            status = NOTE_ON_STATUS + PROGRAMMER_LED_CHANNEL
            self.canonical_parent._send_midi((status, note, palette_value), optimized=False)
        except Exception:
            pass

    def _get_grid_button(self, x, y):
        try:
            return self._grid_matrix.get_button(y, x)
        except IndexError:
            return None

    def _log(self, message):
        try:
            self.canonical_parent._c_instance.log_message("[MelodicStepSequencer] {}".format(message))
        except Exception:
            pass

    def _emit(self, event_name, **payload):
        """Fire a semantic event on the bus. No-op without a bus —
        keeps the component presentation-agnostic. Status bar + M4L
        wiring lives in the subscribers attached at the top level."""
        if self._event_bus is not None:
            self._event_bus.emit(event_name, **payload)

    def _request_midi_map_rebuild(self):
        try:
            self.canonical_parent.request_rebuild_midi_map()
        except Exception:
            pass

    # --- Note shading (clip hue, Push style) ----------------------------

    def _clip_color(self):
        """The clip's Live colour as 0xRRGGBB, or a fallback hue."""
        if liveobj_valid(self._clip):
            try:
                color = int(self._clip.color)
                if color > 0:
                    return color
            except Exception:
                pass
        return DEFAULT_CLIP_COLOR

    def _rgb_leds(self):
        """True when this device renders through RGB colour specs."""
        return SUPPORTS_RGB_LEDS and RGB_NOTE_SHADES

    def _shade_ramp(self, levels):
        """Cached `levels` shades of the clip hue, darkest first. Keyed by
        level count so the 8-level note ramp and the 16-level overlay ramp
        coexist instead of evicting each other."""
        color = self._clip_color()
        if color != self._note_shade_source:
            self._note_shade_source = color
            self._shade_ramps = {}
        ramp = self._shade_ramps.get(levels)
        if ramp is None:
            ramp = rgb_shades(color, levels, floor=NOTE_SHADE_FLOOR)
            self._shade_ramps[levels] = ramp
        return ramp

    def _note_shade_ramp(self):
        return self._shade_ramp(NOTE_SHADE_LEVELS)

    def _shade(self, level, levels=NOTE_SHADE_LEVELS):
        """One shade of the clip hue, `level` in 1..levels."""
        return self._shade_ramp(levels)[max(1, min(levels, level)) - 1]

    def _shade_for_velocity(self, velocity):
        level = max(1, min(NOTE_SHADE_LEVELS,
                           -(-int(velocity) // LANE_VELOCITY_STEP)))
        return self._note_shade_ramp()[level - 1]

    def _is_anchor_pitch(self, pitch):
        """The row acting as the visual landmark: the scale root, or the pad
        Live has selected when the rows are drum lanes."""
        if self._drum_lane_mode():
            return pitch == self._selected_drum_pad_note()
        return pitch % 12 == self._root_pitch() % 12

    def _begin_rgb_batch(self):
        if self._rgb_batch_depth == 0:
            self._rgb_batch = []
        self._rgb_batch_depth += 1

    def _flush_rgb_batch(self):
        self._rgb_batch_depth = max(0, self._rgb_batch_depth - 1)
        if self._rgb_batch_depth:
            return
        batch, self._rgb_batch = self._rgb_batch, None
        if batch:
            send_pad_rgb(self.canonical_parent, batch)

    def _write_rgb(self, index, color):
        """Queue one LED index → RGB write, or send it alone if no batch."""
        if self._rgb_batch is not None:
            self._rgb_batch.append((index, color))
        else:
            send_pad_rgb(self.canonical_parent, [(index, color)])

    def _set_grid_light_rgb(self, x, y, shade):
        button = self._get_grid_button(x, y)
        if button is None:
            return
        try:
            index = button.original_identifier()
        except Exception:
            return
        self._write_rgb(index, shade)

    def _send_programmer_pad_color(self, button, color):
        note, color_value = send_pad_color(
            self.canonical_parent, button, color, MELODIC_COLOR_VALUES)
        if self._led_debug_count < 8:
            self._log("led send: note={}, value={}".format(note, color_value))
            self._led_debug_count += 1
