# CLAUDE.md

Internal reference for working on this repo. The user-facing feature description lives in `README.md` — read that first for a tour. This file focuses on the architecture, the wiring between modes, and the conventions/gotchas that are not obvious from reading any single file.

## What this is

A custom Ableton Live 12 MIDI Remote Script for the **Novation Launchpad Mini MK3**. It replaces the factory `Launchpad_Mini_MK3` script shipped with Live (a decompiled copy lives under `midi-remote-scripts/Launchpad_Mini_MK3/` for reference) and extends it with:

- a 4-mode bottom row (Select/Arm, Stop, Solo, Mute) cycled by the bottom-right scene button (the "shift" button),
- clip and scene copy-paste while shift is held,
- a Push-style drum step sequencer,
- a Launchpad95-style melodic step sequencer,
- direct Programmer-mode LED rendering for the sequencers.

It is built on top of Novation's official framework (`NovationBase`) — every component subclasses or composes a Novation/Ableton v2 control-surface primitive.

## Top-level mode hierarchy

Three nested mode layers run simultaneously:

1. **`_main_modes`** (cycled by the **User** button) — three modes: `session`, `drum_sequence`, `melodic_sequence`. Switches whole subsystems on/off via `__on_main_mode_changed` in `launchpad_mini_mk3.py`. Entering a sequencer mode calls `_set_session_components_enabled(False)`, restores pad MIDI mapping, enables the sequencer, and rewrites the four mode-button LEDs via Programmer-mode CCs.
2. **`_session_modes`** (cycled by the **Session** button, top-right) — only meaningful while `_main_modes == "session"`. Two modes: `launch` (8×8 clip grid) and `overview` (session overview + arrow nav).
3. **`_stop_solo_mute_modes`** (cycled by the **shift** button = `scene_launch_buttons_raw[7]`) — only meaningful while `_main_modes == "session"`. Four modes for the bottom row: `select` (default), `stop`, `solo`, `mute`. `select` mode uses `ChannelStripComponentWithArmToggle` (smart arm-on-second-press).

`TransportComponent` binds the **Drums** button (CC 96) to play/stop and the **Keys** button (CC 97) to session record. It stays live in **every** main mode — global transport is useful regardless of whether the grid is showing the session, the drum sequencer, or the melodic sequencer. Enable is driven by `__on_main_mode_changed` (`self._transport.set_enabled(True)`) — NOT by `_set_session_components_enabled`. None of the `_set_mode_button_lights` branches touch the Drums/Keys CCs (transport owns them in all modes).

The **Session button** (CC 95) gets an extra Push-style momentary-preview behavior while in EITHER sequencer main mode (`drum_sequence` or `melodic_sequence`, see `__on_session_mode_button_value` in `launchpad_mini_mk3.py`): press latches main mode to `session` and remembers which sequencer to return to in `self._session_preview_return_mode`; release decides — tap (≤ `SESSION_HOLD_THRESHOLD`s) keeps session, hold reverts to the originating sequencer. No interference with the standard `session_modes` `cycle_mode_button` because that uses `.pressed` (transition not_pressed→pressed) and session_modes' Button State is freshly constructed at `set_enabled(True)` with `_is_pressed=False`; the release that follows simply transitions False→False, no event fired. In `session` main mode the listener is a no-op and the button keeps its `session_modes` semantics.

The shift button (`scene_launch_buttons_raw[7]`, a.k.a. stop-solo-mute) is overloaded five ways:
  - in `session` main mode: **press to cycle** the bottom-row mode (select/stop/solo/mute), **hold + tap clip slot** to copy/paste a clip, **hold + tap scene button** to copy/paste a scene; release clears both clipboards (`__on_shift_button_value`).
  - in sequencer main modes (drum or melodic): acts as a **modifier**. While the modifier is effective ("held or locked"), the shift-gated controls are visible and responsive — the grid-resolution slots 0-3, the triplet toggle (slot 4), and in the melodic sequencer the **top row** (page selector + preview toggle). Otherwise everything stays greyed (`DefaultButton.Disabled`) and presses are ignored. Each sequencer exposes `set_device_shift_held(bool)` which the parent calls from `__on_shift_button_value` with the effective state.
  - **shift lock**: a **double-tap** on the shift button (two quick presses, each release within `SHIFT_LOCK_TAP_THRESHOLD` ≈ 0.3s, with release-to-release gap ≤ `SHIFT_DOUBLE_TAP_WINDOW` ≈ 0.35s) toggles a sticky `self._shift_locked` flag in the parent. **Sequencer modes only** — in session mode the same button cycles stop-solo-mute and a tap-based toggle would clash, so the detector is gated on `_main_modes.selected_mode in ("drum_sequence", "melodic_sequence")`. While locked, "effective shift" stays on without the user holding the button. Another double-tap clears the lock. A long press (> threshold) resets the double-tap detector so "hold + tap" never accidentally locks. Clipboards still clear on physical release (copy-paste is tied to the hold gesture, not the lock). User feedback: `show_message("Shift LOCKED / unlocked")` in Live's status bar AND slot 7 LED in sequencer modes lights up `Control.Shift` (AMBER) while the modifier is effective (held or locked) — the LED stays on after release if the lock just engaged, so the user can see the state without watching the status bar.

## File map (what lives where)

