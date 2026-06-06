# Drum-variant picker — a grid overlay panel for choosing between the
# drum sequencer variants (Pro MK3: opened with Shift+Sequencer).
#
# The 8x8 grid renders three horizontal bands (2 rows each, separated by
# dark rows), one per variant:
#
#   rows 0-1  drum_sequence          (amber)   4x8 steps + pads + loop
#   rows 3-4  drum_64_sequence       (yellow)  one pad, 64 steps
#   rows 6-7  drum_4_track_sequence  (blue)    4 pads x 16 steps
#
# Tapping anywhere inside a band fires `on_select(mode_name)` — the parent
# wiring switches the main mode and this component gets disabled by the
# mode-change machinery. The band of the currently-active variant (passed
# via set_current_variant) renders bright; the others render dim.
#
# Like the sequencers, LED writes bypass the skin and go straight to the
# Programmer-mode palette (raw indices via palette.send_pad_color).
from __future__ import absolute_import, print_function, unicode_literals

from ableton.v2.control_surface import Component

from .palette import send_pad_color

# Band layout: mode → (top_row, bottom_row) inclusive, y=0 is the top row.
_BANDS = (
    ("drum_sequence", 0, 1),
    ("drum_64_sequence", 3, 4),
    ("drum_4_track_sequence", 6, 7),
)

# Raw Programmer-mode palette indices (0-127, firmware-standard). Bright =
# currently-active variant, dim = available. Tune on hardware if a shade
# reads wrong.
_COLOR_VALUES = {
    "Picker.Drum": 96,            # amber
    "Picker.DrumDim": 11,
    "Picker.Drum64": 13,          # yellow
    "Picker.Drum64Dim": 15,
    "Picker.Drum4Track": 37,      # blue
    "Picker.Drum4TrackDim": 39,
    "Picker.Off": 0,
}

_BAND_COLORS = {
    "drum_sequence": ("Picker.Drum", "Picker.DrumDim"),
    "drum_64_sequence": ("Picker.Drum64", "Picker.Drum64Dim"),
    "drum_4_track_sequence": ("Picker.Drum4Track", "Picker.Drum4TrackDim"),
}


class DrumVariantPickerComponent(Component):
    """Grid takeover panel; lives in `_main_modes` as "variant_picker"."""

    def __init__(self, on_select=None, logger=None, *a, **k):
        super(DrumVariantPickerComponent, self).__init__(*a, **k)
        self._on_select = on_select
        self._logger = logger
        self._grid_matrix = None
        # The variant whose band renders bright (the mode the user came
        # from, or the last one picked). None → all bands dim.
        self._current_variant = None

    def disconnect(self):
        self.set_grid_matrix(None)
        super(DrumVariantPickerComponent, self).disconnect()

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

    def set_current_variant(self, mode_name):
        """Which band renders bright. Accepts None or any mode name —
        non-variant names just mean "no band highlighted"."""
        self._current_variant = mode_name
        if self.is_enabled():
            self._render()

    def set_enabled(self, enabled):
        super(DrumVariantPickerComponent, self).set_enabled(enabled)
        if enabled:
            self._render()

    def update(self):
        super(DrumVariantPickerComponent, self).update()
        if self.is_enabled():
            self._render()

    # ---- input --------------------------------------------------------

    def _on_grid_matrix_value(self, value, x, y, _is_momentary):
        if not self.is_enabled() or not value:
            return
        mode = self._mode_for_row(y)
        if mode is None:
            return
        self._log("variant picked: {}".format(mode))
        if self._on_select is not None:
            self._on_select(mode)

    @staticmethod
    def _mode_for_row(y):
        for mode, top, bottom in _BANDS:
            if top <= y <= bottom:
                return mode
        return None

    # ---- LED rendering ------------------------------------------------

    def _render(self):
        if self._grid_matrix is None:
            return
        for y in range(8):
            mode = self._mode_for_row(y)
            if mode is None:
                color = "Picker.Off"
            else:
                bright, dim = _BAND_COLORS[mode]
                color = bright if mode == self._current_variant else dim
            for x in range(8):
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
                self._logger("[DrumVariantPicker] {}".format(message))
            except Exception:
                pass
