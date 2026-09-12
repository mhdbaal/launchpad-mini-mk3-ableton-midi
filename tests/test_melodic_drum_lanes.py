"""Melodic sequencer drum-lane mode + the 4-track velocity-overlay fix.

Same substitution trick as test_pro_programmer: the module is compiled with its
Ableton imports replaced by Mocks, then the real (unbound) methods are bound
onto a bare host object so the production logic actually runs.
"""
import types
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_pro_programmer import load_handlers


# palette.py builds real SysEx tuples, so the novation sysex constants must be
# real values rather than the default import Mocks.
palette_env = load_handlers("palette.py", {
    "sysex": SimpleNamespace(STD_MSG_HEADER=(240, 0, 32, 41, 2),
                             SYSEX_END_BYTE=247)})

# The melodic module compares against the real colour constants, so inject them
# instead of the Mocks load_handlers would otherwise bind.
_PALETTE_NAMES = ("GREY_EMPTY", "GREY_DIM", "GREY_MID", "GREY_BRIGHT",
                  "RGB_WHITE", "RGB_BLACK", "VELOCITY_LEVEL_DIM",
                  "VELOCITY_LEVEL_PALETTE", "rgb_shades")
melodic_env = load_handlers("melodic_step_sequencer.py", dict(
    {name: palette_env[name] for name in _PALETTE_NAMES},
    SUPPORTS_RGB_LEDS=True))
Melodic = melodic_env["MelodicStepSequencerComponent"]
DRUM_LANES = melodic_env["DRUM_LANES"]
PITCH_ROW_MAX = melodic_env["PITCH_ROW_MAX"]

Drum4 = load_handlers("drum_4_track_step_sequencer.py")[
    "DrumStep4TrackSequencerComponent"]

# Methods that are pure enough to run against a bare host object.
_REAL = ("_scan_used_drum_pads", "_rescan_drum_pads", "_used_drum_pads",
         "_clamped_lane_offset", "_visible_drum_pads", "_scroll_drum_lanes",
         "_pitch_for_row", "_drum_lane_mode", "_selected_drum_pad_note")


def host(notes, offset=0, selected=None):
    """Build a host carrying the real drum-lane helpers over a fake rack."""
    obj = SimpleNamespace()
    pads = [SimpleNamespace(note=n, chains=[object()]) for n in notes]
    obj._drum_group_device = SimpleNamespace(
        drum_pads=pads,
        view=SimpleNamespace(selected_drum_pad=(
            SimpleNamespace(note=selected) if selected is not None else None)))
    obj._drum_lane_offset = offset
    obj._held_grid_buttons = set()
    obj._held_note_cells = {}
    obj._consumed_note_cells = set()
    obj._preview_mode = False
    obj._emit = Mock()
    obj.update = Mock()
    obj._update_audition_translations = Mock()
    for name in _REAL:
        setattr(obj, name, types.MethodType(getattr(Melodic, name), obj))
    obj._rescan_drum_pads()
    return obj


class DrumLaneMappingTest(unittest.TestCase):
    def test_only_pads_with_a_device_become_lanes_lowest_at_the_bottom(self):
        obj = SimpleNamespace(_drum_group_device=SimpleNamespace(drum_pads=[
            SimpleNamespace(note=48, chains=[object()]),
            SimpleNamespace(note=40, chains=[]),        # empty pad — skipped
            SimpleNamespace(note=36, chains=[object()]),
        ]))
        used = Melodic._scan_used_drum_pads(obj)
        self.assertEqual([p.note for p in used], [36, 48])

    def test_rows_map_bottom_up_and_die_past_the_end_of_the_rack(self):
        obj = host([36, 38, 42, 46])
        self.assertEqual(obj._pitch_for_row(PITCH_ROW_MAX), 36)
        self.assertEqual(obj._pitch_for_row(PITCH_ROW_MAX - 1), 38)
        self.assertEqual(obj._pitch_for_row(PITCH_ROW_MAX - 3), 46)
        # Only 4 used pads → the top 4 rows have no lane behind them.
        for y in range(0, 4):
            self.assertIsNone(obj._pitch_for_row(y))

    def test_a_full_rack_fills_all_eight_lanes(self):
        obj = host(list(range(36, 36 + 12)))
        pitches = [obj._pitch_for_row(y) for y in range(8)]
        self.assertEqual(pitches, [43, 42, 41, 40, 39, 38, 37, 36])
        self.assertNotIn(None, pitches)