| File | Responsibility |
|------|---------------|
| `__init__.py` | Capabilities + port declarations; `create_instance` returns the control-surface class. |
| `launchpad_mini_mk3.py` | Top-level `NovationBase` subclass. Owns all mode components, wiring, Programmer-mode SysEx, mode-button LED writes. |
| `elements.py` | Hardware element layer. Adds `drums_mode_button`/`keys_mode_button`/`user_mode_button` and a `Session_Button_Color_Element` (color SysEx) on top of `LaunchpadElements`. |
| `skin.py` | Color skin. Defines `Mode.Session.Launch/Overview`, `Mixer.TrackSelected`, plus full `DrumSequencer.*` / `MelodicSequencer.*` palettes. Merged into the Novation base skin via `merge_skins`. |
| `sysex_ids.py` | `LP_MINI_MK3_FAMILY_CODE = (19, 1)`, `LP_MINI_MK3_ID = 13`. |
| `channel_strip_with_arm_toggle.py` | `ChannelStripComponentWithArmToggle`. Click unselected → select; click selected → toggle arm. Honors `song.exclusive_arm` and multi-track selection. Listens to track `arm` to repaint. |
| `clip_copy_component.py` | `ClipCopyComponent` — clipboard state for clips; validates audio/MIDI compatibility; uses `duplicate_clip_to`. |
| `scene_copy_component.py` | `SceneCopyComponent` — inserts a new scene at the target index, duplicates each non-empty source slot, copies name/color/tempo/time-sig. |
| `clip_slot_with_copy.py` | `ClipSlotComponentWithCopy` — intercepts `_on_launch_button_pressed` and routes to the clip copy handler when shift is held. |
| `transport_component.py` | `TransportComponent` — Drums button = global play/stop toggle, Keys button = session record toggle. Active in every main mode (session, drum_sequence, melodic_sequence). |
| `session_with_copy.py` | `SessionComponentWithCopy` + `SceneComponentWithCopy`. Propagates the shift button and the two copy handlers to every clip slot / scene (including dynamically created ones via `_create_scene`). |
| `notifying_background.py` | `BackgroundComponent` that fires a `value` event instead of swallowing it — used to refresh the layout switch when Drums/Keys mode buttons are pressed. |
| `drum_step_sequencer.py` | `DrumStepSequencerComponent`. 4×8 step grid (top), 4×4 drum-pad selector (bottom-left), 4×4 loop page selector (bottom-right). Step pads support hold-gestures: holding a step with a note + arrow keys edits its velocity (Up/Down) or nudges it (Left/Right); holding a step with a note + pressing another step extends the note's length. Owns its own LED rendering, audition translations, runtime step-grid resolution (1/4–1/32), and the scene-button control row. |
| `melodic_step_sequencer.py` | `MelodicStepSequencerComponent`. 7×8 pitch×step grid + 1 bottom row (7 page pads + 1 preview-toggle pad). Scale-aware pitch rows. |
| `event_bus.py` | Tiny sync pubsub. Components emit semantic events; subscribers translate them to UI side-effects. |
| `events.py` | `Event.*` string constants (event names + payload-shape comments) — the contract between emitters and subscribers. |
| `notification_catalog.py` | `Msg.*` integer wire IDs shared with the LP Notify Max for Live device. Append-only protocol. Also `GRID_RESOLUTION_INDICES`, `MODE_ID_*`. |
| `status_bar_subscriber.py` | Subscribes to the bus, formats events into strings, calls `show_message`. Single owner of every user-visible status-bar wording. |
| `m4l_subscriber.py` | Subscribes to the bus, maps events to `(msg_id, args)`, forwards to the dispatcher. No-op when no LP Notify device is present. |
| `notification_dispatcher.py` | Discovers an LP Notify M4L device on any track (regular/return/master), binds its `device.parameters` by name, writes `msg_id/arg1-3/seq` on each `send()`. Refreshes on add/remove/rename. |
| `install.sh` | WSL → Windows install (copies `*.py` into the Ableton MIDI Remote Scripts folder, optionally clears `Log.txt`). Paths are hard-coded for `mahed`'s machine. |

## Reference tree

`midi-remote-scripts/` (gitignored) is a decompiled snapshot of Ableton 12's bundled Python scripts. It is **read-only context** — never edit it. Useful subtrees:

- `midi-remote-scripts/Launchpad_Mini_MK3/` — the stock script this repo replaces. Diff against it to understand minimal extensions.
- `midi-remote-scripts/novation/` — base framework. The classes we actually subclass/use: `NovationBase`, `LaunchpadElements`, `SessionModesComponent`, `ChannelStripComponent`, `MixerComponent`, `SessionNavigationComponent`, plus `sysex.py`, `colors.py`, `skin.py`.
- Other vendor folders (`APC*`, `Push*`, etc.) are useful for finding precedent patterns (drum group components, step sequencers, etc.).

## Key subsystems

### Programmer mode + direct LED writes

On `on_identified` we put the device into **Programmer mode** (SysEx command byte 14, value 1) with **external feedback on** and sleep off. In Programmer mode the pads no longer respond to skin colors via the normal element-color path; LEDs must be driven explicitly.

- `launchpad_mini_mk3.py::_send_programmer_cc` writes the four CC-controlled mode buttons (`SESSION_BUTTON_CC=95`, `DRUMS=96`, `KEYS=97`, `USER=98`) via a CC on channel 0.
- Both sequencers' `_send_programmer_pad_color` writes a `Note On` on channel 0 (`status = 144`) for the pad's `original_identifier()`. The color value is a raw Novation palette index (0–127), **not** a `Color` instance. Each sequencer keeps its own `*_COLOR_VALUES` dict that maps skin-style names to those palette indices — the skin is consulted only by name; the actual LED write bypasses it. Keep the dict in sync with `skin.py` if you add a new color.
- On `disconnect` we exit Programmer mode and force the firmware back to Standalone via `firmware_mode_switch` so the device is left in a usable state.

### Audition translations (note forwarding to Live)

