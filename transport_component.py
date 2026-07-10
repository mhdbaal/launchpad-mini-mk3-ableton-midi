# Launchpad Mini MK3 - Transport Component
# Global play/stop and session record toggle on the Drums/Keys mode buttons.
#
# Uses direct value listeners + raw CC LED writes (same pattern as the
# sequencer "control buttons"), bypassing ButtonControl/Layer/Skin to avoid
# fighting with BackgroundComponent for ownership of drums/keys buttons.
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.base import listens
from ableton.v2.control_surface import Component

from .programmer_mode import MIDI_CC_STATUS, PROGRAMMER_LED_CHANNEL


# Raw Launchpad palette indices (same values as Rgb.GREEN_HALF, GREEN, RED_HALF, RED).
LED_PLAY_OFF = 27
LED_PLAY_ON = 21
LED_RECORD_OFF = 7
LED_RECORD_ON = 5
LED_OFF = 0


class TransportComponent(Component):
    """Play/Stop on the Drums button, session record on the Keys button.

    Lifecycle:
    - Call set_buttons(play_btn, record_btn) once after construction.
    - Enable in session mode, disable in sequencer modes; disable explicitly
      turns both LEDs off so the caller doesn't have to.
    """

    def __init__(self, *a, **k):
        super(TransportComponent, self).__init__(*a, **k)
        self._play_button = None
        self._record_button = None
        self._play_listener = None
        self._record_listener = None
        # Optional shift-combo plumbing (Pro MK3): with both a shift button
        # and a capture handler set, shift+Record fires the handler (Capture
        # MIDI) instead of toggling session record. The Mini leaves these
        # unset — behavior unchanged.
        self._shift_button = None
        self._capture_handler = None
        self._on_is_playing_changed.subject = self.song
        self._on_session_record_changed.subject = self.song

    def disconnect(self):
        self.set_buttons(None, None)
        super(TransportComponent, self).disconnect()

    def set_buttons(self, play_button, record_button):
        self._detach_listener(self._play_button, self._play_listener)
        self._detach_listener(self._record_button, self._record_listener)
        self._play_button = play_button
        self._record_button = record_button
        self._play_listener = self._on_play_pressed if play_button else None
        self._record_listener = self._on_record_pressed if record_button else None
        if play_button and self._play_listener:
            play_button.add_value_listener(self._play_listener)
        if record_button and self._record_listener:
            record_button.add_value_listener(self._record_listener)
        if self.is_enabled():
            self._update_leds()

    def set_enabled(self, enabled):
        was_enabled = self.is_enabled()
        super(TransportComponent, self).set_enabled(enabled)
        self._log("enabled: {}".format(enabled))
        if enabled:
            self._update_leds()
        elif was_enabled:
            self._send_led(self._play_button, LED_OFF)
            self._send_led(self._record_button, LED_OFF)

    def update(self):
        super(TransportComponent, self).update()
        if self.is_enabled():
            self._update_leds()

    def _on_play_pressed(self, value):
        if not self.is_enabled() or not value:
            return
        self._log("play pressed")
        if self.song.is_playing:
            self.song.stop_playing()
        else:
            self.song.start_playing()

    def set_shift_button(self, button):
        """Optional: plumb a shift button for the shift+Record combo."""
        self._shift_button = button

    def set_capture_handler(self, handler):
        """Optional: callable fired by shift+Record (Capture MIDI)."""
        self._capture_handler = handler

    def _on_record_pressed(self, value):
        if not self.is_enabled() or not value:
            return
        if (self._capture_handler is not None
                and self._shift_button is not None
                and self._shift_button.is_pressed()):
            self._log("record pressed with shift -> capture")
            self._capture_handler()
            return
        self._log("record pressed")
        self.song.session_record = not self.song.session_record

    @listens("is_playing")
    def _on_is_playing_changed(self):
        if self.is_enabled():
            self._update_play_led()

    @listens("session_record")
    def _on_session_record_changed(self):
        if self.is_enabled():
            self._update_record_led()

    def _update_leds(self):
        try:
            self._update_play_led()
            self._update_record_led()
        except Exception as exc:
            self._log("update_leds error: {}".format(exc))

    def _update_play_led(self):
        color = LED_PLAY_ON if self.song.is_playing else LED_PLAY_OFF
        self._send_led(self._play_button, color)

    def _update_record_led(self):
        color = LED_RECORD_ON if self.song.session_record else LED_RECORD_OFF
        self._send_led(self._record_button, color)

    def _send_led(self, button, color_value):
        if button is None:
            return
        try:
            controller = button.original_identifier()
        except Exception:
            return
        try:
            self.canonical_parent._send_midi(
                (MIDI_CC_STATUS + PROGRAMMER_LED_CHANNEL, controller, color_value),
                optimized=False,
            )
        except Exception:
            pass

    def _detach_listener(self, button, listener):
        if button is None or listener is None:
            return
        try:
            button.remove_value_listener(listener)
        except Exception:
            pass

    def _log(self, message):
        try:
            self.canonical_parent._c_instance.log_message("[Transport] {}".format(message))
        except Exception:
            pass
