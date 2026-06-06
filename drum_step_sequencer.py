from __future__ import absolute_import, print_function, unicode_literals

import Live
import time

from ableton.v2.base import listens, liveobj_valid, task
from ableton.v2.control_surface import Component
from ableton.v2.control_surface.components import find_nearest_color
from ableton.v2.control_surface.input_control_element import ScriptForwarding
from novation.colors import CLIP_COLOR_TABLE, RGB_COLOR_TABLE

from .events import Event
from .palette import (
    DRUM_SEQUENCER_COLOR_VALUES,
    VELOCITY_LEVEL_DIM,
    VELOCITY_LEVEL_PALETTE,
    send_pad_color,
)
from .programmer_mode import (
    AUDITION_CHANNEL,
    NOTE_ON_STATUS,
    PROGRAMMER_LED_CHANNEL,
)


STEPS_PER_PAGE = 32
# Step and page lengths are now per-instance (self._step_length, self._page_length)
# so the user can switch the step-grid resolution (1/4 .. 1/32) at runtime.
DEFAULT_VELOCITY = 100
DEFAULT_CLIP_PAGES = 1
BOTTOM_RIGHT_SIZE = 16
NOTE_SELECTOR_BASE_PITCH = 36
MIN_PITCH_OFFSET = -36
MAX_PITCH_OFFSET = 76
DOUBLE_TAP_SECONDS = 0.35
# Step-grid resolutions. 16 values laid out across the bottom-right 4x4 when
# the cycle button (slot 6) is in "grid" mode. Layout (row 0 = top of the
# 4x4, row 3 = bottom; index = (y-4)*4 + (x-4)):
#   Row 0 (binary):   1/4    1/8    1/16   1/32
#   Row 1 (binary):   1/64   1/128  1/256  1/512
#   Row 2 (ternary):  1/4t   1/8t   1/16t  1/32t   ← rendered in a distinct color
#   Row 3 (ternary):  1/64t  1/128t 1/256t 1/512t
# 8 binaries (cells 0-7) + 8 ternaries (cells 8-15). Triplet = binary × 2/3.
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
TERNARY_FIRST_INDEX = 8  # cells 0..7 = binary, 8..15 = ternary
DEFAULT_GRID_INDEX = 2  # 1/16

# Scene-button slot indices in drum_sequence mode (top → bottom):
#     0: Capture MIDI (clip-level action, always accessible)
#     1: Quantize Selected (clip-level action, always accessible)
#   2-5: free / disabled
#     6: cycle button (bottom-right 4x4 mode: loop ↔ grid)
#     7: device shift / stop-solo-mute (untouched here)
CAPTURE_SLOT = 0
QUANTIZE_SLOT = 1
DUPLICATE_PAGE_SLOT = 2     # held + tap page pad = copy current page → that page
DOUBLE_LOOP_SLOT = 3        # tap = double loop length, duplicate content
CYCLE_SLOT = 4              # loop selector ↔ grid resolution selector
SHIFT_SLOT = 5              # sequencer shift (moved from slot 7) — parent-owned
SPECIAL_SHIFT_SLOT = 6      # tap cycles mode (delete/duplicate); hold = action mode
SPECIAL_SHIFT_TAP_THRESHOLD = 0.3  # release within this = "tap, cycle mode"
STEPS_PER_ROW = 8           # row scope in step grid = 8 steps

# Bottom-right 4x4 modes. Cycled by slot 6. Default is "loop" (the historical
# behavior — 16 page pads). "grid" repurposes the 4x4 as a grid resolution
# selector (see GRID_OPTIONS).
BOTTOM_RIGHT_MODE_LOOP = "loop"
BOTTOM_RIGHT_MODE_GRID = "grid"
DEFAULT_STEP_LENGTH = GRID_OPTIONS[DEFAULT_GRID_INDEX][0]  # 1/16

# Per-tick delta when adjusting note velocity via the arrow buttons while a
# step pad is held. 0..127 in ~16 ticks — coarse enough to traverse quickly,
# fine enough to land on a target value with a couple of presses.
VELOCITY_ARROW_STEP = 8
VELOCITY_MIN = 1
VELOCITY_MAX = 127
# Nudge granularity in beats. Independent of the step grid — the point of
# nudge is to make small, off-grid offsets. 1/24 beat ≈ 20-40 ms at typical
# tempos, comparable to Push 2's nudge increment.
NUDGE_BEAT_DELTA = 1.0 / 24
# Velocity tier boundaries used by `_velocity_color_for`. Inclusive upper
# bounds. The 4 tiers map to the StepVel* skin keys defined in skin.py.
VELOCITY_TIER_BOUNDARIES = (31, 63, 95)
# Step-hold velocity selector: 16 levels overlaid on the bottom-right 4x4
# once a step pad has been held for VELOCITY_OVERLAY_HOLD_DELAY seconds.
# Level → velocity mapping is `level * 8` clamped to 1..127 (level 16 = 127).
# The hold delay keeps brief taps (which toggle the step) from briefly
# flashing the bar. An empty held step still arms the overlay; tapping a
# level on it creates a note at the chosen velocity (Push-style).
VELOCITY_OVERLAY_LEVELS = 16
VELOCITY_OVERLAY_HOLD_DELAY = 0.25


