# Launchpad Mini MK3 Control Surface Script - Based on 12.0.1 with select mode, clip copy, and arm toggle
from __future__ import absolute_import, print_function, unicode_literals
import time
from ableton.v2.base import listens
from ableton.v2.control_surface import Layer
from ableton.v2.control_surface.components import SessionOverviewComponent
from ableton.v2.control_surface.mode import AddLayerMode, EnablingMode, ModesComponent
from novation import sysex
from novation.novation_base import NovationBase
from novation.session_modes import SessionModesComponent
from .channel_strip_with_arm_toggle import ChannelStripComponentWithArmToggle
from .clip_copy_component import ClipCopyComponent
from .chord_pad_mode import ChordPadComponent
from .device_profile import (
    DEVICE_FAMILY_CODE,
    DEVICE_SYSEX_ID,
    DOWN_BUTTON_CC,
    DRUMS_BUTTON_CC,
    EXTERNAL_FEEDBACK_ON,
    INTERNAL_FEEDBACK_OFF,
    KEYS_BUTTON_CC,
    LED_ARROW_OCTAVE,
    LED_ARROW_SEMITONE,
    LED_CHORD,
    LED_USER_HELD,
    LED_FEEDBACK_COMMAND_BYTE,
    LED_MELODIC,
    LED_OFF,
    LED_SEQUENCER,
    LED_SESSION,
    LED_SESSION_DIM,
    LED_SESSION_PINNED,
    LEFT_BUTTON_CC,
    PROGRAMMER_MODE_COMMAND_BYTE,
    PROGRAMMER_MODE_OFF,
    PROGRAMMER_MODE_ON,
    RIGHT_BUTTON_CC,
    SESSION_BUTTON_CC,
    SLEEP_COMMAND_BYTE,
    SLEEP_OFF,
    UP_BUTTON_CC,
    USER_BUTTON_CC,
)
from .drum_4_track_step_sequencer import DrumStep4TrackSequencerComponent
from .drum_64_step_sequencer import DrumStep64SequencerComponent
from .drum_step_sequencer import DrumStepSequencerComponent
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


# A press shorter than this on the shift button (slot 7 / stop-solo-mute /
# scene_launch_buttons_raw[7]) qualifies as a "quick tap". Two such taps
# within SHIFT_DOUBLE_TAP_WINDOW (measured release-to-release) toggle the
# shift-lock state in sequencer modes. A long press (> threshold) is a
# momentary hold and resets the double-tap detector — it does NOT toggle.
SHIFT_LOCK_TAP_THRESHOLD = 0.3
SHIFT_DOUBLE_TAP_WINDOW = 0.35
# Session-button hold-to-preview threshold while in drum_sequence main mode.
# Below: tap → latch session mode. Above: hold → revert to drum_sequence on release.
SESSION_HOLD_THRESHOLD = 0.3
# Velocity delta applied per Up/Down arrow press in drum_sequence mode while
# a step pad is held. 16 ticks span the 0..127 range — coarse enough to move
# quickly, fine enough to land precisely with one or two extra presses.
DRUM_VELOCITY_ARROW_STEP = 8


# Stop-solo-mute sub-modes that participate in the single-tap cycle on
# the shift button. `edit` is registered as the 5th mode but
# *intentionally absent here* — it is reached only via a double-tap and
# exited via a single tap (which restores `_pre_edit_mode`).
# DISABLED (ergonomic pass) — stop/solo/mute removed from the cycle. The
# tap on slot 7 still goes through `_cycle_stop_solo_mute` but with a
# single-item list it's effectively a no-op. To re-enable: put back
# ("select", "stop", "solo", "mute") AND uncomment the add_mode calls in
# _create_stop_solo_mute_modes.
_STOP_SOLO_MUTE_CYCLE = ("select",)

# Scene-button → main-mode mapping for the hold-User mode selector. Top
# down: drum / drum 64 / drum 4-track / melodic / chord. Scenes 5-6 are
# inert; scene 7 is the shift / stop-solo-mute and is left alone.
_MODE_SELECTOR_SLOTS = {
    0: "drum_sequence",
    1: "melodic_sequence",
    # DISABLED (ergonomic pass): re-enable by uncommenting alongside the
    # matching add_mode call in _create_main_modes and the LED entry below.
    # Slot positions reflect the active set above — when re-enabling, pick
    # any free slot.
    # 2: "drum_64_sequence",
    # 3: "drum_4_track_sequence",
    # 4: "chord_mode",
}

# Per-mode (active, dim) selector colors. Active = bright (current mode),
# dim = half (other modes). Skipping a mode in the dict isn't supported —
# every value of `_MODE_SELECTOR_SLOTS` must have an entry here.
_MODE_SELECTOR_LED_COLORS = {
    "drum_sequence":         ("Mode.Selector.Drum",        "Mode.Selector.DrumDim"),
    # DISABLED (ergonomic pass) — pair with _MODE_SELECTOR_SLOTS above.
    # "drum_64_sequence":      ("Mode.Selector.Drum64",      "Mode.Selector.Drum64Dim"),
    # "drum_4_track_sequence": ("Mode.Selector.Drum4Track",  "Mode.Selector.Drum4TrackDim"),
    "melodic_sequence":      ("Mode.Selector.Melodic",     "Mode.Selector.MelodicDim"),
    # "chord_mode":            ("Mode.Selector.Chord",       "Mode.Selector.ChordDim"),
}