class DrumLaneCacheTest(unittest.TestCase):
    def test_the_led_path_reads_a_cache_not_a_128_pad_scan(self):
        obj = host(list(range(36, 44)))
        scanned = []
        obj._drum_group_device.drum_pads = _CountingPads(
            obj._drum_group_device.drum_pads, scanned)
        # Resolving every row + every cell color must not re-walk the rack.
        for _ in range(8):
            obj._pitch_for_row(0)
            obj._drum_lane_mode()
        self.assertEqual(scanned, [])
        obj._rescan_drum_pads()
        self.assertEqual(len(scanned), 1)


class _CountingPads(list):
    """List that records each full iteration, to catch a scan on the hot path."""

    def __init__(self, items, log):
        super(_CountingPads, self).__init__(items)
        self._log = log

    def __iter__(self):
        self._log.append(1)
        return super(_CountingPads, self).__iter__()


class DrumLaneScrollTest(unittest.TestCase):
    def test_scrolling_clamps_to_the_last_full_window(self):
        obj = host(list(range(36, 36 + 12)))   # 12 pads, window of 8 → max 4
        obj._scroll_drum_lanes(DRUM_LANES)
        self.assertEqual(obj._drum_lane_offset, 4)
        self.assertEqual(obj._pitch_for_row(PITCH_ROW_MAX), 40)
        # Already at the end: no further move, no event.
        obj._emit.reset_mock()
        obj._scroll_drum_lanes(DRUM_LANES)
        self.assertEqual(obj._drum_lane_offset, 4)
        obj._emit.assert_not_called()

    def test_scrolling_back_stops_at_zero(self):
        obj = host(list(range(36, 36 + 12)), offset=4)
        obj._scroll_drum_lanes(-DRUM_LANES)
        self.assertEqual(obj._drum_lane_offset, 0)
        obj._emit.reset_mock()
        obj._scroll_drum_lanes(-1)
        obj._emit.assert_not_called()

    def test_a_rack_smaller_than_the_window_never_scrolls(self):
        obj = host([36, 38, 42])
        obj._scroll_drum_lanes(1)
        self.assertEqual(obj._drum_lane_offset, 0)

    def test_scrolling_drops_held_cells_so_a_release_cannot_write_a_stale_pitch(self):
        obj = host(list(range(36, 36 + 12)))
        obj._held_grid_buttons = {(0, 7)}
        obj._held_note_cells = {(0, 7): (0, 36, 0.0)}
        obj._consumed_note_cells = {(0, 7)}
        obj._scroll_drum_lanes(1)
        self.assertEqual(obj._held_grid_buttons, set())
        self.assertEqual(obj._held_note_cells, {})
        self.assertEqual(obj._consumed_note_cells, set())


class DrumLaneArrowTest(unittest.TestCase):
    def test_arrows_scroll_lanes_instead_of_transposing_on_a_rack(self):
        m = Mock()
        m._drum_lane_mode.return_value = True
        Melodic._adjust_pitch_offset(m, 12)
        m._scroll_drum_lanes.assert_called_once_with(DRUM_LANES)
        Melodic._adjust_pitch_offset(m, -1)
        m._scroll_drum_lanes.assert_called_with(-1)
        m._set_pitch_offset.assert_not_called()

    def test_arrows_still_transpose_on_a_normal_melodic_track(self):
        m = Mock()
        m._drum_lane_mode.return_value = False
        m._pitch_offset = 0
        Melodic._adjust_pitch_offset(m, 12)
        m._set_pitch_offset.assert_called_once_with(12)
        m._scroll_drum_lanes.assert_not_called()


