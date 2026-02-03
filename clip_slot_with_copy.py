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

    def set_copy_shift_button(self, button):
        """Called by SessionComponent.set_modifier_button() when shift is set."""
        self._copy_shift_button = button

    def set_copy_handler(self, handler):
        """Set the ClipCopyComponent instance that handles copy logic."""
        self._copy_handler = handler

    def _on_launch_button_pressed(self):
        """
        Override to intercept clip slot clicks and check for shift mode.
        If shift is held, trigger copy-paste instead of launch.
        """
        # Check if copy-shift button is held
        if is_button_pressed(self._copy_shift_button):
            # Shift mode - handle copy/paste
            if self._copy_handler is not None:
                self._copy_handler.handle_clip_slot_action(self._clip_slot)
            # Don't call super - we don't want normal launch behavior
            return

        # No shift - normal behavior
        super(ClipSlotComponentWithCopy, self)._on_launch_button_pressed()