# Shift-button LED color per sub-mode while in session main mode. With
# `cycle_mode_button` removed from `_stop_solo_mute_modes`' Layer (so we
# can suppress the auto-cycle on the first tap of a double-tap), we have
# to drive the LED ourselves on mode change. Sequencer modes drive the
# same button separately via "Control.Shift" — leave those alone.
_STOP_SOLO_MUTE_LED_COLORS = {
    "select": "Mixer.TrackSelected",
    "stop":   "Session.StopClip",
    "solo":   "Mixer.SoloOn",
    "mute":   "Mixer.MuteOff",
    "edit":   "EditMode.Cycle",
}


class Launchpad_Mini_MK3(NovationBase):
    model_family_code = DEVICE_FAMILY_CODE
    element_class = Elements
    session_class = SessionComponentWithCopy
    channel_strip_class = ChannelStripComponentWithArmToggle
    skin = skin

    def __init__(self, *a, **k):
        self._last_layout_byte = sysex.SESSION_LAYOUT_BYTE
        # Tracks a session-button press that started while in a sequencer
        # main mode. None when not held-from-sequencer; a time.time() value
        # while held. Used to distinguish a tap (latch session) from a hold
        # (preview + revert). _session_preview_return_mode remembers which
        # sequencer to go back to on long-hold release ("drum_sequence" or
        # "melodic_sequence").
        self._session_preview_press_time = None
        self._session_preview_return_mode = None
        # Shift button lock state. While locked, "effective shift" stays on
        # without the user needing to physically hold the button. Toggled by
        # a double-tap (two quick presses within SHIFT_DOUBLE_TAP_WINDOW) and
        # only in sequencer main modes — in session mode the shift button
        # cycles stop-solo-mute and would clash with a tap-based toggle.
        # Session-mode shift state (slot 7). Tracks press/release of the
        # stop-solo-mute / shift button used to cycle sub-modes and enter
        # edit mode via double-tap. No longer drives sequencer shift.
        self._session_shift_press_time = None
        self._session_shift_last_tap_release_time = None
        # Sequencer-mode shift state (slot 5 — relocated from slot 7).
        # While the button is held (or shift-locked is on), sequencers
        # expose their shift-gated controls (loop range picker, grid
        # resolutions, triplet cells, page selector row in melodic, ...).
        self._seq_shift_press_time = None
        self._seq_shift_last_tap_release_time = None
        self._shift_locked = False
        # Sub-mode we were in when edit was entered, so a single tap on
        # shift can return there. None when not in edit mode.
        self._pre_edit_mode = None
        # True while the User button is physically held down. While True,
        # scene_launch_buttons_raw[0..4] render the mode selector and tap
        # presses switch the main mode. SceneComponentWithCopy + every
        # sequencer's control-button listener check the user button's
        # is_pressed() state to short-circuit their normal scene-button
        # behavior.
        self._user_held = False
        # Whether the user actually tapped a scene to pick a mode during
        # the current hold. Release behavior depends on this:
        #   - tapped → stay in whichever mode the user committed to
        #   - not tapped → bounce back to session (release without a pick
        #     acts as "exit to session" — that's also how you back out of
        #     a sequencer mode without committing to another one).
        self._mode_selected_during_hold = False
        # Direct value listeners attached to scene_launch_buttons_raw[0..4]
        # while the User button is held. Stored so we can detach cleanly
        # on release without touching the sequencer's own listeners.
        self._mode_selector_listeners = []
        # Notification plumbing: created early so components can take the
        # bus reference at construction time in _create_components.
        # Setting _event_bus = None here would make every _emit() a no-op
        # — handy kill switch if you want to mute all notifications.
        self._event_bus = EventBus(logger=self._log)
        self._notification_dispatcher = None  # built in _create_notification_subscribers
        self._status_bar_subscriber = None
        self._m4l_subscriber = None
        (super(Launchpad_Mini_MK3, self).__init__)(*a, **k)

    def on_identified(self, midi_bytes):
        self._enter_programmer_mode()
        self.set_feedback_channels([AUDITION_CHANNEL])
        super(Launchpad_Mini_MK3, self).on_identified(midi_bytes)

    def disconnect(self):
        try:
            if self._notification_dispatcher is not None:
                self._notification_dispatcher.disconnect()
        except Exception:
            pass
        try:
            self._exit_programmer_mode()
        finally:
            super(Launchpad_Mini_MK3, self).disconnect()

    def can_lock_to_devices(self):
        return False

    def _create_components(self):
        super(Launchpad_Mini_MK3, self)._create_components()
        self._create_notification_subscribers()
        self._create_background()
        self._create_clip_copy()
        # Edit mode must exist before _create_stop_solo_mute_modes so it
        # can be registered as the 5th sub-mode and propagated to every
        # clip slot / scene.
        self._create_edit_mode()
        self._create_stop_solo_mute_modes()
        self._create_session_modes()
        self._create_transport()
        self._create_drum_sequencer()
        self._create_drum_64_sequencer()
        self._create_drum_4_track_sequencer()
        self._create_melodic_sequencer()
        self._create_chord_pad_mode()
        self._create_main_modes()
        self._Launchpad_Mini_MK3__on_layout_switch_value.subject = self._elements.layout_switch
        self._Launchpad_Mini_MK3__on_selected_track_changed.subject = self.song.view
        self._Launchpad_Mini_MK3__on_session_mode_button_value.subject = self._elements.session_mode_button
        self._Launchpad_Mini_MK3__on_up_button_value.subject = self._elements.up_button
        self._Launchpad_Mini_MK3__on_down_button_value.subject = self._elements.down_button
        self._Launchpad_Mini_MK3__on_left_button_value.subject = self._elements.left_button
        self._Launchpad_Mini_MK3__on_right_button_value.subject = self._elements.right_button
        self._Launchpad_Mini_MK3__on_user_mode_button_value.subject = self._elements.user_mode_button
        # Propagate the user_mode_button reference into every component that
        # owns scene-launch presses, so each can short-circuit while the
        # button is held (mode selector takes priority over launch / capture
        # / quantize / etc.).
        self._session.set_user_mode_button(self._elements.user_mode_button)
        self._drum_step_sequencer.set_user_mode_button(self._elements.user_mode_button)
        self._drum_64_step_sequencer.set_user_mode_button(self._elements.user_mode_button)
        self._drum_4_track_step_sequencer.set_user_mode_button(self._elements.user_mode_button)
        self._melodic_step_sequencer.set_user_mode_button(self._elements.user_mode_button)
        self._chord_pad_mode.set_user_mode_button(self._elements.user_mode_button)

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

    def _create_edit_mode(self):
        """5th stop-solo-mute sub-mode: owns the bottom row of the 8x8
        grid while active, exposes delete/duplicate/move modifier pads
        on slots 5/6/7. Reached via double-tap on shift in session main
        mode; exited via single tap (see __on_shift_button_value)."""
        self._edit_mode = EditModeComponent(
            name="Edit_Mode",
            is_enabled=False,
            song=self.song,
            event_bus=self._event_bus,
            logger=self._log)

    def _create_stop_solo_mute_modes(self):
        self._shift_button = self._elements.scene_launch_buttons_raw[7]
        # NOTE: cycle_mode_button is intentionally NOT in the Layer.
        # Removing it lets us suppress the auto-cycle on the first tap
        # of a double-tap (which would otherwise produce two visible
        # mode flashes before landing on edit). The shift LED is driven
        # manually in __on_stop_solo_mute_mode_changed.
        self._stop_solo_mute_modes = ModesComponent(name="Stop_Solo_Mute_Modes",
          is_enabled=False,
          support_momentary_mode_cycling=False)
        bottom_row = self._elements.clip_launch_matrix.submatrix[:, 7:8]
        # Mode 1: Select (Arm/Select)
        self._stop_solo_mute_modes.add_mode("select",
          (AddLayerMode(self._mixer, Layer(track_select_buttons=bottom_row))))
        # DISABLED (ergonomic pass): Stop / Solo / Mute removed from the
        # cycle. Edit mode is still reachable via double-tap on shift —
        # registered below. Re-enable by uncommenting these add_mode
        # calls AND restoring "stop"/"solo"/"mute" in _STOP_SOLO_MUTE_CYCLE.
        # # Mode 2: Stop
        # self._stop_solo_mute_modes.add_mode("stop",
        #   (AddLayerMode(self._session, Layer(stop_track_clip_buttons=bottom_row))))
        # # Mode 3: Solo
        # self._stop_solo_mute_modes.add_mode("solo",
        #   (AddLayerMode(self._mixer, Layer(solo_buttons=bottom_row))))
        # # Mode 4: Mute
        # self._stop_solo_mute_modes.add_mode("mute",
        #   (AddLayerMode(self._mixer, Layer(mute_buttons=bottom_row))))
        # Mode 5: Edit (NOT in single-tap cycle — reached via double-tap).
        # The edit component takes ownership of the full bottom row while
        # active so the user sees red/green/blue modifier pads on slots
        # 5/6/7 and dim pads on slots 0-4. EnablingMode is required because
        # AddLayerMode only binds/unbinds the Layer — without it,
        # EditModeComponent stays is_enabled=False and ignores presses
        # while drawing nothing on the bottom row.
        self._stop_solo_mute_modes.add_mode("edit",
          (EnablingMode(self._edit_mode),
           AddLayerMode(self._edit_mode, Layer(modifier_matrix=bottom_row))))
        self._stop_solo_mute_modes.selected_mode = "select"
        # Configure shift button for clip copy (clip slots only)
        self._session.set_modifier_button(self._shift_button, "copy_shift", clip_slots_only=True)
        # Configure shift button for scene copy (scenes only)
        self._session.set_modifier_button(self._shift_button, "copy_shift", clip_slots_only=False)
        # Propagate edit-mode reference to every clip slot and scene so
        # presses can short-circuit the launch / copy paths and route to
        # the edit-mode handler when active.
        self._session.set_edit_mode_component(self._edit_mode)
        # Plumb the shift button into edit mode so its Undo pad (slot 7)
        # can detect a shift-held tap and dispatch redo instead of undo.
        self._edit_mode.set_shift_button(self._shift_button)
        self._Launchpad_Mini_MK3__on_shift_button_value.subject = self._shift_button
        # Slot 5 = sequencer-mode shift modifier (moved from slot 7).
        # In session mode this same button is just a scene launch button.
        self._seq_shift_button = self._elements.scene_launch_buttons_raw[5]
        self._Launchpad_Mini_MK3__on_sequencer_shift_button_value.subject = self._seq_shift_button
        self._Launchpad_Mini_MK3__on_stop_solo_mute_mode_changed.subject = self._stop_solo_mute_modes
        self._stop_solo_mute_modes.set_enabled(True)
        # Apply the initial LED color (cycle_mode_button no longer does
        # this for us).
        self._update_shift_button_led()

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
        """Play/Stop on Drums button, Session Record on Keys button.

        Active in every main mode (session, drum_sequence, melodic_sequence)
        — global transport is useful regardless of what's on the grid. The
        buttons remain in the background layer for their normal nop handling;
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
          event_bus=self._event_bus,
          layer=Layer(grid_matrix="clip_launch_matrix"))
        self._drum_step_sequencer.set_control_buttons(self._elements.scene_launch_buttons_raw)

    def _create_drum_64_sequencer(self):
        """Single-pad 64-step sequencer. Shares the drum_group with the regular
        drum sequencer (instantiated above) so selecting a pad here would also
        update Live's view-selected drum pad."""
        self._drum_64_step_sequencer = DrumStep64SequencerComponent(
            name="Drum_64_Step_Sequencer",
            is_enabled=False,
            drum_group_component=self._drum_group,
            event_bus=self._event_bus,
            layer=Layer(grid_matrix="clip_launch_matrix"))
        self._drum_64_step_sequencer.set_control_buttons(
            self._elements.scene_launch_buttons_raw)

    def _create_drum_4_track_sequencer(self):
        """4-track × 16-step sequencer. 4 drum-rack pads simultaneously,
        each on 2 rows. Shares the drum_group with the other drum
        sequencers so pad selection propagates to Live's view."""
        self._drum_4_track_step_sequencer = DrumStep4TrackSequencerComponent(
            name="Drum_4_Track_Step_Sequencer",
            is_enabled=False,
            drum_group_component=self._drum_group,
            event_bus=self._event_bus,
            layer=Layer(grid_matrix="clip_launch_matrix"))
        self._drum_4_track_step_sequencer.set_control_buttons(
            self._elements.scene_launch_buttons_raw)

    def _create_melodic_sequencer(self):
        self._melodic_step_sequencer = MelodicStepSequencerComponent(name="Melodic_Step_Sequencer",
          is_enabled=False,
          event_bus=self._event_bus,
          layer=Layer(grid_matrix="clip_launch_matrix"))
        self._melodic_step_sequencer.set_control_buttons(self._elements.scene_launch_buttons_raw)

    def _create_chord_pad_mode(self):
        """8x8 chord-pad mode. Each pad triggers a single root note via the
        usual audition translation. For "press one pad = full chord", drop
        Live's stock Chord MIDI effect on the armed track (or listen to
        CHORD_TRIGGERED events from an M4L companion). See
        chord_pad_mode.ChordPadComponent.__doc__ for the rationale."""
        self._chord_pad_mode = ChordPadComponent(name="Chord_Pad_Mode",
          is_enabled=False,
          event_bus=self._event_bus,
          layer=Layer(grid_matrix="clip_launch_matrix"))
        self._chord_pad_mode.set_control_buttons(self._elements.scene_launch_buttons_raw)

    def _create_main_modes(self):
        # NOTE: cycle_mode_button is intentionally NOT bound to the user
        # button. The User button is now a hold-to-show selector — press
        # reveals the mode buttons on scene_launch_buttons_raw[0..4], tap
        # a scene switches mode (or returns to session if tapping the
        # currently-active mode). See __on_user_mode_button_value.
        self._main_modes = ModesComponent(name="Main_Modes",
          is_enabled=False,
          enable_skinning=False,
          support_momentary_mode_cycling=False)
        self._main_modes.add_mode("session", None)
        self._main_modes.add_mode("drum_sequence", None)
        # DISABLED (ergonomic pass) — components still constructed in
        # _create_components so the code stays alive; just no UI path here.
        # self._main_modes.add_mode("drum_64_sequence", None)
        # self._main_modes.add_mode("drum_4_track_sequence", None)
        self._main_modes.add_mode("melodic_sequence", None)
        # self._main_modes.add_mode("chord_mode", None)
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

    def _create_notification_subscribers(self):
        """Wire the event bus to the status bar (always) and the LP Notify
        M4L device (when present). Each subscriber is independent: muting
        one or both has no effect on the rest of the script — components
        emit semantic events regardless of who's listening.

        To kill all M4L notifications, skip the M4LSubscriber subscribe()
        call below. To go full silent (no status bar either), skip the
        StatusBarSubscriber too — components emit into the void.
        """
        # M4L dispatcher: discovers the "LP Notify" device on any track and
        # writes to its exposed parameters. No-ops if device absent.
        self._notification_dispatcher = NotificationDispatcher(
            song=self.song, logger=self._log)
        self._status_bar_subscriber = StatusBarSubscriber(self.show_message)
        self._m4l_subscriber = M4LSubscriber(self._notification_dispatcher)
        self._event_bus.subscribe(self._status_bar_subscriber)
        self._event_bus.subscribe(self._m4l_subscriber)
        # Refresh the Session button LED when a sequencer's pin state changes.
        # The pin can flip either from the user gesture (toggle_pin) or from
        # the sequencer auto-clearing it (e.g., pinned track removed).
        self._event_bus.subscribe(self._on_pin_event)

    def _on_pin_event(self, name, payload):
        if name in (Event.TRACK_PINNED, Event.TRACK_UNPINNED):
            self._set_mode_button_lights(self._main_modes.selected_mode)

    @listens("selected_mode")
    def __on_main_mode_changed(self, mode):
        # "Grid-takeover" modes — anything that owns the 8x8 grid for its
        # own UI and therefore needs session components disabled. Chord
        # mode joins this set even though it's not a sequencer per se;
        # the takeover semantics are identical (audition translations,
        # controlled track, mode-button lights).
        grid_takeover = mode in (
            "drum_sequence", "drum_64_sequence", "drum_4_track_sequence",
            "melodic_sequence", "chord_mode")
        self._log("main mode changed: {}".format(mode))
        # Transport (Drums=Play, Keys=Record) stays live in every main mode;
        # play/record are useful while sequencing as well as in session.
        self._transport.set_enabled(True)
        # Always disable every sequencer + chord mode first — only re-enable
        # the active one below. Avoids two grid owners fighting for the same
        # button matrix when cycling through modes quickly.
        self._drum_step_sequencer.set_enabled(False)
        self._drum_64_step_sequencer.set_enabled(False)
        self._drum_4_track_step_sequencer.set_enabled(False)
        self._melodic_step_sequencer.set_enabled(False)
        self._chord_pad_mode.set_enabled(False)
        if grid_takeover:
            self._set_session_components_enabled(False)
            self._restore_clip_launch_matrix()
            active = self._sequencer_for_mode(mode)
            if active is not None:
                active.set_enabled(True)
            self.set_controlled_track(self.song.view.selected_track)
            self._request_midi_map_rebuild()
            self._set_mode_button_lights(mode)
            self._emit(Event.MAIN_MODE_CHANGED, mode=mode)
            if active is not None:
                active.update()
        else:
            self._restore_clip_launch_matrix()
            self.release_controlled_track()
            self._set_session_components_enabled(True)
            self._request_midi_map_rebuild()
            self._set_mode_button_lights(mode)
            # Sequencer left its own color on the shift button — restore
            # the sub-mode color now that session owns it again.
            self._update_shift_button_led()

    def _sequencer_for_mode(self, mode):
        # Naming kept "_sequencer_for_mode" for backwards compat with all
        # arrow-button call sites; chord_mode plugs in here as just
        # another grid-takeover component since it implements the same
        # adjust_pitch_offset / adjust_held_velocity / nudge_held_notes
        # surface (with the held/nudge variants returning False).
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

    @listens("selected_track")
    def __on_selected_track_changed(self):
        if hasattr(self, "_main_modes") and self._main_modes.selected_mode in (
                "drum_sequence", "drum_64_sequence",
                "drum_4_track_sequence", "melodic_sequence", "chord_mode"):
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
    def __on_user_mode_button_value(self, value):
        """User button = hold-to-show mode selector.

        Press: render the 5 sequencer/chord modes on scene_launch_buttons_raw
        slots 0..4 (active = bright, others = half) and attach direct value
        listeners so a scene tap switches mode. Tap on the currently-active
        mode returns to session. Scenes 5/6 stay dim; scene 7 (shift) is
        untouched.

        Release: detach the temporary listeners and re-render whichever
        component owns the scene buttons in the current main mode (session
        re-renders via session.update(); sequencers via their own
        _update_control_leds()).

        Components (SessionComponentWithCopy, every sequencer, chord pad)
        check user_mode_button.is_pressed() at the start of their scene
        press handler to short-circuit normal behavior during the hold.
        That keeps a tap on scene 0 from also launching scene 0 (in session)
        or firing Capture MIDI (in drum_sequence). The cost of the short
        check is paid only on scene presses, which are rare.
        """
        if value:
            self._enter_mode_selector()
        else:
            self._exit_mode_selector()

    def _enter_mode_selector(self):
        if self._user_held:
            # Idempotent: a stray repeat press shouldn't double-attach
            # listeners or re-render mid-gesture.
            return
        self._user_held = True
        self._mode_selected_during_hold = False
        # Light the User button as visual feedback for the hold. The
        # per-mode color (LED_SEQUENCER / LED_MELODIC / LED_CHORD) is
        # restored on release via _set_mode_button_lights — or to LED_OFF
        # in session mode.
        self._send_programmer_cc(USER_BUTTON_CC, LED_USER_HELD)
        self._render_mode_selector()
        # Attach listeners on slots 0..4 so a tap switches mode. We don't
        # remove the framework / sequencer listeners on the same buttons —
        # those check the user button's pressed state and skip while held.
        self._mode_selector_listeners = []
        for slot in _MODE_SELECTOR_SLOTS:
            button = self._elements.scene_launch_buttons_raw[slot]
            listener = self._make_mode_selector_listener(slot)
            button.add_value_listener(listener)
            self._mode_selector_listeners.append((button, listener))

    def _exit_mode_selector(self):
        if not self._user_held:
            return
        self._user_held = False
        for button, listener in self._mode_selector_listeners:
            try:
                button.remove_value_listener(listener)
            except Exception:
                pass
        self._mode_selector_listeners = []
        # If the user released without picking a mode, fall back to
        # session. That makes "hold + release" a one-handed "back to
        # session" shortcut (works from any mode). A user who actually
        # picked a mode during the hold stays in that mode.
        if not self._mode_selected_during_hold:
            if self._main_modes.selected_mode != "session":
                self._main_modes.selected_mode = "session"
        self._mode_selected_during_hold = False
        # Restore the User-button LED to the mode-appropriate color.
        # __on_main_mode_changed already calls _set_mode_button_lights
        # on mode switches, but if no mode change happened (e.g., release
        # from session-to-session) the call is needed here too.
        self._set_mode_button_lights(self._main_modes.selected_mode)
        self._restore_scene_leds()

    def _make_mode_selector_listener(self, slot):
        target_mode = _MODE_SELECTOR_SLOTS[slot]
        def listener(value):
            if not value:
                return
            if not self._user_held:
                return
            self._mode_selected_during_hold = True
            current = self._main_modes.selected_mode
            # Tap the active mode → bounce back to session. Tap any other
            # mode → switch to it. Either way re-render the selector so
            # the highlight follows.
            self._main_modes.selected_mode = (
                "session" if current == target_mode else target_mode)
            self._render_mode_selector()
        return listener

    def _render_mode_selector(self):
        current = self._main_modes.selected_mode
        for slot in range(7):  # 0..6, skipping 7 (shift / stop-solo-mute)
            mode = _MODE_SELECTOR_SLOTS.get(slot)
            if mode is None:
                color = "DefaultButton.Disabled"
            else:
                bright, dim = _MODE_SELECTOR_LED_COLORS[mode]
                color = bright if mode == current else dim
            try:
                self._elements.scene_launch_buttons_raw[slot].set_light(color)
            except Exception:
                pass

    def _restore_scene_leds(self):
        """After releasing User, hand the scene LEDs back to their owner
        for the current main mode. Blank slots 0-6 first so any "free"
        slot (not owned by the active component) clears its selector
        color instead of staying lit. Slot 7 (shift) has its own driver."""
        for slot in range(7):
            try:
                self._elements.scene_launch_buttons_raw[slot].set_light(
                    "DefaultButton.Disabled")
            except Exception:
                pass
        current = self._main_modes.selected_mode
        if current == "session":
            # SessionComponent owns scene LEDs via ButtonControl. update()
            # walks scenes and re-pushes their colors through the framework.
            try:
                self._session.update()
            except Exception:
                pass
        else:
            seq = self._sequencer_for_mode(current)
            if seq is not None:
                try:
                    seq._update_control_leds()
                except Exception:
                    pass
        # Slot 7 (shift) is driven by _update_shift_button_led — refresh
        # it in case the selector clobbered it (it shouldn't, but defensive).
        self._update_shift_button_led()

    @listens("value")
    def __on_session_mode_button_value(self, value):
        """While in a sequencer main mode (drum_sequence or melodic_sequence),
        the Session button doubles as a return-to-session control with
        momentary-preview semantics:
          - tap (release within SESSION_HOLD_THRESHOLD) -> latch session mode
          - hold (release after threshold)              -> revert to the sequencer
        In session main mode this listener is a no-op; the Session button keeps
        its standard behavior (cycle launch/overview, owned by session_modes).
        """
        sequencer_modes = ("drum_sequence", "drum_64_sequence",
                           "drum_4_track_sequence", "melodic_sequence",
                           "chord_mode")
        if value:
            current = self._main_modes.selected_mode
            if current in sequencer_modes:
                # Shift+Session in sequencer mode = toggle the active sequencer's
                # track pin. We use the press_time state rather than is_pressed()
                # because it's set synchronously by our own listener (no race with
                # framework event dispatch), and the gesture should also work
                # when shift is locked (double-tap latch).
                shift_held = (self._seq_shift_press_time is not None
                              or self._shift_locked)
                self._log("session pressed in {}; seq_shift_held={} shift_locked={}".format(
                    current, self._seq_shift_press_time is not None, self._shift_locked))
                if shift_held:
                    seq = self._sequencer_for_mode(current)
                    if seq is not None and hasattr(seq, "toggle_pin"):
                        pinned = seq.toggle_pin()
                        self._log("toggle_pin on {} → pinned={}".format(current, pinned))
                        return
                # Remember which sequencer to revert to on long-hold release.
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

    def _arrow_target(self):
        """Return the sequencer that should react to the top arrow buttons in
        the current main mode, or None for session mode (where session_navigation
        owns the arrows)."""
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
        # In drum modes, prefer per-note velocity edit when a step pad is held;
        # fall back to pitch_offset shift if no held step has a note.
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
        # Drum modes: held step → nudge (-1 step), else Undo.
        if self._is_drum_mode():
            if target.nudge_held_notes(-1):
                return
            self._undo()
            return
        # Melodic mode: ← navigates to the previous page.
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
        # Drum modes: held step → nudge (+1 step), else Redo.
        if self._is_drum_mode():
            if target.nudge_held_notes(1):
                return
            self._redo()
            return
        # Melodic mode: → navigates to the next page.
        if mode == "melodic_sequence":
            target.nav_page(1)
            return
        target.adjust_pitch_offset(1)

    def _undo(self):
        try:
            if self.song.can_undo:
                self.song.undo()
                self._emit(Event.EDIT_UNDO)
        except Exception as exc:
            self._log("undo failed: {}".format(exc))

    def _redo(self):
        try:
            if self.song.can_redo:
                self.song.redo()
                self._emit(Event.EDIT_REDO)
        except Exception as exc:
            self._log("redo failed: {}".format(exc))

    @listens("selected_mode")
    def __on_stop_solo_mute_mode_changed(self, _mode):
        # Drives the shift-button LED in session main mode. Sequencer
        # modes manage that LED themselves (Control.Shift while held);
        # we only act when stop_solo_mute_modes is the authority.
        self._update_shift_button_led()

    def _update_shift_button_led(self):
        """Set the shift button color from the current stop_solo_mute
        sub-mode. No-op when not in session main mode — sequencer
        components drive the LED themselves there."""
        main_mode = (self._main_modes.selected_mode
                     if hasattr(self, "_main_modes") else "session")
        if main_mode != "session":
            return
        mode = self._stop_solo_mute_modes.selected_mode
        color = _STOP_SOLO_MUTE_LED_COLORS.get(mode, "DefaultButton.Off")
        try:
            self._shift_button.set_light(color)
        except Exception:
            pass

    def _cycle_stop_solo_mute(self, direction=1):
        """Cycle through the standard sub-modes (select → stop → solo →
        mute → select). `edit` is intentionally NOT in the cycle — it's
        reached only via double-tap on shift."""
        current = self._stop_solo_mute_modes.selected_mode
        if current in _STOP_SOLO_MUTE_CYCLE:
            idx = _STOP_SOLO_MUTE_CYCLE.index(current)
        else:
            idx = 0
        target_idx = (idx + direction) % len(_STOP_SOLO_MUTE_CYCLE)
        self._stop_solo_mute_modes.selected_mode = _STOP_SOLO_MUTE_CYCLE[target_idx]

    def _exit_edit_mode(self):
        """Single-tap-out-of-edit: restore the sub-mode the user was in
        before entering edit. Falls back to `select` if we lost track."""
        target = self._pre_edit_mode or "select"
        self._pre_edit_mode = None
        self._stop_solo_mute_modes.selected_mode = target

    def _enter_edit_mode(self):
        """Called on a confirmed double-tap. The first tap already
        cycled the sub-mode forward — undo that, then enter edit so
        `_pre_edit_mode` matches the mode the user actually started in."""
        self._cycle_stop_solo_mute(-1)
        self._pre_edit_mode = self._stop_solo_mute_modes.selected_mode
        self._stop_solo_mute_modes.selected_mode = "edit"

    @listens("value")
    def __on_shift_button_value(self, value):
        """Shift button = scene_launch_buttons_raw[7] — SESSION-MODE only
        now (sequencer shift moved to slot 5 / `_seq_shift_button`).

          - short TAP: cycle stop_solo_mute (select → stop → solo → mute → ...)
          - DOUBLE-TAP: enter edit (the 5th sub-mode); a single tap while
            in edit exits back to `_pre_edit_mode`.
          - HOLD + tap clip/scene: copy modifier (clipboards cleared on
            release).

        In sequencer modes this button is inert (reserved for a future
        feature). The sequencer-side shift behavior — loop range picker,
        grid resolutions, triplet cells, melodic page selector, shift
        lock — all live on `__on_sequencer_shift_button_value` (slot 5).
        """
        held = bool(value)
        now = time.time()
        in_sequencer = (hasattr(self, "_main_modes")
                        and self._main_modes.selected_mode
                            in ("drum_sequence", "drum_64_sequence",
                                "drum_4_track_sequence",
                                "melodic_sequence", "chord_mode"))
        if in_sequencer:
            # Slot 7 is reserved while in a sequencer main mode — no
            # behavior attached yet. We still need to swallow the value
            # event so nothing downstream misinterprets it.
            return
        if held:
            self._session_shift_press_time = now
            return
        duration = (now - self._session_shift_press_time
                    if self._session_shift_press_time is not None else None)
        self._session_shift_press_time = None
        is_tap = (duration is not None
                  and duration <= SHIFT_LOCK_TAP_THRESHOLD)
        if is_tap:
            last = self._session_shift_last_tap_release_time
            is_double_tap = (last is not None
                             and now - last <= SHIFT_DOUBLE_TAP_WINDOW)
            current_sub = self._stop_solo_mute_modes.selected_mode
            if current_sub == "edit":
                # Any single tap exits edit. A double-tap inside edit
                # also exits — there's no second action.
                self._exit_edit_mode()
                self._session_shift_last_tap_release_time = None
            elif is_double_tap:
                self._enter_edit_mode()
                self._session_shift_last_tap_release_time = None
            else:
                # First tap of a possible double-tap. Cycle now; if a
                # second tap arrives within the window, _enter_edit_mode
                # cycles back.
                self._cycle_stop_solo_mute(1)
                self._session_shift_last_tap_release_time = now
        else:
            # Long press: reset detector. Long press is the copy modifier
            # gesture (clip/scene tap while held) — does NOT cycle.
            self._session_shift_last_tap_release_time = None
        # Clipboards always clear on physical release — copy/paste is a
        # momentary action tied to the hold gesture.
        self._clip_copy.clear_clipboard()
        self._scene_copy.clear_clipboard()

    @listens("value")
    def __on_sequencer_shift_button_value(self, value):
        """Sequencer-mode shift (scene_launch_buttons_raw[5]).

        Active only when a sequencer main mode is selected. Drives the
        same `set_device_shift_held` API as the old slot-7 listener used
        to — components don't know the button moved. Double-tap toggles
        the sticky shift LOCK so users can keep the shift-gated overlay
        on without holding a button.
        """
        in_sequencer = (hasattr(self, "_main_modes")
                        and self._main_modes.selected_mode
                            in ("drum_sequence", "drum_64_sequence",
                                "drum_4_track_sequence",
                                "melodic_sequence", "chord_mode"))
        if not in_sequencer:
            # Slot 5 in session mode = standard scene launch button.
            # Don't interfere; just propagate the current locked state.
            return
        held = bool(value)
        now = time.time()
        if held:
            self._seq_shift_press_time = now
        else:
            duration = (now - self._seq_shift_press_time
                        if self._seq_shift_press_time is not None else None)
            self._seq_shift_press_time = None
            is_tap = (duration is not None
                      and duration <= SHIFT_LOCK_TAP_THRESHOLD)
            if is_tap:
                last = self._seq_shift_last_tap_release_time
                is_double_tap = (last is not None
                                 and now - last <= SHIFT_DOUBLE_TAP_WINDOW)
                if is_double_tap:
                    self._shift_locked = not self._shift_locked
                    self._log("shift lock: {}".format(self._shift_locked))
                    self._emit(Event.SHIFT_LOCK_CHANGED,
                               locked=self._shift_locked)
                    self._seq_shift_last_tap_release_time = None
                else:
                    self._seq_shift_last_tap_release_time = now
            else:
                self._seq_shift_last_tap_release_time = None
        effective = held or self._shift_locked
        self._drum_step_sequencer.set_device_shift_held(effective)
        self._drum_64_step_sequencer.set_device_shift_held(effective)
        self._drum_4_track_step_sequencer.set_device_shift_held(effective)
        self._melodic_step_sequencer.set_device_shift_held(effective)
        self._chord_pad_mode.set_device_shift_held(effective)

    def _log(self, message):
        try:
            self._c_instance.log_message("[Launchpad Mini MK3] {}".format(message))
        except Exception:
            pass

    def _emit(self, event_name, **payload):
        """Fire a semantic event on the bus. No-op if the bus is None
        (kill switch). The script's status bar + M4L delivery is handled
        by subscribers attached in _create_notification_subscribers."""
        if self._event_bus is not None:
            self._event_bus.emit(event_name, **payload)

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
            self._send_midi(sysex.STD_MSG_HEADER + (DEVICE_SYSEX_ID, command_byte) + tuple(payload) + (sysex.SYSEX_END_BYTE,))
        except Exception:
            pass

    def _session_button_color_for_mode(self, mode):
        """Pick the Session-button LED color. BLUE when the active sequencer
        is pinned to a track (shift+Session toggles); otherwise dim-green in
        sequencer/chord modes (= preview-session affordance) or bright-green
        in session mode."""
        sequencer_modes = ("drum_sequence", "drum_64_sequence",
                           "drum_4_track_sequence", "melodic_sequence",
                           "chord_mode")
        if mode in sequencer_modes:
            seq = self._sequencer_for_mode(mode)
            if seq is not None and hasattr(seq, "is_pinned") and seq.is_pinned():
                return LED_SESSION_PINNED
            return LED_SESSION_DIM
        return LED_SESSION

    def _set_mode_button_lights(self, mode):
        if mode in ("drum_sequence", "drum_64_sequence", "drum_4_track_sequence"):
            # Session button:
            #   BLUE  = sequencer is pinned to a track (shift+Session toggles)
            #   GREEN = "session button is reachable" (tap to latch, hold to preview)
            self._send_programmer_cc(SESSION_BUTTON_CC,
                                     self._session_button_color_for_mode(mode))
            # Drums/Keys are driven by TransportComponent (still active in drum modes).
            self._send_programmer_cc(USER_BUTTON_CC, LED_SEQUENCER)
            # Arrows drive octave / semitone of the drum-pad selector (regular
            # drum mode) or pitch_offset window for the note selector
            # (drum_64 mode).
            self._send_programmer_cc(UP_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(DOWN_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(LEFT_BUTTON_CC, LED_ARROW_SEMITONE)
            self._send_programmer_cc(RIGHT_BUTTON_CC, LED_ARROW_SEMITONE)
        elif mode == "melodic_sequence":
            # Same affordances as drum_sequence: dim-green session = "tap to
            # return", drums/keys driven by TransportComponent (play/record),
            # arrows = octave / semitone of the pitch row range.
            self._send_programmer_cc(SESSION_BUTTON_CC,
                                     self._session_button_color_for_mode(mode))
            self._send_programmer_cc(USER_BUTTON_CC, LED_MELODIC)
            self._send_programmer_cc(UP_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(DOWN_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(LEFT_BUTTON_CC, LED_ARROW_SEMITONE)
            self._send_programmer_cc(RIGHT_BUTTON_CC, LED_ARROW_SEMITONE)
        elif mode == "chord_mode":
            # Chord layout: session dim-green = "tap to return", drums/keys
            # still drive TransportComponent (play/record), arrows transpose
            # the chord layout (±octave / ±semitone of the root).
            self._send_programmer_cc(SESSION_BUTTON_CC,
                                     self._session_button_color_for_mode(mode))
            self._send_programmer_cc(USER_BUTTON_CC, LED_CHORD)
            self._send_programmer_cc(UP_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(DOWN_BUTTON_CC, LED_ARROW_OCTAVE)
            self._send_programmer_cc(LEFT_BUTTON_CC, LED_ARROW_SEMITONE)
            self._send_programmer_cc(RIGHT_BUTTON_CC, LED_ARROW_SEMITONE)
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
