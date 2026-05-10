from __future__ import absolute_import, print_function, unicode_literals

import Live
import time

from ableton.v2.base import listens, liveobj_valid, task
from ableton.v2.control_surface import Component
from ableton.v2.control_surface.input_control_element import ScriptForwarding


STEP_LENGTH = 0.25
STEPS_PER_PAGE = 8
PAGE_LENGTH = STEP_LENGTH * STEPS_PER_PAGE
DEFAULT_VELOCITY = 100
DEFAULT_CLIP_PAGES = 8
PROGRAMMER_LED_CHANNEL = 0
DOUBLE_TAP_SECONDS = 0.35
BASE_PITCH = 60
MIN_PITCH_OFFSET = -60
MAX_PITCH_OFFSET = 60
PREVIEW_TOGGLE_X = 7
PREVIEW_TOGGLE_Y = 7
MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)

MELODIC_COLOR_VALUES = {
    "DefaultButton.Disabled": 0,
    "MelodicSequencer.StepEmpty": 51,
    "MelodicSequencer.StepBeat": 43,
    "MelodicSequencer.StepActive": 29,
    "MelodicSequencer.Root": 96,
    "MelodicSequencer.Playhead": 21,
    "MelodicSequencer.PlayheadActive": 3,
    "MelodicSequencer.NoClip": 1,
    "MelodicSequencer.Loop.Outside": 1,
    "MelodicSequencer.Loop.Inside": 43,
    "MelodicSequencer.Loop.Selected": 96,
    "MelodicSequencer.Loop.Playhead": 21,
    "MelodicSequencer.Loop.RangeEdit": 1,
    "MelodicSequencer.Preview.Off": 41,
    "MelodicSequencer.Preview.On": 96,
    "MelodicSequencer.Control.Page": 43,
    "MelodicSequencer.Control.Octave": 21,
    "MelodicSequencer.Control.Semitone": 29,
    "MelodicSequencer.Control.Reset": 84,
    "MelodicSequencer.Control.Shift": 96,
}


