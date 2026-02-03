# Launchpad Mini MK3 - Session Component with Copy Support
# Extends SessionComponent to use ClipSlotComponentWithCopy
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.control_surface.components import SessionComponent, SceneComponent
from .clip_slot_with_copy import ClipSlotComponentWithCopy


class SceneComponentWithCopy(SceneComponent):
    """SceneComponent that uses ClipSlotComponentWithCopy."""
    clip_slot_component_type = ClipSlotComponentWithCopy


class SessionComponentWithCopy(SessionComponent):
    """
    Extended SessionComponent that uses ClipSlotComponentWithCopy
    to support copy-paste functionality.
    """
    scene_component_type = SceneComponentWithCopy

    def __init__(self, *a, **k):
        self._copy_handler = None
        super(SessionComponentWithCopy, self).__init__(*a, **k)

    def set_copy_handler(self, copy_handler):
        """Set the ClipCopyComponent to handle copy-paste logic."""
        self._copy_handler = copy_handler
        # Propagate to all existing clip slots
        for scene in self._scenes:
            for clip_slot in scene._clip_slots:
                if hasattr(clip_slot, 'set_copy_handler'):
                    clip_slot.set_copy_handler(copy_handler)

    def _create_scene(self):
        """Override to propagate copy handler to new scenes."""
        scene = super(SessionComponentWithCopy, self)._create_scene()
        # Propagate copy handler to newly created clip slots
        if self._copy_handler is not None:
            for clip_slot in scene._clip_slots:
                if hasattr(clip_slot, 'set_copy_handler'):
                    clip_slot.set_copy_handler(self._copy_handler)
        return scene
