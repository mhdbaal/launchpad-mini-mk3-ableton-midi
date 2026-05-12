# Launchpad Mini MK3 Control Surface Script - Based on 12.0.1 with select mode, clip copy, and arm toggle
from __future__ import absolute_import, print_function, unicode_literals
import time
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
from .drum_step_sequencer import DrumStepSequencerComponent
from .melodic_step_sequencer import MelodicStepSequencerComponent
from .scene_copy_component import SceneCopyComponent
from .elements import Elements
from .notifying_background import NotifyingBackgroundComponent
from .session_with_copy import SessionComponentWithCopy
from .skin import skin
from .transport_component import TransportComponent


DRUM_FEEDBACK_CHANNEL = 1
PROGRAMMER_MODE_COMMAND_BYTE = 14
PROGRAMMER_MODE_ON = 1
PROGRAMMER_MODE_OFF = 0
LED_FEEDBACK_COMMAND_BYTE = 10
INTERNAL_FEEDBACK_OFF = 0
EXTERNAL_FEEDBACK_ON = 1
SLEEP_COMMAND_BYTE = 9
SLEEP_OFF = 1
MIDI_CC_STATUS = 176
PROGRAMMER_LED_CHANNEL = 0
SESSION_BUTTON_CC = 95
DRUMS_BUTTON_CC = 96
KEYS_BUTTON_CC = 97
USER_BUTTON_CC = 98
UP_BUTTON_CC = 91
DOWN_BUTTON_CC = 92
LEFT_BUTTON_CC = 93
RIGHT_BUTTON_CC = 94
LED_OFF = 0
LED_SESSION = 21
LED_SESSION_DIM = 27  # GREEN_HALF — "session button is available, press to switch"
LED_SEQUENCER = 96
LED_MELODIC = 41
LED_ARROW_OCTAVE = 27   # GREEN_HALF, matches Control.Octave skin
LED_ARROW_SEMITONE = 29  # MINT, matches Control.Semitone skin
# Session-button hold-to-preview threshold while in drum_sequence main mode.
# Below: tap → latch session mode. Above: hold → revert to drum_sequence on release.
SESSION_HOLD_THRESHOLD = 0.3