class MelodicStepSequencerComponent(Component):
    """Launchpad95-style melodic step sequencer: 7 pitch rows + 1 page row."""

    def __init__(self, *a, **k):
        super(MelodicStepSequencerComponent, self).__init__(*a, **k)
        self._grid_matrix = None
        self._clip = None
        self._clip_slot = None
        self._notes = []
        self._page_index = 0
        self._loop_press_points = []
        self._loop_range_active = False
        self._last_page_tap = (-1, 0)
        self._held_grid_buttons = set()
        self._preview_mode = False
        self._pitch_offset = 0
        self._control_buttons = ()
        self._control_button_listeners = []
        self._shift_pressed = False
        self._playhead = None
        self._led_debug_count = 0
        self._delayed_update_task = self._tasks.add(task.sequence(task.wait(0.1), task.run(self.update)))
        self._delayed_update_task.kill()
        self._on_detail_clip_changed.subject = self.song.view
        self._on_selected_track_changed.subject = self.song.view

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
            self._preview_mode = False
            self._shift_pressed = False
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
        self._refresh_notes()

    def _selected_clip_slot(self):
        slot = self.song.view.highlighted_clip_slot
        return slot if slot is not None else None

    def _ensure_clip(self):
        if liveobj_valid(self._clip) and self._clip.is_midi_clip:
            return True
        slot = self._selected_clip_slot()
        if slot is None:
            self._show_message("Melodic Sequencer: select a MIDI clip slot")
            return False
        if slot.has_clip:
            if slot.clip.is_midi_clip:
                self.song.view.detail_clip = slot.clip
                self._set_clip(slot.clip)
                return True
            self._show_message("Melodic Sequencer: selected clip is not MIDI")
            return False
        if not self._selected_track_can_hold_midi():
            self._show_message("Melodic Sequencer: select a MIDI track")
            return False
        try:
            slot.create_clip(PAGE_LENGTH * DEFAULT_CLIP_PAGES)
            self.song.view.detail_clip = slot.clip
            self._clip_slot = slot
            self._set_clip(slot.clip)
            return True
        except RuntimeError:
            return False

    def _refresh_notes(self):
        if liveobj_valid(self._clip):
            loop_end = max(self._clip.loop_end, PAGE_LENGTH * DEFAULT_CLIP_PAGES)
            self._notes = list(self._clip.get_notes_extended(from_time=0,
              from_pitch=0,
              time_span=loop_end,
              pitch_span=128))
        else:
            self._notes = []

    def _on_grid_matrix_value(self, value, x, y, is_momentary):
        if not self.is_enabled():
            return
        if y == 7:
            if x == PREVIEW_TOGGLE_X:
                if value:
                    self._toggle_preview_mode()
                return
            self._handle_loop_press(x, bool(value))
            return
        if self._preview_mode:
            return
        if not value:
            self._held_grid_buttons.discard((x, y))
            return
        if (x, y) in self._held_grid_buttons:
            return
        self._held_grid_buttons.add((x, y))
        pitch = self._pitch_for_row(y)
        step = self._page_index * STEPS_PER_PAGE + x
        self._log("grid pressed: {},{} pitch={} step={}".format(x, y, pitch, step))
        if self._ensure_clip():
            self._toggle_note(step, pitch)

    def _handle_loop_press(self, index, pressed):
        if pressed:
            if index not in self._loop_press_points:
                self._loop_press_points.append(index)
            if len(self._loop_press_points) >= 2:
                start = min(self._loop_press_points)
                end = max(self._loop_press_points) + 1
                self._set_loop_pages(start, end)
                self._loop_range_active = True
                self._show_message("Melodic pages {}-{} scoped".format(start + 1, end))
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

    def _toggle_note(self, step, pitch):
        start = step * STEP_LENGTH
        if self._step_has_pitch(step, pitch):
            self._clip.remove_notes_extended(from_time=start,
              from_pitch=pitch,
              time_span=STEP_LENGTH,
              pitch_span=1)
            self._log("note removed: pitch={} start={}".format(pitch, start))
        else:
            note = Live.Clip.MidiNoteSpecification(pitch=pitch,
              start_time=start,
              duration=STEP_LENGTH,
              velocity=DEFAULT_VELOCITY,
              mute=False)
            self._clip.add_new_notes((note,))
            self._clip.deselect_all_notes()
            self._ensure_loop_contains_time(start + STEP_LENGTH)
            self._log("note added: pitch={} start={}".format(pitch, start))
        self._refresh_notes()
        self.update()

    def _step_has_pitch(self, step, pitch):
        start = step * STEP_LENGTH
        end = start + STEP_LENGTH
        for note in self._notes:
            if note.pitch == pitch and start <= note.start_time < end:
                return True
        return False

    def _set_loop_pages(self, start_page, end_page):
        if self._ensure_clip():
            self._page_index = start_page
            self._set_clip_loop(start_page * PAGE_LENGTH, end_page * PAGE_LENGTH)

    def _scope_page(self, page):
        if self._ensure_clip():
            self._page_index = page
            self._set_clip_loop(page * PAGE_LENGTH, (page + 1) * PAGE_LENGTH)
            self._show_message("Melodic page {} scoped".format(page + 1))

    def _is_page_double_tap(self, page):
        now = time.time()
        last_page, last_time = self._last_page_tap
        self._last_page_tap = (page, now)
        return last_page == page and now - last_time <= DOUBLE_TAP_SECONDS

    def _select_page(self, page):
        if liveobj_valid(self._clip):
            self._ensure_loop_contains_time((page + 1) * PAGE_LENGTH)

    def _ensure_loop_contains_time(self, end_time):
        if liveobj_valid(self._clip) and end_time > self._clip.loop_end:
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
        scale = self._current_scale()
        degree = 6 - y
        root = self._root_pitch()
        return root + scale[degree % len(scale)] + 12 * int(degree / len(scale))

    def _current_scale(self):
        scale_name = getattr(self.song, "scale_name", "") or ""
        return MINOR_SCALE if "Minor" in scale_name or "minor" in scale_name else MAJOR_SCALE

    def _root_pitch(self):
        root_note = getattr(self.song, "root_note", 0) or 0
        return BASE_PITCH + int(root_note) + self._pitch_offset

    def _update_pitch_leds(self):
        if self._grid_matrix is None:
            return
        for y in range(7):
            pitch = self._pitch_for_row(y)
            for x in range(8):
                step = self._page_index * STEPS_PER_PAGE + x
                self._set_grid_light(x, y, self._pitch_color(step, pitch, x))

    def _pitch_color(self, step, pitch, x):
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return "MelodicSequencer.NoClip"
        color = "MelodicSequencer.StepBeat" if x == 0 or x == 4 else "MelodicSequencer.StepEmpty"
        if pitch % 12 == self._root_pitch() % 12:
            color = "MelodicSequencer.Root"
        if self._step_has_pitch(step, pitch):
            color = "MelodicSequencer.StepActive"
        if self._playhead_is_on_step(step):
            color = "MelodicSequencer.PlayheadActive" if self._step_has_pitch(step, pitch) else "MelodicSequencer.Playhead"
        return color

    def _update_loop_leds(self):
        if self._grid_matrix is None:
            return
        for x in range(8):
            self._set_grid_light(x, 7, self._loop_color(x))

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
            start = index * PAGE_LENGTH
            if self._clip.loop_start <= start < self._clip.loop_end:
                return "MelodicSequencer.Loop.Inside"
        return "MelodicSequencer.Loop.Outside"

    def _playhead_is_on_step(self, step):
        if self._playhead is None:
            return False
        start = step * STEP_LENGTH
        return start <= self._playhead < start + STEP_LENGTH

    def _playhead_is_on_page(self, page):
        if self._playhead is None:
            return False
        start = page * PAGE_LENGTH
        return start <= self._playhead < start + PAGE_LENGTH

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
            self._show_message("Melodic Sequencer: preview")
        else:
            self._clear_audition_translations()
            self._show_message("Melodic Sequencer: piano roll")
        self.update()

    def _update_audition_translations(self):
        if self._grid_matrix is None or not self.is_enabled():
            return
        for y in range(7):
            pitch = self._pitch_for_row(y)
            for x in range(8):
                button = self._get_grid_button(x, y)
                if button is not None:
                    button.set_identifier(pitch)
                    button.set_channel(0)
                    button.script_forwarding = ScriptForwarding.non_consuming
        self._request_midi_map_rebuild()

    def _make_control_button_listener(self, index):
        def listener(value):
            self._on_control_button_value(index, value)
        return listener

    def _on_control_button_value(self, index, value):
        if not self.is_enabled():
            return
        if index == 7:
            self._shift_pressed = bool(value)
            self._update_control_leds()
            if value:
                self._show_navigation_message()
            return
        if not value:
            return
        if index == 0:
            self._adjust_page(-1)
        elif index == 1:
            self._adjust_page(1)
        elif index == 2:
            self._adjust_pitch_offset(-12)
        elif index == 3:
            self._adjust_pitch_offset(12)
        elif index == 4:
            self._adjust_pitch_offset(-1)
        elif index == 5:
            self._adjust_pitch_offset(1)
        elif index == 6:
            self._set_pitch_offset(0)

    def _adjust_page(self, delta):
        self._page_index = max(0, min(DEFAULT_CLIP_PAGES - 1, self._page_index + delta))
        if liveobj_valid(self._clip):
            self._select_page(self._page_index)
        self._show_message("Melodic page {}".format(self._page_index + 1))
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
        self._show_message("Melodic page {} | octave {:+d} | semitone {:+d}".format(self._page_index + 1, octave, semitone))

    def _update_control_leds(self):
        if not self._control_buttons:
            return
        colors = (
          "MelodicSequencer.Control.Page",
          "MelodicSequencer.Control.Page",
          "MelodicSequencer.Control.Octave",
          "MelodicSequencer.Control.Octave",
          "MelodicSequencer.Control.Semitone",
          "MelodicSequencer.Control.Semitone",
          "MelodicSequencer.Control.Reset",
          "MelodicSequencer.Control.Shift")
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

    def _show_message(self, message):
        try:
            self.canonical_parent.show_message(message)
        except Exception:
            pass

    def _request_midi_map_rebuild(self):
        try:
            self.canonical_parent.request_rebuild_midi_map()
        except Exception:
            pass

    def _send_programmer_pad_color(self, button, color):
        color_value = MELODIC_COLOR_VALUES.get(color, 0)
        note = button.original_identifier()
        status = 144 + PROGRAMMER_LED_CHANNEL
        try:
            self.canonical_parent._send_midi((status, note, color_value), optimized=False)
            if self._led_debug_count < 8:
                self._log("led send: note={}, value={}".format(note, color_value))
                self._led_debug_count += 1
        except Exception:
            try:
                button.send_value(color_value, force=True, channel=PROGRAMMER_LED_CHANNEL)
            except Exception:
                pass
