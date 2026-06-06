# Launchpad Pro MK3 Control Surface Script — native-UX port of the custom
# Mini MK3 script (mini/launchpad_mini_mk3.py is the reference wiring).
#
# Same Programmer-mode takeover, same shared components — but the Mini's
# button-scarcity workarounds are gone, replaced by the Pro's dedicated
# hardware:
#   - Shift (CC 90) replaces the overloaded scene-button shift: hold for
#     copy/paste in session, hold for the sequencers' shift layer. No
#     double-tap shift lock, no tap-cycle.
#   - Clear (60) / Duplicate (50) hold-modifiers replace the edit sub-mode
#     (session: delete/duplicate clips+scenes) and the sequencer's
#     special-shift slot (delete/duplicate steps/pads/pages).
#   - Quantise (40) replaces the sequencer quantize slot.
#   - Play (20) / Record (10) replace Drums/Keys transport; Shift+Record =
#     Capture MIDI.
#   - Note (94) / Sequencer (97) switch main modes directly — the User
#     hold-to-select machinery doesn't exist here.
#   - The track-select row (CC 101-108) + function row (Record Arm/Mute/
#     Solo/Stop Clip, CC 1/2/3/8) carry the mixer modes, so the 8x8 grid
#     keeps all 8 rows for clips and all 8 scene buttons launch scenes.
#   - Shift+Record Arm / Shift+Mute = Undo / Redo; Shift+Stop Clip =
#     Stop All Clips.
from __future__ import absolute_import, print_function, unicode_literals
import time
from ableton.v2.base import listens
from ableton.v2.control_surface import Layer
from ableton.v2.control_surface.components import SessionOverviewComponent
from ableton.v2.control_surface.mode import AddLayerMode, ModesComponent
from novation import sysex
from novation.novation_base import NovationBase
from novation.session_modes import SessionModesComponent
from .channel_strip_with_arm_toggle import ChannelStripComponentWithArmToggle
from .clip_copy_component import ClipCopyComponent
from .chord_pad_mode import ChordPadComponent
from .device_profile import (
    CHORD_BUTTON_CC,
    CLEAR_BUTTON_CC,
    DEVICE_FAMILY_CODE,
    DEVICE_SYSEX_ID,
    DOWN_BUTTON_CC,
    DUPLICATE_BUTTON_CC,
    EXTERNAL_FEEDBACK_ON,
    INERT_BUTTON_CCS,
    INTERNAL_FEEDBACK_OFF,
    LED_ARM_ACTIVE,
    LED_ARM_IDLE,
    LED_ARROW_OCTAVE,
    LED_ARROW_SEMITONE,
    LED_CHORD,
    LED_CLEAR_HELD,
    LED_CLEAR_IDLE,
    LED_DUPLICATE_HELD,
    LED_DUPLICATE_IDLE,
    LED_FEEDBACK_COMMAND_BYTE,
    LED_MELODIC,
    LED_MODE_IDLE,
    LED_MUTE_ACTIVE,
    LED_MUTE_IDLE,
    LED_OFF,
    LED_QUANTIZE_IDLE,
    LED_SEQUENCER,
    LED_SESSION,
    LED_SESSION_DIM,
    LED_SESSION_PINNED,
    LED_SHIFT_HELD,
    LED_SHIFT_IDLE,
    LED_SOLO_ACTIVE,
    LED_SOLO_IDLE,
    LED_STOP_ACTIVE,
    LED_STOP_IDLE,
    LEFT_BUTTON_CC,
    MUTE_BUTTON_CC,
    NOTE_BUTTON_CC,
    PROGRAMMER_MODE_COMMAND_BYTE,
    PROGRAMMER_MODE_OFF,
    PROGRAMMER_MODE_ON,
    QUANTIZE_BUTTON_CC,
    RECORD_ARM_BUTTON_CC,
    RIGHT_BUTTON_CC,
    SEQUENCER_BUTTON_CC,
    SESSION_BUTTON_CC,
    SHIFT_BUTTON_CC,
    SLEEP_COMMAND_BYTE,
    SLEEP_OFF,
    SOLO_BUTTON_CC,
    STOP_CLIP_BUTTON_CC,
    UP_BUTTON_CC,
)
from .drum_4_track_step_sequencer import DrumStep4TrackSequencerComponent
from .drum_64_step_sequencer import DrumStep64SequencerComponent
from .drum_step_sequencer import DrumStepSequencerComponent
from .drum_variant_picker import DrumVariantPickerComponent
from .edit_mode_component import EditModeComponent
from .melodic_step_sequencer import MelodicStepSequencerComponent
from .scene_copy_component import SceneCopyComponent
from .elements import Elements
from .event_bus import EventBus
from .events import Event
from .m4l_subscriber import M4LSubscriber
from .notification_dispatcher import NotificationDispatcher
from .notifying_background import NotifyingBackgroundComponent
from .programmer_mode import AUDITION_CHANNEL, MIDI_CC_STATUS, PROGRAMMER_LED_CHANNEL
from .session_with_copy import SessionComponentWithCopy
from .skin import skin
from .status_bar_subscriber import StatusBarSubscriber
from .transport_component import TransportComponent


