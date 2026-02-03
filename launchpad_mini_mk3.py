# Launchpad Mini MK3 Control Surface Script - Based on 12.0.1 with select mode, clip copy, and arm toggle
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.base import listens
from ableton.v2.control_surface import Layer
from ableton.v2.control_surface.components import SessionOverviewComponent
from ableton.v2.control_surface.mode import AddLayerMode, ModesComponent
from novation import sysex
from novation.novation_base import NovationBase
from novation.session_modes import SessionModesComponent
from . import sysex_ids as ids
from .channel_strip_with_arm_toggle import ChannelStripComponentWithArmToggle
from .clip_copy_component import ClipCopyComponent
from .elements import Elements
from .notifying_background import NotifyingBackgroundComponent
from .session_with_copy import SessionComponentWithCopy
from .skin import skin


class Launchpad_Mini_MK3(NovationBase):
    model_family_code = ids.LP_MINI_MK3_FAMILY_CODE
    element_class = Elements
    session_class = SessionComponentWithCopy
    channel_strip_class = ChannelStripComponentWithArmToggle
    skin = skin

    def __init__(self, *a, **k):
        self._last_layout_byte = sysex.SESSION_LAYOUT_BYTE
        (super(Launchpad_Mini_MK3, self).__init__)(*a, **k)

    def on_identified(self, midi_bytes):
        self._elements.firmware_mode_switch.send_value(sysex.DAW_MODE_BYTE)
        self._elements.layout_switch.send_value(self._last_layout_byte)
        super(Launchpad_Mini_MK3, self).on_identified(midi_bytes)

    def can_lock_to_devices(self):
        return False

    def _create_components(self):
        super(Launchpad_Mini_MK3, self)._create_components()
        self._create_background()
        self._create_clip_copy()
        self._create_stop_solo_mute_modes()
        self._create_session_modes()
        self._Launchpad_Mini_MK3__on_layout_switch_value.subject = self._elements.layout_switch

    def _create_session_layer(self):
        return super(Launchpad_Mini_MK3, self)._create_session_layer() + Layer(scene_launch_buttons="scene_launch_buttons")

    def _create_clip_copy(self):
        """Create clip copy-paste handler."""
        self._clip_copy = ClipCopyComponent(name="Clip_Copy")
        self._session.set_copy_handler(self._clip_copy)

    def _create_stop_solo_mute_modes(self):
        self._shift_button = self._elements.scene_launch_buttons_raw[7]
        self._stop_solo_mute_modes = ModesComponent(name="Stop_Solo_Mute_Modes",
          is_enabled=False,
          support_momentary_mode_cycling=False,
          layer=Layer(cycle_mode_button=self._shift_button))
        bottom_row = self._elements.clip_launch_matrix.submatrix[:, 7:8]
        self._stop_solo_mute_modes.add_mode("launch",
          None, cycle_mode_button_color="Mode.Launch.On")
        self._stop_solo_mute_modes.add_mode("stop",
          (AddLayerMode(self._session, Layer(stop_track_clip_buttons=bottom_row))),
          cycle_mode_button_color="Session.StopClip")
        self._stop_solo_mute_modes.add_mode("solo",
          (AddLayerMode(self._mixer, Layer(solo_buttons=bottom_row))),
          cycle_mode_button_color="Mixer.SoloOn")
        self._stop_solo_mute_modes.add_mode("mute",
          (AddLayerMode(self._mixer, Layer(mute_buttons=bottom_row))),
          cycle_mode_button_color="Mixer.MuteOff")
        # NEW: Add select mode
        self._stop_solo_mute_modes.add_mode("select",
          (AddLayerMode(self._mixer, Layer(track_select_buttons=bottom_row))),
          cycle_mode_button_color="Mixer.TrackSelected")
        self._stop_solo_mute_modes.selected_mode = "launch"
        # Configure shift button for copy-paste
        self._session.set_modifier_button(self._shift_button, "copy_shift", clip_slots_only=True)
        self._Launchpad_Mini_MK3__on_shift_button_value.subject = self._shift_button
        self._stop_solo_mute_modes.set_enabled(True)

    def _create_session_modes(self):
        self._session_overview = SessionOverviewComponent(name="Session_Overview",
          is_enabled=False,
          session_ring=(self._session_ring),
          enable_skinning=True,
          layer=Layer(button_matrix="clip_launch_matrix"))
        self._session_modes = SessionModesComponent(name="Session_Modes",
          is_enabled=False,
          layer=Layer(cycle_mode_button="session_mode_button",
          mode_button_color_control="session_button_color_element"))
        self._session_modes.add_mode("launch", None)
        self._session_modes.add_mode("overview", (
         self._session_overview,
         AddLayerMode(self._session_navigation, Layer(page_up_button="up_button",
           page_down_button="down_button",
           page_left_button="left_button",
           page_right_button="right_button")),
         AddLayerMode(self._background, Layer(scene_launch_buttons="scene_launch_buttons"))))
        self._session_modes.selected_mode = "launch"
        self._session_modes.set_enabled(True)
        self._Launchpad_Mini_MK3__on_session_mode_changed.subject = self._session_modes

    def _create_background(self):
        self._background = NotifyingBackgroundComponent(name="Background",
          is_enabled=False,
          add_nop_listeners=True,
          layer=Layer(drums_mode_button="drums_mode_button",
          keys_mode_button="keys_mode_button",
          user_mode_button="user_mode_button"))
        self._background.set_enabled(True)
        self._Launchpad_Mini_MK3__on_background_control_value.subject = self._background

    @listens("selected_mode")
    def __on_session_mode_changed(self, _):
        self._elements.layout_switch.enquire_value()

    @listens("value")
    def __on_background_control_value(self, control, value):
        if value:
            if "Mode" in control.name:
                self._elements.layout_switch.enquire_value()

    @listens("value")
    def __on_layout_switch_value(self, value):
        self._last_layout_byte = value

    @listens("value")
    def __on_shift_button_value(self, value):
        """Clear clipboard when shift button is released."""
        if not value:
            self._clip_copy.clear_clipboard()
