# Custom-mode picker — a grid overlay panel for choosing between OUR
# script modes (Pro MK3: opened with Shift+Session).
#
# Rationale: on the Pro, plain mode-button presses hand the device to its
# NATIVE engines, and the firmware already owns every Shift+button combo
# in native land (Shift+Note = scale settings, Shift+Sequencer = sequencer
# settings, Shift+Projects = save project, ...). Using those combos for
# our modes collided with that muscle memory — so our modes live behind
# ONE gesture instead: Shift+Session → a panel of large zones on the 8x8
# grid. Bonus: a stray Shift+Session pressed in native land makes the
# firmware switch to the session layout, which the polling reclaim
# detects — the same reflex leads back to script-land from anywhere.
#
#   ┌─────────────┬─────────────┐
#   │   melodic   │ chord pads  │   rows 0-3
#   ├─────────────┼─────────────┤
#   │             │   drum 64   │   rows 4-5
#   │ drum (4x8)  ├─────────────┤
#   │             │ drum 4-trk  │   rows 6-7
#   └─────────────┴─────────────┘
#     cols 0-3        cols 4-7
#
# Tapping a zone fires `on_select(mode_name)`; the parent wiring switches
# the main mode (which disables this component). The zone of the mode the
# user came from renders bright, the others dim.
#
# Like the sequencers, LED writes bypass the skin and go straight to the
# Programmer-mode palette (raw indices via palette.send_pad_color).
from __future__ import absolute_import, print_function, unicode_literals

from ableton.v2.control_surface import Component

from .palette import send_pad_color

# Zones: mode → (x0, x1, y0, y1) inclusive bounds, y=0 is the top row.
_ZONES = (
    ("melodic_sequence", 0, 3, 0, 3),
    ("chord_mode", 4, 7, 0, 3),
    ("drum_sequence", 0, 3, 4, 7),
    ("drum_64_sequence", 4, 7, 4, 5),
    ("drum_4_track_sequence", 4, 7, 6, 7),
)

# Raw Programmer-mode palette indices (0-127, firmware-standard). Bright =
# the mode the user came from, dim = available. Tune on hardware if a
# shade reads wrong.
_COLOR_VALUES = {
    "Picker.Melodic": 41,         # blue-ish (matches the Note-button LED)
    "Picker.MelodicDim": 43,
    "Picker.Chord": 53,           # purple
    "Picker.ChordDim": 55,
    "Picker.Drum": 96,            # amber
    "Picker.DrumDim": 11,
    "Picker.Drum64": 13,          # yellow
    "Picker.Drum64Dim": 15,
    "Picker.Drum4Track": 37,      # blue
    "Picker.Drum4TrackDim": 39,
    "Picker.Off": 0,
}

_ZONE_COLORS = {
    "melodic_sequence": ("Picker.Melodic", "Picker.MelodicDim"),
    "chord_mode": ("Picker.Chord", "Picker.ChordDim"),
    "drum_sequence": ("Picker.Drum", "Picker.DrumDim"),
    "drum_64_sequence": ("Picker.Drum64", "Picker.Drum64Dim"),
    "drum_4_track_sequence": ("Picker.Drum4Track", "Picker.Drum4TrackDim"),
}


class ModePickerComponent(Component):
    """Grid takeover panel; lives in `_main_modes` as "mode_picker"."""

    def __init__(self, on_select=None, logger=None, *a, **k):
        super(ModePickerComponent, self).__init__(*a, **k)
        self._on_select = on_select
        self._logger = logger
        self._grid_matrix = None
        # The mode whose zone renders bright (where the user came from).
        # None → all zones dim.
        self._current_mode = None

    def disconnect(self):
        self.set_grid_matrix(None)
        super(ModePickerComponent, self).disconnect()

    # ---- Layer binding ------------------------------------------------

    def set_grid_matrix(self, matrix):
        if matrix == self._grid_matrix:
            return
        if self._grid_matrix is not None:
            try:
                self._grid_matrix.remove_value_listener(self._on_grid_matrix_value)
            except Exception:
                pass
        self._grid_matrix = matrix
        if self._grid_matrix is not None:
            self._grid_matrix.add_value_listener(self._on_grid_matrix_value)
        if self.is_enabled():
            self._render()

    # ---- public -------------------------------------------------------

    def set_current_mode(self, mode_name):
        """Which zone renders bright. Accepts None or any mode name —
        non-zone names just mean "no zone highlighted"."""
        self._current_mode = mode_name
        if self.is_enabled():
            self._render()

    def set_enabled(self, enabled):
        super(ModePickerComponent, self).set_enabled(enabled)
        if enabled:
            self._render()

    def update(self):
        super(ModePickerComponent, self).update()
        if self.is_enabled():
            self._render()

    # ---- input --------------------------------------------------------

    def _on_grid_matrix_value(self, value, x, y, _is_momentary):
        if not self.is_enabled() or not value:
            return
        mode = self._mode_for_cell(x, y)
        if mode is None:
            return
        self._log("mode picked: {}".format(mode))
        if self._on_select is not None:
            self._on_select(mode)

    @staticmethod
    def _mode_for_cell(x, y):
        for mode, x0, x1, y0, y1 in _ZONES:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return mode
        return None

    # ---- LED rendering ------------------------------------------------

    def _render(self):
        if self._grid_matrix is None:
            return
        for y in range(8):
            for x in range(8):
                mode = self._mode_for_cell(x, y)
                if mode is None:
                    color = "Picker.Off"
                else:
                    bright, dim = _ZONE_COLORS[mode]
                    color = bright if mode == self._current_mode else dim
                button = self._get_grid_button(x, y)
                if button is not None:
                    send_pad_color(self.canonical_parent, button, color, _COLOR_VALUES)

    def _get_grid_button(self, x, y):
        try:
            return self._grid_matrix.get_button(y, x)
        except IndexError:
            return None

    def _log(self, message):
        if self._logger is not None:
            try:
                self._logger("[ModePicker] {}".format(message))
            except Exception:
                pass