class DrumLaneSlotTest(unittest.TestCase):
    def _surface(self, drum_mode):
        m = Mock()
        m.is_enabled.return_value = True
        m._is_main_mode_selector_held.return_value = False
        m._drum_lane_mode.return_value = drum_mode
        m._direct_slot_actions = True
        m._device_shift_held = False
        m._chromatic_slot = 0
        m._scale_cycle_slot = 1
        m._cycle_slot = 6
        m._lane_velocity_armed = False
        # The release path dispatches through this — bind the real one so the
        # test exercises the dispatch, not a Mock.
        m._perform_control_button_action = types.MethodType(
            Melodic._perform_control_button_action, m)
        return m

    def tap(self, m, index):
        """Scene slots now act on RELEASE so hold and tap can share a button."""
        Melodic._on_control_button_value(m, index, 127)
        m._lane_velocity_armed = False          # a tap never arms the view
        Melodic._on_control_button_value(m, index, 0)

    def test_chromatic_and_scale_slots_are_inert_on_a_drum_rack(self):
        m = self._surface(drum_mode=True)
        self.tap(m, 0)
        self.tap(m, 1)
        m._toggle_chromatic_mode.assert_not_called()
        m._cycle_scale.assert_not_called()

    def test_chromatic_and_scale_slots_still_work_on_a_melodic_track(self):
        m = self._surface(drum_mode=False)
        self.tap(m, 0)
        self.tap(m, 1)
        m._toggle_chromatic_mode.assert_called_once_with()
        m._cycle_scale.assert_called_once_with(1)

    def test_a_press_alone_only_arms_the_lane_view(self):
        m = self._surface(drum_mode=False)
        Melodic._on_control_button_value(m, 0, 127)
        self.assertEqual(m._lane_velocity_scene, 0)
        m._lane_velocity_arm_task.restart.assert_called_once_with()
        m._toggle_chromatic_mode.assert_not_called()

    def test_a_hold_closes_without_firing_the_slot_action(self):
        m = self._surface(drum_mode=False)
        Melodic._on_control_button_value(m, 0, 127)
        m._lane_velocity_armed = True           # the arm task fired
        Melodic._on_control_button_value(m, 0, 0)
        m._disarm_lane_velocity.assert_called_once_with()
        m._toggle_chromatic_mode.assert_not_called()


class LaneVelocityTest(unittest.TestCase):
    def _view(self, row=3, pitch=38):
        m = Mock()
        m._lane_velocity_scene = row
        m._lane_velocity_armed = True
        m._device_shift_held = False
        m._page_index = 0
        m._step_length = 0.25
        m._pitch_for_row.return_value = pitch
        m._ensure_clip.return_value = True
        m._velocity_for_lane_level = types.MethodType(
            Melodic._velocity_for_lane_level, m)
        m._lane_velocity_cell_to_level = types.MethodType(
            Melodic._lane_velocity_cell_to_level, m)
        return m

    def test_rows_read_bottom_up(self):
        m = Mock()
        f = types.MethodType(Melodic._lane_velocity_cell_to_level, m)
        self.assertEqual(f(PITCH_ROW_MAX), 1)       # bottom row = quietest
        self.assertEqual(f(0), 8)                   # top row = loudest
        self.assertIsNone(f(8))

    def test_level_eight_reaches_full_velocity_not_128(self):
        m = Mock()
        f = types.MethodType(Melodic._velocity_for_lane_level, m)
        self.assertEqual(f(1), 16)
        self.assertEqual(f(8), 127)

    def test_any_audible_note_lights_at_least_one_cell(self):
        m = Mock()
        f = types.MethodType(Melodic._lane_level_for_velocity, m)
        self.assertEqual(f(1), 1)
        self.assertEqual(f(16), 1)
        self.assertEqual(f(17), 2)
        self.assertEqual(f(127), 8)

    def test_tapping_an_empty_column_creates_the_note_at_that_velocity(self):
        m = self._view()
        m._find_note_at_step_pitch.return_value = None
        Melodic._handle_lane_velocity_press(m, 2, PITCH_ROW_MAX - 3)  # level 4
        m._clip.add_new_notes.assert_called_once()
        m._ensure_loop_contains_time.assert_called_once_with(0.5 + 0.25)

    def test_tapping_a_column_with_a_note_rewrites_its_velocity(self):
        m = self._view()
        m._find_note_at_step_pitch.return_value = SimpleNamespace(velocity=100)
        Melodic._handle_lane_velocity_press(m, 0, PITCH_ROW_MAX)       # level 1
        m._replace_note_at.assert_called_once()
        self.assertEqual(m._replace_note_at.call_args.kwargs["velocity"], 16)
        m._clip.add_new_notes.assert_not_called()

    def test_a_dead_lane_ignores_taps(self):
        m = self._view()
        m._pitch_for_row.return_value = None
        Melodic._handle_lane_velocity_press(m, 0, 0)
        m._ensure_clip.assert_not_called()

    def test_shift_takes_the_grid_back_from_the_lane_view(self):
        m = Mock(_lane_velocity_armed=True, _device_shift_held=True)
        self.assertFalse(Melodic._lane_velocity_active(m))
        m._device_shift_held = False
        self.assertTrue(Melodic._lane_velocity_active(m))

    def test_the_step_hold_overlay_stands_down_while_the_lane_view_is_up(self):
        m = Mock()
        m._lane_velocity_active.return_value = True
        self.assertFalse(Melodic._velocity_overlay_should_show(m))


