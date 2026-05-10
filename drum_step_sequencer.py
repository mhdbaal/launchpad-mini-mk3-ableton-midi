from __future__ import absolute_import, print_function, unicode_literals

import Live

from ableton.v2.base import listens, liveobj_valid, task
from ableton.v2.control_surface import Component


STEP_LENGTH = 0.25
STEPS_PER_PAGE = 32
PAGE_LENGTH = STEP_LENGTH * STEPS_PER_PAGE
DEFAULT_VELOCITY = 100
DEFAULT_CLIP_PAGES = 1
BOTTOM_RIGHT_SIZE = 16
NOTE_SELECTOR_BASE_PITCH = 36
PROGRAMMER_LED_CHANNEL = 0
DRUM_SEQUENCER_COLOR_VALUES = {
    "DefaultButton.Disabled": 0,
    "DrumSequencer.StepEmpty": 51,
    "DrumSequencer.StepBeat": 43,
    "DrumSequencer.StepActive": 29,
    "DrumSequencer.StepMuted": 84,
    "DrumSequencer.Playhead": 21,
    "DrumSequencer.PlayheadActive": 3,
    "DrumSequencer.NoDrumRack": 7,
    "DrumSequencer.NoClip": 1,
    "DrumSequencer.NoteEmpty": 1,
    "DrumSequencer.NoteFilled": 43,
    "DrumSequencer.NoteSelected": 96,
    "DrumSequencer.Loop.Outside": 1,
    "DrumSequencer.Loop.Inside": 43,
    "DrumSequencer.Loop.Selected": 96,
    "DrumSequencer.Loop.Playhead": 21,
    "DrumSequencer.Loop.RangeEdit": 1,
}


