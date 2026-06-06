"""Edit mode — 5th sub-mode of `_stop_solo_mute_modes`.

Entered via a double-tap on the shift button (scene_launch_buttons_raw[7])
while in session main mode. While active, the bottom row of the 8x8 grid
becomes a row of modifier pads:

  slot 0    : Delete       (red)    — hold + tap clip/scene to delete
  slot 1    : Duplicate    (green)  — hold + tap clip/scene to duplicate
                                      into the next scene (Ableton-style
                                      "duplicate to row below" — same as
                                      Ctrl+D)
  slot 2    : Move         (blue)   — hold + 1st tap picks source,
                                      2nd tap moves it to target.
                                      Releasing Blue before the 2nd
                                      tap cancels.
  slot 3    : Color Cycle  (yellow) — hold + tap clip/scene to cycle
                                      its `color_index` through Live's
                                      70-entry palette.
  slot 4    : Stop All     (orange) — single tap: song.stop_all_clips().
  slot 5-6  : inert (dim)
  slot 7    : Undo         (white)  — single tap: song.undo().
                                      Tap while shift held: song.redo().

Only one modifier is "active" at a time. If multiple are held, priority
goes delete > duplicate > move — but that's a degenerate case the user
shouldn't normally trigger.

Scene `move` is intentionally a no-op in v1: the inserted-then-deleted
scene index dance is error-prone, and the user phrased move primarily
around clips ("comme dupliquer sauf que ça bouge le pad"). Delete +
duplicate on scenes work as expected.
"""
from __future__ import absolute_import, print_function, unicode_literals

import Live
from ableton.v2.base import liveobj_valid
from ableton.v2.control_surface.component import Component

from .events import Event


# Bottom-row slot assignments. Three groups:
#   - HOLD-MODIFIERS (0..1): Delete + Duplicate (source→target with blink).
#   - SINGLE-TAP ACTIONS (4, 7): Stop All Clips + Undo (with shift = Redo).
#   - DIM (2, 3, 5, 6): inert.
# DISABLED (ergonomic pass) — Move and Color Cycle modifiers removed
# from the active layout. Handlers (_move_clip / _color_cycle_clip / ...)
# are still defined for re-use; only the modifier slot wiring is gated.
DELETE_SLOT = 0
DUPLICATE_SLOT = 1
# MOVE_SLOT = 2          # disabled — slot now inert
# COLOR_CYCLE_SLOT = 3   # disabled — slot now inert
STOP_ALL_SLOT = 4
UNDO_SLOT = 7

# Live's clip-color palette has 70 indices (0..69). Cycling wraps.
CLIP_COLOR_COUNT = 70


