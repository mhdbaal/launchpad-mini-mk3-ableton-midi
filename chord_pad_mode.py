from __future__ import absolute_import, print_function, unicode_literals

from ableton.v2.base import listens
from ableton.v2.control_surface import Component
from ableton.v2.control_surface.input_control_element import ScriptForwarding

from .events import Event
from .palette import CHORD_COLOR_VALUES, send_pad_color
from .programmer_mode import AUDITION_CHANNEL


# 8x8 chord pad grid.
#   Columns 0..7 = scale degrees (I, ii, iii, IV, V, vi, vii°, I+1oct).
#   Rows    0..7 = octave shift; DEFAULT_ROW is the unshifted reference, rows
#                  above add octaves and rows below subtract them (top y=0 →
#                  high pitch, bottom y=7 → low pitch, mirroring the melodic
#                  sequencer's pitch-row convention).
GRID_WIDTH = 8
GRID_HEIGHT = 8
DEFAULT_ROW = 4

# Chord mode is fundamentally a 1-1 audition mapping per pad — see the
# docstring on ChordPadComponent for why "press one pad get a chord"
# actually requires Live's stock Chord MIDI effect (or a future M4L
# companion) on the armed track. Each pad still emits exactly one MIDI
# note via translation; the multi-note expansion happens downstream.
BASE_PITCH = 60          # MIDI middle C — the "natural" root for key C.
MIN_PITCH_OFFSET = -36   # 3 octaves down
MAX_PITCH_OFFSET = 36    # 3 octaves up
DEFAULT_VELOCITY = 100

# Curated scale list — mirrors the melodic sequencer so the two modes
# stay in sync musically. Same name → same intervals everywhere.
SCALES = (
    ("Major",            (0, 2, 4, 5, 7, 9, 11)),
    ("Minor",            (0, 2, 3, 5, 7, 8, 10)),
    ("Dorian",           (0, 2, 3, 5, 7, 9, 10)),
    ("Mixolydian",       (0, 2, 4, 5, 7, 9, 10)),
    ("Lydian",           (0, 2, 4, 6, 7, 9, 11)),
    ("Phrygian",         (0, 1, 3, 5, 7, 8, 10)),
    ("Locrian",          (0, 1, 3, 5, 6, 8, 10)),
    ("Harmonic Minor",   (0, 2, 3, 5, 7, 8, 11)),
    ("Melodic Minor",    (0, 2, 3, 5, 7, 9, 11)),
    ("Pentatonic Major", (0, 2, 4, 7, 9)),
    ("Pentatonic Minor", (0, 3, 5, 7, 10)),
    ("Blues",            (0, 3, 5, 6, 7, 10)),
)
DEFAULT_SCALE_INDEX = 0


# Chord types — each entry is `(name, scale_degree_offsets)`. Offsets are
# applied within the active scale (modulo len(scale), with each wrap bumping
# the octave). So a Triad on degree V correctly produces V + VII + II+1oct
# in the current key — proper diatonic harmonization, not parallel intervals.
CHORD_TYPES = (
    ("Triad",   (0, 2, 4)),         # 1 - 3 - 5
    ("7th",     (0, 2, 4, 6)),      # 1 - 3 - 5 - 7
    ("Sus4",    (0, 3, 4)),         # 1 - 4 - 5
    ("Sus2",    (0, 1, 4)),         # 1 - 2 - 5
    ("9th",     (0, 2, 4, 6, 8)),   # 1 - 3 - 5 - 7 - 9
    ("Power",   (0, 4)),            # 1 - 5
    ("Octave",  (0, 7)),            # 1 - 1+oct
    ("Root",    (0,)),              # 1 only (no chord — single note)
)
DEFAULT_CHORD_TYPE_INDEX = 0


# 12 key names (C..B). Indexed by self._key_index modulo 12 — adding a key
# bumps both the pad pitch AND the emitted chord pitches by `key_index`
# semitones above BASE_PITCH.
KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


# Scene-button slots (top → bottom). Slot 7 is the device shift, which is
# owned by `_stop_solo_mute_modes` at the top level and must not be touched.
CAPTURE_SLOT     = 0
KEY_CYCLE_SLOT   = 1
SCALE_CYCLE_SLOT = 2
CHORD_TYPE_SLOT  = 3
INVERSION_SLOT   = 4
# Slots 5 and 6 are free / disabled in v1.