class Launchpad_Mini_MK3(NovationBase):
    model_family_code = ids.LP_MINI_MK3_FAMILY_CODE
    element_class = Elements
    session_class = SessionComponentWithCopy
    channel_strip_class = ChannelStripComponentWithArmToggle
    skin = skin

    def __init__(self, *a, **k):
        self._last_layout_byte = sysex.SESSION_LAYOUT_BYTE
        # Tracks a session-button press that started while in drum_sequence
        # main mode. None when not held-from-drum; a time.time() value while
        # held. Used to distinguish a tap (latch session) from a hold (preview).
        self._session_preview_press_time = None
        (super(Launchpad_Mini_MK3, self).__init__)(*a, **k)

    def on_identified(self, midi_bytes):
        self._enter_programmer_mode()
        self.set_feedback_channels([DRUM_FEEDBACK_CHANNEL])
        super(Launchpad_Mini_MK3, self).on_identified(midi_bytes)

    def disconnect(self):
        try:
            self._exit_programmer_mode()
        finally:
            super(Launchpad_Mini_MK3, self).disconnect()

    def can_lock_to_devices(self):
        return False

    def _create_components(self):
        super(Launchpad_Mini_MK3, self)._create_components()
        self._create_background()
        self._create_clip_copy()
        self._create_stop_solo_mute_modes()
        self._create_session_modes()
        self._create_transport()
        self._create_drum_sequencer()
        self._create_melodic_sequencer()
        self._create_main_modes()
        self._Launchpad_Mini_MK3__on_layout_switch_value.subject = self._elements.layout_switch
        self._Launchpad_Mini_MK3__on_selected_track_changed.subject = self.song.view
        self._Launchpad_Mini_MK3__on_session_mode_button_value.subject = self._elements.session_mode_button
        self._Launchpad_Mini_MK3__on_up_button_value.subject = self._elements.up_button
        self._Launchpad_Mini_MK3__on_down_button_value.subject = self._elements.down_button
        self._Launchpad_Mini_MK3__on_left_button_value.subject = self._elements.left_button
        self._Launchpad_Mini_MK3__on_right_button_value.subject = self._elements.right_button

    def _create_session_layer(self):
        return super(Launchpad_Mini_MK3, self)._create_session_layer() + Layer(scene_launch_buttons="scene_launch_buttons")

    def _create_clip_copy(self):
        """Create clip and scene copy-paste handlers."""
        # Clip copy handler
        self._clip_copy = ClipCopyComponent(name="Clip_Copy")
        self._session.set_copy_handler(self._clip_copy)

        # Scene copy handler
        self._scene_copy = SceneCopyComponent(name="Scene_Copy")
        self._session.set_scene_copy_handler(self._scene_copy)

    def _create_stop_solo_mute_modes(self):
        self._shift_button = self._elements.scene_launch_buttons_raw[7]
        self._stop_solo_mute_modes = ModesComponent(name="Stop_Solo_Mute_Modes",
          is_enabled=False,
          support_momentary_mode_cycling=False,
          layer=Layer(cycle_mode_button=self._shift_button))
        bottom_row = self._elements.clip_launch_matrix.submatrix[:, 7:8]
        # Mode 1: Select (Arm/Select) - EN PREMIER
        self._stop_solo_mute_modes.add_mode("select",
          (AddLayerMode(self._mixer, Layer(track_select_buttons=bottom_row))),
          cycle_mode_button_color="Mixer.TrackSelected")
        # Mode 2: Stop
        self._stop_solo_mute_modes.add_mode("stop",
          (AddLayerMode(self._session, Layer(stop_track_clip_buttons=bottom_row))),
          cycle_mode_button_color="Session.StopClip")
        # Mode 3: Solo
        self._stop_solo_mute_modes.add_mode("solo",
          (AddLayerMode(self._mixer, Layer(solo_buttons=bottom_row))),
          cycle_mode_button_color="Mixer.SoloOn")
        # Mode 4: Mute
        self._stop_solo_mute_modes.add_mode("mute",
          (AddLayerMode(self._mixer, Layer(mute_buttons=bottom_row))),
          cycle_mode_button_color="Mixer.MuteOff")
        self._stop_solo_mute_modes.selected_mode = "select"
        # Configure shift button for clip copy (clip slots only)
        self._session.set_modifier_button(self._shift_button, "copy_shift", clip_slots_only=True)
        # Configure shift button for scene copy (scenes only)
        self._session.set_modifier_button(self._shift_button, "copy_shift", clip_slots_only=False)
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

    def _create_transport(self):
        """Play/Stop on Drums button, Session Record on Keys button. Session-mode only.

        The buttons remain in the background layer for their normal nop handling;
        the transport attaches additional value listeners directly to the elements
        (same pattern as the sequencer control buttons) and drives the LEDs via
        raw CC writes."""
        self._transport = TransportComponent(name="Transport", is_enabled=False)
        self._transport.set_buttons(self._elements.drums_mode_button,
          self._elements.keys_mode_button)
        self._transport.set_enabled(True)

    def _create_drum_sequencer(self):
        self._drum_group = None
        self._drum_step_sequencer = DrumStepSequencerComponent(name="Drum_Step_Sequencer",
          is_enabled=False,
          drum_group_component=self._drum_group,
          layer=Layer(grid_matrix="clip_launch_matrix"))
        self._drum_step_sequencer.set_control_buttons(self._elements.scene_launch_buttons_raw)

    def _create_melodic_sequencer(self):
        self._melodic_step_sequencer = MelodicStepSequencerComponent(name="Melodic_Step_Sequencer",
          is_enabled=False,
          layer=Layer(grid_matrix="clip_launch_matrix"))
        self._melodic_step_sequencer.set_control_buttons(self._elements.scene_launch_buttons_raw)

    def _create_main_modes(self):
        self._main_modes = ModesComponent(name="Main_Modes",
          is_enabled=False,
          enable_skinning=True,
          support_momentary_mode_cycling=False,
          layer=Layer(cycle_mode_button="user_mode_button"))
        self._main_modes.add_mode("session", None,
          cycle_mode_button_color="DefaultButton.Off")
        self._main_modes.add_mode("drum_sequence", None,
          cycle_mode_button_color="DrumSequencer.StepActive")
        self._main_modes.add_mode("melodic_sequence", None,
          cycle_mode_button_color="MelodicSequencer.StepActive")
        self._main_modes.selected_mode = "session"
        self._Launchpad_Mini_MK3__on_main_mode_changed.subject = self._main_modes
        self._main_modes.set_enabled(True)

    def _create_background(self):
        # drums/keys stay in the background's nop layer (preserves the layout-switch
        # enquire on press); the TransportComponent attaches its own value listeners
        # on top of these elements in session mode.
        self._background = NotifyingBackgroundComponent(name="Background",
          is_enabled=False,
          add_nop_listeners=True,
          layer=Layer(drums_mode_button="drums_mode_button",
          keys_mode_button="keys_mode_button"))
        self._background.set_enabled(True)
        self._Launchpad_Mini_MK3__on_background_control_value.subject = self._background

    @listens("selected_mode")
    def __on_main_mode_changed(self, mode):
        drum_mode = mode == "drum_sequence"
        melodic_mode = mode == "melodic_sequence"
        sequencer_mode = drum_mode or melodic_mode
        self._log("main mode changed: {}".format(mode))
        # Transport (Drums=Play, Keys=Record) stays live in session and
        # drum_sequence; only melodic_sequence darkens the buttons.
        self._transport.set_enabled(not melodic_mode)
        if sequencer_mode:
            self._set_session_components_enabled(False)
            if drum_mode:
                self._melodic_step_sequencer.set_enabled(False)
            else:
                self._drum_step_sequencer.set_enabled(False)
            self._restore_clip_launch_matrix()
            if drum_mode:
                self._drum_step_sequencer.set_enabled(True)
            else:
                self._melodic_step_sequencer.set_enabled(True)
            self.set_controlled_track(self.song.view.selected_track)
            self._request_midi_map_rebuild()
            self._set_mode_button_lights(mode)
            if drum_mode:
                self.show_message("Launchpad Mini MK3: Drum Sequencer")
                self._drum_step_sequencer.update()
            else:
                self.show_message("Launchpad Mini MK3: Melodic Sequencer")
                self._melodic_step_sequencer.update()
        else:
            self._drum_step_sequencer.set_enabled(False)
            self._melodic_step_sequencer.set_enabled(False)
            self._restore_clip_launch_matrix()
            self.release_controlled_track()
            self._set_session_components_enabled(True)
            self._request_midi_map_rebuild()
            self._set_mode_button_lights(mode)

    @listens("selected_track")
    def __on_selected_track_changed(self):
        if hasattr(self, "_main_modes") and self._main_modes.selected_mode in ("drum_sequence", "melodic_sequence"):
            self.set_controlled_track(self.song.view.selected_track)

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
        layout_byte = value[0] if isinstance(value, tuple) else value
        self._log("layout value: {}".format(value))
        self._last_layout_byte = layout_byte

    @listens("value")
    def __on_session_mode_button_value(self, value):
        """In drum_sequence main mode, the Session button doubles as a return-to-session
        control with momentary-preview semantics:
          - tap (release within SESSION_HOLD_THRESHOLD) -> latch session mode
          - hold (release after threshold)              -> revert to drum_sequence
        In session or melodic main modes this listener is a no-op; the Session button
        keeps its standard behavior (cycle launch/overview, owned by session_modes).
        """
        if value:
            if self._main_modes.selected_mode == "drum_sequence":
                self._session_preview_press_time = time.time()
                self._main_modes.selected_mode = "session"
            return
        if self._session_preview_press_time is None:
            return
        held = time.time() - self._session_preview_press_time
        self._session_preview_press_time = None
        if held > SESSION_HOLD_THRESHOLD:
            self._main_modes.selected_mode = "drum_sequence"

    @listens("value")
    def __on_up_button_value(self, value):
        if value and self._main_modes.selected_mode == "drum_sequence":
            self._drum_step_sequencer.adjust_pitch_offset(12)

    @listens("value")
    def __on_down_button_value(self, value):
        if value and self._main_modes.selected_mode == "drum_sequence":
            self._drum_step_sequencer.adjust_pitch_offset(-12)

    @listens("value")
    def __on_left_button_value(self, value):
        if value and self._main_modes.selected_mode == "drum_sequence":
            self._drum_step_sequencer.adjust_pitch_offset(-1)

    @listens("value")
    def __on_right_button_value(self, value):
        if value and self._main_modes.selected_mode == "drum_sequence":
            self._drum_step_sequencer.adjust_pitch_offset(1)

    @listens("value")
    def __on_shift_button_value(self, value):
        """Clear both clipboards when shift button is released."""
        if not value:
            self._clip_copy.clear_clipboard()
            self._scene_copy.clear_clipboard()

    def _log(self, message):
        try:
            self._c_instance.log_message("[Launchpad Mini MK3] {}".format(message))
        except Exception:
            pass

    def _set_session_components_enabled(self, enabled):
        self._session.set_enabled(enabled)
        self._session_navigation.set_enabled(enabled)
        self._session_modes.set_enabled(enabled)
        self._stop_solo_mute_modes.set_enabled(enabled)
        # NOTE: TransportComponent is handled separately in __on_main_mode_changed.
        # It stays active in session AND drum_sequence (only off in melodic).

    def _restore_clip_launch_matrix(self):
        for button in self._elements.clip_launch_matrix:
            if button is not None:
                button.use_default_message()
        self._request_midi_map_rebuild()

    def _request_midi_map_rebuild(self):
        try:
            self.request_rebuild_midi_map()
        except Exception:
            pass

    def _enter_programmer_mode(self):
        self._send_launchpad_sysex(PROGRAMMER_MODE_COMMAND_BYTE, PROGRAMMER_MODE_ON)
        self._send_launchpad_sysex(LED_FEEDBACK_COMMAND_BYTE, INTERNAL_FEEDBACK_OFF, EXTERNAL_FEEDBACK_ON)
        self._send_launchpad_sysex(SLEEP_COMMAND_BYTE, SLEEP_OFF)
        self._log("programmer mode enabled with external feedback")

    def _exit_programmer_mode(self):
        self._send_launchpad_sysex(PROGRAMMER_MODE_COMMAND_BYTE, PROGRAMMER_MODE_OFF)
        self._elements.firmware_mode_switch.send_value(sysex.STANDALONE_MODE_BYTE)

    def _send_launchpad_sysex(self, command_byte, *payload):
        try:
            self._send_midi(sysex.STD_MSG_HEADER + (ids.LP_MINI_MK3_ID, command_byte) + tuple(payload) + (sysex.SYSEX_END_BYTE,))
        except Exception:
            pass

    def _set_mode_button_lights(self, mode):
        if mode == "drum_sequence":
            # Dim green = "session button is reachable" (tap to latch session,
            # hold to preview). See __on_session_mode_button_value.
            self._send_programmer_cc(SESSION_BUTTON_CC, LED_SESSION_DIM)
            # Drums/Keys are driven by TransportComponent (still active in drum_sequence).
            self._send_programmer_cc(USER_BUTTON_CC, LED_SEQUENCER)
            # Arrows drive octave / semitone of the drum-pad selector.
            self._send_programmer_cc(UP_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(DOWN_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(LEFT_BUTTON_CC, LED_ARROW_SEMITONE)
            self._send_programmer_cc(RIGHT_BUTTON_CC, LED_ARROW_SEMITONE)
        elif mode == "melodic_sequence":
            self._send_programmer_cc(SESSION_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(DRUMS_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(KEYS_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(USER_BUTTON_CC, LED_MELODIC)
            self._send_programmer_cc(UP_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(DOWN_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(LEFT_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(RIGHT_BUTTON_CC, LED_OFF)
        else:
            self._send_programmer_cc(SESSION_BUTTON_CC, LED_SESSION)
            # Drums/Keys are driven by TransportComponent in session mode.
            self._send_programmer_cc(USER_BUTTON_CC, LED_OFF)
            # Hand the arrows back to session_navigation; turn them off here
            # so we don't leave a stale octave/semitone color when leaving the
            # drum sequencer. session_navigation will relight them when the
            # user switches to session overview.
            self._send_programmer_cc(UP_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(DOWN_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(LEFT_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(RIGHT_BUTTON_CC, LED_OFF)

    def _send_programmer_cc(self, identifier, value):
        try:
            self._send_midi((MIDI_CC_STATUS + PROGRAMMER_LED_CHANNEL, identifier, value), optimized=False)
        except Exception:
            pass