class DrumStepSequencerComponent(Component):
    """Small Push-style drum sequencer for the Launchpad Mini MK3 grid."""

    def __init__(self, drum_group_component=None, *a, **k):
        super(DrumStepSequencerComponent, self).__init__(*a, **k)
        self._drum_group = drum_group_component
        self._step_matrix = None
        self._loop_matrix = None
        self._note_matrix = None
        self._grid_matrix = None
        self._clip = None
        self._clip_slot = None
        self._drum_group_device = None
        self._selected_pitch = 36
        self._page_index = 0
        self._loop_press_points = []
        self._playhead = None
        self._notes = []
        self._led_debug_count = 0
        self._delayed_update_task = self._tasks.add(task.sequence(task.wait(0.1), task.run(self.update)))
        self._delayed_update_task.kill()
        self._on_detail_clip_changed.subject = self.song.view
        self._on_selected_track_changed.subject = self.song.view

    def disconnect(self):
        self.set_grid_matrix(None)
        self.set_note_matrix(None)
        self._set_clip(None)
        self._set_drum_group_device(None)
        super(DrumStepSequencerComponent, self).disconnect()

    def set_grid_matrix(self, matrix):
        if matrix != self._grid_matrix:
            if self._grid_matrix is not None:
                self._grid_matrix.remove_value_listener(self._on_grid_matrix_value)
            self._grid_matrix = matrix
            if self._grid_matrix is not None:
                self._grid_matrix.add_value_listener(self._on_grid_matrix_value)
            self._step_matrix = matrix.submatrix[:, :4] if matrix is not None else None
            self._note_matrix = matrix.submatrix[:4, 4:8] if matrix is not None else None
            self._loop_matrix = matrix.submatrix[4:8, 4:8] if matrix is not None else None
            self._request_midi_map_rebuild()
            self._log("grid matrix set: {}x{}".format(matrix.width(), matrix.height()) if matrix is not None else "grid matrix cleared")
            self.update()

    def set_note_matrix(self, matrix):
        if matrix != self._note_matrix:
            if self._note_matrix is not None:
                self._note_matrix.remove_value_listener(self._on_note_matrix_value)
            self._note_matrix = matrix
            if self._note_matrix is not None:
                self._note_matrix.add_value_listener(self._on_note_matrix_value)
            self.update()

    def set_enabled(self, enabled):
        super(DrumStepSequencerComponent, self).set_enabled(enabled)
        self._log("enabled: {}".format(enabled))
        if enabled:
            self._led_debug_count = 0
            self._refresh_targets()
            self._delayed_update_task.restart()
        else:
            self._delayed_update_task.kill()
            self._playhead = None
            self._turn_matrices_off()

    def update(self):
        super(DrumStepSequencerComponent, self).update()
        if self.is_enabled():
            self._update_step_leds()
            self._update_note_leds()
            self._update_loop_leds()

    @listens("detail_clip")
    def _on_detail_clip_changed(self):
        if self.is_enabled():
            self._refresh_clip()

    @listens("selected_track")
    def _on_selected_track_changed(self):
        if self.is_enabled():
            self._refresh_targets()

    @listens("selected_drum_pad")
    def _on_selected_drum_pad_changed(self):
        drum_group = self._drum_group_device
        if liveobj_valid(drum_group):
            selected_pad = drum_group.view.selected_drum_pad
            if liveobj_valid(selected_pad):
                self._selected_pitch = selected_pad.note
        elif self._selected_pitch is None:
            self._selected_pitch = NOTE_SELECTOR_BASE_PITCH
        self._refresh_notes()
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

    def _refresh_targets(self):
        track = self.song.view.selected_track
        drum_group = self._find_drum_group_device(track)
        self._log("target track: {}, drum group: {}".format(getattr(track, "name", "<none>"), getattr(drum_group, "name", "<none>")))
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
        self._refresh_notes()

    def _set_drum_group_device(self, drum_group):
        self._drum_group_device = drum_group
        if self._drum_group is not None:
            self._drum_group.set_drum_group_device(drum_group)
        self._on_selected_drum_pad_changed.subject = drum_group.view if liveobj_valid(drum_group) else None
        if liveobj_valid(drum_group):
            selected_pad = drum_group.view.selected_drum_pad
            if liveobj_valid(selected_pad):
                self._selected_pitch = selected_pad.note

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
                    drum_group = self._find_drum_group_device_in_device(nested_device)
                    if liveobj_valid(drum_group):
                        return drum_group
        return None

    def _ensure_clip(self):
        if liveobj_valid(self._clip) and self._clip.is_midi_clip:
            return True
        slot = self._selected_clip_slot()
        if slot is None:
            self._show_message("Drum Sequencer: select a MIDI clip slot")
            return False
        if slot.has_clip:
            if slot.clip.is_midi_clip:
                self.song.view.detail_clip = slot.clip
                self._set_clip(slot.clip)
                return True
            self._show_message("Drum Sequencer: selected clip is not MIDI")
            return False
        if not self._selected_track_can_hold_midi():
            self._show_message("Drum Sequencer: select a MIDI track")
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
            loop_end = max(self._clip.loop_end, PAGE_LENGTH * BOTTOM_RIGHT_SIZE)
            self._notes = list(self._clip.get_notes_extended(from_time=0,
              from_pitch=0,
              time_span=loop_end,
              pitch_span=128))
        else:
            self._notes = []

    def _on_grid_matrix_value(self, value, x, y, is_momentary):
        if not self.is_enabled():
            return
        if y >= 4 and x >= 4:
            self._handle_loop_press((y - 4) * 4 + (x - 4), bool(value))
            return
        if not value:
            return
        self._log("grid pressed: {},{}".format(x, y))
        if y < 4:
            step = y * 8 + x
            self._log("step pressed: {}".format(step))
            if self._ensure_clip():
                self._toggle_step(step)
        elif x < 4:
            self._select_note_by_grid_position(x, y)

    def _on_note_matrix_value(self, value, x, y, is_momentary):
        if self.is_enabled() and value and self._note_matrix is not None:
            self._select_note_by_grid_position(x, y + 4)

    def _select_note_by_grid_position(self, x, y):
        self._selected_pitch = self._pitch_for_note_button(x, y - 4)
        self._log("note selected: {}".format(self._selected_pitch))
        if liveobj_valid(self._drum_group_device):
            pad = self._drum_pad_for_pitch(self._selected_pitch)
            if liveobj_valid(pad):
                self._drum_group_device.view.selected_drum_pad = pad
        self._refresh_notes()
        self.update()

    def _handle_loop_press(self, index, pressed):
        if pressed:
            if index not in self._loop_press_points:
                self._loop_press_points.append(index)
            self._log("loop pressed: {}".format(index))
            self._update_loop_leds()
        else:
            if len(self._loop_press_points) >= 2:
                start = min(self._loop_press_points)
                end = max(self._loop_press_points) + 1
                self._set_loop_pages(start, end)
            else:
                self._page_index = index
                if self._ensure_clip():
                    self._select_page(index)
            self._loop_press_points = []
            self.update()

    def _pitch_for_note_button(self, x, y):
        index = (4 - y - 1) * 4 + x
        if liveobj_valid(self._drum_group_device):
            visible_pads = self._drum_group_device.visible_drum_pads
            if visible_pads and index < len(visible_pads):
                pad = visible_pads[index]
                if liveobj_valid(pad):
                    return pad.note
        return NOTE_SELECTOR_BASE_PITCH + index

    def _drum_pad_for_pitch(self, pitch):
        if liveobj_valid(self._drum_group_device):
            for pad in self._drum_group_device.drum_pads:
                if pad.note == pitch:
                    return pad
        return None

    def _toggle_step(self, step):
        if self._selected_pitch is None:
            self._selected_pitch = NOTE_SELECTOR_BASE_PITCH
        start = self._time_for_step(step)
        if self._step_has_note(step):
            self._clip.remove_notes_extended(from_time=start,
              from_pitch=self._selected_pitch,
              time_span=STEP_LENGTH,
              pitch_span=1)
        else:
            note = Live.Clip.MidiNoteSpecification(pitch=self._selected_pitch,
              start_time=start,
              duration=STEP_LENGTH,
              velocity=DEFAULT_VELOCITY,
              mute=False)
            self._clip.add_new_notes((note,))
            self._clip.deselect_all_notes()
            self._ensure_loop_contains_time(start + STEP_LENGTH)
        self._refresh_notes()
        self.update()

    def _time_for_step(self, step):
        return self._page_index * PAGE_LENGTH + step * STEP_LENGTH

    def _step_has_note(self, step):
        start = self._time_for_step(step)
        end = start + STEP_LENGTH
        for note in self._notes:
            if note.pitch == self._selected_pitch and start <= note.start_time < end:
                return True
        return False

    def _step_note_muted(self, step):
        start = self._time_for_step(step)
        end = start + STEP_LENGTH
        for note in self._notes:
            if note.pitch == self._selected_pitch and start <= note.start_time < end:
                return note.mute
        return False

    def _set_loop_pages(self, start_page, end_page):
        if self._ensure_clip():
            self._page_index = start_page
            self._set_clip_loop(start_page * PAGE_LENGTH, end_page * PAGE_LENGTH)

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

    def _update_step_leds(self):
        if self._grid_matrix is None:
            return
        for y in range(4):
            for x in range(8):
                self._set_grid_light(x, y, self._step_color(y * 8 + x))

    def _step_color(self, step):
        color = "DrumSequencer.NoClip"
        if liveobj_valid(self._clip) or self._selected_track_can_hold_midi():
            color = "DrumSequencer.StepBeat" if step % 4 == 0 else "DrumSequencer.StepEmpty"
            if self._step_has_note(step):
                color = "DrumSequencer.StepMuted" if self._step_note_muted(step) else "DrumSequencer.StepActive"
            if self._playhead_is_on_step(step):
                color = "DrumSequencer.PlayheadActive" if self._step_has_note(step) else "DrumSequencer.Playhead"
        return color

    def _update_note_leds(self):
        if self._grid_matrix is None:
            return
        for y in range(4):
            for x in range(4):
                pitch = self._pitch_for_note_button(x, y)
                color = "DrumSequencer.NoteSelected" if pitch == self._selected_pitch else "DrumSequencer.NoteEmpty"
                if color != "DrumSequencer.NoteSelected" and self._has_any_note_for_pitch(pitch):
                    color = "DrumSequencer.NoteFilled"
                self._set_grid_light(x, y + 4, color)

    def _update_loop_leds(self):
        if self._grid_matrix is None:
            return
        for y in range(4):
            for x in range(4):
                self._set_grid_light(x + 4, y + 4, self._loop_color(y * 4 + x))

    def _loop_color(self, index):
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return "DrumSequencer.NoClip"
        if index in self._loop_press_points:
            return "DrumSequencer.Loop.RangeEdit"
        if self._playhead_is_on_page(index):
            return "DrumSequencer.Loop.Playhead"
        if index == self._page_index:
            return "DrumSequencer.Loop.Selected"
        if liveobj_valid(self._clip):
            start = index * PAGE_LENGTH
            if self._clip.loop_start <= start < self._clip.loop_end:
                return "DrumSequencer.Loop.Inside"
        return "DrumSequencer.Loop.Outside"

    def _playhead_is_on_step(self, step):
        if self._playhead is None:
            return False
        start = self._time_for_step(step)
        return start <= self._playhead < start + STEP_LENGTH

    def _playhead_is_on_page(self, page):
        if self._playhead is None:
            return False
        start = page * PAGE_LENGTH
        return start <= self._playhead < start + PAGE_LENGTH

    def _has_any_note_for_pitch(self, pitch):
        for note in self._notes:
            if note.pitch == pitch:
                return True
        return False

    def _selected_track_can_hold_midi(self):
        track = self.song.view.selected_track
        return liveobj_valid(track) and getattr(track, "has_midi_input", True)

    def _turn_matrices_off(self):
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
            self.canonical_parent._c_instance.log_message("[DrumStepSequencer] {}".format(message))
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
        color_value = DRUM_SEQUENCER_COLOR_VALUES.get(color, 0)
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
