from __future__ import absolute_import, print_function, unicode_literals

import Live
import time

from ableton.v2.base import listens, liveobj_valid, task
from ableton.v2.control_surface import Component
from ableton.v2.control_surface.input_control_element import ScriptForwarding


STEPS_PER_PAGE = 32
# Step and page lengths are now per-instance (self._step_length, self._page_length)
# so the user can switch the step-grid resolution (1/4 .. 1/32) at runtime.
DEFAULT_VELOCITY = 100
DEFAULT_CLIP_PAGES = 1
BOTTOM_RIGHT_SIZE = 16
NOTE_SELECTOR_BASE_PITCH = 36
MIN_PITCH_OFFSET = -36
MAX_PITCH_OFFSET = 76
PROGRAMMER_LED_CHANNEL = 0
# Audition translations are sent on channel 1 (not 0). The translated pitches
# for the drum-pad selector live in 36-51, which coincides with the
# original_identifier of several OTHER pads in the matrix (e.g., the pad at
# Excel A:4 has original note 51, the loop pads at E:5..H:5 have 45-48).
# If both sat on channel 0, Live's forwarding registry — keyed by
# (channel, identifier) — would collide and route the loop / step presses to
# the drum buttons, playing a drum sound instead of selecting a page. Using a
# different channel for audition makes those registry keys disjoint.
# Channel 1 also matches DRUM_FEEDBACK_CHANNEL in launchpad_mini_mk3.py so the
# drum-pad LED feedback round-trips through the same translation.
PLAY_CHANNEL = 1
DOUBLE_TAP_SECONDS = 0.35
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
    "DrumSequencer.Loop.Outside": 39,
    "DrumSequencer.Loop.Inside": 37,
    "DrumSequencer.Loop.Selected": 77,
    "DrumSequencer.Loop.Playhead": 21,
    "DrumSequencer.Loop.RangeEdit": 3,
    "DrumSequencer.Control.Page": 43,
    "DrumSequencer.Control.Octave": 21,
    "DrumSequencer.Control.Semitone": 29,
    "DrumSequencer.Control.Grid": 11,
    "DrumSequencer.Control.GridSelected": 3,
    "DrumSequencer.Control.Reset": 84,
    "DrumSequencer.Control.Shift": 96,
    "DrumSequencer.Control.CycleLoop": 77,
    "DrumSequencer.Control.CycleVelocity": 97,
    "DrumSequencer.Velocity.Cell": 19,
    "DrumSequencer.Velocity.Selected": 97,
}


# Step-grid resolutions exposed on side-row slots 2-5 (drum sequencer).
# Each entry is (step_length_in_beats, label). The currently active resolution
# lights up GridSelected; the other three light up Grid.
GRID_OPTIONS = (
    (1.0, "1/4"),
    (0.5, "1/8"),
    (0.25, "1/16"),
    (0.125, "1/32"),
)
# Scene-button slot indices used in drum_sequence mode. Page +/- have been
# removed (the bottom-right 4x4 page-selector already does that), so everything
# moved up: grids on 0-3, reset on 4, shift on 5, slots 6-7 free.
GRID_FIRST_SLOT = 0
GRID_LAST_SLOT = GRID_FIRST_SLOT + len(GRID_OPTIONS) - 1
RESET_SLOT = GRID_LAST_SLOT + 1
SHIFT_SLOT = RESET_SLOT + 1
# Slot 6 cycles the bottom-right 4x4 between "loop selector" (default) and
# "velocity selector" modes — Push 2 style. Slot 7 is the device's shift /
# stop-solo-mute button (owned by _stop_solo_mute_modes in session), left free
# in drum mode.
CYCLE_SLOT = 6
DEFAULT_STEP_LENGTH = GRID_OPTIONS[2][0]  # 1/16

