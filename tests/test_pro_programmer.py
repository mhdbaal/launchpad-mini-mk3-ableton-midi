"""Exercise production handler bodies with fake Live objects.

Imports and @listens descriptors are substituted because Ableton owns them.
These tests cover mode/gesture logic, not Live's resource arbitration or USB I/O.
"""
import ast
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


class Component:
    def set_enabled(self, value):
        self.enabled = value

    def is_enabled(self):
        return self.enabled

    def update(self):
        pass

    def on_identified(self, midi_bytes):
        pass

    def disconnect(self):
        pass


def load_handlers(relative_path, extra=None):
    """Compile the real module unchanged except unavailable import bindings."""
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(), filename=str(path))
    env = {}
    body = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                env[alias.asname or alias.name] = Mock(name=alias.name)
        else:
            body.append(node)
    env.update(Component=Component, NovationBase=Component,
               listens=lambda event: lambda fn: fn)
    env.update(extra or {})
    tree.body = body
    exec(compile(tree, str(path), "exec"), env)
    return env


ids = SimpleNamespace(**runpy.run_path(str(ROOT / "pro/sysex_ids.py")))
profile = load_handlers("pro/device_profile.py", {"_ids": ids})
protocol = runpy.run_path(str(ROOT / "programmer_mode.py"))
surface_env = load_handlers("pro/launchpad_pro_mk3.py", dict(
    profile, sysex=SimpleNamespace(STD_MSG_HEADER=(240, 0, 32, 41, 2),
                                  SYSEX_END_BYTE=247,
                                  FIRMWARE_MODE_COMMAND_BYTE=16,
                                  STANDALONE_MODE_BYTE=0),
    **{k: v for k, v in protocol.items() if not k.startswith("__")}))
Surface = surface_env["Launchpad_Pro_MK3"]
Drum = load_handlers("drum_step_sequencer.py")["DrumStepSequencerComponent"]


class Button:
    held = False

    def is_pressed(self):
        return self.held


class Modes:
    def __init__(self, surface):
        self.surface = surface
        self._mode = "session"

    @property
    def selected_mode(self):
        return self._mode

    @selected_mode.setter
    def selected_mode(self, mode):
        if mode != self._mode:
            self._mode = mode
            self.surface._Launchpad_Pro_MK3__on_main_mode_changed(mode)