class FourTrackVelocityOverlayTest(unittest.TestCase):
    def test_overlay_never_claims_track_zeros_rows(self):
        m = Mock(_velocity_overlay_armed=True, _device_shift_held=False)
        self.assertFalse(Drum4._velocity_overlay_should_show(m))

    def test_arming_is_a_no_op(self):
        m = Mock(_velocity_overlay_armed=False, _device_shift_held=False,
                 _held_step_pads={(0, 0): None})
        Drum4._arm_velocity_overlay(m)
        self.assertFalse(m._velocity_overlay_armed)
        m.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class TargetTrackTest(unittest.TestCase):
    """The rack must follow the clip being edited, not the selected track:
    Live keeps detail_clip open when you select another track, and reading the
    rack off the selected track is what wrote scale pitches into a drum clip."""

    def test_the_clips_own_track_wins_over_the_selected_track(self):
        clip_track = SimpleNamespace(name="Drums")
        slot = SimpleNamespace(canonical_parent=clip_track)
        m = Mock()
        m._clip = SimpleNamespace(canonical_parent=slot)
        m.song = SimpleNamespace(
            view=SimpleNamespace(selected_track=SimpleNamespace(name="2-MIDI")))
        self.assertIs(Melodic._target_track(m), clip_track)

    def test_no_clip_falls_back_to_the_selected_track(self):
        selected = SimpleNamespace(name="2-MIDI")
        m = Mock()
        m._clip = None
        m.song = SimpleNamespace(view=SimpleNamespace(selected_track=selected))
        self.assertIs(Melodic._target_track(m), selected)

    def test_an_unreachable_parent_falls_back_instead_of_raising(self):
        class Gone(object):
            @property
            def canonical_parent(self):
                raise RuntimeError("clip deleted")

        selected = SimpleNamespace(name="2-MIDI")
        m = Mock()
        m._clip = Gone()
        m.song = SimpleNamespace(view=SimpleNamespace(selected_track=selected))
        self.assertIs(Melodic._target_track(m), selected)


rgb_shades = palette_env["rgb_shades"]
rgb_sysex_message = palette_env["rgb_sysex_message"]


class RgbShadeTest(unittest.TestCase):
    def test_shades_of_one_hue_ascend_evenly_and_stay_in_range(self):
        shades = rgb_shades(0x00FF00, 8)
        self.assertEqual(len(shades), 8)
        greens = [g for _, g, _ in shades]
        self.assertEqual(greens, sorted(greens))
        self.assertEqual(shades[-1], (0, 127, 0))          # top = full hue
        self.assertTrue(all(r == 0 and b == 0 for r, _, b in shades))
        self.assertTrue(all(0 <= c <= 127 for s in shades for c in s))
        # Evenly spaced: no gap more than one unit off the mean step.
        gaps = [b - a for a, b in zip(greens, greens[1:])]
        self.assertLessEqual(max(gaps) - min(gaps), 1)

    def test_a_dark_clip_colour_is_normalised_instead_of_fading_to_black(self):
        # A dim green clip must still span the full ramp, not collapse near 0.
        shades = rgb_shades(0x003300, 8)
        self.assertEqual(shades[-1], (0, 127, 0))
        self.assertGreater(shades[0][1], 0)

    def test_hue_ratios_survive_the_ramp(self):
        shades = rgb_shades(0xFF8000, 8)   # orange: R twice G
        r, g, b = shades[-1]
        self.assertEqual(b, 0)
        self.assertAlmostEqual(r / float(g), 2.0, delta=0.15)

    def test_black_never_divides_by_zero(self):
        self.assertEqual(rgb_shades(0, 4), [(0, 0, 0)] * 4)