Sequencer pads that should play a sound when pressed (drum-pad selector grid; melodic grid in preview mode) reassign their MIDI identifier and switch `script_forwarding` to `ScriptForwarding.non_consuming`, so the note both reaches the script (for selection/toggle) **and** is forwarded to Live to audition the sound. `_update_audition_translations` / `_clear_audition_translations` set this up and tear it down; both end with `request_rebuild_midi_map()`. The drum sequencer enables `set_feedback_channels([DRUM_FEEDBACK_CHANNEL])` (=1) in `on_identified` so Live's drum-pad feedback lights the selector pads.

**Audition pads live on channel 1, not channel 0.** Live's MIDI forwarding registry is keyed by `(channel, identifier)`. The translated audition pitches (drum sequencer: 36–51, melodic: scale-dependent) coincide with the `original_identifier` of OTHER pads in the same matrix — the bottom-right loop pad at Excel E:5 has note 45, which is also the pitch a drum-pad selector translates to. If both registered on channel 0, the later registration wins and pressing E:5 (loop) routes to the drum-pad button (plays a drum sound, no page change). Translating audition to channel 1 (drum `PLAY_CHANNEL`, melodic `set_channel(1)`) makes the keys disjoint and matches `DRUM_FEEDBACK_CHANNEL` so LED feedback still round-trips. Don't move audition back to channel 0 without checking this.

### Loop scoping pattern (drum + melodic)

The same idiom appears in both sequencers (`_handle_loop_press`):