class ProgrammerModesTest(unittest.TestCase):
    def setUp(self):
        s = self.surface = Surface.__new__(Surface)
        s._picker_return_mode = None
        s._duplicate_consumed = False
        s._elements = SimpleNamespace(**{name + "_button": Button()
            for name in ("shift", "clear", "duplicate")})
        for name in ("_transport", "_drum_step_sequencer", "_drum_64_step_sequencer",
                     "_drum_4_track_step_sequencer", "_melodic_step_sequencer",
                     "_chord_pad_mode", "_mode_picker", "_edit_mode",
                     "_clip_copy", "_scene_copy", "_session_modes"):
            setattr(s, name, Mock())
        for name in ("_log", "_emit", "_restore_clip_launch_matrix",
                     "_set_session_components_enabled", "_request_midi_map_rebuild",
                     "_set_mode_button_lights", "_update_modifier_leds",
                     "_update_mixer_function_leds", "set_controlled_track",
                     "release_controlled_track", "set_feedback_channels",
                     "_clear_inert_button_leds"):
            setattr(s, name, Mock())
        s._send_midi = Mock()
        s.song = SimpleNamespace(view=SimpleNamespace(selected_track=object()))
        s._main_modes = Modes(s)

    def event(self, button, held):
        element = getattr(self.surface._elements, button + "_button", None)
        if element:
            element.held = held
        handler = getattr(self.surface,
            "_Launchpad_Pro_MK3__on_" + button + "_button_value")
        handler(127 if held else 0)

    def test_sequencer_and_shift_sequencer_edit_live_without_firmware_messages(self):
        for shift in (False, True):
            self.event("shift", shift)
            self.event("sequencer_mode", True)
            self.assertEqual(self.surface._main_modes.selected_mode, "drum_sequence")
            self.surface._drum_step_sequencer.set_device_shift_held.assert_called_with(shift)
            self.event("sequencer_mode", False)
            self.surface._main_modes.selected_mode = "session"
        self.surface._send_midi.assert_not_called()

    def test_session_release_cannot_restore_a_previous_mode(self):
        self.event("sequencer_mode", True)
        self.event("session_mode", True)
        self.event("session_mode", False)
        self.assertEqual(self.surface._main_modes.selected_mode, "session")
        self.event("session_mode", True)
        self.event("sequencer_mode", True)
        self.event("session_mode", False)
        self.assertEqual(self.surface._main_modes.selected_mode, "drum_sequence")

    def test_picker_cancel_and_select_never_switch_firmware(self):
        self.event("sequencer_mode", True)
        self.event("shift", True)
        for _ in range(30):
            self.event("session_mode", True)
            self.assertEqual(self.surface._main_modes.selected_mode, "mode_picker")
            self.event("session_mode", False)
            self.event("session_mode", True)
            self.assertEqual(self.surface._main_modes.selected_mode, "drum_sequence")
        for mode in surface_env["_SEQUENCER_MODES"]:
            self.surface._on_picker_mode_selected(mode)
        self.surface._send_midi.assert_not_called()

    def test_clear_is_transferred_and_released_across_modes(self):
        self.event("clear", True)
        self.event("sequencer_mode", True)
        self.surface._edit_mode.set_delete_held.assert_called_with(False)
        self.surface._drum_step_sequencer.set_action_modifier.assert_called_with("delete", True)
        self.event("clear", False)
        self.assertIn(unittest.mock.call("delete", False),
                      self.surface._drum_step_sequencer.set_action_modifier.call_args_list)
        self.event("session_mode", True)
        self.surface._edit_mode.set_delete_held.assert_called_with(False)

    def test_releasing_clear_restores_a_still_held_duplicate(self):
        self.event("sequencer_mode", True)
        self.event("duplicate", True)
        self.event("clear", True)
        self.surface._drum_step_sequencer.set_action_modifier.assert_called_with("delete", True)
        self.event("clear", False)
        self.surface._drum_step_sequencer.set_action_modifier.assert_called_with("duplicate", True)

    def test_double_loop_is_not_repeated_or_converted_on_mode_change(self):
        self.event("sequencer_mode", True)
        self.event("shift", True)
        self.event("duplicate", True)
        self.event("shift", False)
        self.event("session_mode", True)
        self.surface._edit_mode.set_duplicate_held.assert_called_with(False)
        self.event("sequencer_mode", True)
        self.surface._drum_step_sequencer.double_loop.assert_called_once_with()
        self.event("duplicate", False)
        self.event("duplicate", True)
        self.surface._drum_step_sequencer.set_action_modifier.assert_called_with("duplicate", True)

    def test_reconnect_sends_only_programmer_entry_and_restores_active_mode(self):
        self.event("sequencer_mode", True)
        self.surface.on_identified(())
        self.assertEqual(self.surface._main_modes.selected_mode, "drum_sequence")
        self.surface._send_midi.assert_called_once_with(
            (240, 0, 32, 41, 2, 14, 14, 1, 247))

    def test_teardown_selection_does_not_reenable_components(self):
        self.surface._Launchpad_Pro_MK3__on_main_mode_changed(None)
        self.surface._transport.set_enabled.assert_not_called()

    def test_disconnect_restores_live_and_standalone_after_releasing_controls(self):
        self.surface._notification_dispatcher = Mock()
        self.surface.disconnect()
        self.assertEqual([call.args[0] for call in self.surface._send_midi.call_args_list], [
            (240, 0, 32, 41, 2, 14, 14, 0, 247),
            (240, 0, 32, 41, 2, 14, 16, 0, 247)])

    def test_reserved_mode_buttons_are_consumed_by_background(self):
        self.surface._create_background()
        layer = surface_env["Layer"].call_args.kwargs
        for button in ("note_mode_button", "chord_mode_button", "custom_mode_button"):
            self.assertEqual(layer[button], button)
            self.assertFalse(hasattr(Surface, "_Launchpad_Pro_MK3__on_" + button + "_value"))


class DrumReleaseTest(unittest.TestCase):
    def test_unmatched_step_release_does_not_create_clip_or_note(self):
        drum = Mock(_held_step_pads={}, _consumed_step_pads=set())
        Drum._handle_step_press(drum, 3, False)
        drum._ensure_clip.assert_not_called()
        drum._toggle_step.assert_not_called()

    def test_matching_step_release_still_toggles(self):
        drum = Mock(_held_step_pads={3: None}, _consumed_step_pads=set())
        Drum._handle_step_press(drum, 3, False)
        drum._toggle_step.assert_called_once_with(3)

    def test_shift_transition_cancels_a_pending_step_press(self):
        drum = Mock(_held_step_pads={3: None}, _consumed_step_pads=set(),
                    _device_shift_held=False)
        Drum.set_device_shift_held(drum, True)
        Drum.set_device_shift_held(drum, False)
        Drum._handle_step_press(drum, 3, False)
        drum._toggle_step.assert_not_called()

    def test_unmatched_page_release_does_not_create_clip_or_scope_loop(self):
        drum = Mock(_loop_press_points=[])
        Drum._handle_loop_press(drum, 3, False)
        drum._ensure_clip.assert_not_called()
        drum._scope_page.assert_not_called()


if __name__ == "__main__":
    unittest.main()
