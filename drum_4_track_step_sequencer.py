from __future__ import absolute_import, print_function, unicode_literals

import Live

from ableton.v2.base import listens, liveobj_valid, task
from ableton.v2.control_surface import Component
from ableton.v2.control_surface.components import find_nearest_color
from novation.colors import CLIP_COLOR_TABLE, RGB_COLOR_TABLE

from .events import Event
from .palette import (
    DRUM_SEQUENCER_COLOR_VALUES,
    VELOCITY_LEVEL_DIM,
    VELOCITY_LEVEL_PALETTE,
    send_pad_color,
)
from .programmer_mode import NOTE_ON_STATUS, PROGRAMMER_LED_CHANNEL


# 4-track drum step sequencer.
#
# The 8x8 matrix shows 4 drum-rack pads simultaneously, each with 16 steps
# spread across 2 rows. Drum-keyboard layout — lowest pitch at the bottom:
#
#   y=0,1 → track 3 (highest of the 4 visible pads)
#   y=2,3 → track 2
#   y=4,5 → track 1
#   y=6,7 → track 0 (lowest — typically the kick)
#
# Within each 2-row track, the top row (smaller y) holds steps 0..7 and the
# bottom row holds steps 8..15 — reading order top-left → bottom-right.
#
# All tracks share the clip time axis: a step at the same column position
# across two different tracks fires at the same time but on different
# pitches. The clip is a single MIDI clip containing notes for all 4
# visible pitches.
#
# Sister to `DrumStep64SequencerComponent` (single-pad 64 steps) and
# `DrumStepSequencerComponent` (4x8 step grid + selectors). Most helpers
# mirror drum_64_step_sequencer with (x, y) cell keys instead of int step.
TRACKS = 4
STEPS_PER_TRACK = 16
ROWS_PER_TRACK = 2
GRID_ROWS = 8
STEPS_PER_ROW = 8

DEFAULT_VELOCITY = 100
NOTE_SELECTOR_BASE_PITCH = 36

# Step-grid resolutions — same 16-cell table as the other sequencers,
# laid out across the bottom-right 4x4 when the cycle button is in
# "grid_pick" state.
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
DEFAULT_STEP_LENGTH = GRID_OPTIONS[DEFAULT_GRID_INDEX][0]

VELOCITY_ARROW_STEP = 8
VELOCITY_MIN = 1
VELOCITY_MAX = 127
VELOCITY_TIER_BOUNDARIES = (31, 63, 95)
NUDGE_BEAT_DELTA = 1.0 / 24

VELOCITY_OVERLAY_LEVELS = 16
VELOCITY_OVERLAY_ROW_TOP = 6     # levels 9..16
VELOCITY_OVERLAY_ROW_BOTTOM = 7  # levels 1..8
VELOCITY_OVERLAY_HOLD_DELAY = 0.25

MATRIX_MODE_EDIT = "edit"
MATRIX_MODE_LOOP_PICK = "loop_pick"
MATRIX_MODE_GRID_PICK = "grid_pick"

CAPTURE_SLOT = 0
QUANTIZE_SLOT = 1
SHIFT_SLOT = 5      # sequencer shift modifier (parent-owned)
CYCLE_SLOT = 6

DEFAULT_CLIP_PAGES = 1