class RgbSysexTest(unittest.TestCase):
    def test_message_shape_matches_the_programmers_reference(self):
        msg = rgb_sysex_message(14, [(81, (0, 127, 0)), (82, (12, 0, 5))])
        self.assertEqual(msg[:7], (240, 0, 32, 41, 2, 14, 3))
        self.assertEqual(msg[7:12], (3, 81, 0, 127, 0))
        self.assertEqual(msg[12:17], (3, 82, 12, 0, 5))
        self.assertEqual(msg[-1], 247)

    def test_channels_are_clamped_into_the_0_127_range(self):
        msg = rgb_sysex_message(14, [(81, (999, -5, 127))])
        self.assertEqual(msg[7:12], (3, 81, 127, 0, 127))


GREY_EMPTY = palette_env["GREY_EMPTY"]
GREY_DIM = palette_env["GREY_DIM"]
GREY_MID = palette_env["GREY_MID"]
GREY_BRIGHT = palette_env["GREY_BRIGHT"]
RGB_WHITE = palette_env["RGB_WHITE"]
RGB_BLACK = palette_env["RGB_BLACK"]


class RuleSetTest(unittest.TestCase):
    """Hue = content, grey = absence, white = now. A coloured pad must always
    mean something is there, so no structural state may borrow the hue."""

    def _seq(self, **over):
        m = Mock()
        m._rgb_leds.return_value = True
        m._shade.side_effect = lambda level, levels=8: ("HUE", level, levels)
        m._shade_for_velocity.side_effect = lambda v: ("HUE_VEL", v)
        m._playhead_is_on_step.return_value = False
        m._playhead_is_on_page.return_value = False
        m._is_cell_held.return_value = False
        m._is_anchor_pitch.return_value = False
        m._find_note_at_step_pitch.return_value = None
        m._selected_track_can_hold_midi.return_value = True
        m._step_loop_press_points = []
        m._loop_press_points = []
        m._page_index = 0
        m._step_length = 0.25
        m._page_length = 2.0
        m._preview_mode = False
        m._clip = SimpleNamespace(loop_start=0.0, loop_end=2.0)
        for k, v in over.items():
            setattr(m, k, v)
        return m

    # ---- step grid ----
    def test_empty_step_is_grey_and_beat_markers_are_one_grey_brighter(self):
        m = self._seq()
        self.assertEqual(Melodic._pitch_rgb(m, 1, 60, 1), GREY_EMPTY)
        self.assertEqual(Melodic._pitch_rgb(m, 0, 60, 0), GREY_DIM)
        self.assertEqual(Melodic._pitch_rgb(m, 4, 60, 4), GREY_DIM)

    def test_the_anchor_row_is_grey_not_a_second_hue(self):
        m = self._seq()
        m._is_anchor_pitch.return_value = True
        self.assertEqual(Melodic._pitch_rgb(m, 1, 60, 1), GREY_MID)

    def test_a_note_takes_the_hue_scaled_by_velocity(self):
        m = self._seq()
        m._find_note_at_step_pitch.return_value = SimpleNamespace(velocity=90)
        self.assertEqual(Melodic._pitch_rgb(m, 1, 60, 1), ("HUE_VEL", 90))

    def test_held_beats_the_note_and_playhead_beats_held(self):
        m = self._seq()
        m._find_note_at_step_pitch.return_value = SimpleNamespace(velocity=90)
        m._is_cell_held.return_value = True
        self.assertEqual(Melodic._pitch_rgb(m, 1, 60, 1), RGB_WHITE)
        m._playhead_is_on_step.return_value = True
        self.assertEqual(Melodic._pitch_rgb(m, 1, 60, 1), RGB_WHITE)

    def test_the_playhead_over_empty_space_stays_grey(self):
        m = self._seq()
        m._playhead_is_on_step.return_value = True
        self.assertEqual(Melodic._pitch_rgb(m, 1, 60, 1), GREY_BRIGHT)

    # ---- loop backdrop ----
    def test_loop_inside_is_hue_and_outside_is_grey(self):
        m = self._seq()
        self.assertEqual(Melodic._step_loop_rgb(m, 0)[0], "HUE")
        m._clip = SimpleNamespace(loop_start=4.0, loop_end=6.0)
        self.assertEqual(Melodic._step_loop_rgb(m, 0), GREY_EMPTY)

    def test_range_anchor_and_playhead_are_white(self):
        m = self._seq(_step_loop_press_points=[2])
        self.assertEqual(Melodic._step_loop_rgb(m, 2), RGB_WHITE)
        m = self._seq()
        m._playhead_is_on_step.return_value = True
        self.assertEqual(Melodic._step_loop_rgb(m, 0), RGB_WHITE)

    # ---- page selector ----
    def test_current_page_is_full_hue_and_others_grey_or_loop_shade(self):
        m = self._seq(_page_index=1, _clip=SimpleNamespace(loop_start=0.0,
                                                           loop_end=2.0))
        self.assertEqual(Melodic._loop_rgb(m, 1), ("HUE", 8, 8))
        self.assertEqual(Melodic._loop_rgb(m, 0), ("HUE", 3, 8))
        self.assertEqual(Melodic._loop_rgb(m, 5), GREY_EMPTY)

    def test_preview_toggle_is_hue_on_grey_off(self):
        m = self._seq(_preview_mode=True)
        self.assertEqual(Melodic._loop_rgb(m, 7), ("HUE", 8, 8))
        m = self._seq(_preview_mode=False)
        self.assertEqual(Melodic._loop_rgb(m, 7), GREY_DIM)

    # ---- grid resolution selector ----
    def test_selected_resolution_is_hue_binary_and_ternary_split_on_grey(self):
        m = Mock()
        m._rgb_leds.return_value = True
        m._shade.side_effect = lambda level, levels=8: ("HUE", level, levels)
        m._grid_option_index = 2
        self.assertEqual(Melodic._grid_cell_color(m, 2), ("HUE", 8, 8))
        self.assertEqual(Melodic._grid_cell_color(m, 0), GREY_DIM)
        self.assertEqual(Melodic._grid_cell_color(m, 9), GREY_MID)
        self.assertEqual(Melodic._grid_cell_color(m, 99), RGB_BLACK)


