# Launchpad Mini MK3 - Channel Strip with Arm Toggle
# Extension of ChannelStripComponent that toggles arm when clicking selected track
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.base import listens, liveobj_valid
from ableton.v2.control_surface.components import ChannelStripComponent
from novation.colors import Rgb


class ChannelStripComponentWithArmToggle(ChannelStripComponent):
    """
    Extended ChannelStripComponent that adds arm toggle functionality
    when clicking on an already selected track.

    Behavior:
    - Click on unselected track -> Select the track (green button)
    - Click on selected track -> Toggle arm state (red if armed, green if not)
    - Respects Ableton's Exclusive Arm preference setting
    - Supports multi-track selection (arms/disarms all selected tracks)
    """

    def __init__(self, *a, **k):
        super(ChannelStripComponentWithArmToggle, self).__init__(*a, **k)
        # Listener for track arm state changes
        self._ChannelStripComponentWithArmToggle__on_arm_changed.subject = None

    def set_track(self, track):
        """Override to attach arm listener when track is set."""
        super(ChannelStripComponentWithArmToggle, self).set_track(track)
        # Attach listener to track's arm property
        self._ChannelStripComponentWithArmToggle__on_arm_changed.subject = track if liveobj_valid(track) else None
        # Update button color to reflect current state
        self._update_select_button()

    def _on_select_button_pressed(self, button):
        """
        Override to add arm toggle when track is already selected.

        Behavior:
        - If track is not selected -> select it (original behavior)
        - If track is already selected -> toggle arm state
        """
        if liveobj_valid(self._track):
            if self.song.view.selected_track != self._track:
                # Track not selected: select it (original behavior)
                self.song.view.selected_track = self._track
            else:
                # Track already selected: toggle arm (respect exclusive arm preference)
                if self._track.can_be_armed:
                    arm_exclusive = self.song.exclusive_arm
                    new_value = not self._track.arm
                    respect_multi_selection = self._track.is_part_of_selection

                    # Apply arm state to target track(s) and handle exclusive disarming
                    for track in self.song.tracks:
                        if track.can_be_armed:
                            # Arm/disarm target track and any multi-selected tracks
                            if track == self._track or (respect_multi_selection and track.is_part_of_selection):
                                track.arm = new_value
                            # In exclusive mode, disarm other tracks when arming
                            elif arm_exclusive and track.arm:
                                track.arm = False

    def _update_select_button(self):
        """
        Override to update button color based on both selection and arm state.

        Colors:
        - Selected + armed -> Red (Mixer.ArmOn)
        - Selected + not armed -> Green (DefaultButton.On)
        - Not selected -> Grey (Rgb.GREY)
        - Empty track slot -> Empty color
        """
        # Only update if select button is currently mapped/enabled
        # This prevents updating wrong buttons when not in select mode
        if not self.select_button.enabled:
            return

        if liveobj_valid(self._track) or self.empty_color is None:
            if self.song.view.selected_track == self._track:
                # Track is selected
                if self._track.can_be_armed and self._track.arm:
                    # Selected and armed -> Red
                    self.select_button.color = "Mixer.ArmOn"
                else:
                    # Selected but not armed -> Green (use default ON color)
                    self.select_button.color = "DefaultButton.On"
            else:
                # Track not selected -> Grey
                self.select_button.color = Rgb.GREY
        else:
            # Empty track slot
            self.select_button.color = self.empty_color

    @listens("arm")
    def __on_arm_changed(self):
        """
        Listener for track arm state changes.
        Updates button color when arm state changes (via UI, MIDI, or automation).
        """
        self._update_select_button()