class DrumStep4TrackSequencerComponent(Component):
    """4-track × 16-step drum sequencer.

    Each visible drum-rack pad gets 2 rows of step pads (top row of the
    pair = steps 0..7, bottom row = steps 8..15). The 4 visible tracks
    are independently assignable via the per-track shift selector.

    Shift held → each track's row pair becomes a 16-cell pad picker for
    THAT specific track: tapping a cell assigns that pad to that track.
    The currently-assigned pad is highlighted with NoteSelected. Layout
    within each track's pair is drum-keyboard (low pitches on the bottom
    row of the pair, high on the top row).

    Default track assignments = first 4 used drum-rack pads (ascending
    pitch). On drum-group change the assignments reset.

    Cycle button (slot 6) advances edit → loop_pick → grid_pick.
    """

    def __init__(self, drum_group_component=None, event_bus=None, *a, **k):
        super(DrumStep4TrackSequencerComponent, self).__init__(*a, **k)
        self._drum_group = drum_group_component
        self._event_bus = event_bus
        self._grid_matrix = None
        self._clip = None
        self._clip_slot = None
        self._drum_group_device = None
        # Per-track pitch assignments (one entry per track). None means the
        # track has no pad assigned (rendered dim, presses ignored).
        # Track 0 (index 0) = bottom of the display; track 3 = top.
        self._track_pitches = [None] * TRACKS
        self._step_length = DEFAULT_STEP_LENGTH
        self._grid_option_index = DEFAULT_GRID_INDEX
        self._matrix_mode = MATRIX_MODE_EDIT
        self._device_shift_held = False
        # Parent's User button — held = mode selector active, gate scene
        # listener + LED writes (parent paints those slots itself).
        self._user_mode_button = None
        self._clip_just_created = False
        # Held cells, keyed by (x, y). Value = absolute note start_time
        # (beats, float) when the cell sits on an existing note, or None
        # for an empty cell. Mirrors the (x, y) keying used by the
        # melodic sequencer's _held_note_cells.
        self._held_step_pads = {}
        self._consumed_step_pads = set()
        self._loop_press_points = []  # int step indices (0..15)
        self._loop_range_active = False
        self._playhead = None
        self._notes = []
        self._control_buttons = ()
        self._control_button_listeners = []
        self._led_debug_count = 0
        self._delayed_update_task = self._tasks.add(
            task.sequence(task.wait(0.1), task.run(self.update)))
        self._delayed_update_task.kill()
        self._velocity_overlay_armed = False
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
        self._set_drum_group_device(None)
        super(DrumStep4TrackSequencerComponent, self).disconnect()

    # --- Wiring ----------------------------------------------------------

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
            self._grid_matrix = matrix
            if self._grid_matrix is not None:
                self._grid_matrix.add_value_listener(self._on_grid_matrix_value)
            self._request_midi_map_rebuild()
            self.update()

    def set_enabled(self, enabled):
        super(DrumStep4TrackSequencerComponent, self).set_enabled(enabled)
        self._log("enabled: {}".format(enabled))
        if enabled:
            self._led_debug_count = 0
            self._refresh_targets()
            self._delayed_update_task.restart()
            self._update_control_leds()
        else:
            self._delayed_update_task.kill()
            self._playhead = None
            self._held_step_pads = {}
            self._consumed_step_pads = set()
            self._loop_press_points = []
            self._loop_range_active = False
            self._disarm_velocity_overlay()
            self._clip_just_created = False
            self._turn_grid_off()
            self._turn_control_buttons_off()

    def update(self):
        super(DrumStep4TrackSequencerComponent, self).update()
        if self.is_enabled():
            self._update_step_leds()
            self._update_control_leds()

    # --- Listeners -------------------------------------------------------

    @listens("detail_clip")
    def _on_detail_clip_changed(self):
        if self.is_enabled():
            self._refresh_clip()

    @listens("selected_track")
    def _on_selected_track_changed(self):
        if self.is_enabled():
            self._refresh_targets()

    @listens("can_capture_midi")
    def _on_can_capture_midi_changed(self):
        if self.is_enabled():
            self._update_control_leds()

    @listens("selected_drum_pad")
    def _on_selected_drum_pad_changed(self):
        # Track assignments are fully manual via the shift selector — no
        # auto-sync from Live's view-selected pad. Just redraw in case
        # the selection affects rendering (e.g., pad color).
        if self.is_enabled():
            self.update()

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
            self._update_step_leds()

    @listens("playing_status")
    def _on_playing_status_changed(self):
        self._on_playing_position_changed()

    @listens("loop_start")
    def _on_loop_changed(self):
        if self.is_enabled():
            self._update_step_leds()

    @listens("loop_end")
    def _on_loop_end_changed(self):
        self._on_loop_changed()

    # --- Clip / drum group ----------------------------------------------

    def _refresh_targets(self):
        track = self.song.view.selected_track
        drum_group = self._find_drum_group_device(track)
        self._set_drum_group_device(drum_group)
        self._refresh_clip()
        self.update()

    def _refresh_clip(self):
        clip_slot = self._selected_clip_slot()
        clip = None
        detail_clip = self.song.view.detail_clip
        if liveobj_valid(detail_clip) and detail_clip.is_midi_clip:
            clip = detail_clip
        elif clip_slot is not None and clip_slot.has_clip and clip_slot.clip.is_midi_clip:
            clip = clip_slot.clip
        self._clip_slot = clip_slot
        self._set_clip(clip)

    def _set_clip(self, clip):
        if clip != self._clip:
            self._clip = clip
            self._on_clip_notes_changed.subject = clip
            self._on_playing_position_changed.subject = clip
            self._on_playing_status_changed.subject = clip
            self._on_loop_changed.subject = clip
            self._on_loop_end_changed.subject = clip
            self._clip_just_created = False
        self._refresh_notes()

    def _set_drum_group_device(self, drum_group):
        is_new = drum_group != self._drum_group_device
        self._drum_group_device = drum_group
        if self._drum_group is not None:
            self._drum_group.set_drum_group_device(drum_group)
        self._on_selected_drum_pad_changed.subject = (
            drum_group.view if liveobj_valid(drum_group) else None)
        if is_new and liveobj_valid(drum_group):
            # New rack — auto-populate the 4 track assignments from the
            # first 4 used pads. Existing assignments are lost (the rack
            # changed, so old pitches likely don't apply anyway).
            self._init_track_pitches_from_used()

    def _init_track_pitches_from_used(self):
        used = self._used_drum_pads()
        self._track_pitches = [
            used[i].note if i < len(used) else None
            for i in range(TRACKS)]

    def _selected_clip_slot(self):
        slot = self.song.view.highlighted_clip_slot
        return slot if slot is not None else None

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

    def _ensure_clip(self):
        if liveobj_valid(self._clip) and self._clip.is_midi_clip:
            return True
        slot = self._selected_clip_slot()
        if slot is None:
            self._emit(Event.ERR_NEED_MIDI_SLOT, mode="drum")
            return False
        if slot.has_clip:
            if slot.clip.is_midi_clip:
                self.song.view.detail_clip = slot.clip
                self._set_clip(slot.clip)
                return True
            self._emit(Event.ERR_NOT_MIDI, mode="drum")
            return False
        if not self._selected_track_can_hold_midi():
            self._emit(Event.ERR_NEED_MIDI_TRACK, mode="drum")
            return False
        try:
            slot.create_clip(STEPS_PER_TRACK * self._step_length * DEFAULT_CLIP_PAGES)
            self.song.view.detail_clip = slot.clip
            self._clip_slot = slot
            self._set_clip(slot.clip)
            self._clip_just_created = True
            try:
                slot.fire()
            except Exception as exc:
                self._log("clip fire failed: {}".format(exc))
            return True
        except RuntimeError:
            return False

    def _refresh_notes(self):
        if liveobj_valid(self._clip):
            time_span = max(self._clip.loop_end, STEPS_PER_TRACK * self._step_length)
            self._notes = list(self._clip.get_notes_extended(
                from_time=0, from_pitch=0,
                time_span=time_span, pitch_span=128))
        else:
            self._notes = []

    def _selected_track_can_hold_midi(self):
        track = self.song.view.selected_track
        return liveobj_valid(track) and getattr(track, "has_midi_input", True)

    # --- Track / pitch mapping -----------------------------------------

    def _used_drum_pads(self):
        if not liveobj_valid(self._drum_group_device):
            return []
        used = []
        for pad in self._drum_group_device.drum_pads:
            if liveobj_valid(pad) and getattr(pad, "chains", None):
                if len(pad.chains) > 0:
                    used.append(pad)
        used.sort(key=lambda p: p.note)
        return used

    def _track_pads(self):
        """Return [pad_or_None] of length TRACKS — one per track, in the
        order they're displayed (index 0 = bottom of the display, index 3
        = top). None entries mean the track has no pad currently assigned
        OR the assigned pitch isn't in the rack any more."""
        return [self._drum_pad_for_pitch(p) if p is not None else None
                for p in self._track_pitches]

    def _track_for_y(self, y):
        """Map row y (0..7) → track index (0..TRACKS-1). Drum-keyboard
        layout: y=6,7 → 0 (lowest), y=0,1 → 3 (highest)."""
        if not 0 <= y <= 7:
            return None
        return (GRID_ROWS - 1 - y) // ROWS_PER_TRACK

    def _decode_cell(self, x, y):
        """Resolve a cell to (track_index, step_within_track, pitch). Returns
        None when the cell falls on a track that has no pad assigned (or
        the assigned pad is no longer in the rack)."""
        if not 0 <= x <= 7 or not 0 <= y <= 7:
            return None
        track = self._track_for_y(y)
        if track is None:
            return None
        pads = self._track_pads()
        pad = pads[track] if track < len(pads) else None
        if pad is None:
            return None
        # Bottom row of the pair (odd y) → steps 8..15; top row → 0..7.
        step = x + (y % ROWS_PER_TRACK) * STEPS_PER_ROW
        return (track, step, pad.note)

    def _time_for_step(self, step):
        return step * self._step_length

    # --- Press routing -------------------------------------------------

    def _on_grid_matrix_value(self, value, x, y, is_momentary):
        if not self.is_enabled():
            return
        if self._device_shift_held:
            self._handle_selector_press(x, y, bool(value))
            return
        # Velocity overlay wins on rows 6-7 in edit mode once the hold-arm
        # task has fired. Same fall-through pattern as the 64-step.
        if (self._matrix_mode == MATRIX_MODE_EDIT
                and self._velocity_overlay_should_show()
                and y in (VELOCITY_OVERLAY_ROW_TOP, VELOCITY_OVERLAY_ROW_BOTTOM)):
            if value:
                level = self._velocity_overlay_cell_to_level(x, y)
                if level is not None:
                    self._apply_velocity_from_selector(level)
                return
            if (x, y) not in self._held_step_pads:
                return
            self._handle_step_press(x, y, False)
            return
        if self._matrix_mode == MATRIX_MODE_GRID_PICK:
            if y >= 4 and x >= 4 and value:
                index = (y - 4) * 4 + (x - 4)
                self._handle_grid_cell_press(index)
            return
        if self._matrix_mode == MATRIX_MODE_LOOP_PICK:
            self._handle_loop_pick_press(x, y, bool(value))
            return
        self._handle_step_press(x, y, bool(value))

    # --- Step toggling --------------------------------------------------

    def _handle_step_press(self, x, y, pressed):
        cell = (x, y)
        decoded = self._decode_cell(x, y)
        if decoded is None:
            # Cell is on an empty track slot — nothing to do.
            return
        track, step, pitch = decoded
        if pressed:
            self._velocity_overlay_arm_task.restart()
            anchor = self._anchor_for_extension()
            target_note = self._find_note_at_step_pitch(step, pitch)
            target_has_note = target_note is not None
            if anchor is not None and anchor != cell and not target_has_note:
                # Length extension is only valid WITHIN A TRACK — extending
                # across tracks would change pitch, which isn't what a
                # length gesture means.
                anchor_decoded = self._decode_cell(*anchor)
                if (anchor_decoded is not None
                        and anchor_decoded[0] == track
                        and self._ensure_clip()):
                    self._extend_note_length(anchor, cell)
                    self._consumed_step_pads.add(anchor)
                    self._consumed_step_pads.add(cell)
                    self._held_step_pads[cell] = None
                    self._update_step_leds()
                    return
            self._held_step_pads[cell] = (
                target_note.start_time if target_has_note else None)
            self._update_step_leds()
        else:
            consumed = cell in self._consumed_step_pads
            self._consumed_step_pads.discard(cell)
            self._held_step_pads.pop(cell, None)
            if not self._held_step_pads:
                self._disarm_velocity_overlay()
            self._update_step_leds()
            if consumed:
                return
            if self._ensure_clip():
                self._toggle_step(step, pitch)

    def _anchor_for_extension(self):
        """Return a held cell whose note still exists (so it can act as
        the start of a length-extension), or None. Insertion order: the
        FIRST valid held cell wins."""
        for cell, note_start in self._held_step_pads.items():
            if note_start is None:
                continue
            decoded = self._decode_cell(*cell)
            if decoded is None:
                continue
            _, _, pitch = decoded
            if self._find_note_at_pitch_time(pitch, note_start) is not None:
                return cell
        return None

    def _find_note_at_step_pitch(self, step, pitch):
        start = step * self._step_length
        end = start + self._step_length
        for note in self._notes:
            if note.pitch == pitch and start <= note.start_time < end:
                return note
        return None

    def _find_note_at_pitch_time(self, pitch, start_time):
        if start_time is None:
            return None
        tolerance = max(self._step_length * 1e-4, 1e-6)
        for note in self._notes:
            if note.pitch == pitch and abs(note.start_time - start_time) < tolerance:
                return note
        return None

    def _replace_note(self, note, **changes):
        window = max(self._step_length / 8.0, 1e-4)
        self._clip.remove_notes_extended(
            from_time=note.start_time, from_pitch=note.pitch,
            time_span=window, pitch_span=1)
        new = Live.Clip.MidiNoteSpecification(
            pitch=note.pitch,
            start_time=changes.get("start_time", note.start_time),
            duration=changes.get("duration", note.duration),
            velocity=changes.get("velocity", note.velocity),
            mute=changes.get("mute", note.mute))
        self._clip.add_new_notes((new,))
        self._clip.deselect_all_notes()
        self._refresh_notes()

    def _extend_note_length(self, anchor_cell, target_cell):
        anchor_decoded = self._decode_cell(*anchor_cell)
        target_decoded = self._decode_cell(*target_cell)
        if anchor_decoded is None or target_decoded is None:
            return
        _, anchor_step, anchor_pitch = anchor_decoded
        _, target_step, _ = target_decoded
        note_start = self._held_step_pads.get(anchor_cell)
        if note_start is None:
            return
        note = self._find_note_at_pitch_time(anchor_pitch, note_start)
        if note is None:
            return
        end_step = max(target_step, anchor_step)
        target_end_time = (end_step + 1) * self._step_length
        new_duration = target_end_time - note.start_time
        if new_duration <= 0:
            return
        self._replace_note(note, duration=new_duration)
        length_steps = max(1, int(round(new_duration / self._step_length)))
        self._emit(Event.DRUM_NOTE_LENGTH_CHANGED,
                   page=1,
                   anchor_step=anchor_step + 1,
                   length_steps=length_steps,
                   pitch=anchor_pitch)
        self._ensure_loop_contains_time(note.start_time + new_duration)
        self.update()

    def _toggle_step(self, step, pitch):
        start = step * self._step_length
        existing = self._find_note_at_step_pitch(step, pitch)
        if existing is not None:
            self._clip.remove_notes_extended(
                from_time=start, from_pitch=pitch,
                time_span=self._step_length, pitch_span=1)
        else:
            note = Live.Clip.MidiNoteSpecification(
                pitch=pitch, start_time=start,
                duration=self._step_length, velocity=DEFAULT_VELOCITY,
                mute=False)
            self._clip.add_new_notes((note,))
            self._clip.deselect_all_notes()
            self._ensure_loop_contains_time(start + self._step_length)
        self._refresh_notes()
        self.update()

    def _ensure_loop_contains_time(self, end_time):
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

    # --- Velocity arrow edit + nudge (parent dispatches Up/Down/Left/Right) -

    def _adjust_note_velocity(self, cell, note_start, delta):
        decoded = self._decode_cell(*cell)
        if decoded is None:
            return False
        _, _, pitch = decoded
        note = self._find_note_at_pitch_time(pitch, note_start)
        if note is None:
            return False
        new_velocity = max(VELOCITY_MIN, min(VELOCITY_MAX, int(note.velocity) + delta))
        if new_velocity == int(note.velocity):
            return True
        self._replace_note(note, velocity=new_velocity)
        self._emit(Event.DRUM_VELOCITY_CHANGED, velocity=new_velocity)
        self.update()
        return True

    def _nudge_note(self, cell, note_start, delta_beats):
        decoded = self._decode_cell(*cell)
        if decoded is None:
            return None
        _, _, pitch = decoded
        note = self._find_note_at_pitch_time(pitch, note_start)
        if note is None:
            return None
        new_start = note.start_time + delta_beats
        if new_start < 0:
            return None
        self._replace_note(note, start_time=new_start)
        self._emit(Event.DRUM_NOTE_NUDGED,
                   delta_beats=delta_beats,
                   start_time=new_start,
                   pitch=pitch)
        self._ensure_loop_contains_time(new_start + note.duration)
        self.update()
        return new_start

    def adjust_held_velocity(self, delta):
        if not self.is_enabled():
            return False
        consumed_any = False
        for cell, note_start in list(self._held_step_pads.items()):
            if note_start is None:
                continue
            if self._adjust_note_velocity(cell, note_start, delta):
                self._consumed_step_pads.add(cell)
                consumed_any = True
        return consumed_any

    def nudge_held_notes(self, direction):
        if not self.is_enabled():
            return False
        delta_beats = direction * NUDGE_BEAT_DELTA
        consumed_any = False
        for cell, note_start in list(self._held_step_pads.items()):
            if note_start is None:
                continue
            new_start = self._nudge_note(cell, note_start, delta_beats)
            if new_start is not None:
                self._held_step_pads[cell] = new_start
                self._consumed_step_pads.add(cell)
                consumed_any = True
        return consumed_any

    def adjust_pitch_offset(self, delta):
        """Shift every track's pad assignment in parallel within the
        used-pads list. ±12 = ±4 pads (full set), ±1 = single pad. Each
        track is clamped to the available pads independently. Falls back
        through the parent's arrow → adjust_held_velocity →
        adjust_pitch_offset chain so this only fires when no step is held."""
        if not self.is_enabled():
            return
        used = self._used_drum_pads()
        if not used:
            return
        pads_step = TRACKS if abs(delta) >= 12 else 1
        direction = 1 if delta > 0 else -1
        offset = direction * pads_step
        changed = False
        for i, pitch in enumerate(self._track_pitches):
            if pitch is None:
                continue
            current_idx = None
            for j, pad in enumerate(used):
                if pad.note == pitch:
                    current_idx = j
                    break
            if current_idx is None:
                continue
            new_idx = max(0, min(len(used) - 1, current_idx + offset))
            new_pitch = used[new_idx].note
            if new_pitch != pitch:
                self._track_pitches[i] = new_pitch
                changed = True
        if changed:
            self._refresh_notes()
            self.update()
            self._emit(Event.DRUM_NAV_CHANGED,
                       label=self._current_grid_label(),
                       page=1, octave=0, semitone=0)

    # --- Velocity overlay (step-hold gesture, rows 6-7) ----------------

    def _velocity_overlay_should_show(self):
        """Active once the hold-arm task has fired AND shift is NOT held."""
        return self._velocity_overlay_armed and not self._device_shift_held

    def _arm_velocity_overlay(self):
        if not self.is_enabled():
            return
        if self._device_shift_held:
            return
        if not self._held_step_pads:
            return
        if self._velocity_overlay_armed:
            return
        self._velocity_overlay_armed = True
        self.update()

    def _disarm_velocity_overlay(self):
        self._velocity_overlay_arm_task.kill()
        if self._velocity_overlay_armed:
            self._velocity_overlay_armed = False
            if self.is_enabled():
                self.update()

    def _velocity_overlay_cell_to_level(self, x, y):
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
        """Velocity of the most-recently-held note. Falls back to
        DEFAULT_VELOCITY when no held cell currently resolves to a note —
        i.e., when every held cell is on an empty step."""
        for cell, note_start in reversed(list(self._held_step_pads.items())):
            if note_start is None:
                continue
            decoded = self._decode_cell(*cell)
            if decoded is None:
                continue
            _, _, pitch = decoded
            note = self._find_note_at_pitch_time(pitch, note_start)
            if note is not None:
                return int(note.velocity)
        return DEFAULT_VELOCITY

    def _render_velocity_overlay(self):
        current = self._level_for_velocity(self._current_held_velocity())
        for level in range(1, VELOCITY_OVERLAY_LEVELS + 1):
            if level <= 8:
                x = level - 1
                y = VELOCITY_OVERLAY_ROW_BOTTOM
            else:
                x = level - 9
                y = VELOCITY_OVERLAY_ROW_TOP
            palette = (VELOCITY_LEVEL_PALETTE[level - 1] if level <= current
                       else VELOCITY_LEVEL_DIM)
            self._set_grid_light_palette(x, y, palette)

    def _apply_velocity_from_selector(self, level):
        """Set every held note's velocity to `level`'s value, OR create new
        notes for held cells sitting on empty steps. Each held cell maps to
        its own (step, pitch) so multi-track holds create multiple notes
        at the same velocity."""
        if not self.is_enabled() or not self._ensure_clip():
            return
        velocity = self._velocity_for_level(level)
        new_notes = []
        modified = False
        for cell, note_start in list(self._held_step_pads.items()):
            decoded = self._decode_cell(*cell)
            if decoded is None:
                continue
            _, step, pitch = decoded
            if note_start is None:
                start = step * self._step_length
                new_notes.append(Live.Clip.MidiNoteSpecification(
                    pitch=pitch, start_time=start,
                    duration=self._step_length, velocity=velocity,
                    mute=False))
                self._held_step_pads[cell] = start
                self._consumed_step_pads.add(cell)
                self._ensure_loop_contains_time(start + self._step_length)
                modified = True
                continue
            note = self._find_note_at_pitch_time(pitch, note_start)
            if note is None:
                continue
            if int(note.velocity) != velocity:
                self._replace_note(note, velocity=velocity)
                modified = True
            self._consumed_step_pads.add(cell)
        if new_notes:
            self._clip.add_new_notes(tuple(new_notes))
            self._clip.deselect_all_notes()
            self._refresh_notes()
        if modified:
            self._emit(Event.DRUM_VELOCITY_CHANGED, velocity=velocity)
        self.update()

    # --- Loop pick (cycle mode 2) ---------------------------------------

    def _handle_loop_pick_press(self, x, y, pressed):
        """Step-precise loop scoping. Any cell in any track maps to its
        step index — all tracks share the clip's time axis. Single tap =
        1-step loop. Two-pad press = [min..max+1] range."""
        # Cells outside the visible tracks (decoded == None) are ignored.
        if self._decode_cell(x, y) is None:
            return
        step = x + (y % ROWS_PER_TRACK) * STEPS_PER_ROW
        if pressed:
            if step not in self._loop_press_points:
                self._loop_press_points.append(step)
            if len(self._loop_press_points) >= 2:
                start = min(self._loop_press_points)
                end = max(self._loop_press_points) + 1
                self._set_loop_range_steps(start, end)
                self._loop_range_active = True
                self._emit(Event.DRUM_STEP_LOOP_SCOPED,
                           page=1, start_step=start + 1, end_step=end,
                           label=self._current_grid_label())
            self._update_step_leds()
        else:
            if step not in self._loop_press_points and not self._loop_range_active:
                return
            was_range_active = self._loop_range_active
            if step in self._loop_press_points:
                self._loop_press_points.remove(step)
            if was_range_active:
                if not self._loop_press_points:
                    self._loop_range_active = False
                self._update_step_leds()
                return
            self._set_loop_range_steps(step, step + 1)
            self._emit(Event.DRUM_STEP_LOOP_SCOPED,
                       page=1, start_step=step + 1, end_step=step + 1,
                       label=self._current_grid_label())
            self._update_step_leds()

    def _set_loop_range_steps(self, start_step, end_step):
        if self._ensure_clip():
            self._set_clip_loop(start_step * self._step_length,
                                end_step * self._step_length)
            self._clip_just_created = False

    # --- Grid resolution pick (cycle mode 3) ---------------------------

    def _handle_grid_cell_press(self, index):
        if not 0 <= index < len(GRID_OPTIONS):
            return
        if index == self._grid_option_index:
            return
        self._grid_option_index = index
        self._recompute_grid()
        label = self._current_grid_label()
        self._emit(Event.DRUM_GRID_CHANGED,
                   label=label, is_triplet=label.endswith("t"))

    def _recompute_grid(self):
        self._step_length = GRID_OPTIONS[self._grid_option_index][0]
        self._refresh_notes()
        self.update()

    def _current_grid_label(self):
        return GRID_OPTIONS[self._grid_option_index][1]

    # --- Cycle button + matrix mode ------------------------------------

    def _cycle_matrix_mode(self):
        order = (MATRIX_MODE_EDIT, MATRIX_MODE_LOOP_PICK, MATRIX_MODE_GRID_PICK)
        next_index = (order.index(self._matrix_mode) + 1) % len(order)
        self._matrix_mode = order[next_index]
        self._loop_press_points = []
        self._loop_range_active = False
        self._held_step_pads = {}
        self._consumed_step_pads = set()
        self._disarm_velocity_overlay()
        self._emit(Event.DRUM_4_TRACK_MATRIX_MODE, mode=self._matrix_mode)
        self.update()

    # --- Per-track pad selector (shift held) ---------------------------
    #
    # Each track's 2-row pair becomes an independent 16-cell pad picker
    # while shift is held. Layout within the pair (drum-keyboard):
    #   - Bottom row of the pair (y_within_pair == 1, odd y): pads 0..7
    #     of the used-pads list (lowest 8 pitches).
    #   - Top row of the pair (y_within_pair == 0, even y): pads 8..15.
    # All four tracks display the SAME 16 used pads — tapping any cell
    # assigns that pad to THAT track only.

    def _selector_pad_index(self, y, x):
        """Pad index (0..15) within the per-track selector for cell (x, y).
        Returns None for cells outside the selector area (shouldn't happen
        since the selector covers the whole grid)."""
        if not 0 <= x <= 7 or not 0 <= y <= 7:
            return None
        # y % ROWS_PER_TRACK == 1 ↔ bottom row of the pair ↔ pads 0..7.
        # y % ROWS_PER_TRACK == 0 ↔ top row of the pair ↔ pads 8..15.
        return (1 - (y % ROWS_PER_TRACK)) * STEPS_PER_ROW + x

    def _handle_selector_press(self, x, y, pressed):
        if not pressed:
            return
        track = self._track_for_y(y)
        if track is None:
            return
        used = self._used_drum_pads()[:STEPS_PER_TRACK]
        pad_idx = self._selector_pad_index(y, x)
        if pad_idx is None or pad_idx >= len(used):
            return
        pad = used[pad_idx]
        self._track_pitches[track] = pad.note
        # Set Live's view-selected pad to the just-tapped one so the user
        # can see / edit it in the drum rack panel.
        if liveobj_valid(self._drum_group_device):
            self._drum_group_device.view.selected_drum_pad = pad
        self._refresh_notes()
        self.update()

    def _drum_pad_for_pitch(self, pitch):
        if pitch is None:
            return None
        if liveobj_valid(self._drum_group_device):
            for pad in self._drum_group_device.drum_pads:
                if pad.note == pitch:
                    return pad
        return None

    def _render_per_track_selector(self):
        """Paint each track's row pair as an independent 16-cell pad picker.
        The currently-assigned pad for each track is highlighted with
        NoteSelected; other cells show the pad's drum-rack color."""
        used = self._used_drum_pads()[:STEPS_PER_TRACK]
        for y in range(GRID_ROWS):
            track = self._track_for_y(y)
            for x in range(STEPS_PER_ROW):
                pad_idx = self._selector_pad_index(y, x)
                if pad_idx is None or pad_idx >= len(used):
                    self._set_grid_light(x, y, "DefaultButton.Disabled")
                    continue
                pad = used[pad_idx]
                if (track is not None
                        and self._track_pitches[track] == pad.note):
                    self._set_grid_light(x, y, "DrumSequencer.NoteSelected")
                    continue
                palette = self._color_for_drum_pad(pad)
                if palette is not None and palette > 0:
                    self._set_grid_light_palette(x, y, palette)
                else:
                    self._set_grid_light(x, y, "DrumSequencer.NoteFilled")

    def _color_for_drum_pad(self, pad):
        if not liveobj_valid(pad):
            return None
        chains = getattr(pad, "chains", None)
        if not chains:
            return None
        chain = chains[0]
        rgb = None
        for attr in ("color", "_color"):
            try:
                value = getattr(chain, attr, None)
                if isinstance(value, int) and value > 0:
                    rgb = value
                    break
            except Exception:
                continue
        if rgb is None:
            return None
        palette = CLIP_COLOR_TABLE.get(rgb)
        if palette is None:
            try:
                palette = find_nearest_color(RGB_COLOR_TABLE, rgb)
            except Exception:
                palette = None
        return palette

    # --- Shift handling (external API for parent surface) --------------

    def set_device_shift_held(self, pressed):
        pressed = bool(pressed)
        if pressed == self._device_shift_held:
            return
        self._device_shift_held = pressed
        # Meaning of presses just flipped between step-edit and selector.
        self._held_step_pads = {}
        self._consumed_step_pads = set()
        self._disarm_velocity_overlay()
        if self.is_enabled():
            self.update()

    # --- LED rendering -------------------------------------------------

    def _update_step_leds(self):
        if self._grid_matrix is None:
            return
        if self._device_shift_held:
            self._render_per_track_selector()
            return
        if self._matrix_mode == MATRIX_MODE_GRID_PICK:
            self._render_grid_pick()
            return
        if self._matrix_mode == MATRIX_MODE_LOOP_PICK:
            self._render_loop_pick()
            return
        # Edit mode — default.
        overlay_active = self._velocity_overlay_should_show()
        for y in range(GRID_ROWS):
            if overlay_active and y in (
                    VELOCITY_OVERLAY_ROW_TOP, VELOCITY_OVERLAY_ROW_BOTTOM):
                continue
            for x in range(STEPS_PER_ROW):
                self._set_grid_light(x, y, self._step_color(x, y))
        if overlay_active:
            self._render_velocity_overlay()

    def _step_color(self, x, y):
        decoded = self._decode_cell(x, y)
        if decoded is None:
            return "DefaultButton.Disabled"
        _, step, pitch = decoded
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return "DrumSequencer.NoClip"
        color = "DrumSequencer.StepBeat" if step % 4 == 0 else "DrumSequencer.StepEmpty"
        note = self._find_note_at_step_pitch(step, pitch)
        if note is not None:
            if note.mute:
                color = "DrumSequencer.StepMuted"
            else:
                color = self._velocity_color_for(int(note.velocity))
        if (x, y) in self._held_step_pads:
            color = "DrumSequencer.StepHeld"
        if self._playhead_is_on_step(step):
            color = ("DrumSequencer.PlayheadActive"
                     if note is not None else "DrumSequencer.Playhead")
        return color

    def _velocity_color_for(self, velocity):
        if velocity <= VELOCITY_TIER_BOUNDARIES[0]:
            return "DrumSequencer.StepVelGhost"
        if velocity <= VELOCITY_TIER_BOUNDARIES[1]:
            return "DrumSequencer.StepVelSoft"
        if velocity <= VELOCITY_TIER_BOUNDARIES[2]:
            return "DrumSequencer.StepVelMedium"
        return "DrumSequencer.StepVelLoud"

    def _render_loop_pick(self):
        for y in range(GRID_ROWS):
            for x in range(STEPS_PER_ROW):
                self._set_grid_light(x, y, self._loop_pick_color(x, y))

    def _loop_pick_color(self, x, y):
        # Cells that have no track behind them stay dim — there's no step
        # to scope onto. (All tracks share the time axis, so the WHERE
        # picker still works even for "no track" cells. But disabling them
        # keeps the loop picker visually tied to actual content rows.)
        if self._decode_cell(x, y) is None:
            return "DefaultButton.Disabled"
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return "DrumSequencer.NoClip"
        step = x + (y % ROWS_PER_TRACK) * STEPS_PER_ROW
        if step in self._loop_press_points:
            return "DrumSequencer.Loop.RangeEdit"
        if self._playhead_is_on_step(step):
            return "DrumSequencer.Loop.Playhead"
        if liveobj_valid(self._clip):
            time = self._time_for_step(step)
            if self._clip.loop_start <= time < self._clip.loop_end:
                return "DrumSequencer.Loop.Inside"
        return "DrumSequencer.Loop.Outside"

    def _render_grid_pick(self):
        for y in range(GRID_ROWS):
            for x in range(STEPS_PER_ROW):
                if y >= 4 and x >= 4:
                    index = (y - 4) * 4 + (x - 4)
                    self._set_grid_light(x, y, self._grid_cell_color(index))
                else:
                    self._set_grid_light(x, y, "DefaultButton.Disabled")

    def _grid_cell_color(self, index):
        if not 0 <= index < len(GRID_OPTIONS):
            return "DefaultButton.Disabled"
        if index == self._grid_option_index:
            return "DrumSequencer.Control.GridSelected"
        if index >= TERNARY_FIRST_INDEX:
            return "DrumSequencer.Control.GridTernary"
        return "DrumSequencer.Control.Grid"

    def _playhead_is_on_step(self, step):
        if self._playhead is None:
            return False
        start = self._time_for_step(step)
        return start <= self._playhead < start + self._step_length

    # --- Scene-column buttons ------------------------------------------

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
        if not self.is_enabled() or not value:
            return
        if self._is_main_mode_selector_held():
            return
        if index == CAPTURE_SLOT:
            self._capture_midi()
        elif index == QUANTIZE_SLOT:
            self._quantize_selected()
        elif index == CYCLE_SLOT:
            self._cycle_matrix_mode()

    def _capture_midi(self):
        """Post-capture: re-resolve the clip and re-arm the build-out
        gate so future note adds can still extend the loop. This matrix
        has no page navigation (16 steps × 4 tracks fit in the 8x8 grid)."""
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
        self.update()
        self._emit(Event.MIDI_CAPTURED, ok=True, reason="")

    def _quantize_selected(self):
        """Quantize. Held set → quantize the notes under those cells.
        Otherwise quantize every note for any of the 4 visible tracks'
        pitches — i.e., what's currently visible on screen."""
        if not liveobj_valid(self._clip):
            return
        grid = self._step_length
        if grid <= 0:
            return
        held = [(cell, start) for cell, start in self._held_step_pads.items()
                if start is not None]
        if held:
            scope = "selected"
            targets = []
            for cell, start in held:
                decoded = self._decode_cell(*cell)
                if decoded is None:
                    continue
                _, _, pitch = decoded
                note = self._find_note_at_pitch_time(pitch, start)
                if note is not None:
                    targets.append((cell, note))
        else:
            scope = "pad_all"
            visible_pitches = {pad.note for pad in self._track_pads() if pad is not None}
            targets = [(None, n) for n in self._notes
                       if n.pitch in visible_pitches]
        moved = 0
        for cell, note in targets:
            new_start = round(note.start_time / grid) * grid
            if abs(new_start - note.start_time) <= 1e-6:
                continue
            self._replace_note(note, start_time=new_start)
            if cell is not None:
                self._held_step_pads[cell] = new_start
            moved += 1
        for cell, _ in held:
            self._consumed_step_pads.add(cell)
        self._emit(Event.DRUM_NOTES_QUANTIZED,
                   count=moved, scope=scope,
                   grid=self._current_grid_label())
        self.update()

    def _update_control_leds(self):
        if not self._control_buttons:
            return
        if self._is_main_mode_selector_held():
            return
        shift_color = ("DrumSequencer.Control.Shift"
                       if self._device_shift_held
                       else "DefaultButton.Disabled")
        capture_color = ("DrumSequencer.Control.CaptureMidiReady"
                         if getattr(self.song, "can_capture_midi", False)
                         else "DrumSequencer.Control.CaptureMidi")
        cycle_color = self._cycle_button_color()
        colors = (
            capture_color,                        # slot 0
            "DrumSequencer.Control.Quantize",     # slot 1
            "DefaultButton.Disabled",             # slot 2
            "DefaultButton.Disabled",             # slot 3
            "DefaultButton.Disabled",             # slot 4
            shift_color,                          # slot 5 = seq shift
            cycle_color,                          # slot 6
            "DefaultButton.Disabled")             # slot 7 reserved
        for index, button in enumerate(self._control_buttons):
            try:
                button.set_light(colors[index] if self.is_enabled() else "DefaultButton.Disabled")
            except Exception:
                pass

    def _cycle_button_color(self):
        if self._matrix_mode == MATRIX_MODE_LOOP_PICK:
            return "DrumSequencer.Loop.Selected"
        if self._matrix_mode == MATRIX_MODE_GRID_PICK:
            return "DrumSequencer.Control.CycleGrid"
        return "DrumSequencer.Control.CycleLoop"

    def _turn_control_buttons_off(self):
        for button in self._control_buttons:
            try:
                button.set_light("DefaultButton.Disabled")
            except Exception:
                pass

    def _turn_grid_off(self):
        if self._grid_matrix is not None:
            for y in range(GRID_ROWS):
                for x in range(STEPS_PER_ROW):
                    self._set_grid_light(x, y, "DefaultButton.Disabled")

    # --- Low-level helpers ---------------------------------------------

    def _set_grid_light(self, x, y, color):
        button = self._get_grid_button(x, y)
        if button is not None:
            self._send_programmer_pad_color(button, color)

    def _set_grid_light_palette(self, x, y, palette_value):
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

    def _send_programmer_pad_color(self, button, color):
        note, color_value = send_pad_color(
            self.canonical_parent, button, color, DRUM_SEQUENCER_COLOR_VALUES)
        if self._led_debug_count < 8:
            self._log("led send: note={}, value={}".format(note, color_value))
            self._led_debug_count += 1

    def _log(self, message):
        try:
            self.canonical_parent._c_instance.log_message(
                "[DrumStep4TrackSequencer] {}".format(message))
        except Exception:
            pass

    def _emit(self, event_name, **payload):
        if self._event_bus is not None:
            self._event_bus.emit(event_name, **payload)

    def _request_midi_map_rebuild(self):
        try:
            self.canonical_parent.request_rebuild_midi_map()
        except Exception:
            pass