class DrumStepSequencerComponent(Component):
    """Small Push-style drum sequencer for the Launchpad Mini MK3 grid."""

    def __init__(self, drum_group_component=None, event_bus=None, *a, **k):
        super(DrumStepSequencerComponent, self).__init__(*a, **k)
        self._drum_group = drum_group_component
        self._event_bus = event_bus
        self._step_matrix = None
        self._loop_matrix = None
        self._note_matrix = None
        self._grid_matrix = None
        self._clip = None
        self._clip_slot = None
        self._drum_group_device = None
        # Listeners attached on drum-pad chain.color so the bottom-left
        # selector refreshes immediately when the user changes a pad's
        # color in Live (rather than waiting for the next playhead tick).
        # Stored as list of (live_obj, prop_name, callback) for cleanup.
        self._drum_color_listeners = []
        self._selected_pitch = 36
        self._page_index = 0
        self._pitch_offset = 0
        self._step_length = DEFAULT_STEP_LENGTH
        self._page_length = self._step_length * STEPS_PER_PAGE
        # "Build-out" flag: True only while we're editing a clip we just
        # created in this session. Note adds, page navigation, and length
        # changes are allowed to auto-extend the clip's loop while this is
        # True. Cleared on: clip switch, explicit loop scoping gesture,
        # or leaving sequencer mode. Once cleared, the user's loop is
        # treated as sacred and nothing auto-extends it.
        self._clip_just_created = False
        # Step pads currently held (with the user's finger on them). The map
        # value is the ABSOLUTE START TIME (beats, float) of the held pad's
        # note, tracked across nudges so subsequent arrow presses keep editing
        # the same note even after it's been moved off-grid. None when the pad
        # was pressed on an empty step.
        self._held_step_pads = {}
        # Pad steps whose release should NOT toggle their step — they were
        # consumed by a gesture (length extension or arrow edit). Discarded
        # on release, then the toggle is suppressed.
        self._consumed_step_pads = set()
        # Device shift (scene_launch_buttons_raw[7], a.k.a. stop-solo-mute
        # button) acts as a modifier in sequencer modes: while held, the
        # grid-resolution slots 0-3 become active; otherwise they're grey
        # and presses are ignored.
        self._device_shift_held = False
        # User-button reference: while the parent's User button is held,
        # scene_launch_buttons_raw doubles as the main-mode selector. We
        # short-circuit our own control-button handling + LED updates so
        # the parent's mode selector LEDs aren't clobbered.
        self._user_mode_button = None
        self._grid_option_index = DEFAULT_GRID_INDEX
        # Bottom-right 4x4 mode: "loop" (page selector) or "grid" (resolution
        # selector). Cycled via the slot 6 cycle button.
        self._bottom_right_mode = BOTTOM_RIGHT_MODE_LOOP
        self._control_buttons = ()
        self._control_button_listeners = []
        # Scene-button slot assignments. Defaults are the Mini MK3 layout
        # (module constants); device wiring can remap or disable (None)
        # individual slots via configure_slots() — e.g. the Pro MK3 moves
        # capture/quantize/shift/special-shift onto dedicated buttons.
        self._capture_slot = CAPTURE_SLOT
        self._quantize_slot = QUANTIZE_SLOT
        self._duplicate_page_slot = DUPLICATE_PAGE_SLOT
        self._double_loop_slot = DOUBLE_LOOP_SLOT
        self._cycle_slot = CYCLE_SLOT
        self._shift_slot = SHIFT_SLOT
        self._special_shift_slot = SPECIAL_SHIFT_SLOT
        # Track pin: when not None, sequencer ignores Live's selected_track and
        # operates on this track instead. Set via toggle_pin(). Cleared when the
        # pinned track is removed from the song (see _on_tracks_changed).
        self._pinned_track = None
        self._loop_press_points = []
        self._loop_range_active = False
        # Duplicate Page modifier (slot 2). While held, a tap on a page
        # pad in the bottom-right 4x4 copies the current page's notes
        # onto that page (extending the loop if needed). Suppresses the
        # normal page-view-on-tap so the page index doesn't jump first.
        self._duplicate_page_held = False
        # Special Shift (slot 6): single button cycling between
        # "delete" (red) and "duplicate" (green) modes. Quick tap cycles
        # the mode. Long press = "armed" mode: scene 0-3 become step-row
        # selectors and presses on pads/rows/pages/steps execute the
        # currently-selected mode's action. Top controls (Capture, etc.)
        # are hidden while held. Action wins → no cycle on release.
        self._special_shift_mode = "duplicate"
        self._special_shift_held = False
        self._special_shift_press_time = None
        self._special_shift_action_performed = False
        # True while the modifier is driven by a dedicated hardware button
        # (Pro MK3 Clear/Duplicate via set_action_modifier) — release must
        # never tap-cycle the mode in that case: the button IS the mode.
        self._special_shift_external = False
        # For duplicate mode only: captured source on 1st tap. None means
        # "no source yet, next tap captures". Tuples discriminate the
        # target kind so a cross-type 2nd tap (pad → row) resets rather
        # than producing a meaningless copy.
        #   ("pad", pitch)
        #   ("row", row_idx_0_to_3, page_idx)
        #   ("page", page_idx)
        #   ("step", global_step_idx)
        self._duplicate_source = None
        # Step-grid loop range picker — active while device shift is held.
        # The step grid (top 4x8) doubles as a sub-page loop selector:
        # tap one step => loop = that single step; hold + range = scope.
        self._step_loop_press_points = []
        self._step_loop_range_active = False
        self._last_page_tap = (-1, 0)
        self._playhead = None
        self._notes = []
        self._led_debug_count = 0
        self._delayed_update_task = self._tasks.add(task.sequence(task.wait(0.1), task.run(self.update)))
        self._delayed_update_task.kill()
        # Velocity overlay arming: a step pad must be held continuously for
        # VELOCITY_OVERLAY_HOLD_DELAY seconds before the bar appears. The
        # task is restarted on every step press; the release path disarms
        # when the held set empties.
        self._velocity_overlay_armed = False
        self._velocity_overlay_arm_task = self._tasks.add(
            task.sequence(task.wait(VELOCITY_OVERLAY_HOLD_DELAY),
                          task.run(self._arm_velocity_overlay)))
        self._velocity_overlay_arm_task.kill()
        self._on_detail_clip_changed.subject = self.song.view
        self._on_selected_track_changed.subject = self.song.view
        self._on_selected_scene_changed.subject = self.song.view
        self._on_tracks_changed.subject = self.song
        self._on_can_capture_midi_changed.subject = self.song

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
            self._held_step_pads = {}
            self._consumed_step_pads = set()
            self._disarm_velocity_overlay()
            # Leaving sequencer mode counts as "done with build-out". Re-entering
            # later should treat the (now unchanged) clip's loop as sacred.
            self._clip_just_created = False
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
        # When pinned, Live's detail_clip can wander to other tracks (the user
        # may click around in the arrangement). _refresh_clip already ignores
        # detail_clip in that case, but we still re-run it so anything that
        # depends on the clip-listener side effects stays consistent.
        if self.is_enabled():
            self._refresh_clip()

    @listens("selected_track")
    def _on_selected_track_changed(self):
        # When pinned, selection changes in Live must NOT swap our target —
        # the whole point of pinning is to stay on a specific track. _refresh_targets
        # already routes through _resolve_target_track, so it's a no-op refresh
        # in that case (drum-rack discovery may still re-run, harmless).
        if self.is_enabled():
            self._refresh_targets()

    @listens("selected_scene")
    def _on_selected_scene_changed(self):
        # When pinned, the target clip slot follows the selected scene index
        # on the pinned track. Live's detail_clip listener doesn't fire on a
        # pure scene navigation, so we listen to selected_scene explicitly.
        # When unpinned, this is redundant with detail_clip + highlighted_clip_slot
        # but harmless.
        if self.is_enabled():
            self._refresh_clip()

    @listens("tracks")
    def _on_tracks_changed(self):
        # If the pinned track was removed from the song, release the pin.
        if (self._pinned_track is not None
                and self._pinned_track not in self.song.tracks):
            self._pinned_track = None
            self._emit(Event.TRACK_UNPINNED, mode="drum_sequence")
            if self.is_enabled():
                self._refresh_targets()

    @listens("can_capture_midi")
    def _on_can_capture_midi_changed(self):
        if self.is_enabled():
            self._update_control_leds()

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
            self._update_bottom_right_leds()
            self._update_note_leds()

    @listens("playing_status")
    def _on_playing_status_changed(self):
        self._on_playing_position_changed()

    @listens("loop_start")
    def _on_loop_changed(self):
        if self.is_enabled():
            self._update_bottom_right_leds()
            # The step grid shows the loop backdrop while shift is held —
            # refresh it so external loop changes (e.g., user dragged loop in
            # Live) are reflected immediately.
            if self._device_shift_held:
                self._update_step_leds()

    @listens("loop_end")
    def _on_loop_end_changed(self):
        self._on_loop_changed()

    def _refresh_targets(self):
        track = self._resolve_target_track()
        drum_group = self._find_drum_group_device(track)
        self._log("target track: {} (pinned={}), drum group: {}".format(
            getattr(track, "name", "<none>"),
            self._pinned_track is not None,
            getattr(drum_group, "name", "<none>")))
        self._set_drum_group_device(drum_group)
        self._refresh_clip()
        self._update_audition_translations()
        self.update()

    def _refresh_clip(self):
        clip_slot = self._selected_clip_slot()
        clip = None
        if self._pinned_track is not None and liveobj_valid(self._pinned_track):
            # Pinned: detail_clip can belong to any track and must not override
            # the pinned slot. Use only the slot's clip.
            if clip_slot is not None and clip_slot.has_clip and clip_slot.clip.is_midi_clip:
                clip = clip_slot.clip
        else:
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
            # Different clip — drop the "just created" state. The caller
            # (`_ensure_clip` create path) re-sets it after this call when
            # the new clip was born inside that path.
            self._clip_just_created = False
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
        self._rebuild_drum_color_listeners()

    def _rebuild_drum_color_listeners(self):
        """Attach `color` listeners on the FIRST chain of every drum pad
        in the current drum group, so a color change in Live propagates
        instantly to the bottom-left pad selector instead of waiting for
        the next note refresh or playhead tick.

        Also listens on each pad's `chains` collection — adding/removing a
        sample on a pad replaces the chain object, which would orphan our
        listener. On `chains` change we rebuild everything for safety.
        Cost is O(num_pads) per rebuild, which is small (drum racks max ~128
        pads, in practice ~16 visible)."""
        # Tear down previous slots.
        for obj, name, cb in self._drum_color_listeners:
            try:
                getattr(obj, "remove_{}_listener".format(name))(cb)
            except Exception:
                pass
        self._drum_color_listeners = []
        if not liveobj_valid(self._drum_group_device):
            return
        for pad in self._drum_group_device.drum_pads:
            if not liveobj_valid(pad):
                continue
            # Rebuild on chains change (sample loaded/removed).
            try:
                pad.add_chains_listener(self._on_drum_chains_changed)
                self._drum_color_listeners.append((pad, "chains", self._on_drum_chains_changed))
            except Exception:
                pass
            chains = list(pad.chains) if pad.chains else []
            if not chains:
                continue
            chain = chains[0]
            if not liveobj_valid(chain):
                continue
            try:
                chain.add_color_listener(self._on_drum_color_changed)
                self._drum_color_listeners.append((chain, "color", self._on_drum_color_changed))
            except Exception:
                pass

    def _on_drum_color_changed(self):
        if self.is_enabled():
            self._update_note_leds()

    def _on_drum_chains_changed(self):
        # Chains list mutated — rebuild listeners (chain object reference
        # changes) and repaint.
        self._rebuild_drum_color_listeners()
        if self.is_enabled():
            self._update_note_leds()

    def _selected_clip_slot(self):
        if self._pinned_track is not None and liveobj_valid(self._pinned_track):
            try:
                scene = self.song.view.selected_scene
                scene_idx = list(self.song.scenes).index(scene)
                return self._pinned_track.clip_slots[scene_idx]
            except (ValueError, IndexError, AttributeError):
                return None
        slot = self.song.view.highlighted_clip_slot
        return slot if slot is not None else None

    def _resolve_target_track(self):
        """Track to operate on. Returns the pinned track if still valid,
        otherwise falls back to Live's selected_track. Tracks listener
        clears the pin if the track is removed; this also guards against
        races where a stale reference survives a teardown."""
        if self._pinned_track is not None and liveobj_valid(self._pinned_track):
            return self._pinned_track
        return self.song.view.selected_track

    def toggle_pin(self):
        """Pin/unpin the sequencer to a Live track.

        - Unpinned → pin to currently-selected track. Returns True.
        - Pinned   → release. Returns False.
        - Selection is invalid (no track) → no-op, returns current state.

        On pin: track.arm = True so the drum-pad audition routes through the
        locked track even when Live's selection moves elsewhere. We don't
        un-arm on unpin (the user may have wanted the track armed regardless).

        Wired from launchpad_mini_mk3 via the shift+Session gesture.
        """
        if self._pinned_track is not None and liveobj_valid(self._pinned_track):
            self._pinned_track = None
            self._emit(Event.TRACK_UNPINNED, mode="drum_sequence")
            self._refresh_targets()
            return False
        track = self.song.view.selected_track
        if not liveobj_valid(track):
            return False
        # Only allow pinning regular tracks (master/return don't have clip_slots
        # we can write to).
        if track not in self.song.tracks:
            return False
        self._pinned_track = track
        # Force-arm the pinned track. Without this, the drum-pad selector's
        # audition pitches reach Live but get routed to whatever track Live
        # currently considers armed/selected. Note: with song.exclusive_arm=True
        # (Live's default), this will disarm other tracks. For a Launchpad+Push
        # workflow where both controllers audition different tracks, the user
        # needs Exclusive Arm disabled.
        try:
            if getattr(track, "can_be_armed", False):
                track.arm = True
        except (RuntimeError, AttributeError):
            # Frozen tracks etc. raise; leave arm state untouched then.
            pass
        self._emit(Event.TRACK_PINNED, mode="drum_sequence",
                   track_name=getattr(track, "name", "(unnamed)"))
        self._refresh_targets()
        return True

    def is_pinned(self):
        return (self._pinned_track is not None
                and liveobj_valid(self._pinned_track))

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
            slot.create_clip(self._page_length * DEFAULT_CLIP_PAGES)
            self.song.view.detail_clip = slot.clip
            self._clip_slot = slot
            self._set_clip(slot.clip)
            # Mark the new clip as "just created" — _ensure_loop_contains_time
            # is now gated on this flag, so subsequent note adds and page
            # navigation can auto-extend the loop during the initial build-out.
            self._clip_just_created = True
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
        # Special Shift held: redirect every pad press to the action
        # dispatcher and short-circuit normal grid handling (step toggle,
        # loop scoping, drum-pad select, velocity overlay, ...). Release
        # events are swallowed so leftover hold state in normal handlers
        # doesn't fire on the way out.
        if self._special_shift_held:
            if not value:
                return
            if y >= 4 and x >= 4:
                page_idx = (y - 4) * 4 + (x - 4)
                self._special_shift_page_action(page_idx=page_idx)
                return
            if y >= 4 and x < 4:
                pitch = self._pitch_for_note_button(x, y - 4)
                self._special_shift_pad_action(pitch=pitch)
                return
            # y < 4 → step pad
            step_in_page = y * 8 + x
            global_step = self._page_index * STEPS_PER_PAGE + step_in_page
            self._special_shift_step_action(global_step=global_step)
            return
        if y >= 4 and x >= 4:
            # Step-hold velocity selector wins over loop/grid rendering whenever
            # a held step pad has a note (and shift isn't grabbing the surface
            # for the loop-range picker). Selector "press" = apply velocity;
            # "release" is a no-op (we don't want the overlay to ghost-toggle).
            if self._velocity_overlay_should_show():
                if value:
                    level = self._velocity_overlay_cell_to_level(x, y)
                    if level is not None:
                        self._apply_velocity_from_selector(level)
                return
            index = (y - 4) * 4 + (x - 4)
            if self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID:
                self._handle_grid_cell_press(index, bool(value))
            else:
                self._handle_loop_press(index, bool(value))
            return
        # Shift-gated: the step grid (top 4x8) becomes a sub-page loop range
        # picker. Note this branch fires on both press AND release (unlike the
        # toggle path below) because we need release tracking for the
        # single-tap-vs-range distinction in _handle_step_loop_press.
        if y < 4 and self._device_shift_held:
            step = y * 8 + x
            self._handle_step_loop_press(step, bool(value))
            return
        # Step grid (top 4x8): hold-aware press/release for length-extension
        # and arrow-editing gestures.
        if y < 4:
            step = y * 8 + x
            self._handle_step_press(step, bool(value))
            return
        if not value:
            return
        self._log("grid pressed: {},{}".format(x, y))
        if x < 4:
            self._select_note_by_grid_position(x, y)

    def _on_note_matrix_value(self, value, x, y, is_momentary):
        if self.is_enabled() and value and self._note_matrix is not None:
            self._select_note_by_grid_position(x, y + 4)

    def _select_note_by_grid_position(self, x, y):
        new_pitch = self._pitch_for_note_button(x, y - 4)
        self._selected_pitch = new_pitch
        self._log("note selected: {}".format(self._selected_pitch))
        if liveobj_valid(self._drum_group_device):
            pad = self._drum_pad_for_pitch(self._selected_pitch)
            if liveobj_valid(pad):
                self._drum_group_device.view.selected_drum_pad = pad
        self._refresh_notes()
        self.update()

    def _handle_loop_press(self, index, pressed):
        # Duplicate Page modifier wins: hold slot 2 + tap page pad =
        # copy current page → that page. Swallow both press and release
        # so the page-view / range-scope paths don't see this gesture.
        if self._duplicate_page_held:
            if pressed:
                self._duplicate_page(index)
            return
        if pressed:
            if index not in self._loop_press_points:
                self._loop_press_points.append(index)
            self._log("loop pressed: {}".format(index))
            if len(self._loop_press_points) >= 2:
                start = min(self._loop_press_points)
                end = max(self._loop_press_points) + 1
                self._set_loop_pages(start, end)
                self._loop_range_active = True
                self._emit(Event.DRUM_PAGE_SCOPED, start=start + 1, end=end)
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

    def _velocity_overlay_should_show(self):
        """Overlay is active once the hold-arm task has fired AND device
        shift is NOT held (shift gestures keep priority for the
        bottom-right surface). The arm fires when a step pad has been
        held continuously for VELOCITY_OVERLAY_HOLD_DELAY — brief taps
        for step toggling don't flash the bar."""
        return self._velocity_overlay_armed and not self._device_shift_held

    def _arm_velocity_overlay(self):
        """Promote the current hold into a velocity-edit gesture. Called
        by the delayed task; bails if the user already released or shift
        is now held."""
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
        """Kill the pending arm task and clear the armed flag. Called when
        the held set empties, shift transitions, or sequencer is disabled."""
        self._velocity_overlay_arm_task.kill()
        if self._velocity_overlay_armed:
            self._velocity_overlay_armed = False
            if self.is_enabled():
                self.update()

    def _velocity_overlay_cell_to_level(self, x, y):
        """Bottom-right cell (x in 4..7, y in 4..7) → level 1..16.
        Bottom row (y=7) = levels 1..4; top row (y=4) = levels 13..16."""
        if not (4 <= x <= 7 and 4 <= y <= 7):
            return None
        return (7 - y) * 4 + (x - 4) + 1

    def _velocity_for_level(self, level):
        """Map a level (1..16) → MIDI velocity. `level * 8` clamped to 1..127;
        level 16 → 127."""
        return max(VELOCITY_MIN, min(VELOCITY_MAX, level * 8))

    def _level_for_velocity(self, velocity):
        """Inverse of `_velocity_for_level` (used to size the lit bar)."""
        return max(1, min(VELOCITY_OVERLAY_LEVELS, (int(velocity) + 7) // 8))

    def _current_held_velocity(self):
        """Velocity of the most-recently held note. Falls back to
        DEFAULT_VELOCITY when no held note is currently resolvable."""
        for _, note_start in reversed(list(self._held_step_pads.items())):
            if note_start is None:
                continue
            note = self._find_note_at_time(note_start)
            if note is not None:
                return int(note.velocity)
        return DEFAULT_VELOCITY

    def _render_velocity_overlay(self):
        """Write the 16-pad velocity bar into the bottom-right 4x4. Lit cells
        use the cool→hot ramp from VELOCITY_LEVEL_PALETTE; cells above the
        current level go dim."""
        current = self._level_for_velocity(self._current_held_velocity())
        for level in range(1, VELOCITY_OVERLAY_LEVELS + 1):
            x = 4 + (level - 1) % 4
            y = 7 - (level - 1) // 4
            palette = (VELOCITY_LEVEL_PALETTE[level - 1] if level <= current
                       else VELOCITY_LEVEL_DIM)
            self._set_grid_light_palette(x, y, palette)

    def _apply_velocity_from_selector(self, level):
        """Set every held note's velocity to `level`'s value, OR create
        new notes for held pads sitting on empty steps. Marks held pads
        consumed so their release doesn't toggle. Emits
        DRUM_VELOCITY_CHANGED once."""
        if not self.is_enabled() or not self._ensure_clip():
            return
        if self._selected_pitch is None:
            self._selected_pitch = NOTE_SELECTOR_BASE_PITCH
        velocity = self._velocity_for_level(level)
        new_notes = []
        modified = False
        for pad_step, note_start in list(self._held_step_pads.items()):
            if note_start is None:
                # Empty held step → create a note at this level's
                # velocity. Update the held entry to the new start_time so
                # subsequent bar taps adjust the same note.
                start = self._time_for_step(pad_step)
                new_notes.append(Live.Clip.MidiNoteSpecification(
                    pitch=self._selected_pitch, start_time=start,
                    duration=self._step_length, velocity=velocity, mute=False))
                self._held_step_pads[pad_step] = start
                self._consumed_step_pads.add(pad_step)
                self._ensure_loop_contains_time(start + self._step_length)
                modified = True
                continue
            note = self._find_note_at_time(note_start)
            if note is None:
                continue
            if int(note.velocity) != velocity:
                self._replace_note(note, velocity=velocity)
                modified = True
            self._consumed_step_pads.add(pad_step)
        if new_notes:
            self._clip.add_new_notes(tuple(new_notes))
            self._clip.deselect_all_notes()
            self._refresh_notes()
        if modified:
            self._emit(Event.DRUM_VELOCITY_CHANGED, velocity=velocity)
        self._update_step_leds()
        self._update_bottom_right_leds()

    def _handle_step_press(self, step, pressed):
        """Toggle a step OR perform a hold-gesture (length extension /
        arrow-driven edit). The toggle fires on RELEASE — pressing the pad
        is the start of a potential gesture; if nothing consumes the press,
        the release toggles.

        Disambiguation when another step is pressed while one is already held:
          - Held step has a note AND target step is EMPTY → length-extend the
            held note to reach the target.
          - Held step has a note AND target step ALSO has a note → multi-
            select: add target to held so arrow edits hit both notes.
          - Held step is empty → just track this press, no gesture."""
        if pressed:
            # Restart the velocity-overlay arm timer on every press. The
            # arm fires only if the user keeps holding past the delay —
            # quick taps disarm via the release path before then.
            self._velocity_overlay_arm_task.restart()
            anchor = self._anchor_for_extension()
            target_note = self._find_note_at_step(step)
            target_has_note = target_note is not None
            if anchor is not None and step != anchor and not target_has_note:
                # Length extension: extend the anchor's note to reach `step`.
                if self._ensure_clip():
                    self._extend_note_length(anchor, step)
                # Mark both ends consumed so their releases don't toggle.
                self._consumed_step_pads.add(anchor)
                self._consumed_step_pads.add(step)
                # Track the endpoint in held_step_pads (value None: it has no
                # note of its own to edit) so its release is recognized.
                self._held_step_pads[step] = None
                self._update_step_leds()
                self._update_bottom_right_leds()
                return
            # Multi-select OR plain anchor. Record the held pad with the
            # current note start_time (or None if empty).
            self._held_step_pads[step] = (target_note.start_time
                                          if target_has_note else None)
            self._update_step_leds()
            self._update_bottom_right_leds()
        else:
            consumed = step in self._consumed_step_pads
            self._consumed_step_pads.discard(step)
            self._held_step_pads.pop(step, None)
            if not self._held_step_pads:
                self._disarm_velocity_overlay()
            self._update_step_leds()
            self._update_bottom_right_leds()
            if consumed:
                return
            if self._ensure_clip():
                self._toggle_step(step)

    def _anchor_for_extension(self):
        """Return a pad_step from the currently-held set whose note still
        exists, or None. Used to decide whether a new step press should be
        interpreted as a length-extension target. With multi-select, the
        FIRST held pad with a still-valid note wins (insertion order)."""
        for pad_step, note_start in self._held_step_pads.items():
            if note_start is not None and self._find_note_at_time(note_start) is not None:
                return pad_step
        return None

    def _find_note_at_step(self, step):
        """Find the first note at the selected pitch whose start_time falls
        within the step's window [start, start + step_length)."""
        start = self._time_for_step(step)
        end = start + self._step_length
        for note in self._notes:
            if note.pitch == self._selected_pitch and start <= note.start_time < end:
                return note
        return None

    def _find_note_at_time(self, start_time):
        """Find a note at the selected pitch whose start_time matches
        `start_time` within float tolerance. Used to track a note across
        off-grid nudges where step-window lookup would miss it."""
        if start_time is None:
            return None
        tolerance = max(self._step_length * 1e-4, 1e-6)
        for note in self._notes:
            if note.pitch == self._selected_pitch and abs(note.start_time - start_time) < tolerance:
                return note
        return None

    def _replace_note(self, note, **changes):
        """Remove the original (matched by start_time + pitch within a tight
        window) and re-add with selected attribute overrides. The window is
        smaller than step_length so off-grid notes near a step boundary aren't
        collateral-damaged."""
        # Use a removal window of step_length / 8 around the original start.
        # Wide enough to absorb float-precision noise, narrow enough to leave
        # adjacent off-grid notes alone.
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

    def _extend_note_length(self, anchor_pad_step, target_pad_step):
        """Length-extend the note anchored at `anchor_pad_step` to reach
        the end of `target_pad_step`. The note keeps its start; only the
        duration changes. Anchor's note may be off-grid after nudges, so we
        compute duration from its actual start_time."""
        note_start = self._held_step_pads.get(anchor_pad_step)
        if note_start is None:
            return
        note = self._find_note_at_time(note_start)
        if note is None:
            return
        end_step = max(target_pad_step, anchor_pad_step)
        target_end_time = self._time_for_step(end_step) + self._step_length
        new_duration = target_end_time - note.start_time
        if new_duration <= 0:
            return
        self._replace_note(note, duration=new_duration)
        length_steps = max(1, int(round(new_duration / self._step_length)))
        self._emit(Event.DRUM_NOTE_LENGTH_CHANGED,
                   page=self._page_index + 1,
                   anchor_step=anchor_pad_step + 1,
                   length_steps=length_steps,
                   pitch=self._selected_pitch)
        self._ensure_loop_contains_time(note.start_time + new_duration)
        self.update()

    def _adjust_note_velocity_at_time(self, start_time, delta):
        """Bump the velocity of the note at `start_time` by `delta`, clamped
        to [VELOCITY_MIN..VELOCITY_MAX]. Returns True if found."""
        note = self._find_note_at_time(start_time)
        if note is None:
            return False
        new_velocity = max(VELOCITY_MIN, min(VELOCITY_MAX, int(note.velocity) + delta))
        if new_velocity == int(note.velocity):
            return True  # already at boundary; still treat as handled
        self._replace_note(note, velocity=new_velocity)
        self._emit(Event.DRUM_VELOCITY_CHANGED, velocity=new_velocity)
        self.update()
        return True

    def _nudge_note_at_time(self, start_time, delta_beats):
        """Move the note at `start_time` by `delta_beats` (a fractional beat
        amount, may be sub-step). Returns the new start_time on success or
        None if the move would push the start before time 0."""
        note = self._find_note_at_time(start_time)
        if note is None:
            return None
        new_start = note.start_time + delta_beats
        if new_start < 0:
            return None
        self._replace_note(note, start_time=new_start)
        self._emit(Event.DRUM_NOTE_NUDGED,
                   delta_beats=delta_beats,
                   start_time=new_start,
                   pitch=self._selected_pitch)
        self._ensure_loop_contains_time(new_start + note.duration)
        self.update()
        return new_start

    def adjust_held_velocity(self, delta):
        """Public: change the velocity of every held-pad note by `delta`.
        Called by the parent on Up/Down arrows. Returns True if at least one
        held pad had a note and was modified — the parent falls back to
        `adjust_pitch_offset` (legacy octave shift) when this returns False."""
        if not self.is_enabled():
            return False
        consumed_any = False
        for pad_step, note_start in list(self._held_step_pads.items()):
            if note_start is None:
                continue
            if self._adjust_note_velocity_at_time(note_start, delta):
                self._consumed_step_pads.add(pad_step)
                consumed_any = True
        return consumed_any

    def nudge_held_notes(self, direction):
        """Public: nudge every held-pad note by `direction * NUDGE_BEAT_DELTA`
        beats. `direction` is +1 (right) or -1 (left). Returns True if at
        least one note was moved (parent uses this as fallback signal).
        The stored start_time per held pad is updated so subsequent presses
        keep editing the same (now-displaced) note."""
        if not self.is_enabled():
            return False
        delta_beats = direction * NUDGE_BEAT_DELTA
        consumed_any = False
        for pad_step, note_start in list(self._held_step_pads.items()):
            if note_start is None:
                continue
            new_start = self._nudge_note_at_time(note_start, delta_beats)
            if new_start is not None:
                self._held_step_pads[pad_step] = new_start
                self._consumed_step_pads.add(pad_step)
                consumed_any = True
        return consumed_any

    def _handle_step_loop_press(self, step, pressed):
        """Sub-page loop scoping on the step grid while device shift is held.
        Mirror of `_handle_loop_press` but operating on steps within the
        currently-viewed page. Single tap = loop on that 1 step (Push-2 style);
        hold + press another step = scope on [min..max+1]."""
        if pressed:
            if step not in self._step_loop_press_points:
                self._step_loop_press_points.append(step)
            self._log("step loop pressed: {}".format(step))
            if len(self._step_loop_press_points) >= 2:
                start = min(self._step_loop_press_points)
                end = max(self._step_loop_press_points) + 1
                self._set_step_loop_in_current_page(start, end)
                self._step_loop_range_active = True
                self._emit(Event.DRUM_STEP_LOOP_SCOPED,
                           page=self._page_index + 1,
                           start_step=start + 1,
                           end_step=end,
                           label=self._current_grid_label())
            self._update_step_leds()
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
                self._update_step_leds()
                return
            # Single tap → scope loop to just this one step.
            self._set_step_loop_in_current_page(step, step + 1)
            self._emit(Event.DRUM_STEP_LOOP_SCOPED,
                       page=self._page_index + 1,
                       start_step=step + 1,
                       end_step=step + 1,
                       label=self._current_grid_label())
            self._update_step_leds()

    def _set_step_loop_in_current_page(self, start_step, end_step):
        if self._ensure_clip():
            page_start = self._page_index * self._page_length
            self._set_clip_loop(page_start + start_step * self._step_length,
                                page_start + end_step * self._step_length)
            self._clip_just_created = False

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
              velocity=DEFAULT_VELOCITY,
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

    def _set_loop_pages(self, start_page, end_page):
        if self._ensure_clip():
            self._page_index = start_page
            self._set_clip_loop(start_page * self._page_length, end_page * self._page_length)
            # Explicit loop scope ends "build-out" mode.
            self._clip_just_created = False

    def _scope_page(self, page):
        if self._ensure_clip():
            self._page_index = page
            self._set_clip_loop(page * self._page_length, (page + 1) * self._page_length)
            self._clip_just_created = False
            self._emit(Event.DRUM_PAGE_SCOPED, start=page + 1, end=page + 1)

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
        # established a loop (or opened an existing clip), this is a no-op —
        # the loop is the source of truth, even when a note ends past it.
        # The note will still be added to the clip; it just won't play in the
        # current loop pass.
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

    def _duplicate_page(self, target_index):
        """Copy notes from the currently-viewed page to `target_index`.
        Extends the loop to cover the target page if needed. No-op when
        source == target (the user can still pass through to view that
        page by releasing the modifier first)."""
        if not self._ensure_clip():
            return
        source_index = self._page_index
        if target_index == source_index:
            return
        source_start = source_index * self._page_length
        source_end = source_start + self._page_length
        target_start = target_index * self._page_length
        notes = list(self._clip.get_notes_extended(
            from_time=source_start, from_pitch=0,
            time_span=self._page_length, pitch_span=128))
        if not notes:
            self._emit(Event.DRUM_PAGE_DUPLICATED,
                       source=source_index + 1,
                       target=target_index + 1, notes=0)
            return
        copies = []
        for note in notes:
            offset = note.start_time - source_start
            copies.append(Live.Clip.MidiNoteSpecification(
                pitch=note.pitch,
                start_time=target_start + offset,
                duration=note.duration,
                velocity=note.velocity,
                mute=note.mute))
        target_end = target_start + self._page_length
        if target_end > self._clip.loop_end:
            self._set_clip_loop(self._clip.loop_start, target_end)
        self._clip.add_new_notes(tuple(copies))
        self._clip.deselect_all_notes()
        self._refresh_notes()
        self._emit(Event.DRUM_PAGE_DUPLICATED,
                   source=source_index + 1,
                   target=target_index + 1, notes=len(copies))
        self.update()

    def _double_loop(self):
        """Double the loop length and duplicate the existing loop content
        forward. 1-page loop → 2 pages with the same content; 4-page → 8.
        Useful for building variations of an existing pattern in place."""
        if not self._ensure_clip():
            return
        loop_start = self._clip.loop_start
        loop_end = self._clip.loop_end
        length = loop_end - loop_start
        if length <= 0:
            return
        notes = list(self._clip.get_notes_extended(
            from_time=loop_start, from_pitch=0,
            time_span=length, pitch_span=128))
        copies = []
        for note in notes:
            copies.append(Live.Clip.MidiNoteSpecification(
                pitch=note.pitch,
                start_time=note.start_time + length,
                duration=note.duration,
                velocity=note.velocity,
                mute=note.mute))
        new_end = loop_start + 2 * length
        self._set_clip_loop(loop_start, new_end)
        if copies:
            self._clip.add_new_notes(tuple(copies))
            self._clip.deselect_all_notes()
        self._refresh_notes()
        self._emit(Event.DRUM_LOOP_DOUBLED,
                   old_length=length, new_length=2 * length,
                   notes=len(copies))
        self.update()

    # ---- Special Shift (slot 6) ---------------------------------------

    def _enter_special_shift(self):
        if self._special_shift_held:
            return
        self._special_shift_held = True
        self._special_shift_press_time = time.time()
        self._special_shift_action_performed = False
        self._duplicate_source = None
        self.update()

    def _exit_special_shift(self):
        if not self._special_shift_held:
            return
        held_for = (time.time() - self._special_shift_press_time
                    if self._special_shift_press_time is not None else 0.0)
        self._special_shift_held = False
        self._special_shift_press_time = None
        # Quick tap without doing anything = cycle the mode. Long press
        # without doing anything = just exit ("I was hesitating"). Action
        # during hold = exit without cycling regardless of duration.
        # External modifiers (dedicated Clear/Duplicate buttons) never
        # cycle — the button itself selects the mode.
        if (not self._special_shift_external
                and not self._special_shift_action_performed
                and held_for <= SPECIAL_SHIFT_TAP_THRESHOLD):
            self._cycle_special_shift_mode()
        self._special_shift_external = False
        self._special_shift_action_performed = False
        self._duplicate_source = None
        self.update()

    def _cycle_special_shift_mode(self):
        self._special_shift_mode = (
            "delete" if self._special_shift_mode == "duplicate"
            else "duplicate")
        self._log("special shift mode: {}".format(self._special_shift_mode))

    # ---- Special Shift action dispatchers ----------------------------

    def _special_shift_pad_action(self, pitch):
        if self._special_shift_mode == "delete":
            self._special_delete_pad(pitch)
        else:
            self._special_duplicate_capture_or_apply(("pad", pitch))

    def _special_shift_row_action(self, row_idx):
        page_idx = self._page_index
        if self._special_shift_mode == "delete":
            self._special_delete_row(row_idx, page_idx)
        else:
            self._special_duplicate_capture_or_apply(("row", row_idx, page_idx))

    def _special_shift_page_action(self, page_idx):
        if self._special_shift_mode == "delete":
            self._special_delete_page(page_idx)
        else:
            self._special_duplicate_capture_or_apply(("page", page_idx))

    def _special_shift_step_action(self, global_step):
        if self._special_shift_mode == "delete":
            self._special_delete_step(global_step)
        else:
            self._special_duplicate_capture_or_apply(("step", global_step))

    def _special_duplicate_capture_or_apply(self, target):
        """Duplicate is a two-tap gesture: 1st tap = capture source,
        2nd tap (same kind) = apply. Cross-kind 2nd tap (e.g. pad source
        then row target) resets so the user can re-start without an
        explicit cancel."""
        src = self._duplicate_source
        if src is None or src[0] != target[0]:
            self._duplicate_source = target
            self.update()
            return
        # Same-kind: execute.
        if target == src:
            # Source == target → no-op, just release the capture.
            self._duplicate_source = None
            self.update()
            return
        kind = target[0]
        if kind == "pad":
            self._special_duplicate_pad(src[1], target[1])
        elif kind == "row":
            self._special_duplicate_row(src[1], src[2], target[1], target[2])
        elif kind == "page":
            self._special_duplicate_page(src[1], target[1])
        elif kind == "step":
            self._special_duplicate_step(src[1], target[1])
        self._duplicate_source = None
        self._special_shift_action_performed = True
        self.update()

    # ---- Delete primitives -------------------------------------------

    def _special_delete_pad(self, pitch):
        """Remove every note with this pitch from the entire clip."""
        if not self._ensure_clip():
            return
        clip = self._clip
        loop_end = max(clip.loop_end, self._page_length)
        notes = list(clip.get_notes_extended(
            from_time=0, from_pitch=pitch,
            time_span=loop_end, pitch_span=1))
        if not notes:
            return
        for note in notes:
            try:
                clip.remove_notes_extended(
                    from_time=note.start_time, from_pitch=pitch,
                    time_span=note.duration, pitch_span=1)
            except Exception:
                pass
        self._refresh_notes()
        self._special_shift_action_performed = True

    def _special_delete_row(self, row_idx, page_idx):
        """Remove notes of the selected pitch within the row's time range
        on the given page (row = 8-step slice)."""
        if not self._ensure_clip():
            return
        pitch = self._selected_pitch
        start = (page_idx * self._page_length
                 + row_idx * STEPS_PER_ROW * self._step_length)
        span = STEPS_PER_ROW * self._step_length
        try:
            self._clip.remove_notes_extended(
                from_time=start, from_pitch=pitch,
                time_span=span, pitch_span=1)
        except Exception:
            pass
        self._refresh_notes()
        self._special_shift_action_performed = True

    def _special_delete_page(self, page_idx):
        """Wipe every pitch on the given page."""
        if not self._ensure_clip():
            return
        start = page_idx * self._page_length
        try:
            self._clip.remove_notes_extended(
                from_time=start, from_pitch=0,
                time_span=self._page_length, pitch_span=128)
        except Exception:
            pass
        self._refresh_notes()
        self._special_shift_action_performed = True

    def _special_delete_step(self, global_step):
        """Remove the single step's note for the currently selected pitch."""
        if not self._ensure_clip():
            return
        pitch = self._selected_pitch
        start = global_step * self._step_length
        try:
            self._clip.remove_notes_extended(
                from_time=start, from_pitch=pitch,
                time_span=self._step_length, pitch_span=1)
        except Exception:
            pass
        self._refresh_notes()
        self._special_shift_action_performed = True

    # ---- Duplicate primitives ----------------------------------------

    def _special_duplicate_pad(self, source_pitch, target_pitch):
        if not self._ensure_clip():
            return
        clip = self._clip
        loop_end = max(clip.loop_end, self._page_length)
        notes = list(clip.get_notes_extended(
            from_time=0, from_pitch=source_pitch,
            time_span=loop_end, pitch_span=1))
        if not notes:
            return
        copies = [Live.Clip.MidiNoteSpecification(
            pitch=target_pitch, start_time=n.start_time,
            duration=n.duration, velocity=n.velocity, mute=n.mute)
            for n in notes]
        clip.add_new_notes(tuple(copies))
        clip.deselect_all_notes()
        self._refresh_notes()

    def _special_duplicate_row(self, source_row, source_page,
                                target_row, target_page):
        if not self._ensure_clip():
            return
        clip = self._clip
        pitch = self._selected_pitch
        source_start = (source_page * self._page_length
                        + source_row * STEPS_PER_ROW * self._step_length)
        target_start = (target_page * self._page_length
                        + target_row * STEPS_PER_ROW * self._step_length)
        span = STEPS_PER_ROW * self._step_length
        notes = list(clip.get_notes_extended(
            from_time=source_start, from_pitch=pitch,
            time_span=span, pitch_span=1))
        if not notes:
            return
        copies = [Live.Clip.MidiNoteSpecification(
            pitch=pitch,
            start_time=target_start + (n.start_time - source_start),
            duration=n.duration, velocity=n.velocity, mute=n.mute)
            for n in notes]
        target_end = target_start + span
        if target_end > clip.loop_end:
            self._set_clip_loop(clip.loop_start, target_end)
        clip.add_new_notes(tuple(copies))
        clip.deselect_all_notes()
        self._refresh_notes()

    def _special_duplicate_page(self, source_page, target_page):
        if not self._ensure_clip():
            return
        clip = self._clip
        source_start = source_page * self._page_length
        target_start = target_page * self._page_length
        notes = list(clip.get_notes_extended(
            from_time=source_start, from_pitch=0,
            time_span=self._page_length, pitch_span=128))
        if not notes:
            return
        copies = [Live.Clip.MidiNoteSpecification(
            pitch=n.pitch,
            start_time=target_start + (n.start_time - source_start),
            duration=n.duration, velocity=n.velocity, mute=n.mute)
            for n in notes]
        target_end = target_start + self._page_length
        if target_end > clip.loop_end:
            self._set_clip_loop(clip.loop_start, target_end)
        clip.add_new_notes(tuple(copies))
        clip.deselect_all_notes()
        self._refresh_notes()

    def _special_duplicate_step(self, source_step, target_step):
        if not self._ensure_clip():
            return
        clip = self._clip
        pitch = self._selected_pitch
        source_time = source_step * self._step_length
        target_time = target_step * self._step_length
        notes = list(clip.get_notes_extended(
            from_time=source_time, from_pitch=pitch,
            time_span=self._step_length, pitch_span=1))
        if not notes:
            return
        n = notes[0]
        spec = Live.Clip.MidiNoteSpecification(
            pitch=pitch, start_time=target_time,
            duration=n.duration, velocity=n.velocity, mute=n.mute)
        if target_time + self._step_length > clip.loop_end:
            self._set_clip_loop(clip.loop_start,
                                target_time + self._step_length)
        clip.add_new_notes((spec,))
        clip.deselect_all_notes()
        self._refresh_notes()

    def _update_step_leds(self):
        if self._grid_matrix is None:
            return
        # While device shift is held, the step grid switches to the loop range
        # picker backdrop: each step lit Inside/Outside per the clip loop
        # intersected with the current page; press anchors lit RangeEdit.
        if self._device_shift_held:
            for y in range(4):
                for x in range(8):
                    self._set_grid_light(x, y, self._step_loop_color(y * 8 + x))
            return
        src = self._duplicate_source
        # Step source is keyed by GLOBAL step index. Only highlight when
        # the source falls inside the currently-viewed page.
        source_step_in_page = None
        if src is not None and src[0] == "step":
            global_step = src[1]
            local = global_step - self._page_index * STEPS_PER_PAGE
            if 0 <= local < STEPS_PER_PAGE:
                source_step_in_page = local
        for y in range(4):
            for x in range(8):
                step = y * 8 + x
                self._set_grid_light(x, y, self._step_color(step))
                if step == source_step_in_page:
                    self._set_grid_light_blink(x, y, 3)  # WHITE blink

    def _step_loop_color(self, step):
        if not liveobj_valid(self._clip) and not self._selected_track_can_hold_midi():
            return "DrumSequencer.NoClip"
        if step in self._step_loop_press_points:
            return "DrumSequencer.Loop.RangeEdit"
        if self._playhead_is_on_step(step):
            return "DrumSequencer.Loop.Playhead"
        if liveobj_valid(self._clip):
            time = self._time_for_step(step)
            if self._clip.loop_start <= time < self._clip.loop_end:
                return "DrumSequencer.Loop.Inside"
        return "DrumSequencer.Loop.Outside"

    def _step_color(self, step):
        color = "DrumSequencer.NoClip"
        if liveobj_valid(self._clip) or self._selected_track_can_hold_midi():
            color = "DrumSequencer.StepBeat" if step % 4 == 0 else "DrumSequencer.StepEmpty"
            note = self._find_note_at_step(step)
            if note is not None:
                if note.mute:
                    color = "DrumSequencer.StepMuted"
                else:
                    color = self._velocity_color_for(int(note.velocity))
            # Held pads override the base note color so the user can see
            # which step their finger is anchored on. Playhead still wins.
            if step in self._held_step_pads:
                color = "DrumSequencer.StepHeld"
            if self._playhead_is_on_step(step):
                color = "DrumSequencer.PlayheadActive" if note is not None else "DrumSequencer.Playhead"
        return color

    def _velocity_color_for(self, velocity):
        """Map a MIDI velocity (1..127) to its StepVel* skin key. 4 tiers,
        cold → hot. Boundaries from `VELOCITY_TIER_BOUNDARIES`."""
        if velocity <= VELOCITY_TIER_BOUNDARIES[0]:
            return "DrumSequencer.StepVelGhost"
        if velocity <= VELOCITY_TIER_BOUNDARIES[1]:
            return "DrumSequencer.StepVelSoft"
        if velocity <= VELOCITY_TIER_BOUNDARIES[2]:
            return "DrumSequencer.StepVelMedium"
        return "DrumSequencer.StepVelLoud"

    def _update_note_leds(self):
        if self._grid_matrix is None:
            return
        # Drum-pad selector: each cell shows the drum rack pad's own color
        # (translated from Live's RGB to a Launchpad palette index) whenever
        # a drum pad exists at that pitch. The currently selected pad always
        # wins with `NoteSelected` (bright highlight). Cells with no drum pad
        # fall back to `NoteEmpty` (dim grey). Showing the color regardless
        # of whether the pad has notes in the clip makes the drum-rack layout
        # visible at a glance, Push-2-style.
        # Pads whose pitch has a note firing AT the playhead get
        # `NotePlaying` (white) on top of any base color — gives the user
        # a real-time view of which drum hits are firing.
        playing = self._playing_pitches()
        src = self._duplicate_source
        source_pad_pitch = src[1] if src is not None and src[0] == "pad" else None
        # While special shift is held, dim pads with NO notes so the user
        # can see which drum pads actually have content (useful to know
        # what's about to be duplicated/deleted before tapping).
        emphasize_filled = self._special_shift_held
        for y in range(4):
            for x in range(4):
                pitch = self._pitch_for_note_button(x, y)
                if pitch in playing:
                    self._set_grid_light(x, y + 4, "DrumSequencer.NotePlaying")
                    continue
                if pitch == self._selected_pitch:
                    self._set_grid_light(x, y + 4, "DrumSequencer.NoteSelected")
                else:
                    pad = self._drum_pad_for_pitch(pitch)
                    palette = self._color_for_drum_pad(pad) if liveobj_valid(pad) else None
                    has_notes = (liveobj_valid(pad)
                                 and self._has_any_note_for_pitch(pitch))
                    if emphasize_filled and not has_notes:
                        # Special-shift overview: pad has no notes → grey out,
                        # ignore the drum-rack color so empty pads read clearly.
                        self._set_grid_light(x, y + 4, "DrumSequencer.NoteEmpty")
                    elif palette is not None and palette > 0:
                        self._set_grid_light_palette(x, y + 4, palette)
                    elif has_notes:
                        self._set_grid_light(x, y + 4, "DrumSequencer.NoteFilled")
                    else:
                        self._set_grid_light(x, y + 4, "DrumSequencer.NoteEmpty")
                # Duplicate-source blink overlay (Programmer ch 1) — drawn
                # AFTER the static color so the firmware animates between
                # the two. Re-applied on every refresh to survive playhead
                # ticks (channel-0 writes reset the blink).
                if pitch == source_pad_pitch:
                    self._set_grid_light_blink(x, y + 4, 3)  # WHITE blink

    def _playing_pitches(self):
        """Pitches with a note currently firing at the playhead. Empty
        when the clip isn't playing or the song is stopped."""
        if self._playhead is None or not self._notes:
            return set()
        ph = self._playhead
        return {n.pitch for n in self._notes
                if n.start_time <= ph < n.start_time + n.duration}

    def _color_for_drum_pad(self, pad):
        """Return the Launchpad palette index for `pad`'s color, or None when
        no color can be read. Drum-pad coloring in Live lives on the FIRST
        chain in the pad — for an empty pad (no sampler/instrument loaded)
        `pad.chains` is empty, so we fall back gracefully. Live exposes both
        `chain.color` (RGB int) and `chain.color_index` (Live UI palette
        0..69); we prefer the RGB integer since it maps directly through
        `CLIP_COLOR_TABLE` / `find_nearest_color`."""
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
            self._log("drum pad pitch={} chains[0] has no usable RGB color".format(
                getattr(pad, "note", "?")))
            return None
        palette = CLIP_COLOR_TABLE.get(rgb)
        if palette is None:
            try:
                palette = find_nearest_color(RGB_COLOR_TABLE, rgb)
            except Exception:
                palette = None
        if palette is None:
            self._log("drum pad pitch={} rgb={} -> no palette match".format(
                getattr(pad, "note", "?"), rgb))
        return palette

    def _update_bottom_right_leds(self):
        if self._grid_matrix is None:
            return
        if self._velocity_overlay_should_show():
            self._render_velocity_overlay()
            return
        grid_mode = self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID
        src = self._duplicate_source
        source_page_idx = (src[1] if src is not None and src[0] == "page"
                           and not grid_mode else None)
        for y in range(4):
            for x in range(4):
                index = y * 4 + x
                color = (self._grid_cell_color(index) if grid_mode
                         else self._loop_color(index))
                self._set_grid_light(x + 4, y + 4, color)
                if index == source_page_idx:
                    self._set_grid_light_blink(x + 4, y + 4, 3)  # WHITE blink

    def _grid_cell_color(self, index):
        """LED color for a grid-resolution cell in the bottom-right 4x4 while
        in 'grid' mode. Currently-selected option = bright (GridSelected =
        WHITE). Binary cells (0..7) = ORANGE_HALF. Ternary cells (8..15) =
        PURPLE to flag them at a glance."""
        if not 0 <= index < len(GRID_OPTIONS):
            return "DefaultButton.Disabled"
        if index == self._grid_option_index:
            return "DrumSequencer.Control.GridSelected"
        if index >= TERNARY_FIRST_INDEX:
            return "DrumSequencer.Control.GridTernary"
        return "DrumSequencer.Control.Grid"

    def _handle_grid_cell_press(self, index, pressed):
        """Cell press in the bottom-right 4x4 while in 'grid' mode. Selects
        the corresponding entry from `GRID_OPTIONS`."""
        if not pressed:
            return
        self._set_grid_option(index)

    def _toggle_bottom_right_mode(self):
        """Cycle the bottom-right 4x4 between loop (page selector) and grid
        (resolution selector). Drops any in-flight loop-press state so a
        leftover hold can't accidentally re-scope the loop after the swap."""
        if self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID:
            self._bottom_right_mode = BOTTOM_RIGHT_MODE_LOOP
        else:
            self._bottom_right_mode = BOTTOM_RIGHT_MODE_GRID
        self._log("bottom-right mode: {}".format(self._bottom_right_mode))
        self._loop_press_points = []
        self._loop_range_active = False
        self._emit(Event.DRUM_BOTTOM_RIGHT_MODE,
                   mode=self._bottom_right_mode)
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
        # Reset every pad to default identifier + exclusive forwarding so
        # stale state from a previous mode can't leak a non_consuming
        # translation and double-trigger Live.
        for y in range(8):
            for x in range(8):
                button = self._get_grid_button(x, y)
                if button is not None:
                    button.use_default_message()
                    button.script_forwarding = ScriptForwarding.exclusive
        # Bottom-LEFT drum-pad selector — 16 cells, each translated to its
        # drum pitch on AUDITION_CHANNEL. The grid (top 4x8) and bottom-right
        # loop selector use default identifiers and don't forward notes to Live.
        for y in range(4):
            for x in range(4):
                pitch = self._pitch_for_note_button(x, y)
                self._translate_button_for_audition(x, y + 4, pitch)
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
            button.set_channel(AUDITION_CHANNEL if channel is None else channel)
            button.script_forwarding = ScriptForwarding.non_consuming

    def _make_control_button_listener(self, index):
        def listener(value):
            self._on_control_button_value(index, value)
        return listener

    def set_user_mode_button(self, button):
        """Plumb the parent's User button. While it's held, our scene
        column doubles as the main-mode selector — gate listener + LEDs."""
        self._user_mode_button = button

    def _is_main_mode_selector_held(self):
        return (self._user_mode_button is not None
                and self._user_mode_button.is_pressed())

    def _on_control_button_value(self, index, value):
        if not self.is_enabled():
            return
        # Sequencer shift modifier slot, parent-owned. Parent's
        # `__on_sequencer_shift_button_value` tracks press/release and
        # drives our `_device_shift_held` via set_device_shift_held(),
        # so the sequencer-side listener does nothing for this slot.
        if index == self._shift_slot:
            return
        # Special Shift — tap-vs-hold modifier. Tracked on both press and
        # release.
        if index == self._special_shift_slot:
            if self._is_main_mode_selector_held():
                return
            if value:
                self._enter_special_shift()
            else:
                self._exit_special_shift()
            return
        # While special shift is held, slots 0-3 become row selectors
        # (positional — they align with the 4 step rows) and the other
        # slots' normal actions are suppressed.
        if self._special_shift_held:
            if not value:
                return
            if self._is_main_mode_selector_held():
                return
            if 0 <= index <= 3:
                self._special_shift_row_action(row_idx=index)
            # Other slots ignored. Slot 7 stays as regular shift (untouched).
            return
        # Duplicate Page is a modifier — needs press AND release tracking.
        if index == self._duplicate_page_slot:
            if self._is_main_mode_selector_held():
                return
            self._duplicate_page_held = bool(value)
            self._update_control_leds()
            return
        if not value:
            return
        if self._is_main_mode_selector_held():
            # Scene press belongs to the parent's mode selector — swallow.
            return
        if index == self._capture_slot:
            self._capture_midi()
        elif index == self._quantize_slot:
            self._quantize_selected()
        elif index == self._double_loop_slot:
            self._double_loop()
        elif index == self._cycle_slot:
            self._toggle_bottom_right_mode()
        # Unassigned slots are free; slot 7 is the device shift (driven
        # elsewhere).

    def adjust_pitch_offset(self, delta):
        """Public: shift the drum-pad selector pitch range by `delta` semitones.

        Called from the parent control surface when the user presses the top
        arrow buttons in drum_sequence main mode.
        """
        if self.is_enabled():
            self._adjust_pitch_offset(delta)

    # ---- public API for device-specific wiring -------------------------
    # The Mini reaches these actions through scene-button slots; the Pro
    # MK3 wiring calls them directly from dedicated hardware buttons.

    def configure_slots(self, **overrides):
        """Remap or disable scene-button slot assignments.

        Keys: capture, quantize, duplicate_page, double_loop, cycle, shift,
        special_shift. Values: slot index 0-7, or None to disable the slot.
        Defaults are the Mini MK3 layout (module constants). The Pro MK3
        wiring disables the slots whose functions live on dedicated buttons.
        """
        for key, value in overrides.items():
            attr = "_{}_slot".format(key)
            if not hasattr(self, attr):
                raise ValueError("unknown slot key: {}".format(key))
            setattr(self, attr, value)
        if self.is_enabled():
            self._update_control_leds()

    def capture_midi(self):
        """Public: trigger Capture MIDI (same path as the capture slot)."""
        if self.is_enabled():
            self._capture_midi()

    def quantize_selected(self):
        """Public: quantize the current selection (held steps, else the
        selected drum pad's notes)."""
        if self.is_enabled():
            self._quantize_selected()

    def double_loop(self):
        """Public: double the loop length and duplicate its content."""
        if self.is_enabled():
            self._double_loop()

    def toggle_bottom_right_mode(self):
        """Public: cycle the bottom-right 4x4 (loop ↔ grid resolution)."""
        if self.is_enabled():
            self._toggle_bottom_right_mode()

    def set_action_modifier(self, mode, held):
        """Public: drive the delete/duplicate action modifier from dedicated
        hardware buttons (Pro MK3: Clear / Duplicate held).

        Reuses the special-shift machinery, but the release never tap-cycles
        the mode — the button itself selects it. Pressing the other button
        while one is already held just switches the live mode.
        """
        if mode not in ("delete", "duplicate"):
            return
        if held:
            if not self.is_enabled():
                return
            self._special_shift_mode = mode
            if self._special_shift_held:
                self.update()
            else:
                self._enter_special_shift()
                self._special_shift_external = True
        elif self._special_shift_held and self._special_shift_mode == mode:
            if self.is_enabled():
                self._exit_special_shift()
            else:
                # Main mode changed mid-hold — drop the state silently so
                # the next engagement starts clean (no LED writes while
                # another component owns the scene buttons).
                self._special_shift_held = False
                self._special_shift_press_time = None
                self._special_shift_external = False
                self._special_shift_action_performed = False
                self._duplicate_source = None

    def _set_grid_option(self, index):
        """Select a grid resolution from `GRID_OPTIONS` (0..15). No-op when
        the index is out of range or already current."""
        if not 0 <= index < len(GRID_OPTIONS):
            return
        if index == self._grid_option_index:
            return
        self._grid_option_index = index
        self._recompute_grid()
        # The legacy event is still useful for the status bar — `is_triplet`
        # is derived from whether the label ends with "t".
        label = self._current_grid_label()
        self._emit(Event.DRUM_GRID_CHANGED,
                   label=label,
                   is_triplet=label.endswith("t"))

    def _recompute_grid(self):
        self._step_length = GRID_OPTIONS[self._grid_option_index][0]
        self._page_length = self._step_length * STEPS_PER_PAGE
        self._page_index = min(self._page_index, BOTTOM_RIGHT_SIZE - 1)
        self._refresh_notes()
        self.update()

    def _current_grid_label(self):
        return GRID_OPTIONS[self._grid_option_index][1]

    def set_device_shift_held(self, pressed):
        """Notify of device shift (scene_launch_buttons_raw[7]) press/release.
        Called from the parent control surface; gates the grid-resolution slots
        AND flips the step grid between toggle-mode and loop-range-picker mode."""
        pressed = bool(pressed)
        if pressed == self._device_shift_held:
            return
        self._device_shift_held = pressed
        # Drop any in-flight step-loop press state so a held step pad can't
        # leak its anchor across a shift transition. The scoped loop stays put.
        if not pressed:
            self._step_loop_press_points = []
            self._step_loop_range_active = False
        # Either transition direction invalidates the held / consumed tracking
        # for the step grid — the grid's meaning just changed (toggle/edit ↔
        # loop range picker). Releases that follow won't be matched to the
        # old press state, so wipe it explicitly.
        self._held_step_pads = {}
        self._consumed_step_pads = set()
        self._disarm_velocity_overlay()
        if self.is_enabled():
            self._update_step_leds()
            self._update_control_leds()

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
        self._emit(Event.DRUM_NAV_CHANGED,
                   label=self._current_grid_label(),
                   page=self._page_index + 1,
                   octave=octave,
                   semitone=semitone)

    def _capture_midi(self):
        """Wrap `Live.Song.capture_midi()`. Gated on `can_capture_midi` so the
        call only fires when Live has something to capture; otherwise we emit a
        status-bar notice rather than failing silently.

        Post-capture: re-resolve the clip (capture creates or extends one),
        re-arm the "just created" build-out gate so further note adds can
        auto-extend the loop, and jump the page index to wherever the
        captured content ends — saves the user from manually paging out
        to find the new notes."""
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
        """Page that contains the end of the loop (so the captured tail
        is visible). 0 if there's no clip or page length is 0."""
        if not liveobj_valid(self._clip) or self._page_length <= 0:
            return 0
        loop_end = max(0.0, float(self._clip.loop_end))
        if loop_end <= 0:
            return 0
        # Step just inside the loop end so a loop ending exactly on a page
        # boundary lands on the LAST page, not the empty page after it.
        idx = int((loop_end - 1e-6) / self._page_length)
        return max(0, idx)

    def _quantize_selected(self):
        """Quantize notes to the current step grid. If any step pads are held
        with notes, only those notes are moved. Otherwise the fallback scope
        is "all notes for the currently-selected drum pad" — i.e., the
        currently-edited pad's row of notes. Quantization is 100% (full pull
        to grid). Held entries are updated so subsequent gestures still find
        the (now-moved) notes; the held pads are marked consumed so their
        release doesn't toggle anything."""
        if not liveobj_valid(self._clip):
            return
        grid = self._step_length
        if grid <= 0:
            return
        held = [(pad_step, start) for pad_step, start in self._held_step_pads.items()
                if start is not None]
        if held:
            scope = "selected"
            targets = []
            for pad_step, start in held:
                note = self._find_note_at_time(start)
                if note is not None:
                    targets.append((pad_step, note))
        else:
            scope = "pad_all"
            targets = [(None, n) for n in self._notes
                       if n.pitch == self._selected_pitch]
        moved = 0
        for pad_step, note in targets:
            new_start = round(note.start_time / grid) * grid
            if abs(new_start - note.start_time) <= 1e-6:
                continue
            self._replace_note(note, start_time=new_start)
            if pad_step is not None:
                self._held_step_pads[pad_step] = new_start
            moved += 1
        # Mark all held pads as consumed regardless of whether they moved —
        # the user explicitly pressed Quantize, so the implicit "release =
        # toggle" gesture should be suppressed for this hold session.
        for pad_step, _ in held:
            self._consumed_step_pads.add(pad_step)
        self._emit(Event.DRUM_NOTES_QUANTIZED,
                   count=moved,
                   scope=scope,
                   grid=self._current_grid_label())
        self.update()

    def _update_control_leds(self):
        if not self._control_buttons:
            return
        if self._is_main_mode_selector_held():
            # Parent's User-held mode selector owns the scene column right
            # now — don't paint over its LEDs.
            return
        # Default (Mini MK3) slot layout: 0 = Capture MIDI, 1 = Quantize
        # Selected, 2 = Duplicate Page (modifier), 3 = Double Loop (action),
        # 4 = cycle button (loop ↔ grid), 5 = sequencer shift (bright when
        # held/locked), 6 = Special Shift (cycle delete/duplicate; hold =
        # action mode), 7 = RESERVED (was device shift, now session-only).
        # Actual positions come from the configure_slots() assignments.
        shift_color = ("DrumSequencer.Control.Shift"
                       if self._device_shift_held
                       else "DrumSequencer.Control.ShiftIdle")
        # Colors are assembled per configured slot; unassigned (or None,
        # i.e. disabled) slots stay dark.
        colors = ["DefaultButton.Disabled"] * len(self._control_buttons)

        def assign(slot, color):
            if slot is not None and 0 <= slot < len(colors):
                colors[slot] = color

        # While special shift is held, slots 0-3 become row selectors
        # (positional — aligned with the 4 step rows) and everything else
        # is blacked out except the shift + special-shift slots.
        if self._special_shift_held:
            mode = self._special_shift_mode
            row_idle = ("DrumSequencer.Control.SpecialDeleteHalf"
                        if mode == "delete"
                        else "DrumSequencer.Control.SpecialDuplicateHalf")
            row_armed = ("DrumSequencer.Control.SpecialDelete"
                         if mode == "delete"
                         else "DrumSequencer.Control.SpecialDuplicate")
            # Row selectors highlight the captured source if any. For
            # duplicate, source-row's slot lights up brighter so the user
            # knows what was captured.
            def _row_color(row_idx):
                src = self._duplicate_source
                if (mode == "duplicate" and src is not None
                        and src[0] == "row" and src[1] == row_idx
                        and src[2] == self._page_index):
                    return row_armed
                return row_idle
            for row_idx in range(4):
                assign(row_idx, _row_color(row_idx))
            assign(self._shift_slot, shift_color)
            assign(self._special_shift_slot, row_armed)
        else:
            capture_color = ("DrumSequencer.Control.CaptureMidiReady"
                             if getattr(self.song, "can_capture_midi", False)
                             else "DrumSequencer.Control.CaptureMidi")
            cycle_color = ("DrumSequencer.Control.CycleGrid"
                           if self._bottom_right_mode == BOTTOM_RIGHT_MODE_GRID
                           else "DrumSequencer.Control.CycleLoop")
            duplicate_color = ("DrumSequencer.Control.DuplicatePageHeld"
                               if self._duplicate_page_held
                               else "DrumSequencer.Control.DuplicatePage")
            # Idle special-shift slot shows the current cycle mode
            # (half-bright) so the user knows which action a hold will
            # execute.
            special_idle = ("DrumSequencer.Control.SpecialDeleteHalf"
                            if self._special_shift_mode == "delete"
                            else "DrumSequencer.Control.SpecialDuplicateHalf")
            assign(self._capture_slot, capture_color)
            assign(self._quantize_slot, "DrumSequencer.Control.Quantize")
            assign(self._duplicate_page_slot, duplicate_color)
            assign(self._double_loop_slot, "DrumSequencer.Control.DoubleLoop")
            assign(self._cycle_slot, cycle_color)
            assign(self._shift_slot, shift_color)
            assign(self._special_shift_slot, special_idle)
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
        track = self._resolve_target_track()
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

    def _set_grid_light_palette(self, x, y, palette_value):
        """Same as `_set_grid_light` but takes a raw Launchpad palette index
        (0-127) instead of a skin color name. Used when rendering colors that
        come from outside the skin map — e.g., the drum rack pad colors that
        we translate at runtime from Live's per-chain RGB value."""
        button = self._get_grid_button(x, y)
        if button is None:
            return
        try:
            note = button.original_identifier()
            status = NOTE_ON_STATUS + PROGRAMMER_LED_CHANNEL
            self.canonical_parent._send_midi((status, note, palette_value), optimized=False)
        except Exception:
            pass

    def _set_grid_light_blink(self, x, y, palette_value):
        """Make a pad blink between its previously-set static color and
        `palette_value`. Uses Programmer-mode channel 1 (flashing). To
        stop the blink, re-send a static color on channel 0 — the
        animation engine resets on the next channel-0 write.

        Used for the duplicate-mode source highlight: after the user's
        first tap, the captured cell blinks until the second tap
        completes the copy (or the gesture is reset)."""
        button = self._get_grid_button(x, y)
        if button is None:
            return
        try:
            note = button.original_identifier()
            # Channel 1 = flashing in Programmer mode. PROGRAMMER_LED_CHANNEL
            # is 0 (static); +1 = blink.
            status = NOTE_ON_STATUS + PROGRAMMER_LED_CHANNEL + 1
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
            self.canonical_parent._c_instance.log_message("[DrumStepSequencer] {}".format(message))
        except Exception:
            pass

    def _emit(self, event_name, **payload):
        """Fire a semantic event on the bus. No-op if no bus is wired —
        the component itself stays presentation-agnostic. Status bar +
        M4L plumbing live in subscribers attached at the top level."""
        if self._event_bus is not None:
            self._event_bus.emit(event_name, **payload)

    def _request_midi_map_rebuild(self):
        try:
            self.canonical_parent.request_rebuild_midi_map()
        except Exception:
            pass

    def _send_programmer_pad_color(self, button, color):
        note, color_value = send_pad_color(
            self.canonical_parent, button, color, DRUM_SEQUENCER_COLOR_VALUES)
        if self._led_debug_count < 8:
            self._log("led send: note={}, value={}".format(note, color_value))
            self._led_debug_count += 1