- **Single tap on a page pad** → view that page (don't shrink loop).
- **Double-tap (≤0.35s) on a page pad** → scope clip loop to that single page.
- **Hold one page pad + press another** → scope clip loop to the page range. `_loop_range_active` blocks the release-time double-tap path.
- Loop changes go through `_set_clip_loop(start, end)`, which also moves `start_marker`/`end_marker`. The order of `loop_start`/`loop_end` assignment matters when shifting the loop forward (avoid `start >= end` momentarily).

### Sequencer side-control row (scene buttons)

When a sequencer is active, the 8 right-column scene buttons become a control strip (`set_control_buttons`).

**Drum sequencer** layout (page +/- removed — the bottom-right 4×4 page selector already does navigation; octave/semitone moved to the top arrows; slot 7 is the shared device shift / stop-solo-mute button owned by `_stop_solo_mute_modes` in session mode and intentionally left untouched by the drum sequencer):

| idx | function | LED skin key |
|---|---|---|
| 0 | Capture MIDI (clip action, always on) | `CaptureMidiReady` (GREEN) when `song.can_capture_midi`, else `CaptureMidi` (GREEN_HALF) |
| 1 | Quantize Selected (clip action, always on) | `Quantize` (AQUA) |
| 2 | (free) | `DefaultButton.Disabled` |
| 3 | (free) | `DefaultButton.Disabled` |
| 4 | (free) | `DefaultButton.Disabled` |
| 5 | (free) | `DefaultButton.Disabled` |
| 6 | cycle button — bottom-right 4x4 mode: loop ↔ grid | `CycleLoop` (AQUA) in loop mode, `CycleGrid` (ORANGE) in grid mode |
| 7 | (untouched — device shift / stop-solo-mute) | (driven by `_stop_solo_mute_modes` in session) |

Slot indices come from `CAPTURE_SLOT`/`QUANTIZE_SLOT`/`CYCLE_SLOT` in `drum_step_sequencer.py`. **Grid resolution selection has moved off the scene buttons** into the bottom-right 4×4 (cycled into "grid" mode via slot 6) — see "Bottom-right 4×4 modes" below. Capture MIDI wraps `song.capture_midi()` with a `can_capture_midi` guard; LED brightness reflects availability via the `can_capture_midi` listener. Quantize is documented in "Clip-level actions" further down.

### Bottom-right 4×4 modes (drum + melodic)

The slot 6 cycle button toggles the bottom-right 4×4 between two modes. Drum starts in `loop`, melodic in `pitch`. State per sequencer: `self._bottom_right_mode`.

**Drum:**
- `loop` (default): 16 page pads (existing page-selector / loop-scope behavior).
- `grid`: 16 grid resolutions from `GRID_OPTIONS`. Press any cell to pick that resolution.

**Melodic:**
- `pitch` (default): the bottom-right 4×4 cells continue the pitch grid (no change from before).
- `grid`: those 16 cells become the resolution selector. The rest of the pitch grid keeps its normal pitch behavior. Cycling back to `pitch` restores the pitch cells unchanged.

`GRID_OPTIONS` (same tuple in both sequencers, defined per-file) lays out 16 resolutions across the 4x4 grid as 8 binaries (cells 0–7) followed by 8 ternaries (cells 8–15): row 0 = `1/4, 1/8, 1/16, 1/32`, row 1 = `1/64, 1/128, 1/256, 1/512`, row 2 = `1/4t, 1/8t, 1/16t, 1/32t`, row 3 = `1/64t, 1/128t, 1/256t, 1/512t`. **Ternary cells render in a distinct color** (`Control.GridTernary` = PURPLE) so binary/ternary is visible at a glance — `TERNARY_FIRST_INDEX = 8` is the split point. The selected cell always wins with `GridSelected` (WHITE) regardless of family. Internal state is a single `self._grid_option_index` (0..15) — replacing the old `_grid_binary_index` + `_is_triplet` pair. `_current_grid_label()` reads the label from `GRID_OPTIONS[self._grid_option_index][1]`; events still emit a `is_triplet` flag derived from `label.endswith("t")` for back-compat with the M4L wire format.

Shift-held step-loop range picker (drum: top 4×8; melodic: rows 1–7) keeps priority over the bottom-right mode — pressing a bottom-right cell with shift held fires the step-loop picker (X coord), not the grid selector. The LED in melodic also follows: shift held = loop-range colors on rows 1–7 including bottom-right; shift not held = pitch colors (or grid colors in grid mode). **The grid slots and the triplet toggle are shift-gated**: `_grid_color_for_slot`/`_triplet_color` return `DefaultButton.Disabled` and `_on_control_button_value` ignores those presses unless `self._device_shift_held` is true. The parent control surface flips that flag via `set_device_shift_held(...)` from `__on_shift_button_value` with the effective state. The grid resolution is split into two orthogonal pieces of state: `self._grid_binary_index` (0..3 selecting `GRID_BINARY_OPTIONS[i]`) and `self._is_triplet` (bool). The effective step length is `binary × TRIPLET_FACTOR` when the triplet flag is on, else just the binary value — mirroring Live's `GRID_RESOLUTIONS` from `ableton/v3/control_surface/components/grid_resolution.py` (4 binary divisions × triplet flag = 8 effective resolutions). `GRID_BINARY_OPTIONS` is ordered finest-first (slot 0 = 1/32 at the top, slot 3 = 1/4 at the bottom) so the visible scene-button column reads "fine → coarse" going down. Pressing slot 0-3 selects the binary slot; pressing slot 4 flips the triplet flag without touching the selected binary, so `1/16 → 1/16t` and back. `STEP_LENGTH`/`PAGE_LENGTH` used to be module constants but are now per-instance (`self._step_length`, `self._page_length`) since they change at runtime via `_set_step_length`. Existing notes are NOT remapped on grid change — only the step-to-time alignment changes, so a 1/16 note already in the clip starts in step 0 at 1/16, step 0 at 1/32 (because both windows start at beat 0), or some non-step-0 column if the start time isn't aligned to the new grid. Pages, loop scoping, and clip-creation lengths all scale with `self._page_length`.

### Step-pad hold gestures (drum sequencer)

Pressing a step pad no longer toggles the step on press — it toggles on **release**, leaving the press to act as a gesture anchor. State: `self._held_step_pads` is a dict mapping `pad_step → note_step` (the absolute step where the held pad's note currently sits, or `None` if the pad was pressed on an empty step). `note_step` is updated when a nudge moves the note. `self._consumed_step_pads` collects pad_steps whose release should NOT toggle — set whenever a gesture has used the hold (extension target, length-extension anchor, or arrow edit). The release path checks "consumed?" first; if so the toggle is suppressed and the pad is dropped.

Three gestures are layered on top of this hold:

- **Length extension** (hold step A with a note + press step B): `_anchor_for_extension` finds the first held pad whose tracked note still exists. If found AND a different step is pressed, `_extend_note_length` keeps the note's start time, sets duration to `(end_step - start_step + 1) * step_length`, and both A and B are marked consumed. Calls `_ensure_loop_contains_time` for the new tail — but the gate (see "Conventions and gotchas" below) means the loop only auto-extends while `_clip_just_created` is True; on an established clip, an extended note can run past `loop_end` and is silent in the unplayed tail.
- **Velocity edit via arrows** (hold step with a note + Up/Down): the parent control surface routes Up/Down to `adjust_held_velocity(±DRUM_VELOCITY_ARROW_STEP)`. That iterates every held pad with a note and bumps each note's velocity by ±8, clamped to `[VELOCITY_MIN, VELOCITY_MAX]`. Returns True if at least one note was modified; the parent uses the return value to decide whether to fall back to the legacy `adjust_pitch_offset(±12)` (no held pad → behaves as before). The pad is added to `_consumed_step_pads` so its release doesn't toggle.
- **Nudge via arrows** (hold step with a note + Left/Right): same fallback pattern, but routes to `nudge_held_notes(±1)`. The note's start time moves by ±`step_length`; the held entry is updated to the new note position so subsequent arrow presses keep editing the same note even after it moved. New_start < 0 is rejected (no-op). The loop is auto-extended if the move pushed the note's end past `loop_end`.

LED feedback: `_step_color` returns `DrumSequencer.StepHeld` (AMBER) for any step that is in `_held_step_pads` — overrides the base StepEmpty/StepActive but is itself overridden by the playhead colors. The user sees their finger position. The note's actual current position (which may differ from the held pad after nudges) shows in the normal StepActive color elsewhere.

Note: this changes the default tap-toggle latency by one release-cycle. A pure tap (press + immediate release) still toggles the step exactly once; the difference is that the visual feedback now happens on release rather than press. In practice imperceptible. `_replace_note` is the helper that removes the original note and re-adds it with attribute overrides — used by all three gestures so the Live API call shape is in one place.

### Clip-level actions: Capture MIDI + Quantize Selected (drum + melodic)

Both sequencers expose two clip-level actions on scene-button slots **0** (Capture MIDI) and **1** (Quantize Selected), at the top of the scene-button column. Drum: always available there. Melodic: dual-purpose — shift held shows chromatic/scale toggles on those same slots, shift not held shows Capture/Quantize.

- **Capture MIDI** wraps `song.capture_midi()` gated on `song.can_capture_midi`. If nothing is capturable, a no-op + `MIDI_CAPTURED ok=False` event is emitted (so the status bar tells the user why nothing happened). The LED reflects `can_capture_midi` via a `@listens("can_capture_midi")` listener on both sequencers, going dim (`CaptureMidi`) → bright (`CaptureMidiReady`) as soon as the song reports capturable input.
- **Quantize Selected** scope is the SET OF NOTES UNDER CURRENTLY-HELD STEP PADS. Hold one or more pads with notes, press Quantize → only those notes snap to the current step grid (100% pull). With no held pads the fallback is "all notes of the selected drum pad" (drum) or "all notes in the clip" (melodic). Math is `round(note.start_time / step_length) * step_length` per note. Held pads get their tracked positions updated AND marked `_consumed_step_pads` so the implicit release-toggle is suppressed. Emits `DRUM_NOTES_QUANTIZED` / `MELODIC_NOTES_QUANTIZED` with `count`, `scope`, and grid label.

The melodic sequencer was refactored to mirror drum's "toggle on release" pattern so the hold-without-toggle gesture works there too — see `_held_note_cells` + `_consumed_note_cells` + the `(x, y) not in _held_grid_buttons: return` guard in `_on_grid_matrix_value`. Without that change, pressing a pitch cell would immediately remove the note and the subsequent Quantize would have nothing to operate on.

**Melodic sequencer** layout — top to bottom, with slots 0/1 dual-purpose (clip actions when shift is NOT held, scale/chromatic toggles when shift IS held), grid/triplet shift-gated as in the drum sequencer. The bottom row of the grid carries 7 page pads (pages 0-6) + a preview toggle at `(7, 7)`; octave/semitone live on the top arrows; slot 7 is the device shift.

| idx | function | LED skin key |
|---|---|---|
| 0 | **chromatic toggle** *(shift held)* / **Capture MIDI** *(shift not held)* | `Grid`/`GridSelected` when shift held; `CaptureMidi`/`CaptureMidiReady` when shift not held |
| 1 | **scale cycle** *(shift held)* / **Quantize Selected** *(shift not held)* | `ScaleCycle` (AQUA) when shift held; `Quantize` (AQUA) when shift not held |
| 2 | (free) | `DefaultButton.Disabled` |
| 3 | (free) | `DefaultButton.Disabled` |
| 4 | (free) | `DefaultButton.Disabled` |
| 5 | (free) | `DefaultButton.Disabled` |
| 6 | cycle button — bottom-right 4x4 mode: pitch ↔ grid | `CycleLoop` (AQUA) in pitch mode, `CycleGrid` (ORANGE) in grid mode |
| 7 | (untouched — device shift / stop-solo-mute) | (driven by `_stop_solo_mute_modes` in session) |

Grid resolution selector lives in the bottom-right 4×4 when slot 6 is in "grid" mode (see "Bottom-right 4×4 modes"); scene-button slots 2–5 are intentionally free. Slot 0 (`CHROMATIC_SLOT` = `CAPTURE_SLOT`) toggles `self._chromatic_mode` when shift is held: when off the pitch grid is scale-based (8 rows = 1 octave of `_current_scale`, `degree = 7 - y`, wraps via `scale[degree % len(scale)] + 12 * (degree // len(scale))`); when on the grid is chromatic (`pitch = root + (7 - y)`, every row is exactly one semitone above the row below). Slot 1 (`SCALE_CYCLE_SLOT` = `QUANTIZE_SLOT`) cycles `self._scale_index` through the `MELODIC_SCALES` tuple. `_current_scale()` reads from `_scale_index` instead of `song.scale_name` so the user gets explicit, on-device control. Toggling chromatic or cycling scale does NOT move existing notes — they keep their absolute pitches; only the row→pitch mapping changes. Both also affect `_update_audition_translations` indirectly via `_pitch_for_row` (each pitch row routes to its mode-dependent pitch).

Pressing 5 (shift) triggers `_show_navigation_message()` showing the current grid + page + octave + semitone — there is no chord/shift functionality yet despite the name. Same `STEPS_PER_PAGE = 8` as before but `STEP_LENGTH` / `PAGE_LENGTH` are now per-instance via `self._step_length` / `self._page_length` and switchable at runtime (`GRID_OPTIONS` tuple). Page count via the bottom row is still 7 (pads 0-6 at row 7); pages beyond 6 exist in the clip but aren't navigable from the device.

The melodic sequencer's `_ensure_clip` also calls `slot.fire()` on the create-from-scratch path (same Push-2 affordance as the drum sequencer).

### Top-row arrow buttons in `drum_sequence` / `melodic_sequence`

The four arrow buttons (`up_button`/`down_button`/`left_button`/`right_button`, CC 91–94) are reused as pitch-offset controls for whichever sequencer is currently active. `__on_up_button_value` etc. in `launchpad_mini_mk3.py` dispatch to `_arrow_target()` which returns the drum sequencer in `drum_sequence`, the melodic sequencer in `melodic_sequence`, and `None` in `session` (so `session_navigation` keeps its standard arrow behavior in session overview). Each sequencer exposes a public `adjust_pitch_offset(delta)` wrapper around its private `_adjust_pitch_offset`. Mapping: ↑ = +12, ↓ = −12, ← = −1, → = +1. LEDs are set in `_set_mode_button_lights` (`LED_ARROW_OCTAVE` / `LED_ARROW_SEMITONE`) for both sequencer modes and turned off when entering session so a stale color doesn't linger.

### Drum sequencer specifics

- Grid split: `step_matrix = submatrix[:, :4]` (top 4 rows), `note_matrix = submatrix[:4, 4:8]` (bottom-left 4×4), `loop_matrix = submatrix[4:8, 4:8]` (bottom-right 4×4). **`submatrix` indexing is `[cols, rows]`**, not the usual `[rows, cols]`.
- `STEPS_PER_PAGE = 32` is a module constant. `STEP_LENGTH` / `PAGE_LENGTH` are per-instance (`self._step_length`, `self._page_length`) since the user can switch the step-grid resolution at runtime via the scene-button slots 0-3 (1/4, 1/8, 1/16, 1/32). Default is 1/16 → step=0.25 beats, page=8 beats. A 1/32 grid gives a 1-measure page in 4/4.
- `_pitch_for_note_button(x, y)`: when a Drum Rack device exists on the track and pitch_offset is zero, the selector reads `drum_group_device.visible_drum_pads` directly so the layout follows Live's drum rack window. Otherwise it falls back to `NOTE_SELECTOR_BASE_PITCH (36) + pitch_offset + index`.
- **Drum-rack-pad colors on the selector**: `_update_note_leds` no longer renders every filled cell with a uniform "NoteFilled" blue. When a cell's drum pad has notes in the clip, the LED uses the pad's own color (translated from `pad.chains[0].color` via `CLIP_COLOR_TABLE` / `find_nearest_color`). The currently selected pad always wins with the bright `NoteSelected` highlight; cells with no notes (or no drum at all) stay on `NoteEmpty` so the selector reads "selected + drums-with-notes are colored + everything else is grey", Push-2-style. Dynamic colors bypass the skin via `_set_grid_light_palette(x, y, palette)` which writes a raw Launchpad palette index directly (the per-skin `DRUM_SEQUENCER_COLOR_VALUES` map is only consulted for static skin keys).
- Created clips default to one page (`self._page_length * DEFAULT_CLIP_PAGES`), so 8 beats at 1/16 or 4 beats at 1/32. Creating a clip from scratch via a step press also calls `slot.fire()` to start playback immediately (Push-2 style — see the `_ensure_clip` gotcha in "Conventions and gotchas" below).

### Melodic sequencer specifics

- `STEPS_PER_PAGE = 8`, `DEFAULT_CLIP_PAGES = 8`. `STEP_LENGTH` / `PAGE_LENGTH` are per-instance (`self._step_length`, `self._page_length`) — same runtime grid-resolution pattern as the drum sequencer (`GRID_OPTIONS` tuple, slot 0-3 → 1/4..1/32, default 1/16 → page = 2 beats, fresh clip = 16 beats).
- **Layout: row 0 is dual-purpose, pitch rows go 0-7.** `PITCH_ROW_MIN = 0`, `PITCH_ROW_MAX = 7` so the 8 grid rows are all available as pitch rows by default. `degree = 7 - y` puts the root at y=7 (bottom) and the octave above the root at y=0 (top — `degree = 7` wraps via `% len(scale)` to `scale[0]` plus a full octave). **When the device shift is held or locked**, row 0 morphs into the page selector + preview toggle:
   - LED: `_update_pitch_leds` and `_update_loop_leds` are mutually exclusive on row 0 — they each ONLY write row 0 when their respective mode is active. With shift held, `_update_pitch_leds` iterates rows 1..7 and `_update_loop_leds` paints row 0 with page-selector colors. Without shift, `_update_pitch_leds` covers rows 0..7 and `_update_loop_leds` is a no-op for the row. Writing the row from BOTH paths produced a visible color mix because every `_set_grid_light` sends its own MIDI message (a few ms apart on the device).
   - Press routing: `_on_grid_matrix_value` checks `y == PREVIEW_TOGGLE_Y and self._device_shift_held` to enter the page/preview branch. Without shift, row 0 falls through to the standard pitch-row handling (toggle a note at `pitch_for_row(0) = root + 12`).
   - Audition: `_update_audition_translations` (only called in preview mode) iterates `start_row = 1 if device_shift_held else 0`. When shift is held it skips row 0 so the page selector doesn't audition; when shift is released it re-translates row 0 back into the pitch pool. `set_device_shift_held` re-calls `_update_audition_translations` if preview is on, and clears `_held_grid_buttons` to drop stale press-dedup entries from before the row meaning changed.
- Pitch rows use the song's `root_note` and the on-device scale list (`MELODIC_SCALES` — 12 scales cycled via slot 6 `SCALE_CYCLE_SLOT`, see the side-row table above). `_current_scale()` returns the tuple from the active index; `_current_scale_name()` is used in status-bar feedback. The legacy `MAJOR_SCALE` / `MINOR_SCALE` constants are still defined for backwards compatibility but are now just `MELODIC_SCALES[0/1][1]`.
- Preview mode swaps rows 1-7 from piano-roll editing to live audition (via `_update_audition_translations`, iterating `range(PITCH_ROW_MIN, PITCH_ROW_MAX + 1)`); the page row stays live in both modes.
- `_held_grid_buttons` deduplicates note-on bursts so a sustained press only toggles once.
- `_ensure_clip` calls `slot.fire()` on the create-from-scratch path so playback starts automatically on the first note (Push-2 style — same as the drum sequencer).

### Clip & scene copy

- The shift button is registered twice on `SessionComponentWithCopy.set_modifier_button(..., "copy_shift", clip_slots_only=...)` so it is propagated to both clip slots **and** scenes. The custom subclass stashes a reference in `self._copy_shift_button` and forwards it to every scene.
- `_create_scene` is overridden so newly instantiated scenes (after track add/remove) also receive the shift button and both handlers.
- Both handlers expose `clear_clipboard()`. The top-level `__on_shift_button_value` listener calls both on release.

### Notification event bus

> Full guide with cookbook, wire-protocol table, troubleshooting, and `.amxd` contract: **`docs/notifications.md`**. This section is just the cheat sheet.

User-facing notifications go through a 3-layer pipeline. Components never call `show_message` directly — they emit *semantic events* on an `EventBus`; one or more *subscribers* translate those events to side-effects (status bar string, M4L parameter write, …). Adding a future channel (OSC, log file, …) means writing one more subscriber; the components stay untouched.

**Layers:**

1. **Emit** (`event_bus.py`, `events.py`) — `Event.*` constants name semantic happenings (`MAIN_MODE_CHANGED`, `DRUM_PAGE_SCOPED`, `MELODIC_SCALE_CHANGED`, etc.). Payload is keyword args, shape documented inline in `events.py`. Components hold an optional `self._event_bus` (passed in via the constructor kwarg `event_bus=`) and call `self._emit(Event.XXX, **payload)`. With no bus wired the helper is a no-op — the script runs identically without notifications.
2. **Subscribe** — `StatusBarSubscriber` owns every user-visible wording (`_FORMATTERS` table in `status_bar_subscriber.py`). `M4LSubscriber` maps events to `(msg_id, args)` (`_MAPPING` in `m4l_subscriber.py`) and forwards to the dispatcher. The two are independent — muting one doesn't affect the other.
3. **Transport** (`notification_dispatcher.py`) — finds a Max for Live device named `LP Notify` (constant `DEVICE_NAME`) on any regular track, return track, or the master. Binds its parameters by name (`msg_id`, `arg1`, `arg2`, `arg3`, `seq`, `enabled`) and writes them on every `send()`. `seq` is bumped last (monotonic 0..127 wrap) so the device-side `live.observer` on `seq` reliably fires even on repeated identical notifications. Listeners on `song.tracks` / `track.devices` / `device.name` refresh discovery on add/remove/rename.

**Wire protocol (`Msg.*` in `notification_catalog.py`)** — integer IDs only, append-only. String labels (scale names, resolution names, drum/melodic discriminator) live in secondary lookup tables INSIDE the `.amxd` patch. The script never sends strings.

**To add a new notification:**
1. Add an `Event.XXX` constant in `events.py` with the payload-shape comment.
2. Emit it from the component (`self._emit(Event.XXX, foo=…)`).
3. Add an entry in `status_bar_subscriber._FORMATTERS` (string formatter).
4. If it should also surface in the M4L overlay: add an `Msg.XXX` integer in `notification_catalog.py` (append, never reuse) and an entry in `m4l_subscriber._MAPPING`.

**Kill switches:**
- Skip `_event_bus.subscribe(self._m4l_subscriber)` in `_create_notification_subscribers` → M4L silent, status bar still works.
- Skip both subscribes → status bar and M4L silent, but components still emit. Useful for debugging without UI noise.
- Pass `event_bus=None` to the sequencer constructors (or set `self._event_bus = None` in the top-level `__init__`) → emit helpers no-op everywhere, identical behavior modulo zero user-visible feedback.

**LP Notify .amxd contract** — the device must expose `msg_id`, `arg1`, `arg2`, `arg3`, `seq` as `live.numbox` int (range fits in -128..127) plus `enabled` as `live.toggle`. Each must have "Long Name" set in Max's Inspector so `device.parameters[i].name` matches. The patch keeps its own `[coll]` or `[dict]` indexed by `msg_id` and resolves the strings locally. Multiple `LP Notify` devices = first one found wins (scan order: regular tracks → returns → master), warning logged.

## Conventions and gotchas

- **Matrix coordinate quirks.** `ButtonMatrixElement.submatrix[cols, rows]` is `[x, y]`; `matrix.get_button(y, x)` is `(row, col)`. Both forms appear in the sequencers — don't swap them blindly.
- **`_log` writes to Ableton's `Log.txt`** (`<Live prefs>/Log.txt`). Each sequencer prefixes its own tag (`[DrumStepSequencer]`, `[MelodicStepSequencer]`); the control surface prefixes `[Launchpad Mini MK3]`. Useful when iterating; `install.sh` clears the log on each install for the WSL path.
- **`show_message`** displays in Live's status bar (bottom-left of the main window). **Don't call it directly from components** — emit a semantic event on the bus (`self._emit(Event.XXX, …)`) and let `StatusBarSubscriber` decide the wording. The only direct caller of `self.show_message` should be the subscriber wiring in `_create_notification_subscribers`. Same for the M4L overlay: never reference `Msg.*` or `device.parameters` from a component.
- **`request_rebuild_midi_map()`** must be called after changing button identifiers/channels or `script_forwarding` (audition translations, leaving sequencer mode, etc.) — otherwise the new mapping won't take effect until a manual map rebuild.
- **Color sources are split.** `skin.py` is used by the standard component pipeline (session grid, mixer, mode buttons via `set_light`). Sequencer pads bypass the skin entirely and write raw palette indices (see `DRUM_SEQUENCER_COLOR_VALUES` / `MELODIC_COLOR_VALUES`). If a sequencer pad shows the wrong color, the palette dict — not the skin — is the source of truth.
- **The shift button is `scene_launch_buttons_raw[7]`.** The scene buttons are stored top-to-bottom (`range(89, 18, -10)`), so index 7 is the bottom one. This is wired by hand in `_create_stop_solo_mute_modes`.
- **`detail_clip` vs `highlighted_clip_slot`.** Sequencers prefer `song.view.detail_clip` if it is a valid MIDI clip; otherwise they fall back to the highlighted slot. `_ensure_clip` will create an empty MIDI clip in the highlighted slot only if the track can hold MIDI. **Drum sequencer auto-fires the new clip.** When a step press creates the clip from scratch, `_ensure_clip` calls `slot.fire()` immediately so the clip starts playing (Push-2 style — instant audible feedback for the first step). Live's session-view semantics handle the transport: if the song wasn't playing, `fire()` starts global playback; if it was, the clip is queued at the next launch quantization. Only the create-from-scratch path fires; pressing a step on an existing clip does not.
- **Loop auto-extension is gated by `_clip_just_created`.** Both sequencers carry this flag. It's set to True ONLY in `_ensure_clip`'s create-from-scratch branch (right after the new clip is bound) and cleared on: clip change (`_set_clip` detects a different clip), leaving sequencer mode (`set_enabled(False)`), or any explicit user loop-scoping gesture (`_set_loop_pages`, `_scope_page`, `_set_step_loop_in_current_page`). `_ensure_loop_contains_time` is the SINGLE gate: it no-ops when the flag is False. Consequence: opening an existing clip and adding a note past `loop_end` writes the note to the clip but leaves the loop untouched (the note is silent in the current loop pass). Same for page navigation (`_select_page`) and length/nudge edits — they all funnel through `_ensure_loop_contains_time`. Don't bypass the gate from new code paths unless you have a strong reason.
- **The "user" button cycles through three modes** (`session → drum_sequence → melodic_sequence → session`). The Drums/Keys buttons are not used for mode switching — they're owned by `TransportComponent` for global play / session record. They also remain in the `BackgroundComponent`'s nop layer so the original layout-enquire round-trip still fires; multiple value listeners coexist on the same element without conflict.
- **`SessionOverviewComponent` uses the same `clip_launch_matrix`** as the launch view. Restoring pad identifiers when leaving a sequencer mode is done via `_restore_clip_launch_matrix` (`use_default_message()` on every button + map rebuild). Skipping this leaves the overview lit with sequencer-mode LEDs.
- **Compatibility.** Live 12 (v2 control-surface API). Decompiled source uses Python 3.7 conventions (`from __future__ import` headers, old-style `super()`); match that style for files that originate from the Live bundle so future re-syncs diff cleanly. New files written from scratch don't have to.
- **The shift button cycle vs hold** rely on `support_momentary_mode_cycling=False` on `_stop_solo_mute_modes`. Don't flip that flag — it would cause the bottom row to flicker into another mode every time the user holds shift to copy.

## Development workflow

### Iterative test loop

There is no way to run this code outside Live — Ableton owns the Python runtime and the device. The loop is:

1. **Claude edits the `.py` files** at the repo root.
2. **Claude runs `./install.sh`.** This copies every root-level `.py` to `…/MIDI Remote Scripts/Launchpad_Mini_MK3/` on the Windows side and **deletes Ableton's `Log.txt`**. Clearing the log is the important part: it guarantees the next read of `Log.txt` only contains output from the user's test session, with no carryover from previous runs.
3. **User restarts Ableton Live** (the MIDI Remote Script is only loaded at startup; reloading the control surface in MIDI prefs is not enough — full restart) and exercises the change on the hardware.
4. **If something is wrong, user reports back.** Claude reads `Log.txt` (path below) to see `_log` output, Python tracebacks, and Live's MIDI port / control surface messages.
5. **Claude fixes**, then back to step 1.

Stay quiet about restart instructions unless the user asks — they know. The job is: edit → `./install.sh` → wait → debug log if needed.

### Paths

- **Source (this repo):** `/home/mahed/projects/launchpad-mini-mk3-script/`
- **Install target (Ableton):** `/mnt/c/ProgramData/Ableton/Live 12 Suite/Resources/MIDI Remote Scripts/Launchpad_Mini_MK3/` (hard-coded as `DEST_DIR` in `install.sh`)
- **Ableton log:** `/mnt/c/Users/mahed/AppData/Roaming/Ableton/Live 12.3/Preferences/Log.txt` (also hard-coded in `install.sh`)

If the Ableton install path or the Live version changes, both must be updated in `install.sh`. The script has no fallback discovery.

### Reading the log

The log mixes Ableton internals with our messages. Useful filters:

- `[Launchpad Mini MK3]` — top-level control surface (`launchpad_mini_mk3.py::_log`)
- `[DrumStepSequencer]` — drum sequencer (`drum_step_sequencer.py::_log`)
- `[MelodicStepSequencer]` — melodic sequencer (`melodic_step_sequencer.py::_log`)
- `Traceback` / `Error` / `Exception` — Python errors loading or running the script
- `RemoteScriptError` / `Control Surface` — Ableton's view of the script

If `Log.txt` is empty or missing, either the user hasn't started Live yet, or Live failed before initializing the script (check `Log.txt` parent dir for crash reports, and confirm the install actually copied — `install.sh` prints the file list).

`show_message(...)` writes to Live's bottom status bar (transient, not persisted). Useful for "did this code path run?" feedback during interactive testing — won't appear in `Log.txt`.

### Sanity check before pushing changes to the device

```bash
python3 -m py_compile *.py
```

Catches syntax errors before the round-trip through Live. Cannot validate Ableton API usage (the `ableton.*` modules aren't importable here), but rules out the most common mistakes. The resulting `__pycache__/` is gitignored.

### MIDI port reminder

For sequencer LEDs to render, the script must be bound to `MIDIIN2 (LPMiniMK3 MIDI)` / `MIDIOUT2 (LPMiniMK3 MIDI)` in Live's MIDI prefs. The non-`MIDIIN2` ports work for the launch grid but won't drive Programmer-mode LEDs correctly. If a feature works for clip launching but the sequencer pads stay dark, suspect the port mapping first.

### No automated tests

There is no test suite and no linting. The `.github/` directory contains only `release.yml`. Validation is 100% through the iterative loop above.

## Things this repo does NOT have

- No unit tests, no mocks of the Live API, no static type checking.
- No abstraction over the two sequencers — they share patterns by copy/paste, not by inheritance. Changes to loop-scoping or control-row behavior need to be applied to both files.
- No support for Live versions before 12 (the framework imports under `ableton.v2.*` would need versioning otherwise).
- No support for other Launchpad models — `model_family_code` and `LP_MINI_MK3_ID` are pinned in `sysex_ids.py`.