# 16 velocity levels mapped to the bottom-right 4x4 when in "velocity" mode.
# Layout matches loop indexing: index 0 = top-left of bottom-right quadrant
# (Excel E:5), index 15 = bottom-right corner (H:8). Quieter at the top so a
# vertical line of "velocity" reads like a ramp going down.
BOTTOM_RIGHT_VELOCITIES = (8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 127)
BOTTOM_RIGHT_MODE_LOOP = "loop"
BOTTOM_RIGHT_MODE_VELOCITY = "velocity"


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
        self._pitch_offset = 0
        self._step_length = DEFAULT_STEP_LENGTH
        self._page_length = self._step_length * STEPS_PER_PAGE
        self._bottom_right_mode = BOTTOM_RIGHT_MODE_LOOP
        self._default_velocity = DEFAULT_VELOCITY
        self._control_buttons = ()
        self._control_button_listeners = []
        self._shift_pressed = False
        self._loop_press_points = []
        self._loop_range_active = False
        self._last_page_tap = (-1, 0)
        self._playhead = None
        self._notes = []
        self._led_debug_count = 0
        self._delayed_update_task = self._tasks.add(task.sequence(task.wait(0.1), task.run(self.update)))
        self._delayed_update_task.kill()
        self._on_detail_clip_changed.subject = self.song.view
        self._on_selected_track_changed.subject = self.song.view

    def disconnect(self):
        self.set_control_buttons(None)
        self.set_grid_matrix(None)
        self.set_note_matrix(None)
        self._set_clip(None)
        self._set_drum_group_device(None)
        super(DrumStepSequencerComponent, self).disconnect()

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
            self._step_matrix = matrix.submatrix[:, :4] if matrix is not None else None
            self._note_matrix = matrix.submatrix[:4, 4:8] if matrix is not None else None
            self._loop_matrix = matrix.submatrix[4:8, 4:8] if matrix is not None else None
            self._request_midi_map_rebuild()
            self._log("grid matrix set: {}x{}".format(matrix.width(), matrix.height()) if matrix is not None else "grid matrix cleared")
            self._update_audition_translations()
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
            self._update_audition_translations()
            self._delayed_update_task.restart()
            self._update_control_leds()
        else:
            self._delayed_update_task.kill()
            self._playhead = None
            self._shift_pressed = False
            self._turn_matrices_off()
            self._clear_audition_translations()
            self._turn_control_buttons_off()

    def update(self):
        super(DrumStepSequencerComponent, self).update()
        if self.is_enabled():
            self._update_step_leds()
            self._update_note_leds()
            self._update_bottom_right_leds()
            self._update_control_leds()

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
        previous_pitch = self._selected_pitch
        drum_group = self._drum_group_device
        if liveobj_valid(drum_group):
            selected_pad = drum_group.view.selected_drum_pad
            if liveobj_valid(selected_pad):
                self._selected_pitch = selected_pad.note
        elif self._selected_pitch is None:
            self._selected_pitch = NOTE_SELECTOR_BASE_PITCH
        if (self._selected_pitch != previous_pitch
                and self._bottom_right_mode == BOTTOM_RIGHT_MODE_VELOCITY):
            self._update_audition_translations()
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
            self._update_bottom_right_leds()

    @listens("playing_status")
    def _on_playing_status_changed(self):
        self._on_playing_position_changed()

    @listens("loop_start")
    def _on_loop_changed(self):
        if self.is_enabled():
            self._update_bottom_right_leds()

    @listens("loop_end")
    def _on_loop_end_changed(self):
        self._on_loop_changed()

    def _refresh_targets(self):
        track = self.song.view.selected_track
        drum_group = self._find_drum_group_device(track)
        self._log("target track: {}, drum group: {}".format(getattr(track, "name", "<none>"), getattr(drum_group, "name", "<none>")))
        self._set_drum_group_device(drum_group)
        self._refresh_clip()
        self._update_audition_translations()
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
            slot.create_clip(self._page_length * DEFAULT_CLIP_PAGES)
            self.song.view.detail_clip = slot.clip
            self._clip_slot = slot
            self._set_clip(slot.clip)
            # Push-2 style: firing the newly-created slot launches the clip and,
            # if global playback isn't running yet, starts it. The user hears
            # their first step immediately.
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
            loop_end = max(self._clip.loop_end, self._page_length * BOTTOM_RIGHT_SIZE)
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
            index = (y - 4) * 4 + (x - 4)
            if self._bottom_right_mode == BOTTOM_RIGHT_MODE_VELOCITY:
                self._handle_velocity_press(index, bool(value))
            else:
                self._handle_loop_press(index, bool(value))
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
        new_pitch = self._pitch_for_note_button(x, y - 4)
        pitch_changed = new_pitch != self._selected_pitch
        self._selected_pitch = new_pitch
        self._log("note selected: {}".format(self._selected_pitch))
        if liveobj_valid(self._drum_group_device):
            pad = self._drum_pad_for_pitch(self._selected_pitch)
            if liveobj_valid(pad):
                self._drum_group_device.view.selected_drum_pad = pad
        # Velocity cells in the bottom-right point at the selected drum's
        # pitch; if that pitch changed we must re-translate them.
        if pitch_changed and self._bottom_right_mode == BOTTOM_RIGHT_MODE_VELOCITY:
            self._update_audition_translations()
        self._refresh_notes()
        self.update()

    def _handle_loop_press(self, index, pressed):
        if pressed:
            if index not in self._loop_press_points:
                self._loop_press_points.append(index)
            self._log("loop pressed: {}".format(index))
            if len(self._loop_press_points) >= 2:
                start = min(self._loop_press_points)
                end = max(self._loop_press_points) + 1
                self._set_loop_pages(start, end)
                self._loop_range_active = True
                self._show_message("Drum pages {}-{} scoped".format(start + 1, end))
            self._update_bottom_right_leds()
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

    def _pitch_for_note_button(self, x, y):
        index = (4 - y - 1) * 4 + x
        if liveobj_valid(self._drum_group_device) and self._pitch_offset == 0:
            visible_pads = self._drum_group_device.visible_drum_pads
            if visible_pads and index < len(visible_pads):
                pad = visible_pads[index]
                if liveobj_valid(pad):
                    return pad.note
        return max(0, min(127, NOTE_SELECTOR_BASE_PITCH + self._pitch_offset + index))

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
              time_span=self._step_length,
              pitch_span=1)
        else:
            note = Live.Clip.MidiNoteSpecification(pitch=self._selected_pitch,
              start_time=start,
              duration=self._step_length,
              velocity=self._default_velocity,
              mute=False)
            self._clip.add_new_notes((note,))
            self._clip.deselect_all_notes()
            self._ensure_loop_contains_time(start + self._step_length)
        self._refresh_notes()
        self.update()

    def _time_for_step(self, step):
        return self._page_index * self._page_length + step * self._step_length

    def _step_has_note(self, step):
        start = self._time_for_step(step)
        end = start + self._step_length
        for note in self._notes:
            if note.pitch == self._selected_pitch and start <= note.start_time < end:
                return True
        return False

    def _step_note_muted(self, step):
        start = self._time_for_step(step)
        end = start + self._step_length
        for note in self._notes:
            if note.pitch == self._selected_pitch and start <= note.start_time < end:
                return note.mute
        return False

    def _set_loop_pages(self, start_page, end_page):
        if self._ensure_clip():
            self._page_index = start_page
            self._set_clip_loop(start_page * self._page_length, end_page * self._page_length)

    def _scope_page(self, page):
        if self._ensure_clip():
            self._page_index = page
            self._set_clip_loop(page * self._page_length, (page + 1) * self._page_length)
            self._show_message("Drum page {} scoped".format(page + 1))

    def _is_page_double_tap(self, page):
        now = time.time()
        last_page, last_time = self._last_page_tap
        self._last_page_tap = (page, now)
        return last_page == page and now - last_time <= DOUBLE_TAP_SECONDS

    def _select_page(self, page):
        if liveobj_valid(self._clip):
            self._ensure_loop_contains_time((page + 1) * self._page_length)

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

    def _update_bottom_right_leds(self):
        if self._grid_matrix is None:
            return
        velocity_mode = self._bottom_right_mode == BOTTOM_RIGHT_MODE_VELOCITY
        for y in range(4):
            for x in range(4):
                index = y * 4 + x
                color = self._velocity_color(index) if velocity_mode else self._loop_color(index)
                self._set_grid_light(x + 4, y + 4, color)

    def _velocity_color(self, index):
        if not 0 <= index < len(BOTTOM_RIGHT_VELOCITIES):
            return "DefaultButton.Disabled"
        if BOTTOM_RIGHT_VELOCITIES[index] == self._default_velocity:
            return "DrumSequencer.Velocity.Selected"
        return "DrumSequencer.Velocity.Cell"

    def _handle_velocity_press(self, index, pressed):
        if not pressed:
            return
        if not 0 <= index < len(BOTTOM_RIGHT_VELOCITIES):
            return
        self._default_velocity = BOTTOM_RIGHT_VELOCITIES[index]
        self._log("velocity cell pressed: index={}, velocity={}".format(
            index, self._default_velocity))
        self._show_message("Velocity: {}".format(self._default_velocity))
        self._update_bottom_right_leds()

    def _toggle_bottom_right_mode(self):
        if self._bottom_right_mode == BOTTOM_RIGHT_MODE_VELOCITY:
            self._bottom_right_mode = BOTTOM_RIGHT_MODE_LOOP
            label = "loop selector"
        else:
            self._bottom_right_mode = BOTTOM_RIGHT_MODE_VELOCITY
            label = "velocity ({})".format(self._default_velocity)
        self._log("bottom-right mode: {}".format(self._bottom_right_mode))
        # Drop any in-flight loop press state so a leftover hold can't
        # scope the loop after we've already switched away.
        self._loop_press_points = []
        self._loop_range_active = False
        # Re-install audition translations: in velocity mode each cell of the
        # bottom-right 4x4 routes to (selected_pitch, cell_index_as_channel).
        self._update_audition_translations()
        self._show_message("Bottom-right: {}".format(label))
        self._update_bottom_right_leds()
        self._update_control_leds()

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
            start = index * self._page_length
            if self._clip.loop_start <= start < self._clip.loop_end:
                return "DrumSequencer.Loop.Inside"
        return "DrumSequencer.Loop.Outside"

    def _playhead_is_on_step(self, step):
        if self._playhead is None:
            return False
        start = self._time_for_step(step)
        return start <= self._playhead < start + self._step_length

    def _playhead_is_on_page(self, page):
        if self._playhead is None:
            return False
        start = page * self._page_length
        return start <= self._playhead < start + self._page_length

    def _has_any_note_for_pitch(self, pitch):
        for note in self._notes:
            if note.pitch == pitch:
                return True
        return False

    def _update_audition_translations(self):
        if self._grid_matrix is None or not self.is_enabled():
            return
        # Make state explicit: every pad reverts to default identifier + exclusive
        # forwarding first, so stale state from a previous mode (or a previous
        # audition translation that was never cleared) can't leak a pad into
        # non_consuming and double-trigger Live. Only the bottom-left drum-pad
        # selector is then re-translated for audition.
        for y in range(8):
            for x in range(8):
                button = self._get_grid_button(x, y)
                if button is not None:
                    button.use_default_message()
                    button.script_forwarding = ScriptForwarding.exclusive
        # Bottom-LEFT drum-pad selector — always fully translated, regardless of
        # whether the bottom-right is in loop or velocity mode. The 16 cells
        # each route to a unique pitch (drum) on channel 1 (PLAY_CHANNEL).
        for y in range(4):
            for x in range(4):
                pitch = self._pitch_for_note_button(x, y)
                self._translate_button_for_audition(x, y + 4, pitch)
        # Bottom-RIGHT velocity cells (only in velocity mode). To make each
        # cell distinguishable in Live's forwarding registry — keyed by
        # (channel, identifier) — every cell points at the selected drum's
        # pitch but on a UNIQUE channel. We use channels 2-15 (14 cells)
        # because channel 0 is reserved for the device's raw pad notes and
        # channel 1 is already used by the bottom-left drum-pad selector
        # (every drum pitch is registered as `(1, pitch)` for it). Cells 14
        # and 15 (the highest two velocities, 120 and 127) deliberately stay
        # in default exclusive state — they don't audition, only set the
        # default velocity when pressed. This asymmetry beats the alternative
        # of dropping a bottom-left drum-pad cell or accepting a registry
        # collision. Live's translation map can't fix per-cell velocity either
        # way; the actual velocity heard is the hardware press velocity.
        if self._bottom_right_mode == BOTTOM_RIGHT_MODE_VELOCITY:
            audition_cells = len(BOTTOM_RIGHT_VELOCITIES) - 2  # 14
            for cell_index in range(audition_cells):
                inner_x = cell_index % 4
                inner_y = cell_index // 4
                channel = cell_index + 2  # channels 2..15
                self._translate_button_for_audition(inner_x + 4, inner_y + 4,
                                                   self._selected_pitch,
                                                   channel=channel)
        self._request_midi_map_rebuild()

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

    def _translate_button_for_audition(self, x, y, pitch, channel=None):
        button = self._get_grid_button(x, y)
        if button is not None:
            button.set_identifier(pitch)
            button.set_channel(PLAY_CHANNEL if channel is None else channel)
            button.script_forwarding = ScriptForwarding.non_consuming

    def _make_control_button_listener(self, index):
        def listener(value):
            self._on_control_button_value(index, value)
        return listener

    def _on_control_button_value(self, index, value):
        if not self.is_enabled():
            return
        if index == SHIFT_SLOT:
            self._shift_pressed = bool(value)
            self._update_control_leds()
            if value:
                self._show_navigation_message()
            return
        if not value:
            return
        if GRID_FIRST_SLOT <= index <= GRID_LAST_SLOT:
            self._set_step_length(GRID_OPTIONS[index - GRID_FIRST_SLOT][0])
        elif index == RESET_SLOT:
            self._set_pitch_offset(0)
        elif index == CYCLE_SLOT:
            self._toggle_bottom_right_mode()

    def adjust_pitch_offset(self, delta):
        """Public: shift the drum-pad selector pitch range by `delta` semitones.

        Called from the parent control surface when the user presses the top
        arrow buttons in drum_sequence main mode.
        """
        if self.is_enabled():
            self._adjust_pitch_offset(delta)

    def _set_step_length(self, length):
        """Change the step-grid resolution. Notes already in the clip keep their
        absolute time positions; only their on-screen step alignment changes."""
        if length == self._step_length:
            return
        self._step_length = length
        self._page_length = length * STEPS_PER_PAGE
        self._page_index = min(self._page_index, BOTTOM_RIGHT_SIZE - 1)
        self._refresh_notes()
        self.update()
        self._show_message("Drum grid: {}".format(self._current_grid_label()))

    def _current_grid_label(self):
        for length, label in GRID_OPTIONS:
            if length == self._step_length:
                return label
        return "{}b".format(self._step_length)

    def _grid_color_for_slot(self, slot_index):
        grid_idx = slot_index - GRID_FIRST_SLOT
        if not 0 <= grid_idx < len(GRID_OPTIONS):
            return "DefaultButton.Disabled"
        return ("DrumSequencer.Control.GridSelected"
                if GRID_OPTIONS[grid_idx][0] == self._step_length
                else "DrumSequencer.Control.Grid")

    def _adjust_pitch_offset(self, delta):
        self._set_pitch_offset(self._pitch_offset + delta)

    def _set_pitch_offset(self, offset):
        self._pitch_offset = max(MIN_PITCH_OFFSET, min(MAX_PITCH_OFFSET, offset))
        self._selected_pitch = self._pitch_for_note_button(0, 3)
        self._update_audition_translations()
        self._show_navigation_message()
        self.update()

    def _show_navigation_message(self):
        octave = int(self._pitch_offset / 12)
        semitone = self._pitch_offset - octave * 12
        self._show_message("Drum grid {} | page {} | octave {:+d} | semitone {:+d}".format(
            self._current_grid_label(), self._page_index + 1, octave, semitone))

    def _update_control_leds(self):
        if not self._control_buttons:
            return
        # Grids on 0-3, reset on 4, shift on 5, slot 6 free, slot 7 cycles
        # the bottom-right 4x4 between loop and velocity modes.
        cycle_color = ("DrumSequencer.Control.CycleVelocity"
                       if self._bottom_right_mode == BOTTOM_RIGHT_MODE_VELOCITY
                       else "DrumSequencer.Control.CycleLoop")
        colors = (
          self._grid_color_for_slot(0),
          self._grid_color_for_slot(1),
          self._grid_color_for_slot(2),
          self._grid_color_for_slot(3),
          "DrumSequencer.Control.Reset",
          "DrumSequencer.Control.Shift",
          "DefaultButton.Disabled",
          cycle_color)
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