# Session-button hold-to-preview threshold while in a sequencer main mode.
# Below: tap → latch session mode. Above: hold → revert on release.
SESSION_HOLD_THRESHOLD = 0.3
# Velocity delta applied per Up/Down arrow press in drum modes while a step
# pad is held (same value as the Mini).
DRUM_VELOCITY_ARROW_STEP = 8

# Main modes that take over the 8x8 grid for their own UI. The drum
# variants are reachable through the Shift+Sequencer picker panel; chord
# has its dedicated button (95). "variant_picker" is the overlay panel
# itself — also a grid takeover, handled separately (it isn't a
# sequencer: no arrows, no audition, no scene-slot controls).
_SEQUENCER_MODES = ("drum_sequence", "drum_64_sequence",
                    "drum_4_track_sequence", "melodic_sequence",
                    "chord_mode")
_DRUM_MODES = ("drum_sequence", "drum_64_sequence", "drum_4_track_sequence")
VARIANT_PICKER_MODE = "variant_picker"


class Launchpad_Pro_MK3(NovationBase):
    model_family_code = DEVICE_FAMILY_CODE
    element_class = Elements
    session_class = SessionComponentWithCopy
    channel_strip_class = ChannelStripComponentWithArmToggle
    skin = skin

    def __init__(self, *a, **k):
        # Session-button preview state (press started in a sequencer mode).
        self._session_preview_press_time = None
        self._session_preview_return_mode = None
        # Drum-variant picker state: which variant the Sequencer button
        # opens on a plain press (the last one used), and which mode to
        # return to when the picker is cancelled.
        self._last_drum_variant = "drum_sequence"
        self._picker_return_mode = None
        # Notification plumbing — created early so components can take the
        # bus reference at construction time. _event_bus = None would make
        # every _emit() a no-op (kill switch).
        self._event_bus = EventBus(logger=self._log)
        self._notification_dispatcher = None
        self._status_bar_subscriber = None
        self._m4l_subscriber = None
        (super(Launchpad_Pro_MK3, self).__init__)(*a, **k)

    def on_identified(self, midi_bytes):
        self._enter_programmer_mode()
        self.set_feedback_channels([AUDITION_CHANNEL])
        super(Launchpad_Pro_MK3, self).on_identified(midi_bytes)
        # Paint the static button LEDs — on_identified re-fires on port
        # reconnection, so this doubles as the LED recovery path.
        self._set_mode_button_lights(self._main_modes.selected_mode)
        self._update_modifier_leds()
        self._update_mixer_function_leds()
        self._clear_inert_button_leds()

    def disconnect(self):
        try:
            if self._notification_dispatcher is not None:
                self._notification_dispatcher.disconnect()
        except Exception:
            pass
        try:
            self._exit_programmer_mode()
        finally:
            super(Launchpad_Pro_MK3, self).disconnect()

    def can_lock_to_devices(self):
        return False

    def _create_components(self):
        super(Launchpad_Pro_MK3, self)._create_components()
        self._create_notification_subscribers()
        self._create_background()
        self._create_clip_copy()
        self._create_edit_mode()
        self._create_mixer_modes()
        self._create_session_modes()
        self._create_transport()
        self._create_drum_sequencer()
        self._create_drum_64_sequencer()
        self._create_drum_4_track_sequencer()
        self._create_melodic_sequencer()
        self._create_chord_pad_mode()
        self._create_variant_picker()
        self._create_main_modes()
        self._Launchpad_Pro_MK3__on_selected_track_changed.subject = self.song.view
        self._Launchpad_Pro_MK3__on_session_mode_button_value.subject = self._elements.session_mode_button
        self._Launchpad_Pro_MK3__on_up_button_value.subject = self._elements.up_button
        self._Launchpad_Pro_MK3__on_down_button_value.subject = self._elements.down_button
        self._Launchpad_Pro_MK3__on_left_button_value.subject = self._elements.left_button
        self._Launchpad_Pro_MK3__on_right_button_value.subject = self._elements.right_button
        # Dedicated-button listeners (direct value listeners, same pattern
        # as the sequencer control buttons — no Layer competition).
        self._Launchpad_Pro_MK3__on_shift_button_value.subject = self._elements.shift_button
        self._Launchpad_Pro_MK3__on_clear_button_value.subject = self._elements.clear_button
        self._Launchpad_Pro_MK3__on_duplicate_button_value.subject = self._elements.duplicate_button
        self._Launchpad_Pro_MK3__on_quantize_button_value.subject = self._elements.quantize_button
        self._Launchpad_Pro_MK3__on_note_mode_button_value.subject = self._elements.note_mode_button
        self._Launchpad_Pro_MK3__on_chord_mode_button_value.subject = self._elements.chord_mode_button
        self._Launchpad_Pro_MK3__on_sequencer_mode_button_value.subject = self._elements.sequencer_mode_button
        self._Launchpad_Pro_MK3__on_record_arm_button_value.subject = self._elements.record_arm_button
        self._Launchpad_Pro_MK3__on_mute_button_value.subject = self._elements.mute_button
        self._Launchpad_Pro_MK3__on_solo_button_value.subject = self._elements.solo_button
        self._Launchpad_Pro_MK3__on_stop_clip_button_value.subject = self._elements.stop_clip_button
        # NOTE: set_user_mode_button is never called — the Pro has no User
        # hold-to-select; the components' None-safe gates stay inactive.

    def _create_session_layer(self):
        return super(Launchpad_Pro_MK3, self)._create_session_layer() + Layer(scene_launch_buttons="scene_launch_buttons")

    def _create_clip_copy(self):
        """Clip and scene copy-paste handlers — gesture is hold Shift (90)
        + tap clip/scene, identical semantics to the Mini's shift hold."""
        self._clip_copy = ClipCopyComponent(name="Clip_Copy")
        self._session.set_copy_handler(self._clip_copy)
        self._scene_copy = SceneCopyComponent(name="Scene_Copy")
        self._session.set_scene_copy_handler(self._scene_copy)
        shift = self._elements.shift_button
        self._session.set_modifier_button(shift, "copy_shift", clip_slots_only=True)
        self._session.set_modifier_button(shift, "copy_shift", clip_slots_only=False)

    def _create_edit_mode(self):
        """Standalone edit modifiers: no `edit` sub-mode on the Pro. The
        component stays enabled through session main mode; Clear/Duplicate
        drive set_delete_held/set_duplicate_held and is_active() only
        claims clip/scene presses while a modifier is held, so bare
        presses keep launching."""
        self._edit_mode = EditModeComponent(
            name="Edit_Mode",
            is_enabled=False,
            song=self.song,
            event_bus=self._event_bus,
            logger=self._log)
        self._edit_mode.set_standalone(True)
        self._edit_mode.set_shift_button(self._elements.shift_button)
        self._session.set_edit_mode_component(self._edit_mode)
        self._edit_mode.set_enabled(True)

    def _create_mixer_modes(self):
        """Track-select row (CC 101-108) modes, selected by the function
        row: Record Arm / Mute / Solo / Stop Clip (CC 1/2/3/8). Default =
        track select (with the Mini's arm-on-second-press strips). Pressing
        the active function again returns to track select. Volume/Pan/
        Sends/Device stay inert (button faders need the DAW fader layout).
        """
        self._mixer_modes = ModesComponent(name="Mixer_Modes",
          is_enabled=False,
          support_momentary_mode_cycling=False)
        row = self._elements.track_select_buttons
        self._mixer_modes.add_mode("track_select",
          (AddLayerMode(self._mixer, Layer(track_select_buttons=row))))
        self._mixer_modes.add_mode("arm",
          (AddLayerMode(self._mixer, Layer(arm_buttons=row))))
        self._mixer_modes.add_mode("mute",
          (AddLayerMode(self._mixer, Layer(mute_buttons=row))))
        self._mixer_modes.add_mode("solo",
          (AddLayerMode(self._mixer, Layer(solo_buttons=row))))
        self._mixer_modes.add_mode("stop",
          (AddLayerMode(self._session, Layer(stop_track_clip_buttons=row))))
        self._mixer_modes.selected_mode = "track_select"
        self._Launchpad_Pro_MK3__on_mixer_mode_changed.subject = self._mixer_modes
        self._mixer_modes.set_enabled(True)

    def _create_session_modes(self):
        self._session_overview = SessionOverviewComponent(name="Session_Overview",
          is_enabled=False,
          session_ring=(self._session_ring),
          enable_skinning=True,
          layer=Layer(button_matrix="clip_launch_matrix"))
        # No mode_button_color_control here — the Mini drove the Session
        # button color through a Mini-specific SysEx element; the Pro's
        # Session LED is written directly in _set_mode_button_lights.
        self._session_modes = SessionModesComponent(name="Session_Modes",
          is_enabled=False,
          layer=Layer(cycle_mode_button="session_mode_button"))
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

    def _create_transport(self):
        """Play/Stop on the dedicated Play button, session record on the
        dedicated Record button. Shift+Record = Capture MIDI (routed to the
        active sequencer's capture, or song-level capture in session).
        Active in every main mode."""
        self._transport = TransportComponent(name="Transport", is_enabled=False)
        self._transport.set_buttons(self._elements.play_button,
          self._elements.record_button)
        self._transport.set_shift_button(self._elements.shift_button)
        self._transport.set_capture_handler(self._capture_midi)
        self._transport.set_enabled(True)

    def _create_drum_sequencer(self):
        self._drum_group = None
        self._drum_step_sequencer = DrumStepSequencerComponent(name="Drum_Step_Sequencer",
          is_enabled=False,
          drum_group_component=self._drum_group,
          event_bus=self._event_bus,
          layer=Layer(grid_matrix="clip_launch_matrix"))
        self._drum_step_sequencer.set_control_buttons(self._elements.scene_launch_buttons_raw)
        # Native Pro mapping: these functions live on dedicated buttons
        # (Quantise, Clear/Duplicate, Shift, Shift+Record, Shift+Duplicate)
        # — free their scene slots. Only the cycle slot (4) stays.
        self._drum_step_sequencer.configure_slots(
            capture=None,
            quantize=None,
            duplicate_page=None,
            double_loop=None,
            shift=None,
            special_shift=None)

    def _create_drum_64_sequencer(self):
        """Single-pad 64-step variant — reached via the Shift+Sequencer
        picker panel. Capture/Quantize/Shift live on dedicated buttons;
        only the cycle slot (6) stays on the scene column."""
        self._drum_64_step_sequencer = DrumStep64SequencerComponent(
            name="Drum_64_Step_Sequencer",
            is_enabled=False,
            drum_group_component=self._drum_group,
            event_bus=self._event_bus,
            layer=Layer(grid_matrix="clip_launch_matrix"))
        self._drum_64_step_sequencer.set_control_buttons(
            self._elements.scene_launch_buttons_raw)
        self._drum_64_step_sequencer.configure_slots(
            capture=None, quantize=None, shift=None)

    def _create_drum_4_track_sequencer(self):
        """4-track × 16-step variant — reached via the Shift+Sequencer
        picker panel. Same dedicated-button slot config as drum_64."""
        self._drum_4_track_step_sequencer = DrumStep4TrackSequencerComponent(
            name="Drum_4_Track_Step_Sequencer",
            is_enabled=False,
            drum_group_component=self._drum_group,
            event_bus=self._event_bus,
            layer=Layer(grid_matrix="clip_launch_matrix"))
        self._drum_4_track_step_sequencer.set_control_buttons(
            self._elements.scene_launch_buttons_raw)
        self._drum_4_track_step_sequencer.configure_slots(
            capture=None, quantize=None, shift=None)

    def _create_melodic_sequencer(self):
        self._melodic_step_sequencer = MelodicStepSequencerComponent(name="Melodic_Step_Sequencer",
          is_enabled=False,
          event_bus=self._event_bus,
          layer=Layer(grid_matrix="clip_launch_matrix"))
        self._melodic_step_sequencer.set_control_buttons(self._elements.scene_launch_buttons_raw)
        # Capture/Quantize live on dedicated buttons → slots 0/1 act
        # directly as chromatic toggle / scale cycle, no shift needed.
        # The sequencer-shift LED slot is freed (Shift is a real button).
        self._melodic_step_sequencer.configure_slots(shift=None)
        self._melodic_step_sequencer.set_direct_slot_actions(True)

    def _create_chord_pad_mode(self):
        """8x8 chord-pad mode — on its dedicated Chord button (95). Scene
        slots keep the Mini layout (capture/key/scale/chord-type/inversion)."""
        self._chord_pad_mode = ChordPadComponent(name="Chord_Pad_Mode",
          is_enabled=False,
          event_bus=self._event_bus,
          layer=Layer(grid_matrix="clip_launch_matrix"))
        self._chord_pad_mode.set_control_buttons(self._elements.scene_launch_buttons_raw)

    def _create_variant_picker(self):
        """Shift+Sequencer → grid overlay panel with one band per drum
        variant. Picking a band switches the main mode; a plain Sequencer
        press cancels back to where the user came from."""
        self._variant_picker = DrumVariantPickerComponent(
            name="Drum_Variant_Picker",
            is_enabled=False,
            on_select=self._on_drum_variant_selected,
            logger=self._log,
            layer=Layer(grid_matrix="clip_launch_matrix"))

    def _create_main_modes(self):
        """Direct mode buttons — Session (93), Note (94) → melodic,
        Chord (95) → chord pads, Sequencer (97) → last drum variant
        (Shift+Sequencer → variant picker panel). Pressing the active
        mode's button returns to session. No hold-to-select, no cycling."""
        self._main_modes = ModesComponent(name="Main_Modes",
          is_enabled=False,
          enable_skinning=False,
          support_momentary_mode_cycling=False)
        self._main_modes.add_mode("session", None)
        self._main_modes.add_mode("drum_sequence", None)
        self._main_modes.add_mode("drum_64_sequence", None)
        self._main_modes.add_mode("drum_4_track_sequence", None)
        self._main_modes.add_mode("melodic_sequence", None)
        self._main_modes.add_mode("chord_mode", None)
        self._main_modes.add_mode(VARIANT_PICKER_MODE, None)
        self._main_modes.selected_mode = "session"
        self._Launchpad_Pro_MK3__on_main_mode_changed.subject = self._main_modes
        self._main_modes.set_enabled(True)

    def _create_background(self):
        """Swallow every dedicated button that isn't Layer-bound elsewhere
        so the elements stay connected (MIDI keeps flowing to the direct
        value listeners) and unhandled presses do nothing. Priority -1 so
        any real Layer (mixer modes on the track row, overview scene grab)
        wins while active."""
        self._background = NotifyingBackgroundComponent(name="Background",
          is_enabled=False,
          add_nop_listeners=True,
          layer=Layer(shift_button="shift_button",
          clear_button="clear_button",
          duplicate_button="duplicate_button",
          quantize_button="quantize_button",
          fixed_length_button="fixed_length_button",
          play_button="play_button",
          record_button="record_button",
          note_mode_button="note_mode_button",
          chord_mode_button="chord_mode_button",
          custom_mode_button="custom_mode_button",
          sequencer_mode_button="sequencer_mode_button",
          projects_button="projects_button",
          record_arm_button="record_arm_button",
          mute_button="mute_button",
          solo_button="solo_button",
          volume_button="volume_button",
          pan_button="pan_button",
          sends_button="sends_button",
          device_button="device_button",
          stop_clip_button="stop_clip_button",
          track_select_buttons="track_select_buttons",
          priority=-1))
        self._background.set_enabled(True)

    def _create_notification_subscribers(self):
        """Same event-bus plumbing as the Mini: status bar (always) + LP
        Notify M4L device (when present)."""
        self._notification_dispatcher = NotificationDispatcher(
            song=self.song, logger=self._log)
        self._status_bar_subscriber = StatusBarSubscriber(self.show_message)
        self._m4l_subscriber = M4LSubscriber(self._notification_dispatcher)
        self._event_bus.subscribe(self._status_bar_subscriber)
        self._event_bus.subscribe(self._m4l_subscriber)
        self._event_bus.subscribe(self._on_pin_event)

    def _on_pin_event(self, name, payload):
        if name in (Event.TRACK_PINNED, Event.TRACK_UNPINNED):
            self._set_mode_button_lights(self._main_modes.selected_mode)

    # ---- main modes -----------------------------------------------------

    @listens("selected_mode")
    def __on_main_mode_changed(self, mode):
        grid_takeover = mode in _SEQUENCER_MODES or mode == VARIANT_PICKER_MODE
        self._log("main mode changed: {}".format(mode))
        if mode in _DRUM_MODES:
            # A plain Sequencer press re-opens the variant last used.
            self._last_drum_variant = mode
        # Transport stays live in every main mode.
        self._transport.set_enabled(True)
        self._drum_step_sequencer.set_enabled(False)
        self._drum_64_step_sequencer.set_enabled(False)
        self._drum_4_track_step_sequencer.set_enabled(False)
        self._melodic_step_sequencer.set_enabled(False)
        self._chord_pad_mode.set_enabled(False)
        self._variant_picker.set_enabled(False)
        if grid_takeover:
            self._set_session_components_enabled(False)
            self._restore_clip_launch_matrix()
            if mode == VARIANT_PICKER_MODE:
                self._variant_picker.set_current_variant(self._last_drum_variant)
                self._variant_picker.set_enabled(True)
                active = None
            else:
                active = self._sequencer_for_mode(mode)
                if active is not None:
                    active.set_enabled(True)
                    # Sync the shift layer with the physical button — the
                    # mode may have changed while Shift was held (e.g.
                    # Shift+Sequencer → picker → variant) or released.
                    active.set_device_shift_held(self._is_shift_pressed())
                self.set_controlled_track(self.song.view.selected_track)
            self._request_midi_map_rebuild()
            self._emit(Event.MAIN_MODE_CHANGED, mode=mode)
            if active is not None:
                active.update()
        else:
            self._restore_clip_launch_matrix()
            self.release_controlled_track()
            self._set_session_components_enabled(True)
            self._request_midi_map_rebuild()
        self._set_mode_button_lights(mode)
        self._update_modifier_leds()
        self._update_mixer_function_leds()

    def _sequencer_for_mode(self, mode):
        if mode == "drum_sequence":
            return self._drum_step_sequencer
        if mode == "drum_64_sequence":
            return self._drum_64_step_sequencer
        if mode == "drum_4_track_sequence":
            return self._drum_4_track_step_sequencer
        if mode == "melodic_sequence":
            return self._melodic_step_sequencer
        if mode == "chord_mode":
            return self._chord_pad_mode
        return None

    def _in_sequencer_mode(self):
        return (hasattr(self, "_main_modes")
                and self._main_modes.selected_mode in _SEQUENCER_MODES)

    def _toggle_main_mode(self, mode):
        """Dedicated mode button press: switch to `mode`, or back to
        session when `mode` is already active."""
        self._main_modes.selected_mode = (
            "session" if self._main_modes.selected_mode == mode else mode)

    @listens("value")
    def __on_note_mode_button_value(self, value):
        if value:
            self._toggle_main_mode("melodic_sequence")

    @listens("value")
    def __on_chord_mode_button_value(self, value):
        if value:
            self._toggle_main_mode("chord_mode")

    @listens("value")
    def __on_sequencer_mode_button_value(self, value):
        """Sequencer (97). Plain press: open the last-used drum variant
        (press again → back to session). Shift+press: open the variant
        picker panel. Press while the picker is up: cancel back to the
        mode the picker was opened from."""
        if not value:
            return
        current = self._main_modes.selected_mode
        if current == VARIANT_PICKER_MODE:
            self._main_modes.selected_mode = (self._picker_return_mode
                                              or "session")
            self._picker_return_mode = None
            return
        if self._is_shift_pressed():
            self._picker_return_mode = current
            self._main_modes.selected_mode = VARIANT_PICKER_MODE
            return
        self._toggle_main_mode(self._last_drum_variant)

    def _on_drum_variant_selected(self, mode):
        """Callback from the picker panel — commit the chosen variant."""
        self._picker_return_mode = None
        self._main_modes.selected_mode = mode

    @listens("selected_track")
    def __on_selected_track_changed(self):
        if self._in_sequencer_mode():
            self.set_controlled_track(self.song.view.selected_track)

    # ---- session button (93): launch/overview + sequencer preview -------

    @listens("value")
    def __on_session_mode_button_value(self, value):
        """In sequencer modes the Session button is a return-to-session
        control with momentary-preview semantics (tap latches, hold
        previews and reverts). Shift+Session toggles the active
        sequencer's track pin. In session main mode this listener is a
        no-op — session_modes owns the button (overview double-click)."""
        if value:
            current = self._main_modes.selected_mode
            if current == VARIANT_PICKER_MODE:
                # Session press cancels the picker straight to session.
                self._picker_return_mode = None
                self._main_modes.selected_mode = "session"
                return
            if current in _SEQUENCER_MODES:
                if self._is_shift_pressed():
                    seq = self._sequencer_for_mode(current)
                    if seq is not None and hasattr(seq, "toggle_pin"):
                        pinned = seq.toggle_pin()
                        self._log("toggle_pin on {} → pinned={}".format(current, pinned))
                        return
                self._session_preview_press_time = time.time()
                self._session_preview_return_mode = current
                self._main_modes.selected_mode = "session"
            return
        if self._session_preview_press_time is None:
            return
        held = time.time() - self._session_preview_press_time
        self._session_preview_press_time = None
        return_mode = self._session_preview_return_mode
        self._session_preview_return_mode = None
        if held > SESSION_HOLD_THRESHOLD and return_mode is not None:
            self._main_modes.selected_mode = return_mode

    # ---- arrows ----------------------------------------------------------

    def _arrow_target(self):
        return self._sequencer_for_mode(self._main_modes.selected_mode)

    def _is_drum_mode(self):
        return self._main_modes.selected_mode in (
            "drum_sequence", "drum_64_sequence", "drum_4_track_sequence")

    @listens("value")
    def __on_up_button_value(self, value):
        if not value:
            return
        target = self._arrow_target()
        if target is None:
            return
        if self._is_drum_mode() and target.adjust_held_velocity(DRUM_VELOCITY_ARROW_STEP):
            return
        target.adjust_pitch_offset(12)

    @listens("value")
    def __on_down_button_value(self, value):
        if not value:
            return
        target = self._arrow_target()
        if target is None:
            return
        if self._is_drum_mode() and target.adjust_held_velocity(-DRUM_VELOCITY_ARROW_STEP):
            return
        target.adjust_pitch_offset(-12)

    @listens("value")
    def __on_left_button_value(self, value):
        if not value:
            return
        target = self._arrow_target()
        if target is None:
            return
        mode = self._main_modes.selected_mode
        if self._is_drum_mode():
            if target.nudge_held_notes(-1):
                return
            self._undo()
            return
        if mode == "melodic_sequence":
            target.nav_page(-1)
            return
        target.adjust_pitch_offset(-1)

    @listens("value")
    def __on_right_button_value(self, value):
        if not value:
            return
        target = self._arrow_target()
        if target is None:
            return
        mode = self._main_modes.selected_mode
        if self._is_drum_mode():
            if target.nudge_held_notes(1):
                return
            self._redo()
            return
        if mode == "melodic_sequence":
            target.nav_page(1)
            return
        target.adjust_pitch_offset(1)

    def _undo(self):
        self._edit_mode.undo()

    def _redo(self):
        self._edit_mode.redo()

    # ---- dedicated modifiers: Shift / Clear / Duplicate / Quantise -------

    def _is_shift_pressed(self):
        try:
            return self._elements.shift_button.is_pressed()
        except Exception:
            return False

    @listens("value")
    def __on_shift_button_value(self, value):
        """Shift (90), pure hold — no taps, no double-taps, no lock.
        Session: copy modifier (clip_slot_with_copy checks is_pressed at
        clip-press time; clipboards clear on release). Sequencer modes:
        drives the shift-gated layer via set_device_shift_held."""
        held = bool(value)
        if self._in_sequencer_mode():
            target = self._sequencer_for_mode(self._main_modes.selected_mode)
            if target is not None:
                target.set_device_shift_held(held)
        if not held:
            self._clip_copy.clear_clipboard()
            self._scene_copy.clear_clipboard()
        self._update_modifier_leds()

    @listens("value")
    def __on_clear_button_value(self, value):
        """Clear (60) hold-modifier. Session: delete clip/scene on tap
        (EditModeComponent). Drum mode: the special-shift 'delete' action
        layer (steps / pads / pages / scene-row selectors)."""
        held = bool(value)
        if held:
            if self._in_sequencer_mode():
                target = self._sequencer_for_mode(self._main_modes.selected_mode)
                if target is not None and hasattr(target, "set_action_modifier"):
                    target.set_action_modifier("delete", True)
            else:
                self._edit_mode.set_delete_held(True)
        else:
            # Release routes everywhere; disengaged targets no-op. Covers
            # the mode-changed-mid-hold edge.
            if hasattr(self._drum_step_sequencer, "set_action_modifier"):
                self._drum_step_sequencer.set_action_modifier("delete", False)
            self._edit_mode.set_delete_held(False)
        self._update_modifier_leds()

    @listens("value")
    def __on_duplicate_button_value(self, value):
        """Duplicate (50) hold-modifier. Session: duplicate clip/scene on
        tap. Drum mode: special-shift 'duplicate' layer (capture source,
        apply to target). Shift+Duplicate in drum mode: double loop."""
        held = bool(value)
        if held:
            if self._in_sequencer_mode():
                target = self._sequencer_for_mode(self._main_modes.selected_mode)
                if target is None:
                    return
                if self._is_shift_pressed() and hasattr(target, "double_loop"):
                    target.double_loop()
                    return
                if hasattr(target, "set_action_modifier"):
                    target.set_action_modifier("duplicate", True)
            else:
                self._edit_mode.set_duplicate_held(True)
        else:
            if hasattr(self._drum_step_sequencer, "set_action_modifier"):
                self._drum_step_sequencer.set_action_modifier("duplicate", False)
            self._edit_mode.set_duplicate_held(False)
        self._update_modifier_leds()

    @listens("value")
    def __on_quantize_button_value(self, value):
        """Quantise (40): quantize the active sequencer's selection (held
        steps, else pad/clip scope). Session: reserved in v1 (clip
        quantize is the natural future assignment)."""
        if not value:
            return
        if self._in_sequencer_mode():
            target = self._sequencer_for_mode(self._main_modes.selected_mode)
            if target is not None and hasattr(target, "quantize_selected"):
                target.quantize_selected()

    def _capture_midi(self):
        """Shift+Record. Sequencer modes: the active sequencer's capture
        (re-resolves clip, jumps to the captured page). Session: song-level
        capture with the same notification."""
        target = self._sequencer_for_mode(self._main_modes.selected_mode)
        if target is not None and hasattr(target, "capture_midi"):
            target.capture_midi()
            return
        try:
            if getattr(self.song, "can_capture_midi", False):
                self.song.capture_midi()
                self._emit(Event.MIDI_CAPTURED, ok=True)
            else:
                self._emit(Event.MIDI_CAPTURED, ok=False, reason="nothing to capture")
        except Exception as exc:
            self._log("capture failed: {}".format(exc))
            self._emit(Event.MIDI_CAPTURED, ok=False, reason="error")

    # ---- mixer function row (CC 1/2/3/8) ---------------------------------

    def _handle_function_button(self, value, mode_name, shift_action=None):
        """Shared press handler for the function row. Shift+press fires the
        combo action (undo/redo/stop-all) in any main mode; a bare press
        toggles the track-row mode, session main mode only."""
        if not value:
            return
        if self._is_shift_pressed():
            if shift_action is not None:
                shift_action()
            return
        if self._main_modes.selected_mode != "session":
            return
        current = self._mixer_modes.selected_mode
        self._mixer_modes.selected_mode = (
            "track_select" if current == mode_name else mode_name)

    @listens("value")
    def __on_record_arm_button_value(self, value):
        self._handle_function_button(value, "arm", shift_action=self._undo)

    @listens("value")
    def __on_mute_button_value(self, value):
        self._handle_function_button(value, "mute", shift_action=self._redo)

    @listens("value")
    def __on_solo_button_value(self, value):
        self._handle_function_button(value, "solo")

    @listens("value")
    def __on_stop_clip_button_value(self, value):
        self._handle_function_button(value, "stop",
                                     shift_action=self._edit_mode.stop_all_clips)

    @listens("selected_mode")
    def __on_mixer_mode_changed(self, _mode):
        self._update_mixer_function_leds()

    # ---- LED rendering (raw CC writes, Programmer mode) -------------------

    def _update_mixer_function_leds(self):
        """Function-row LEDs: idle dim, bright when that row mode is on.
        Dark outside session main mode (the row is inert there)."""
        in_session = (hasattr(self, "_main_modes")
                      and self._main_modes.selected_mode == "session")
        mode = (self._mixer_modes.selected_mode
                if hasattr(self, "_mixer_modes") else "track_select")
        table = (
            (RECORD_ARM_BUTTON_CC, "arm", LED_ARM_ACTIVE, LED_ARM_IDLE),
            (MUTE_BUTTON_CC, "mute", LED_MUTE_ACTIVE, LED_MUTE_IDLE),
            (SOLO_BUTTON_CC, "solo", LED_SOLO_ACTIVE, LED_SOLO_IDLE),
            (STOP_CLIP_BUTTON_CC, "stop", LED_STOP_ACTIVE, LED_STOP_IDLE),
        )
        for cc, mode_name, active, idle in table:
            if not in_session:
                self._send_programmer_cc(cc, LED_OFF)
            else:
                self._send_programmer_cc(cc, active if mode == mode_name else idle)

    def _update_modifier_leds(self):
        """Shift/Clear/Duplicate/Quantise LEDs: idle dim where the button
        does something in the current mode, bright while held, dark where
        inert. Availability follows the active component's capabilities
        (e.g. drum_64 has quantize but no delete/duplicate action layer)."""
        mode = (self._main_modes.selected_mode
                if hasattr(self, "_main_modes") else "session")
        in_session = mode == "session"
        target = self._sequencer_for_mode(mode)
        shift_held = self._is_shift_pressed()
        self._send_programmer_cc(
            SHIFT_BUTTON_CC, LED_SHIFT_HELD if shift_held else LED_SHIFT_IDLE)

        def modifier_led(button, cc, held_color, idle_color, available):
            if not available:
                self._send_programmer_cc(cc, LED_OFF)
                return
            try:
                held = button.is_pressed()
            except Exception:
                held = False
            self._send_programmer_cc(cc, held_color if held else idle_color)

        clear_dup_available = in_session or (
            target is not None and hasattr(target, "set_action_modifier"))
        modifier_led(self._elements.clear_button, CLEAR_BUTTON_CC,
                     LED_CLEAR_HELD, LED_CLEAR_IDLE, clear_dup_available)
        modifier_led(self._elements.duplicate_button, DUPLICATE_BUTTON_CC,
                     LED_DUPLICATE_HELD, LED_DUPLICATE_IDLE, clear_dup_available)
        quantize_available = (target is not None
                              and hasattr(target, "quantize_selected"))
        self._send_programmer_cc(
            QUANTIZE_BUTTON_CC,
            LED_QUANTIZE_IDLE if quantize_available else LED_OFF)

    def _session_button_color_for_mode(self, mode):
        if mode in _SEQUENCER_MODES:
            seq = self._sequencer_for_mode(mode)
            if seq is not None and hasattr(seq, "is_pinned") and seq.is_pinned():
                return LED_SESSION_PINNED
            return LED_SESSION_DIM
        return LED_SESSION

    def _set_mode_button_lights(self, mode):
        """Top-row mode buttons + arrows. Active mode bright, available
        modes dim grey, Session per its pinned/preview logic."""
        self._send_programmer_cc(SESSION_BUTTON_CC,
                                 self._session_button_color_for_mode(mode))
        self._send_programmer_cc(
            NOTE_BUTTON_CC,
            LED_MELODIC if mode == "melodic_sequence" else LED_MODE_IDLE)
        self._send_programmer_cc(
            CHORD_BUTTON_CC,
            LED_CHORD if mode == "chord_mode" else LED_MODE_IDLE)
        self._send_programmer_cc(
            SEQUENCER_BUTTON_CC,
            LED_SEQUENCER if mode in _DRUM_MODES + (VARIANT_PICKER_MODE,)
            else LED_MODE_IDLE)
        if mode in _SEQUENCER_MODES:
            self._send_programmer_cc(UP_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(DOWN_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(LEFT_BUTTON_CC, LED_ARROW_SEMITONE)
            self._send_programmer_cc(RIGHT_BUTTON_CC, LED_ARROW_SEMITONE)
        else:
            self._send_programmer_cc(UP_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(DOWN_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(LEFT_BUTTON_CC, LED_OFF)
            self._send_programmer_cc(RIGHT_BUTTON_CC, LED_OFF)

    def _clear_inert_button_leds(self):
        for cc in INERT_BUTTON_CCS:
            self._send_programmer_cc(cc, LED_OFF)

    # ---- shared infrastructure (mirrors the Mini) -------------------------

    def _log(self, message):
        try:
            self._c_instance.log_message("[Launchpad Pro MK3] {}".format(message))
        except Exception:
            pass

    def _emit(self, event_name, **payload):
        if self._event_bus is not None:
            self._event_bus.emit(event_name, **payload)

    def _set_session_components_enabled(self, enabled):
        self._session.set_enabled(enabled)
        self._session_navigation.set_enabled(enabled)
        self._session_modes.set_enabled(enabled)
        self._mixer_modes.set_enabled(enabled)
        self._edit_mode.set_enabled(enabled)

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
            self._send_midi(sysex.STD_MSG_HEADER + (DEVICE_SYSEX_ID, command_byte) + tuple(payload) + (sysex.SYSEX_END_BYTE,))
        except Exception:
            pass

    def _send_programmer_cc(self, identifier, value):
        try:
            self._send_midi((MIDI_CC_STATUS + PROGRAMMER_LED_CHANNEL, identifier, value), optimized=False)
        except Exception:
            pass
