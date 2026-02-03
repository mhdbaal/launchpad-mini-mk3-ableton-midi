# Launchpad Mini MK3 - Clip Copy Component
# Handles clip copy-paste functionality with clipboard management
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.base import liveobj_valid
from ableton.v2.control_surface.component import Component


class ClipCopyComponent(Component):
    """
    Manages clip copy-paste clipboard state and validation.
    Based on Push2's ClipSlotCopyHandler pattern.
    """

    def __init__(self, *a, **k):
        super(ClipCopyComponent, self).__init__(*a, **k)
        self._source_clip_slot = None

    def is_copying(self):
        """Returns True if a clip is in the clipboard waiting to be pasted."""
        return self._source_clip_slot is not None

    def handle_clip_slot_action(self, clip_slot):
        """
        Called when user clicks a clip slot while shift is held.
        First click with clip -> copy
        Second click on empty slot -> paste
        """
        if not liveobj_valid(clip_slot):
            return

        if clip_slot.is_group_slot:
            # Can't copy from or paste to group track slots
            return

        if self.is_copying():
            # Paste mode - we have a source clip
            if not clip_slot.has_clip:
                # Target is empty, attempt paste
                self._paste_clip(clip_slot)
            # If target has clip, ignore (don't overwrite)
        else:
            # Copy mode - no source clip yet
            if clip_slot.has_clip:
                self._copy_clip(clip_slot)
            # If empty, ignore

    def _copy_clip(self, source_clip_slot):
        """Validate and store source clip for copying."""
        if source_clip_slot.clip.is_recording:
            # Can't copy recording clips
            return

        self._source_clip_slot = source_clip_slot

    def _paste_clip(self, target_clip_slot):
        """Validate compatibility and paste clip."""
        if not liveobj_valid(self._source_clip_slot):
            self._source_clip_slot = None
            return

        source_clip = self._source_clip_slot.clip
        target_track = target_clip_slot.canonical_parent

        # Validate track type compatibility
        if source_clip.is_audio_clip:
            # Audio clips can only go to audio tracks
            if not target_track.has_audio_input:
                return  # Incompatible - ignore
        # MIDI clips can go to MIDI or audio tracks (Live handles conversion)

        # Perform the copy
        try:
            self._source_clip_slot.duplicate_clip_to(target_clip_slot)
            # Keep source in clipboard for multiple pastes
        except:
            # If copy fails (e.g., Live API error), clear clipboard
            self._source_clip_slot = None

    def clear_clipboard(self):
        """Clear the clipboard when shift is released."""
        self._source_clip_slot = None
