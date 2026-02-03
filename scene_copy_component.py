# Launchpad Mini MK3 - Scene Copy Component
# Handles scene copy-paste functionality with clipboard management
from __future__ import absolute_import, print_function, unicode_literals
import Live
from ableton.v2.base import liveobj_valid
from ableton.v2.control_surface.component import Component


class SceneCopyComponent(Component):
    """
    Manages scene copy-paste clipboard state and validation.
    Mirrors ClipCopyComponent pattern for scenes.
    """

    def __init__(self, *a, **k):
        super(SceneCopyComponent, self).__init__(*a, **k)
        self._source_scene = None

    def is_copying(self):
        """Returns True if a scene is in the clipboard waiting to be pasted."""
        return self._source_scene is not None

    def handle_scene_action(self, scene):
        """
        Called when user clicks a scene button while shift is held.
        First click with valid scene -> copy
        Second click on different scene -> paste (duplicate)
        """
        if not liveobj_valid(scene):
            return

        if self.is_copying():
            # Paste mode - we have a source scene
            self._paste_scene(scene)
        else:
            # Copy mode - no source scene yet
            self._copy_scene(scene)

    def _copy_scene(self, source_scene):
        """Store source scene for copying."""
        self._source_scene = source_scene

    def _paste_scene(self, target_scene):
        """Insert a duplicate of source scene at target scene position."""
        if not liveobj_valid(self._source_scene):
            self._source_scene = None
            return

        song = self.song
        try:
            source_index = list(song.scenes).index(self._source_scene)
            target_index = list(song.scenes).index(target_scene)

            # Don't paste onto itself
            if source_index == target_index:
                return

            # Create a new empty scene at the target position
            # This will push the current target scene down
            new_scene = song.create_scene(target_index)

            # Copy all clips from source scene to new scene
            source_clip_slots = self._source_scene.clip_slots
            new_clip_slots = new_scene.clip_slots

            # Iterate through all tracks and copy clips
            for i, source_slot in enumerate(source_clip_slots):
                if i < len(new_clip_slots):  # Safety check
                    target_slot = new_clip_slots[i]
                    # If source slot has a clip, duplicate it to target
                    if source_slot.has_clip:
                        try:
                            source_slot.duplicate_clip_to(target_slot)
                        except:
                            # Skip if duplication fails (e.g., incompatible track types)
                            pass

            # Copy scene properties (name, color, tempo, time signature)
            try:
                new_scene.name = self._source_scene.name
                new_scene.color = self._source_scene.color
                if hasattr(self._source_scene, 'tempo') and self._source_scene.tempo > 0:
                    new_scene.tempo = self._source_scene.tempo
                if hasattr(self._source_scene, 'time_signature_numerator'):
                    new_scene.time_signature_numerator = self._source_scene.time_signature_numerator
                    new_scene.time_signature_denominator = self._source_scene.time_signature_denominator
            except:
                # Some properties might not be available or editable
                pass

            # Keep source in clipboard for multiple pastes
        except (Live.Base.LimitationError, IndexError, RuntimeError):
            # If operation fails, clear clipboard
            self._source_scene = None

    def clear_clipboard(self):
        """Clear the clipboard when shift is released."""
        self._source_scene = None
