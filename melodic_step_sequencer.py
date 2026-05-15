from __future__ import absolute_import, print_function, unicode_literals

import Live
import time

from ableton.v2.base import listens, liveobj_valid, task
from ableton.v2.control_surface import Component
from ableton.v2.control_surface.input_control_element import ScriptForwarding

from .events import Event
from .palette import MELODIC_COLOR_VALUES, send_pad_color
from .programmer_mode import AUDITION_CHANNEL


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
        self._control_buttons = ()
        self._control_button_listeners = []
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
        self._on_detail_clip_changed.subject = self.song.view
        self._on_selected_track_changed.subject = self.song.view
        self._on_can_capture_midi_changed.subject = self.song

    def disconnect(self):
        self.set_control_buttons(None)
        self.set_grid_matrix(None)
        self._set_clip(None)
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
            self._refresh_clip()
            self._delayed_update_task.restart()
            self._update_control_leds()
        else:
            self._delayed_update_task.kill()
            self._playhead = None
            self._held_grid_buttons = set()
            self._held_note_cells = {}
            self._consumed_note_cells = set()
            self._preview_mode = False
            # Leaving sequencer mode ends "build-out": the next session treats
            # the clip's loop as sacred again.
            self._clip_just_created = False
            self._turn_grid_off()
            self._clear_audition_translations()
            self._turn_control_buttons_off()

    def update(self):
        super(MelodicStepSequencerComponent, self).update()
        if self.is_enabled():
            self._update_pitch_leds()
            self._update_loop_leds()
            self._update_control_leds()

    @listens("detail_clip")
    def _on_detail_clip_changed(self):
        if self.is_enabled():
            self._refresh_clip()

    @listens("selected_track")
    def _on_selected_track_changed(self):
        if self.is_enabled():
            self._refresh_clip()

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
        self.update()

    def _set_clip(self, clip):
        if clip != self._clip:
            self._clip = clip
            self._on_clip_notes_changed.subject = clip
            self._on_playing_position_changed.subject = clip
            self._on_playing_status_changed.subject = clip
            self._on_loop_changed.subject = clip
            self._on_loop_end_changed.subject = clip
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
        step = self._page_index * STEPS_PER_PAGE + x
        if not value:
            # Release. Ignore if we never recorded the press (stray edge).
            if (x, y) not in self._held_grid_buttons:
                return
            self._held_grid_buttons.discard((x, y))
            self._held_note_cells.pop((x, y), None)
            consumed = (x, y) in self._consumed_note_cells
            self._consumed_note_cells.discard((x, y))
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
        if self._grid_matrix is None:
            return
        # When shift is held: row 0 is the page selector (owned by
        # _update_loop_leds), and rows 1..7 become a step range picker
        # backdrop — each column lit Inside/Outside per the clip loop in the
        # current page (Y ignored, all rows in a column share the same color).
        # _update_loop_leds keeps owning row 0; we cover rows 1..7 here.
        # When shift is NOT held: every row 0..7 is a pitch row, except that
        # the bottom-right 4x4 may be overridden when the slot 6 cycle is in
        # "grid" mode (each of those cells displays a grid-resolution option).
        if self._device_shift_held:
            for y in range(PITCH_ROW_MIN + 1, PITCH_ROW_MAX + 1):
                for x in range(8):
                    self._set_grid_light(x, y, self._step_loop_color(x))
            return
        grid_mode = self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID
        for y in range(PITCH_ROW_MIN, PITCH_ROW_MAX + 1):
            pitch = self._pitch_for_row(y)
            for x in range(8):
                if grid_mode and y >= 4 and x >= 4:
                    index = (y - 4) * 4 + (x - 4)
                    self._set_grid_light(x, y, self._grid_cell_color(index))
                    continue
                step = self._page_index * STEPS_PER_PAGE + x
                self._set_grid_light(x, y, self._pitch_color(step, pitch, x))

    def _step_loop_color(self, step):
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

    def _pitch_color(self, step, pitch, x):
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return "MelodicSequencer.NoClip"
        color = "MelodicSequencer.StepBeat" if x == 0 or x == 4 else "MelodicSequencer.StepEmpty"
        if pitch % 12 == self._root_pitch() % 12:
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
        if not self._device_shift_held:
            return
        for x in range(8):
            self._set_grid_light(x, PREVIEW_TOGGLE_Y, self._loop_color(x))

    def _loop_color(self, index):
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
            for x in range(8):
                button = self._get_grid_button(x, y)
                if button is not None:
                    button.set_identifier(pitch)
                    button.set_channel(AUDITION_CHANNEL)
                    button.script_forwarding = ScriptForwarding.non_consuming
        self._request_midi_map_rebuild()

    def _make_control_button_listener(self, index):
        def listener(value):
            self._on_control_button_value(index, value)
        return listener

    def _on_control_button_value(self, index, value):
        if not self.is_enabled():
            return
        if not value:
            return
        if index == CHROMATIC_SLOT:
            # Slot 0 dual-purpose: chromatic toggle when shift held,
            # Capture MIDI when shift not held.
            if self._device_shift_held:
                self._toggle_chromatic_mode()
            else:
                self._capture_midi()
        elif index == SCALE_CYCLE_SLOT:
            # Slot 1 dual-purpose: scale cycle / Quantize.
            if self._device_shift_held:
                self._cycle_scale(1)
            else:
                self._quantize_selected()
        elif index == CYCLE_SLOT:
            self._toggle_bottom_right_mode()
        # Slots 2-5 are free; slot 7 is the device shift (untouched).

    def adjust_pitch_offset(self, delta):
        """Public: shift the pitch row range by `delta` semitones.

        Called from the parent control surface when the user presses the top
        arrow buttons in melodic_sequence main mode.
        """
        if self.is_enabled():
            self._adjust_pitch_offset(delta)

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
        return ("MelodicSequencer.Control.CycleGrid"
                if self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID
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
        # Slot 5 is dual-purpose. Shift held → chromatic toggle. Shift not
        # held → Capture MIDI (bright when capturable, dim otherwise).
        if self._device_shift_held:
            return ("MelodicSequencer.Control.GridSelected"
                    if self._chromatic_mode
                    else "MelodicSequencer.Control.Grid")
        if getattr(self.song, "can_capture_midi", False):
            return "MelodicSequencer.Control.CaptureMidiReady"
        return "MelodicSequencer.Control.CaptureMidi"

    def _scale_or_quantize_color(self):
        """Slot 6 is dual-purpose: scale cycle (shift held) / Quantize (shift
        not held). Encapsulates both LED states in one helper to keep
        `_update_control_leds` compact."""
        if self._device_shift_held:
            return "MelodicSequencer.Control.ScaleCycle"
        return "MelodicSequencer.Control.Quantize"

    def _capture_midi(self):
        song = self.song
        if not getattr(song, "can_capture_midi", False):
            self._emit(Event.MIDI_CAPTURED, ok=False, reason="nothing to capture")
            return
        try:
            song.capture_midi()
            self._emit(Event.MIDI_CAPTURED, ok=True, reason="")
        except Exception as exc:
            self._log("capture_midi failed: {}".format(exc))
            self._emit(Event.MIDI_CAPTURED, ok=False, reason=str(exc))

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
        # Drop step-loop press anchors so a held step pad can't leak across
        # a shift transition. The scoped loop itself stays put.
        if not pressed:
            self._step_loop_press_points = []
            self._step_loop_range_active = False
        if self.is_enabled():
            if self._preview_mode:
                self._update_audition_translations()
            self.update()

    def _adjust_pitch_offset(self, delta):
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
        # Slot 0 = Capture / Chromatic (dual via shift). Slot 1 = Quantize /
        # Scale cycle. Slots 2-5 = free (grid resolutions moved to the
        # bottom-right 4x4 in "grid" mode). Slot 6 = cycle (pitch ↔ grid).
        # Slot 7 = device shift; session mode overrides via _stop_solo_mute_modes.
        shift_color = ("MelodicSequencer.Control.Shift"
                       if self._device_shift_held
                       else "DefaultButton.Disabled")
        colors = (
          self._chromatic_color(),             # slot 0
          self._scale_or_quantize_color(),     # slot 1
          "DefaultButton.Disabled",            # slot 2
          "DefaultButton.Disabled",            # slot 3
          "DefaultButton.Disabled",            # slot 4
          "DefaultButton.Disabled",            # slot 5
          self._cycle_color(),                 # slot 6
          shift_color)                         # slot 7
        for index, button in enumerate(self._control_buttons):
            try:
                button.set_light(colors[index] if self.is_enabled() else "DefaultButton.Disabled")
            except Exception:
                pass

    def _turn_control_buttons_off(self):
        for button in self._control_buttons:
            try:
                button.set_light("DefaultButton.Disabled")
            except Exception:
                pass

    def _selected_track_can_hold_midi(self):
        track = self.song.view.selected_track
        return liveobj_valid(track) and getattr(track, "has_midi_input", True)

    def _turn_grid_off(self):
        if self._grid_matrix is not None:
            for y in range(8):
                for x in range(8):
                    self._set_grid_light(x, y, "DefaultButton.Disabled")

    def _set_grid_light(self, x, y, color):
        button = self._get_grid_button(x, y)
        if button is not None:
            self._send_programmer_pad_color(button, color)

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

    def _send_programmer_pad_color(self, button, color):
        note, color_value = send_pad_color(
            self.canonical_parent, button, color, MELODIC_COLOR_VALUES)
        if self._led_debug_count < 8:
            self._log("led send: note={}, value={}".format(note, color_value))
            self._led_debug_count += 1
