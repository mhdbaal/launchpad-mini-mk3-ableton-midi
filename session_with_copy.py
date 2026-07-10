# Launchpad Mini MK3 - Session Component with Copy Support
# Extends SessionComponent to use ClipSlotComponentWithCopy
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.control_surface.components import SessionComponent, SceneComponent
from .clip_slot_with_copy import ClipSlotComponentWithCopy


def is_button_pressed(button):
    """Helper to check if a button is currently pressed."""
    return button and button.is_pressed()


class SceneComponentWithCopy(SceneComponent):
    """SceneComponent that supports both clip and scene copy."""
    clip_slot_component_type = ClipSlotComponentWithCopy

    def __init__(self, *a, **k):
        super(SceneComponentWithCopy, self).__init__(*a, **k)
        self._copy_shift_button = None
        self._scene_copy_handler = None
        self._edit_mode = None
        self._user_mode_button = None

    def set_copy_shift_button(self, button):
        """Set the shift button reference."""
        self._copy_shift_button = button

    def set_scene_copy_handler(self, handler):
        """Set the SceneCopyComponent instance."""
        self._scene_copy_handler = handler

    def set_edit_mode_component(self, edit_mode):
        """Set the EditModeComponent. Mirrors the clip-slot setter — when
        edit mode is active, scene presses route to the edit-mode
        handler (delete/duplicate). Move-on-scene is a no-op in v1."""
        self._edit_mode = edit_mode

    def set_user_mode_button(self, button):
        """Set the user_mode_button reference. While the button is held,
        scene presses are owned by the main-mode selector — swallow them
        here so a tap on scene 0 doesn't also launch scene 0."""
        self._user_mode_button = button

    def _on_launch_button_pressed(self):
        """Priority: user-held mode selector → edit mode → copy_shift →
        normal launch. Mirrors ClipSlotComponentWithCopy._on_launch_button_pressed."""
        if is_button_pressed(self._user_mode_button):
            return

        if self._edit_mode is not None and self._edit_mode.is_active():
            self._edit_mode.handle_scene_action(self._scene)
            return

        if is_button_pressed(self._copy_shift_button):
            if self._scene_copy_handler is not None:
                self._scene_copy_handler.handle_scene_action(self._scene)
            return

        super(SceneComponentWithCopy, self)._on_launch_button_pressed()

    def _on_launch_button_released(self):
        """The base SceneComponent fires `_do_launch_scene(False)` on
        release too — so even when we swallow the press, the release
        still launches the scene. Mirror the same guards here so a
        scene tap during User-held / edit-mode / copy is truly a no-op."""
        if is_button_pressed(self._user_mode_button):
            return
        if self._edit_mode is not None and self._edit_mode.is_active():
            return
        if is_button_pressed(self._copy_shift_button):
            return
        super(SceneComponentWithCopy, self)._on_launch_button_released()


class SessionComponentWithCopy(SessionComponent):
    """
    Extended SessionComponent that uses ClipSlotComponentWithCopy
    to support copy-paste functionality.
    """
    scene_component_type = SceneComponentWithCopy

    def __init__(self, *a, **k):
        self._copy_handler = None
        self._scene_copy_handler = None
        self._edit_mode = None
        self._user_mode_button = None
        super(SessionComponentWithCopy, self).__init__(*a, **k)

    def set_copy_handler(self, copy_handler):
        """Set the ClipCopyComponent to handle copy-paste logic."""
        self._copy_handler = copy_handler
        # Propagate to all existing clip slots
        for scene in self._scenes:
            for clip_slot in scene._clip_slots:
                if hasattr(clip_slot, 'set_copy_handler'):
                    clip_slot.set_copy_handler(copy_handler)

    def set_scene_copy_handler(self, scene_copy_handler):
        """Set the SceneCopyComponent to handle scene copy-paste logic."""
        self._scene_copy_handler = scene_copy_handler
        # Propagate to all existing scenes
        for scene in self._scenes:
            if hasattr(scene, 'set_scene_copy_handler'):
                scene.set_scene_copy_handler(scene_copy_handler)
        # Propagate shift button to scenes
        if hasattr(self, '_copy_shift_button'):
            for scene in self._scenes:
                if hasattr(scene, 'set_copy_shift_button'):
                    scene.set_copy_shift_button(self._copy_shift_button)

    def set_edit_mode_component(self, edit_mode):
        """Set the EditModeComponent and propagate to every existing
        clip slot and scene. New scenes / clip slots created later pick
        it up via `_create_scene`."""
        self._edit_mode = edit_mode
        for scene in self._scenes:
            if hasattr(scene, 'set_edit_mode_component'):
                scene.set_edit_mode_component(edit_mode)
            for clip_slot in scene._clip_slots:
                if hasattr(clip_slot, 'set_edit_mode_component'):
                    clip_slot.set_edit_mode_component(edit_mode)

    def set_user_mode_button(self, button):
        """Set the user_mode_button reference and propagate to every
        existing scene so scene-launch presses can short-circuit while
        the button is held (mode selector takes priority)."""
        self._user_mode_button = button
        for scene in self._scenes:
            if hasattr(scene, 'set_user_mode_button'):
                scene.set_user_mode_button(button)

    def set_modifier_button(self, button, name, clip_slots_only=False):
        """Store shift button and propagate to scenes."""
        if name == "copy_shift":
            self._copy_shift_button = button
            if not clip_slots_only:
                # Propagate to scenes for scene copy
                for scene in self._scenes:
                    if hasattr(scene, 'set_copy_shift_button'):
                        scene.set_copy_shift_button(button)
        # Call parent for standard behavior
        super(SessionComponentWithCopy, self).set_modifier_button(button, name, clip_slots_only)

    def _create_scene(self):
        """Override to propagate both copy handlers to new scenes."""
        scene = super(SessionComponentWithCopy, self)._create_scene()

        # Propagate clip copy handler to newly created clip slots
        if self._copy_handler is not None:
            for clip_slot in scene._clip_slots:
                if hasattr(clip_slot, 'set_copy_handler'):
                    clip_slot.set_copy_handler(self._copy_handler)

        # Propagate scene copy handler to newly created scene
        if self._scene_copy_handler is not None:
            if hasattr(scene, 'set_scene_copy_handler'):
                scene.set_scene_copy_handler(self._scene_copy_handler)

        # Propagate shift button to new scene
        if hasattr(self, '_copy_shift_button'):
            if hasattr(scene, 'set_copy_shift_button'):
                scene.set_copy_shift_button(self._copy_shift_button)

        # Propagate edit-mode component to new scene + its clip slots
        if self._edit_mode is not None:
            if hasattr(scene, 'set_edit_mode_component'):
                scene.set_edit_mode_component(self._edit_mode)
            for clip_slot in scene._clip_slots:
                if hasattr(clip_slot, 'set_edit_mode_component'):
                    clip_slot.set_edit_mode_component(self._edit_mode)

        # Propagate user_mode_button reference to new scene
        if self._user_mode_button is not None:
            if hasattr(scene, 'set_user_mode_button'):
                scene.set_user_mode_button(self._user_mode_button)

        return scene
