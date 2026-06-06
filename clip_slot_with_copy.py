# Launchpad Mini MK3 - ClipSlot Component with Copy Support
# Extends ClipSlotComponent to detect shift mode and trigger copy-paste
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.control_surface.components import ClipSlotComponent


def is_button_pressed(button):
    """Helper to check if a button is currently pressed."""
    return button and button.is_pressed()


class ClipSlotComponentWithCopy(ClipSlotComponent):
    """
    Extended ClipSlotComponent that checks for shift button (copy_shift)
    and triggers copy-paste operations instead of normal clip launch.
    """

    def __init__(self, *a, **k):
        super(ClipSlotComponentWithCopy, self).__init__(*a, **k)
        self._copy_shift_button = None
        self._copy_handler = None
        self._edit_mode = None

    def set_copy_shift_button(self, button):
        """Called by SessionComponent.set_modifier_button() when shift is set."""
        self._copy_shift_button = button

    def set_copy_handler(self, handler):
        """Set the ClipCopyComponent instance that handles copy logic."""
        self._copy_handler = handler

    def set_edit_mode_component(self, edit_mode):
        """Set the EditModeComponent. When edit mode is active, presses on
        this clip slot route to the edit-mode handler (delete/duplicate/move)
        instead of the normal launch or copy-shift path."""
        self._edit_mode = edit_mode

    def _on_launch_button_pressed(self):
        """
        Override to intercept clip slot clicks. Priority order:
          1. edit mode active  → route to EditModeComponent.handle_clip_action
             (this also short-circuits copy_shift, so the shift+tap
             copy gesture is intentionally disabled in edit mode)
          2. copy_shift held   → route to clip copy/paste handler
          3. nothing held      → normal launch
        """
        if self._edit_mode is not None and self._edit_mode.is_active():
            self._edit_mode.handle_clip_action(self)
            return

        if is_button_pressed(self._copy_shift_button):
            if self._copy_handler is not None:
                self._copy_handler.handle_clip_slot_action(self._clip_slot)
            return

        super(ClipSlotComponentWithCopy, self)._on_launch_button_pressed()

    def _on_launch_button_released(self):
        """The base ClipSlotComponent fires `_do_launch_clip(False)` on
        release too. Without the same edit/copy guards here, swallowing
        the press alone isn't enough — the clip would still launch when
        the user lifts the finger. Mirror the press priority order so
        edit-mode taps and copy gestures are truly no-launch."""
        if self._edit_mode is not None and self._edit_mode.is_active():
            return
        if is_button_pressed(self._copy_shift_button):
            return
        super(ClipSlotComponentWithCopy, self)._on_launch_button_released()