# Number of available inversions. 0 = root position, 1 = first inversion
# (root bumped one octave up), 2 = second inversion (root + 3rd bumped),
# 3 = third inversion (root + 3rd + 5th bumped — only meaningful for
# chord types with >= 4 notes, otherwise wraps).
NUM_INVERSIONS = 4


class ChordPadComponent(Component):
    """8x8 chord-pad mode — pad press triggers a chord ROOT note.

    Layout
    ------
      Columns 0..7 → scale degrees (I, ii, iii, IV, V, vi, vii°, I+1oct).
      Rows    0..7 → octave shift. DEFAULT_ROW (=4) is the unshifted
                     reference; rows above bump pitch up by 12 per row,
                     rows below shift it down. The y-axis follows the
                     melodic sequencer convention: y=0 is the top of the
                     grid and the *highest* pitch.

    Why each pad plays only ONE note
    --------------------------------
    A Live MIDI Remote Script cannot inject arbitrary MIDI events into a
    track from the script side. The only path from a pad press to the
    track is `script_forwarding = non_consuming` plus a 1-1 identifier
    translation — i.e., one pad maps to exactly one note. There is no
    public API for "the script sends a chord to the track".

    The user gets a real chord-from-one-pad in two ways:
      1. Drop Live's stock **Chord** MIDI effect on the armed track. It
         adds fixed-interval voicings (e.g., +0/+4/+7 for a major triad)
         to every incoming note, so each pad's root note becomes a chord.
         Simple, no extra install — fixed intervals though (not
         diatonic), which is often fine for pop voicings.
      2. Listen to `Event.CHORD_TRIGGERED` from an external companion
         (e.g., an LP Chord M4L device, sibling to LP Notify). The event
         payload carries the *full* diatonic chord pitches, so the
         companion can play proper harmony per-degree. The script emits
         this event regardless of whether anything is listening.

    Per-pad audition still works: the user hears the root note in their
    DAW exactly as they'd expect from melodic preview mode.

    Scene buttons (top → bottom):
        0  Capture MIDI               (matches other modes)
        1  Cycle key                  (C → C# → ... → B → C)
        2  Cycle scale                (Major → Minor → ... → Blues)
        3  Cycle chord type           (Triad → 7th → Sus4 → ...)
        4  Cycle inversion            (root → 1st → 2nd → 3rd)
        5  (free)
        6  (free)
        7  Device shift               (owned by _stop_solo_mute_modes)

    Arrow buttons:
        ↑ / ↓  → pitch_offset ±12  (octave the whole pad layout up/down)
        ← / →  → pitch_offset ±1   (transpose by a semitone)
    """

    def __init__(self, event_bus=None, *a, **k):
        super(ChordPadComponent, self).__init__(*a, **k)
        self._event_bus = event_bus
        self._grid_matrix = None
        self._key_index = 0                       # 0..11 (C..B)
        self._scale_index = DEFAULT_SCALE_INDEX
        self._chord_type_index = DEFAULT_CHORD_TYPE_INDEX
        self._inversion = 0                       # 0..NUM_INVERSIONS-1
        self._pitch_offset = 0
        self._control_buttons = ()
        self._control_button_listeners = []
        # Dedupe sustained Note On bursts on a held pad and drive the
        # "Pressed" LED highlight on press / release.
        self._held_pads = set()
        self._device_shift_held = False
        # Parent's User button — held = mode selector active, gate scene
        # listener + LED writes (parent paints those slots itself).
        self._user_mode_button = None
        self._on_can_capture_midi_changed.subject = self.song

    def disconnect(self):
        self.set_control_buttons(None)
        self.set_grid_matrix(None)
        super(ChordPadComponent, self).disconnect()

    # ---- wiring -------------------------------------------------------

    def set_control_buttons(self, buttons):
        if self._control_buttons:
            for button, listener in self._control_button_listeners:
                try:
                    button.remove_value_listener(listener)
                except Exception:
                    pass
        self._control_buttons = tuple(buttons) if buttons is not None else ()
        self._control_button_listeners = []
        for index, button in enumerate(self._control_buttons):
            listener = self._make_control_button_listener(index)
            button.add_value_listener(listener)
            self._control_button_listeners.append((button, listener))
        self._update_control_leds()

    def set_grid_matrix(self, matrix):
        if matrix != self._grid_matrix:
            if self._grid_matrix is not None:
                self._grid_matrix.remove_value_listener(self._on_grid_matrix_value)
                self._clear_audition_translations()
            self._grid_matrix = matrix
            if self._grid_matrix is not None:
                self._grid_matrix.add_value_listener(self._on_grid_matrix_value)
            self._request_midi_map_rebuild()
            self.update()

    def set_enabled(self, enabled):
        super(ChordPadComponent, self).set_enabled(enabled)
        self._log("enabled: {}".format(enabled))
        if enabled:
            self._update_audition_translations()
            self.update()
        else:
            self._held_pads = set()
            self._turn_grid_off()
            self._clear_audition_translations()
            self._turn_control_buttons_off()

    def update(self):
        super(ChordPadComponent, self).update()
        if self.is_enabled():
            self._update_grid_leds()
            self._update_control_leds()

    # ---- arrow-button hooks (called from launchpad_mini_mk3.py) -------

    def adjust_pitch_offset(self, delta):
        """Public: transpose the chord layout by `delta` semitones."""
        if not self.is_enabled():
            return
        self._set_pitch_offset(self._pitch_offset + delta)

    def adjust_held_velocity(self, _delta):
        """Parity hook with the drum sequencers — chord mode has no
        held-step velocity gesture, so the parent's fallback to
        `adjust_pitch_offset` always runs."""
        return False

    def nudge_held_notes(self, _delta):
        """Parity hook with the drum sequencers — same rationale."""
        return False

    # ---- shift hook ---------------------------------------------------

    def set_device_shift_held(self, pressed):
        """Hook for the global shift modifier. Chord mode has no shift
        overlay in v1; the hook is here so the parent can call it
        uniformly. Future use: shift could cycle voicing spread / strum
        direction / inversion presets without taking a scene-button slot.
        """
        self._device_shift_held = bool(pressed)

    # ---- pad press ----------------------------------------------------

    def _on_grid_matrix_value(self, value, x, y, _is_momentary):
        if not self.is_enabled():
            return
        if value:
            if (x, y) in self._held_pads:
                # Dedupe sustained MIDI ons (some firmware repeats).
                return
            self._held_pads.add((x, y))
            self._emit_chord_triggered(x, y, int(value))
            self.update()
        else:
            if (x, y) not in self._held_pads:
                return
            self._held_pads.discard((x, y))
            self._emit(Event.CHORD_RELEASED,
                       degree=x,
                       root_pitch=self._pad_pitch(x, y))
            self.update()

    def _emit_chord_triggered(self, x, y, velocity):
        degree = x  # column index = scale-degree index
        root_pitch = self._pad_pitch(x, y)
        chord_pitches = self._compute_chord_pitches(x, y)
        self._log("pad pressed: ({},{}) deg={} root={} chord={}".format(
            x, y, degree, root_pitch, chord_pitches))
        self._emit(Event.CHORD_TRIGGERED,
                   degree=degree,
                   root_pitch=root_pitch,
                   chord_pitches=tuple(chord_pitches),
                   velocity=velocity)

    # ---- pitch + chord math -------------------------------------------

    def _effective_root(self):
        """Root MIDI pitch the layout is anchored to.

        Combines:
          - `BASE_PITCH`     fixed C4 baseline
          - `_key_index`     0..11 cycle (slot 1)
          - `_pitch_offset`  ±semitones from arrow buttons
        """
        return BASE_PITCH + self._key_index + self._pitch_offset

    def _pad_pitch(self, x, y):
        """MIDI pitch for pad (x, y). x = scale degree, y = octave-shift row.
        Wraps via the scale length so non-7-note scales (penta, blues)
        behave correctly: degree past the last index lands in the next
        octave's degree 0."""
        root = self._effective_root()
        scale = SCALES[self._scale_index][1]
        degree = x
        # Scale degree → semitone offset, wrapping into higher octaves.
        scale_offset = scale[degree % len(scale)] + 12 * int(degree / len(scale))
        octave_shift = (DEFAULT_ROW - y) * 12
        pitch = root + scale_offset + octave_shift
        return max(0, min(127, pitch))

    def _compute_chord_pitches(self, x, y):
        """Compute the full diatonic chord pitches for pad (x, y).

        Each interval from the active chord type is interpreted as a
        scale-degree offset (not a semitone offset!) — that is what makes
        the chord *diatonic*. Inversions bump the first N notes one
        octave up. The result is the chord that an LP Chord M4L companion
        would play; the actual pad-triggered audio only plays the root
        (see ChordPadComponent docstring).
        """
        root = self._effective_root()
        scale = SCALES[self._scale_index][1]
        intervals = CHORD_TYPES[self._chord_type_index][1]
        degree = x
        octave_shift = (DEFAULT_ROW - y) * 12
        pitches = []
        for i, interval in enumerate(intervals):
            d = degree + interval
            scale_offset = scale[d % len(scale)] + 12 * int(d / len(scale))
            inv_shift = 12 if i < self._inversion else 0
            pitch = root + scale_offset + octave_shift + inv_shift
            pitches.append(max(0, min(127, pitch)))
        return pitches

    # ---- audition translation -----------------------------------------

    def _clear_audition_translations(self):
        if self._grid_matrix is None:
            return
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                button = self._get_grid_button(x, y)
                if button is not None:
                    button.use_default_message()
                    button.script_forwarding = ScriptForwarding.exclusive
        self._request_midi_map_rebuild()

    def _update_audition_translations(self):
        """Wire every pad to forward its root pitch (1-1) on AUDITION_CHANNEL.

        Mirrors the melodic preview-mode pattern: non_consuming forwarding
        sends the translated Note On to the armed track AND lets the
        script's listener fire so we can light the pad and emit events.

        Audition stays on AUDITION_CHANNEL (=1) for the same collision
        reason explained in `melodic_step_sequencer._update_audition_
        translations`: channel-0 keys collide with other pads'
        original_identifier and the later registration wins, which would
        scramble routing across the matrix.
        """
        if self._grid_matrix is None or not self.is_enabled():
            return
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                button = self._get_grid_button(x, y)
                if button is None:
                    continue
                pitch = self._pad_pitch(x, y)
                button.set_identifier(pitch)
                button.set_channel(AUDITION_CHANNEL)
                button.script_forwarding = ScriptForwarding.non_consuming
        self._request_midi_map_rebuild()

    # ---- LED rendering ------------------------------------------------

    def _update_grid_leds(self):
        if self._grid_matrix is None:
            return
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                self._set_grid_light(x, y, self._pad_color(x, y))

    def _pad_color(self, x, y):
        """Skin name for pad (x, y).

        Layered priorities (top wins):
          1. Currently-held pad         → ChordPad.Pressed (WHITE)
          2. Row = DEFAULT_ROW (anchor) → bright variant of the column hue
          3. Otherwise                  → dim variant of the column hue
        The column hue depends on whether the degree is a chord tone of a
        diatonic triad rooted at degree 0 (the I): degrees 0/2/4/7 are
        chord-tones, others are scale tones — a useful at-a-glance hint
        for diatonic substitutions even when the current chord type isn't
        a plain triad.
        """
        if (x, y) in self._held_pads:
            return "ChordPad.Pressed"
        degree = x
        # Highlight the tonic and chord-tones of the I in the active scale.
        # Sharper than coloring per-actual-chord-type because the user
        # might cycle chord types but always wants "I-iii-V" as the
        # diatonic backbone of the layout.
        if degree == 0 or degree == 7:
            return "ChordPad.Root" if y == DEFAULT_ROW else "ChordPad.RootDim"
        if degree in (2, 4):
            return "ChordPad.ChordTone" if y == DEFAULT_ROW else "ChordPad.ChordToneDim"
        return "ChordPad.ScaleTone" if y == DEFAULT_ROW else "ChordPad.ScaleToneDim"

    def _set_grid_light(self, x, y, color):
        button = self._get_grid_button(x, y)
        if button is not None:
            send_pad_color(self.canonical_parent, button, color, CHORD_COLOR_VALUES)

    def _get_grid_button(self, x, y):
        try:
            return self._grid_matrix.get_button(y, x)
        except IndexError:
            return None

    def _turn_grid_off(self):
        if self._grid_matrix is None:
            return
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                self._set_grid_light(x, y, "DefaultButton.Disabled")

    # ---- scene-button column ------------------------------------------

    def _make_control_button_listener(self, index):
        def listener(value):
            self._on_control_button_value(index, value)
        return listener

    def set_user_mode_button(self, button):
        self._user_mode_button = button

    def _is_main_mode_selector_held(self):
        return (self._user_mode_button is not None
                and self._user_mode_button.is_pressed())

    def _on_control_button_value(self, index, value):
        if not self.is_enabled():
            return
        if not value:
            return
        if self._is_main_mode_selector_held():
            return
        if index == CAPTURE_SLOT:
            self._capture_midi()
        elif index == KEY_CYCLE_SLOT:
            self._cycle_key(1)
        elif index == SCALE_CYCLE_SLOT:
            self._cycle_scale(1)
        elif index == CHORD_TYPE_SLOT:
            self._cycle_chord_type(1)
        elif index == INVERSION_SLOT:
            self._cycle_inversion()
        # Slots 5-6 free; slot 7 reserved for stop-solo-mute.

    def _capture_midi(self):
        song = self.song
        if not getattr(song, "can_capture_midi", False):
            self._emit(Event.MIDI_CAPTURED, ok=False, reason="nothing to capture")
            return
        try:
            song.capture_midi()
            self._emit(Event.MIDI_CAPTURED, ok=True, reason="")
        except Exception as exc:
            self._log("capture_midi failed: {}".format(exc))
            self._emit(Event.MIDI_CAPTURED, ok=False, reason=str(exc))

    def _cycle_key(self, delta):
        self._key_index = (self._key_index + delta) % len(KEY_NAMES)
        self._update_audition_translations()
        self.update()
        self._emit(Event.CHORD_KEY_CHANGED,
                   key_index=self._key_index,
                   key_name=KEY_NAMES[self._key_index])

    def _cycle_scale(self, delta):
        self._scale_index = (self._scale_index + delta) % len(SCALES)
        self._update_audition_translations()
        self.update()
        self._emit(Event.CHORD_SCALE_CHANGED,
                   scale_index=self._scale_index,
                   scale_name=SCALES[self._scale_index][0])

    def _cycle_chord_type(self, delta):
        self._chord_type_index = (self._chord_type_index + delta) % len(CHORD_TYPES)
        self.update()
        self._emit(Event.CHORD_TYPE_CHANGED,
                   type_index=self._chord_type_index,
                   type_name=CHORD_TYPES[self._chord_type_index][0])

    def _cycle_inversion(self):
        self._inversion = (self._inversion + 1) % NUM_INVERSIONS
        self.update()
        self._emit(Event.CHORD_INVERSION_CHANGED,
                   inversion=self._inversion)

    # ---- arrow nav ----------------------------------------------------

    def _set_pitch_offset(self, offset):
        offset = max(MIN_PITCH_OFFSET, min(MAX_PITCH_OFFSET, offset))
        if offset == self._pitch_offset:
            return
        self._pitch_offset = offset
        self._update_audition_translations()
        self.update()
        octave = int(self._pitch_offset / 12)
        semitone = self._pitch_offset - octave * 12
        self._emit(Event.CHORD_NAV_CHANGED,
                   octave=octave,
                   semitone=semitone,
                   key_name=KEY_NAMES[self._key_index])

    # ---- control-row LEDs ---------------------------------------------

    def _update_control_leds(self):
        if not self._control_buttons:
            return
        if self._is_main_mode_selector_held():
            return
        capture = ("ChordPad.Control.CaptureMidiReady"
                   if getattr(self.song, "can_capture_midi", False)
                   else "ChordPad.Control.CaptureMidi")
        # Slot 5 = sequencer shift (relocated from slot 7). The chord pad
        # uses the same `_device_shift_held` flag as the sequencers even
        # though it doesn't currently bind any shift-gated affordance —
        # keeps the per-mode LED feedback consistent.
        shift_color = ("ChordPad.Control.Shift"
                       if self._device_shift_held
                       else "DefaultButton.Disabled")
        colors = (
            capture,                          # 0: Capture MIDI
            "ChordPad.Control.Key",           # 1: Key cycle
            "ChordPad.Control.Scale",         # 2: Scale cycle
            "ChordPad.Control.ChordType",     # 3: Chord type cycle
            "ChordPad.Control.Inversion",     # 4: Inversion cycle
            shift_color,                      # 5: seq shift
            "DefaultButton.Disabled",         # 6: free
            "DefaultButton.Disabled",         # 7: reserved (session-only)
        )
        for index, button in enumerate(self._control_buttons):
            try:
                button.set_light(colors[index] if self.is_enabled()
                                 else "DefaultButton.Disabled")
            except Exception:
                pass

    def _turn_control_buttons_off(self):
        for button in self._control_buttons:
            try:
                button.set_light("DefaultButton.Disabled")
            except Exception:
                pass

    # ---- listeners ----------------------------------------------------

    @listens("can_capture_midi")
    def _on_can_capture_midi_changed(self):
        if self.is_enabled():
            self._update_control_leds()

    # ---- utilities ----------------------------------------------------

    def _emit(self, event_name, **payload):
        if self._event_bus is not None:
            self._event_bus.emit(event_name, **payload)

    def _request_midi_map_rebuild(self):
        try:
            self.canonical_parent.request_rebuild_midi_map()
        except Exception:
            pass

    def _log(self, message):
        try:
            self.canonical_parent._c_instance.log_message("[ChordPad] {}".format(message))
        except Exception:
            pass