class EditModeComponent(Component):
    """Owns the bottom row while edit mode is active.

    The component is enabled/disabled by `_stop_solo_mute_modes` via
    `AddLayerMode` — entering `edit` enables the component and binds the
    bottom row to `modifier_matrix`; leaving it disables and unbinds.

    Clip slots and scenes hold a back-reference to this component (set
    by `SessionComponentWithCopy.set_edit_mode_component` and propagated
    on `_create_scene`). When pressed, they short-circuit their normal
    behavior and route to `handle_clip_action` / `handle_scene_action`
    if `is_active()` returns True.
    """

    def __init__(self, song=None, event_bus=None, logger=None, *a, **k):
        super(EditModeComponent, self).__init__(*a, **k)
        self._song = song
        self._event_bus = event_bus
        self._logger = logger
        self._modifier_matrix = None
        self._delete_held = False
        self._duplicate_held = False
        self._move_held = False
        self._color_cycle_held = False
        # ("clip", clip_slot) or ("scene", scene) once the move 1st tap
        # has captured a source. Reset on move release without 2nd tap
        # (cancel) or after successful 2nd tap (consume).
        self._move_source = None
        # Duplicate source captured by the 1st tap of the duplicate
        # gesture: 1st tap = capture (the source clip blinks), 2nd tap
        # on another slot = copy. Same-slot 2nd tap cancels. Releasing
        # the Duplicate modifier before the 2nd tap cancels and clears
        # the blink. Tuple shape mirrors `_move_source`:
        #   ("clip", clip_slot)
        self._duplicate_source = None
        # Shift button reference used to disambiguate undo (single tap)
        # from redo (tap while shift held). Set by Launchpad_Mini_MK3 via
        # set_shift_button after _create_stop_solo_mute_modes.
        self._shift_button = None

    # ---- enable / disable lifecycle -----------------------------------

    def set_enabled(self, enabled):
        was_enabled = self.is_enabled()
        super(EditModeComponent, self).set_enabled(enabled)
        if enabled and not was_enabled:
            self._emit(Event.EDIT_MODE_CHANGED, on=True)
            self.update()
        elif was_enabled and not enabled:
            # Drop any in-flight move so it doesn't survive the next
            # entry into edit mode.
            if self._move_source is not None:
                self._move_source = None
                self._emit(Event.EDIT_MOVE_CANCELLED)
            # Clear duplicate source's blink if any was armed.
            self._set_duplicate_source(None)
            self._delete_held = False
            self._duplicate_held = False
            self._move_held = False
            self._color_cycle_held = False
            self._turn_modifier_matrix_off()
            self._emit(Event.EDIT_MODE_CHANGED, on=False)

    def set_shift_button(self, button):
        """Plumb the shift button so the Undo pad can detect the shift+tap
        gesture and dispatch redo instead of undo."""
        self._shift_button = button

    def disconnect(self):
        self.set_modifier_matrix(None)
        super(EditModeComponent, self).disconnect()

    # ---- Layer binding ------------------------------------------------

    def set_modifier_matrix(self, matrix):
        if matrix == self._modifier_matrix:
            return
        if self._modifier_matrix is not None:
            try:
                self._modifier_matrix.remove_value_listener(
                    self._on_modifier_matrix_value)
            except Exception:
                pass
        self._modifier_matrix = matrix
        if self._modifier_matrix is not None:
            self._modifier_matrix.add_value_listener(
                self._on_modifier_matrix_value)
        if self.is_enabled():
            self.update()

    # ---- press dispatch -----------------------------------------------

    def _on_modifier_matrix_value(self, value, x, y, _is_momentary):
        if not self.is_enabled():
            return
        pressed = bool(value)
        if x == DELETE_SLOT:
            self._delete_held = pressed
        elif x == DUPLICATE_SLOT:
            self._duplicate_held = pressed
            if not pressed and self._duplicate_source is not None:
                # User let go of Green before completing the duplicate —
                # cancel the capture (clears the source's blink).
                self._set_duplicate_source(None)
        # DISABLED (ergonomic pass) — Move + Color Cycle removed.
        # elif x == MOVE_SLOT:
        #     self._move_held = pressed
        #     if not pressed and self._move_source is not None:
        #         self._move_source = None
        #         self._emit(Event.EDIT_MOVE_CANCELLED)
        # elif x == COLOR_CYCLE_SLOT:
        #     self._color_cycle_held = pressed
        elif x == STOP_ALL_SLOT:
            # Fire on press only — single-tap action, no target needed.
            if pressed:
                self._stop_all_clips()
        elif x == UNDO_SLOT:
            if pressed:
                self._undo_or_redo()
        # Slots 5/6 are inert.
        self.update()

    # ---- public state -------------------------------------------------

    def is_active(self):
        return self.is_enabled()

    def current_modifier(self):
        """The modifier the user is currently engaging. None if none held.

        Priority: delete > duplicate. The user shouldn't normally hold
        multiple, but if they do, the most-destructive wins.
        """
        if self._delete_held:
            return "delete"
        if self._duplicate_held:
            return "duplicate"
        # DISABLED (ergonomic pass) — kept for re-enable.
        # if self._move_held:
        #     return "move"
        # if self._color_cycle_held:
        #     return "color_cycle"
        return None

    # ---- action handlers ---------------------------------------------

    def handle_clip_action(self, slot):
        """Called by ClipSlotComponentWithCopy when a clip slot is pressed
        in edit mode. `slot` is the wrapping COMPONENT (not the raw Live
        clip slot); we extract the Live object via `slot._clip_slot` for
        Ableton API calls."""
        live_slot = getattr(slot, "_clip_slot", None)
        if not liveobj_valid(live_slot):
            return
        modifier = self.current_modifier()
        if modifier == "delete":
            self._delete_clip(slot)
        elif modifier == "duplicate":
            self._duplicate_clip(slot)
        # DISABLED (ergonomic pass) — Move / Color Cycle removed.
        # elif modifier == "move":
        #     self._move_clip(slot)
        # elif modifier == "color_cycle":
        #     self._color_cycle_clip(slot)
        # else: no modifier held in edit mode → swallow the press so the
        # clip isn't launched by accident.

    def handle_scene_action(self, scene):
        """Called by SceneComponentWithCopy when a scene button is pressed
        in edit mode."""
        if not liveobj_valid(scene):
            return
        modifier = self.current_modifier()
        if modifier == "delete":
            self._delete_scene(scene)
        elif modifier == "duplicate":
            self._duplicate_scene(scene)
        # DISABLED (ergonomic pass) — Move / Color Cycle removed.
        # elif modifier == "move":
        #     self._move_scene(scene)
        # elif modifier == "color_cycle":
        #     self._color_cycle_scene(scene)

    # ---- clip actions -------------------------------------------------

    def _delete_clip(self, slot):
        live = slot._clip_slot
        if live.is_group_slot:
            return
        if not live.has_clip:
            return
        track_idx, scene_idx = self._clip_slot_coords(live)
        try:
            live.delete_clip()
        except Exception as exc:
            self._log("delete_clip failed: {}".format(exc))
            return
        self._emit(Event.EDIT_CLIP_DELETED,
                   track=track_idx, scene=scene_idx)

    def _duplicate_clip(self, slot):
        """Two-tap source → target duplicate. 1st tap on a clip captures
        it (the source pad blinks). 2nd tap on any other slot copies the
        clip there. Replaces the old "Ctrl+D into next scene" behavior so
        the user can pick an arbitrary destination.

        Same-slot 2nd tap = no-op (releases the capture). Cross-track
        copies require source/target audio-MIDI compatibility (mirrors
        the Move logic).

        `slot` is the ClipSlotComponentWithCopy wrapper; we read
        `_clip_slot` from it for Live API calls."""
        live = slot._clip_slot
        if live.is_group_slot:
            return
        if self._duplicate_source is None:
            # 1st tap: capture source (empty slot = no-op).
            if not live.has_clip:
                return
            self._set_duplicate_source(("clip", slot))
            return
        # 2nd tap: complete the copy.
        kind, source_slot = self._duplicate_source
        if kind != "clip":
            self._set_duplicate_source(None)
            return
        if source_slot is slot:
            # Same slot tapped twice → cancel.
            self._set_duplicate_source(None)
            return
        source_live = source_slot._clip_slot
        if not liveobj_valid(source_live) or not source_live.has_clip:
            self._set_duplicate_source(None)
            return
        source_clip = source_live.clip
        target_track = live.canonical_parent
        if source_clip.is_audio_clip and not target_track.has_audio_input:
            self._set_duplicate_source(None)
            return
        from_track, from_scene = self._clip_slot_coords(source_live)
        to_track, to_scene = self._clip_slot_coords(live)
        try:
            source_live.duplicate_clip_to(live)
        except Exception as exc:
            self._log("duplicate_clip_to failed: {}".format(exc))
            self._set_duplicate_source(None)
            return
        self._set_duplicate_source(None)
        self._emit(Event.EDIT_CLIP_DUPLICATED,
                   track=from_track, scene=from_scene)

    def _set_duplicate_source(self, source):
        """Store the captured source (or clear with None). The source's
        LED is unchanged — the device's firmware doesn't reliably blink
        a clip pad via channel-1 in this setup, and the user gesture
        works fine without visual feedback."""
        self._duplicate_source = source

    def _move_clip(self, clip_slot):
        if clip_slot.is_group_slot:
            return
        if self._move_source is None:
            # 1st tap: capture source. Only meaningful if there's a clip
            # to move — empty source is a no-op.
            if not clip_slot.has_clip:
                return
            self._move_source = ("clip", clip_slot)
            self._emit(Event.EDIT_MOVE_SOURCE_SET, kind="clip")
            self.update()
            return
        # 2nd tap: complete move from source to target.
        kind, source = self._move_source
        self._move_source = None
        if kind != "clip":
            # Mixed source kinds (scene then clip target) — discard.
            self.update()
            return
        if source is clip_slot:
            # Same slot tapped twice — nothing to do.
            self.update()
            return
        if not liveobj_valid(source) or not source.has_clip:
            self.update()
            return
        if clip_slot.has_clip:
            # Target occupied — don't overwrite silently.
            self.update()
            return
        # Track compatibility check, mirroring ClipCopyComponent._paste_clip.
        source_clip = source.clip
        target_track = clip_slot.canonical_parent
        if source_clip.is_audio_clip and not target_track.has_audio_input:
            self.update()
            return
        from_track, from_scene = self._clip_slot_coords(source)
        to_track, to_scene = self._clip_slot_coords(clip_slot)
        try:
            source.duplicate_clip_to(clip_slot)
            source.delete_clip()
        except Exception as exc:
            self._log("move clip failed: {}".format(exc))
            self.update()
            return
        self._emit(Event.EDIT_CLIP_MOVED,
                   from_track=from_track, from_scene=from_scene,
                   to_track=to_track, to_scene=to_scene)
        self.update()

    # ---- scene actions ------------------------------------------------

    def _delete_scene(self, scene):
        idx = self._scene_index(scene)
        if idx < 0:
            return
        # Live requires at least one scene. Skip the delete if there's
        # only one — the API would raise and we'd log noise.
        if len(self._song.scenes) <= 1:
            return
        try:
            self._song.delete_scene(idx)
        except Exception as exc:
            self._log("delete_scene failed: {}".format(exc))
            return
        self._emit(Event.EDIT_SCENE_DELETED, scene=idx)

    def _duplicate_scene(self, scene):
        idx = self._scene_index(scene)
        if idx < 0:
            return
        try:
            self._song.duplicate_scene(idx)
        except (Live.Base.LimitationError, RuntimeError) as exc:
            self._log("duplicate_scene failed: {}".format(exc))
            return
        self._emit(Event.EDIT_SCENE_DUPLICATED, scene=idx)

    def _move_scene(self, scene):
        # Scene move intentionally not implemented in v1. The
        # insert-then-delete dance is error-prone (indices shift after
        # both operations) and the user described move primarily for
        # clips. Treat as no-op — the move modifier still works for
        # clips. Capture/consume the source so the gesture is consistent
        # with clip move (1st tap stores, 2nd tap clears).
        if self._move_source is None:
            self._move_source = ("scene", scene)
            self._emit(Event.EDIT_MOVE_SOURCE_SET, kind="scene")
            self.update()
            return
        # 2nd tap: discard without action.
        self._move_source = None
        self.update()

    # ---- color cycle --------------------------------------------------

    def _color_cycle_clip(self, clip_slot):
        if not clip_slot.has_clip:
            return
        clip = clip_slot.clip
        track_idx, scene_idx = self._clip_slot_coords(clip_slot)
        new_index = (clip.color_index + 1) % CLIP_COLOR_COUNT
        try:
            clip.color_index = new_index
        except Exception as exc:
            self._log("clip color cycle failed: {}".format(exc))
            return
        self._emit(Event.EDIT_CLIP_COLOR_CYCLED,
                   track=track_idx, scene=scene_idx, color_index=new_index)

    def _color_cycle_scene(self, scene):
        idx = self._scene_index(scene)
        if idx < 0:
            return
        new_index = (scene.color_index + 1) % CLIP_COLOR_COUNT
        try:
            scene.color_index = new_index
        except Exception as exc:
            self._log("scene color cycle failed: {}".format(exc))
            return
        self._emit(Event.EDIT_SCENE_COLOR_CYCLED,
                   scene=idx, color_index=new_index)

    # ---- single-tap action pads --------------------------------------

    def _stop_all_clips(self):
        try:
            self._song.stop_all_clips()
        except Exception as exc:
            self._log("stop_all_clips failed: {}".format(exc))
            return
        self._emit(Event.EDIT_STOP_ALL_CLIPS)

    def _undo_or_redo(self):
        """Single-tap on slot 7. Redo iff the shift button is held at the
        moment of press; otherwise undo. The shift button stays in edit
        mode (no auto-exit) as long as it's held > SHIFT_LOCK_TAP_THRESHOLD,
        so the natural gesture is press-shift-tap-undo-release-shift."""
        shift_held = (self._shift_button is not None
                      and self._shift_button.is_pressed())
        if shift_held:
            try:
                if self._song.can_redo:
                    self._song.redo()
            except Exception as exc:
                self._log("redo failed: {}".format(exc))
                return
            self._emit(Event.EDIT_REDO)
        else:
            try:
                if self._song.can_undo:
                    self._song.undo()
            except Exception as exc:
                self._log("undo failed: {}".format(exc))
                return
            self._emit(Event.EDIT_UNDO)

    # ---- helpers ------------------------------------------------------

    def _clip_slot_coords(self, clip_slot):
        """Return (track_index, scene_index) of a clip slot. Both -1 if
        the slot can't be located (shouldn't happen for a valid slot but
        keep us defensive)."""
        track = clip_slot.canonical_parent
        if not liveobj_valid(track):
            return (-1, -1)
        try:
            track_idx = list(self._song.tracks).index(track)
        except ValueError:
            track_idx = -1
        try:
            scene_idx = list(track.clip_slots).index(clip_slot)
        except ValueError:
            scene_idx = -1
        return (track_idx, scene_idx)

    def _scene_index(self, scene):
        try:
            return list(self._song.scenes).index(scene)
        except ValueError:
            return -1

    # ---- LED rendering ------------------------------------------------

    def update(self):
        super(EditModeComponent, self).update()
        if not self.is_enabled():
            return
        self._render_modifier_matrix()

    def _render_modifier_matrix(self):
        if self._modifier_matrix is None:
            return
        # Bottom row is 8 cols × 1 row. submatrix is addressed
        # [cols, rows]; .get_button(y, x) is (row, col).
        for x in range(8):
            color = self._color_for_slot(x)
            self._set_pad_light(x, color)

    def _color_for_slot(self, x):
        if x == DELETE_SLOT:
            return "EditMode.DeleteHeld" if self._delete_held else "EditMode.Delete"
        if x == DUPLICATE_SLOT:
            return ("EditMode.DuplicateHeld" if self._duplicate_held
                    else "EditMode.Duplicate")
        # DISABLED (ergonomic pass) — slots 2/3 fall through to Dim now.
        # if x == MOVE_SLOT:
        #     if self._move_source is not None:
        #         return "EditMode.MoveArmed"
        #     return "EditMode.MoveHeld" if self._move_held else "EditMode.Move"
        # if x == COLOR_CYCLE_SLOT:
        #     return ("EditMode.ColorCycleHeld" if self._color_cycle_held
        #             else "EditMode.ColorCycle")
        if x == STOP_ALL_SLOT:
            return "EditMode.StopAll"
        if x == UNDO_SLOT:
            return "EditMode.Undo"
        return "EditMode.Dim"

    def _set_pad_light(self, x, color):
        try:
            button = self._modifier_matrix.get_button(0, x)
        except IndexError:
            return
        if button is None:
            return
        try:
            button.set_light(color)
        except Exception:
            pass

    def _turn_modifier_matrix_off(self):
        if self._modifier_matrix is None:
            return
        for x in range(8):
            self._set_pad_light(x, "DefaultButton.Disabled")

    # ---- event bus ----------------------------------------------------

    def _emit(self, name, **payload):
        if self._event_bus is not None:
            self._event_bus.emit(name, **payload)

    def _log(self, message):
        if self._logger is not None:
            try:
                self._logger("[EditMode] {}".format(message))
            except Exception:
                pass