class PaletteFallbackTest(unittest.TestCase):
    """SUPPORTS_RGB_LEDS False (the Mini overlay) must keep skin colours, so
    the device that has not been ported is left exactly as it was."""

    def test_skin_names_are_returned_when_the_device_has_no_rgb(self):
        env = load_handlers("melodic_step_sequencer.py", dict(
            {n: palette_env[n] for n in _PALETTE_NAMES},
            SUPPORTS_RGB_LEDS=False))
        seq = env["MelodicStepSequencerComponent"]
        m = Mock()
        m._rgb_leds = types.MethodType(seq._rgb_leds, m)
        self.assertFalse(m._rgb_leds())
        m._grid_option_index = 2
        self.assertEqual(seq._grid_cell_color(m, 2),
                         "MelodicSequencer.Control.GridSelected")
        self.assertEqual(seq._grid_cell_color(m, 9),
                         "MelodicSequencer.Control.GridTernary")


class RgbBatchTest(unittest.TestCase):
    def test_nested_passes_share_one_message(self):
        m = Mock(_rgb_batch=None, _rgb_batch_depth=0)
        for name in ("_begin_rgb_batch", "_flush_rgb_batch", "_write_rgb"):
            setattr(m, name, types.MethodType(getattr(Melodic, name), m))
        sent = []
        melodic_env["send_pad_rgb"] = lambda parent, specs: sent.append(specs)
        try:
            m._begin_rgb_batch()
            m._begin_rgb_batch()          # inner pass joins the outer batch
            m._write_rgb(11, (0, 127, 0))
            m._flush_rgb_batch()
            self.assertEqual(sent, [])    # inner flush must not send
            m._write_rgb(12, (0, 64, 0))
            m._flush_rgb_batch()
            self.assertEqual(sent, [[(11, (0, 127, 0)), (12, (0, 64, 0))]])
        finally:
            melodic_env["send_pad_rgb"] = palette_env["send_pad_rgb"]
