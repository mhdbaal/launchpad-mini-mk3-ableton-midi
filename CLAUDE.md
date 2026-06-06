# CLAUDE.md

Internal reference. Read `README.md` first for the feature tour — this file focuses on architecture, wiring, and non-obvious gotchas.

## What this is

Custom Ableton Live 12 MIDI Remote Scripts for the **Novation Launchpad Mini MK3** and **Launchpad Pro MK3** — a shared component core + per-device overlays (see [Repo layout](#repo-layout--overlay-assembly)). The Mini script replaces the factory `Launchpad_Mini_MK3` script (decompiled copies of both factory scripts under `midi-remote-scripts/` for reference) and adds:

- 4-mode bottom row (Select/Arm, Stop, Solo, Mute) cycled by the bottom-right scene button (the "shift" button)
- clip and scene copy-paste while shift is held
- Push-style drum step sequencer
- Launchpad95-style melodic step sequencer
- 8×8 chord-pad mode (single root note per pad via translation; relies on Live's stock Chord MIDI effect for the chord expansion, or a future LP Chord M4L companion)
- direct Programmer-mode LED rendering for the sequencers

Built on Novation's official framework (`NovationBase`) — every component subclasses or composes a Novation/Ableton v2 control-surface primitive.

## Mode hierarchy

Three nested layers run simultaneously:

1. **`_main_modes`** (User button) — `session`, `drum_sequence`, `drum_64_sequence`, `drum_4_track_sequence`, `melodic_sequence`, `chord_mode`. `__on_main_mode_changed` swaps subsystems and rewrites mode-button LEDs. Sequencer + chord modes all count as "grid-takeover" — session components disable, audition translations install, mode-button lights update.

   **User button is hold-to-select, not tap-to-cycle.** Press User → scene_launch_buttons_raw[0..4] light up as a mode selector (drum/drum64/drum4-track/melodic/chord, top to bottom; active mode = bright, others = half). Tap a scene to switch mode; tap the active mode's scene to bounce back to session. Release User → if a mode was tapped during the hold, stay there; otherwise fall back to session (so a quick hold+release acts as a one-handed "exit to session" shortcut from anywhere). Scene LEDs revert to whatever the new active mode's component renders (`session.update()` for session, `seq._update_control_leds()` for sequencer/chord). Scenes 5-6 stay dim; scene 7 (shift) is untouched.

   `cycle_mode_button` is intentionally **not** in `_main_modes`' Layer — cycling is gone. The framework no longer writes the User button LED via mode color; `_set_mode_button_lights` still writes it manually from `__on_main_mode_changed`.

   While User is held, every scene-press consumer (`SceneComponentWithCopy._on_launch_button_pressed`, each sequencer's `_on_control_button_value`, chord pad's same) checks `user_mode_button.is_pressed()` at the top and returns early. Same gate applies to `_update_control_leds` so the sequencer doesn't repaint over the selector during the hold. References are wired via `set_user_mode_button(button)` setters from `_create_components` in `launchpad_mini_mk3.py`.
2. **`_session_modes`** (Session button) — `launch` / `overview`. Only meaningful in `session` main mode.
3. **`_stop_solo_mute_modes`** (shift button = `scene_launch_buttons_raw[7]`) — `select` / `stop` / `solo` / `mute` / `edit`. `select` uses `ChannelStripComponentWithArmToggle` (smart arm-on-second-press). Only meaningful in `session` main mode. `edit` is the 5th mode, **not in the single-tap cycle** — reached only via double-tap (see [Edit mode](#edit-mode)).

`TransportComponent` (Drums = play/stop, Keys = session record) stays live in **every** main mode — enabled via `__on_main_mode_changed`, not `_set_session_components_enabled`. No `_set_mode_button_lights` branch touches Drums/Keys.

**Session button extra behavior in sequencer modes** (`__on_session_mode_button_value`): press latches `_main_modes` to `session` and remembers return mode in `_session_preview_return_mode`; release tap (≤`SESSION_HOLD_THRESHOLD`) keeps session, hold reverts. Doesn't fight `session_modes.cycle_mode_button` because that uses `.pressed` (False→False on release fires nothing).

**Shift button is overloaded 6 ways**:
- session, short tap (≤`SHIFT_LOCK_TAP_THRESHOLD`): cycles bottom-row sub-mode (select → stop → solo → mute → select). Cycling happens on RELEASE — `cycle_mode_button` is intentionally **not** wired into the Layer so the first tap of a double-tap can be undone by the second tap. LED is driven manually via `__on_stop_solo_mute_mode_changed` and `_update_shift_button_led`.
- session, double-tap (release-to-release ≤ `SHIFT_DOUBLE_TAP_WINDOW`): enters `edit` sub-mode. `_enter_edit_mode` cycles BACK one step to undo the visible flash from the first tap, then sets `selected_mode = "edit"`. `_pre_edit_mode` remembers the mode to return to on single-tap exit.
- session, single tap **while in edit**: exits edit, restores `_pre_edit_mode`.
- session, long hold: copy modifier. `hold + tap clip` = copy/paste; `hold + tap scene` = copy/paste; release clears clipboards (`__on_shift_button_value`). Long press does NOT cycle.
- sequencer modes: modifier. While "effective" (held or locked), shift-gated controls render lit and accept input — grid-resolution slots 0-3, triplet slot 4, and (melodic only) the top row (page selector + preview toggle). Otherwise `DefaultButton.Disabled` and presses ignored. Each sequencer exposes `set_device_shift_held(bool)`.
- **shift lock** (sequencer modes only): double-tap toggles sticky `_shift_locked`. Same release-to-release timing as the session-mode edit-entry detection; the discriminator is `_main_modes.selected_mode`. Long press resets the detector. Clipboards still clear on physical release. Feedback: `show_message` + slot 7 LED lights `Control.Shift` (AMBER) while effective.

## Repo layout — overlay assembly

Shared `.py` files live at the **repo root**; device-specific modules live in `mini/` and `pro/` under the **same module names** (`__init__.py`, `device_profile.py`, `sysex_ids.py`, `elements.py`, + the wiring file). `install.sh` assembles root + overlay **flat** into each device's MIDI Remote Scripts folder, so every relative import (`from .x import y`) resolves unchanged. Consequence: a shared component MAY `from .device_profile import X` — the assembly injects the right device's file at install time. **Never install a sub-folder directly** (imports would break); never let a basename exist both at root and in an overlay (install.sh refuses).

## File map

| File | Responsibility |
|------|---------------|
| `mini/__init__.py` · `pro/__init__.py` | Capabilities, port declarations, `create_instance`. Mini: 2 port pairs. Pro: 3 pairs (bind the SCRIPT pair). |
| `mini/launchpad_mini_mk3.py` | Top-level `NovationBase` (Mini). Owns modes, wiring, Programmer-mode SysEx, mode-button LEDs. |
| `pro/launchpad_pro_mk3.py` | Top-level `NovationBase` (Pro). Native-UX wiring: dedicated buttons replace the Mini's hold/double-tap workarounds (see [Launchpad Pro MK3 package](#launchpad-pro-mk3-package)). |
| `mini/elements.py` | Mini hardware layer. Adds `drums_mode_button`/`keys_mode_button`/`user_mode_button` + `Session_Button_Color_Element`. |
| `pro/elements.py` | Pro hardware layer. Arrows (80/70/91/92), Session 93, dedicated Shift/Clear/Duplicate/Quantise/Play/Record + function row CC 1-8 + track-select row CC 101-108. No faders/print-to-clip in v1. |
| `skin.py` | Skin: `Mode.Session.*`, `Mixer.TrackSelected`, full `DrumSequencer.*` / `MelodicSequencer.*` palettes. Merged via `merge_skins`. Shared by both devices. |
| `mini/sysex_ids.py` · `pro/sysex_ids.py` | Mini: family (19,1), id 13. Pro: family (35,1), id 14 + layout bytes. |
| `mini/device_profile.py` · `pro/device_profile.py` | **Device-specific seam.** USB vendor/product, SysEx command bytes (Programmer mode entry, LED feedback, sleep), button CCs, LED palette indices. Same public symbol names on both — swap wholesale when porting. |
| `programmer_mode.py` | Novation-wide Programmer-mode MIDI conventions: `NOTE_ON_STATUS`, `MIDI_CC_STATUS`, `PROGRAMMER_LED_CHANNEL`, `AUDITION_CHANNEL`. Same on Mini MK3 / X / Pro MK3. |
| `palette.py` | Shared `DRUM_SEQUENCER_COLOR_VALUES` / `MELODIC_COLOR_VALUES` dicts + `send_pad_color()` helper. Indices 0-127 are the Launchpad firmware palette, identical across models. |
| `channel_strip_with_arm_toggle.py` | Click unselected → select; click selected → toggle arm. Honors `song.exclusive_arm`. |
| `clip_copy_component.py` | Clip clipboard. Validates audio/MIDI; uses `duplicate_clip_to`. |
| `scene_copy_component.py` | Inserts new scene at target index, duplicates non-empty slots, copies name/color/tempo/time-sig. |
| `clip_slot_with_copy.py` | Intercepts `_on_launch_button_pressed`, routes to clip copy when shift held. |
| `transport_component.py` | Drums = play/stop, Keys = session record. Active in every main mode. |
| `session_with_copy.py` | Propagates shift + copy + edit-mode handlers to every clip slot/scene (incl. via `_create_scene`). |
| `edit_mode_component.py` | 5th stop-solo-mute sub-mode. Owns the bottom row while active; slots 0-3 are Delete/Duplicate/Move/ColorCycle hold-modifiers, slot 4 is Stop-All-Clips, slot 7 is Undo (or Redo with shift held). Clip slots + scenes route presses to this component when `is_active()` returns True (see [Edit mode](#edit-mode)). |
| `notifying_background.py` | `BackgroundComponent` that fires `value` instead of swallowing — refreshes layout switch on Drums/Keys press. |
| `drum_step_sequencer.py` | 4×8 step grid + 4×4 drum-pad selector + 4×4 loop/grid selector. Step-hold gestures (velocity/nudge/extend). Owns LED rendering + audition. |
| `melodic_step_sequencer.py` | 7×8 pitch×step grid + dual-purpose row 0 (page selector + preview toggle when shift held). |
| `chord_pad_mode.py` | 8×8 chord-pad grid (cols = scale degrees, rows = octave shift). 1-1 audition translation → each pad triggers one root note. Emits `CHORD_TRIGGERED` with full diatonic chord pitches. |
| `event_bus.py` / `events.py` | Tiny sync pubsub. `Event.*` string constants are the contract between emitters and subscribers. |
| `notification_catalog.py` | `Msg.*` integer wire IDs for LP Notify M4L device. **Append-only.** Plus `GRID_RESOLUTION_INDICES`, `MODE_ID_*`. |
| `status_bar_subscriber.py` | Single owner of every user-visible `show_message` wording (`_FORMATTERS` table). |
| `m4l_subscriber.py` | Maps events to `(msg_id, args)`, forwards to dispatcher. No-op without LP Notify device. |
| `notification_dispatcher.py` | Discovers LP Notify device on any track, binds params by name, writes `msg_id/arg1-3/seq` on `send()`. |
| `install.sh` | WSL→Windows install, `--mini` / `--pro` / `--all` (default). Assembles root + overlay flat per device; refuses on root∩overlay basename collision. Paths hard-coded for `mahed`'s machine. |

## Key subsystems

### Programmer mode + direct LED writes

On `on_identified` device enters Programmer mode (SysEx cmd 14, value 1), external feedback on, sleep off. Pads no longer respond to skin colors via the normal element-color path.

- `_send_programmer_cc` writes mode buttons (`SESSION_BUTTON_CC=95`, `DRUMS=96`, `KEYS=97`, `USER=98`) via CC chan 0.
- Sequencers' `_send_programmer_pad_color` writes `Note On` chan 0 (`status=144`) with **raw Novation palette index (0–127)**, NOT a `Color` instance. Each sequencer has its own `*_COLOR_VALUES` dict mapping skin names → palette indices. Skin is consulted only by name; LED write bypasses it. **Keep the dict in sync with `skin.py` when adding colors.**
- `disconnect` exits Programmer mode + `firmware_mode_switch` back to Standalone.

### Audition translations

Pads that should play a sound (drum-pad selector; melodic grid in preview) reassign MIDI identifier + switch `script_forwarding` to `non_consuming` so the note reaches both the script and Live. `_update_audition_translations` / `_clear_audition_translations`; both end with `request_rebuild_midi_map()`. Drum sequencer enables `set_feedback_channels([DRUM_FEEDBACK_CHANNEL])` (=1) so drum-pad feedback lights the selector.

**Audition pads live on channel 1, not 0.** Live's MIDI forwarding registry is keyed by `(channel, identifier)`. Translated audition pitches collide with the `original_identifier` of other pads in the same matrix (e.g. bottom-right loop pad note 45 = drum-pad selector translation target). On channel 0, the later registration wins and pressing the loop pad plays a drum sound. Channel 1 makes keys disjoint and matches `DRUM_FEEDBACK_CHANNEL`. **Don't move audition back to channel 0.**

### Loop scoping pattern (drum + melodic)

`_handle_loop_press`:
- single tap on page pad → view page (no shrink)
- double-tap (≤0.35s) → scope loop to that page
- hold one + press another → scope loop to range (`_loop_range_active` blocks release-time double-tap)
- All loop changes go through `_set_clip_loop(start, end)` which also moves `start_marker`/`end_marker`. **When shifting loop forward, order of `loop_start`/`loop_end` writes matters** (avoid `start >= end` momentarily).

### Bottom-right 4×4 modes (drum + melodic)

Slot 6 cycle button toggles between two modes per sequencer. State: `self._bottom_right_mode`.

- **Drum:** `loop` (default, 16 page pads) ↔ `grid` (16 resolutions from `GRID_OPTIONS`).
- **Melodic:** `pitch` (default, 16 pitch cells unchanged) ↔ `grid` (those 16 cells become resolution selector; rest of pitch grid keeps pitch behavior).

`GRID_OPTIONS` (16 resolutions, same shape per file): row 0 = `1/4, 1/8, 1/16, 1/32`, row 1 = `1/64, 1/128, 1/256, 1/512`, row 2-3 = same with `t` suffix. Ternary cells render `Control.GridTernary` (PURPLE); `TERNARY_FIRST_INDEX = 8`. Selected always `GridSelected` (WHITE). State: `_grid_option_index`. Event payload still emits `is_triplet` (`label.endswith("t")`) for M4L wire-format back-compat.

**Existing notes are NOT remapped on grid change** — only step-to-time alignment changes. Pages/loop scoping/clip-creation lengths scale with `self._page_length`.

Shift-held step-loop range picker keeps priority over bottom-right grid mode: pressing a bottom-right cell with shift fires the loop picker (X coord), not the grid selector. **Grid slots and triplet toggle are shift-gated**: `_grid_color_for_slot`/`_triplet_color` return `DefaultButton.Disabled` and presses are ignored unless `_device_shift_held` is true.

### Step-pad hold gestures (drum sequencer)

Step pads toggle on **release**, not press — leaves the press as a gesture anchor. State: `_held_step_pads` = `{pad_step → note_step_or_None}` (note_step updated when nudge moves the note). `_consumed_step_pads` = pads whose release must NOT toggle. Release checks consumed first.

Three gestures on top of the hold:
- **Length extension**: hold A + press B → `_extend_note_length` keeps start, sets duration to `(end_step - start_step + 1) * step_length`. Both consumed. Calls `_ensure_loop_contains_time` (gated by `_clip_just_created` — see gotchas).
- **Velocity edit**: hold + Up/Down → parent routes to `adjust_held_velocity(±DRUM_VELOCITY_ARROW_STEP)` (=±8, clamped). Returns True if any note modified; parent uses that to decide fallback to `adjust_pitch_offset(±12)`. Pad consumed.
- **Nudge**: hold + Left/Right → `nudge_held_notes(±1)`. Moves start ±`step_length`; held entry updated to new position so subsequent arrows keep editing the same note. `new_start < 0` rejected.

LED feedback: held steps render `DrumSequencer.StepHeld` (AMBER), overrides StepEmpty/StepActive but is overridden by playhead.

Pure tap (press+immediate release) still toggles once — visual feedback just moves to release.

`_replace_note` is the shared helper that removes + re-adds with attribute overrides (one place for the Live API shape).

### Clip-level actions: Capture MIDI + Quantize Selected

Both sequencers expose two clip-level actions on scene-button slots **0** (Capture MIDI) and **1** (Quantize Selected). Drum: always available. Melodic: dual-purpose — shift held → chromatic/scale toggles on same slots; shift not held → Capture/Quantize.

- **Capture MIDI** wraps `song.capture_midi()` gated on `song.can_capture_midi`. Listener flips LED `CaptureMidi` (dim) ↔ `CaptureMidiReady` (bright).
- **Quantize Selected** scope: set of notes under currently-held step pads. With no held pads: drum = "all notes of selected drum pad", melodic = "all notes in clip". Math: `round(note.start_time / step_length) * step_length`, 100% pull. Held pads get tracked positions updated AND marked consumed.

Melodic was refactored to mirror drum's "toggle on release" so the hold-without-toggle gesture works there too — see `_held_note_cells` + `_consumed_note_cells` + the `(x, y) not in _held_grid_buttons: return` guard.

### Scene-button column (both sequencers)

Slots top→bottom. Slot 7 is the shared device-shift / stop-solo-mute, **untouched by either sequencer** (owned by `_stop_solo_mute_modes`).

**Drum**: 0=Capture, 1=Quantize, 2-5=free, 6=cycle (loop ↔ grid).
**Melodic**: 0=chromatic toggle (shift) / Capture, 1=scale cycle (shift) / Quantize, 2-5=free, 6=cycle (pitch ↔ grid).

### Top-row arrow buttons in sequencer modes

CC 91-94 become pitch-offset controls. `__on_*_button_value` dispatches to `_arrow_target()` → drum seq in `drum_sequence`, melodic in `melodic_sequence`, `None` in `session` (keeps `session_navigation`). Mapping: ↑=+12, ↓=−12, ←=−1, →=+1. LEDs in `_set_mode_button_lights` (`LED_ARROW_OCTAVE` / `LED_ARROW_SEMITONE`), cleared entering session.

### Drum sequencer specifics

- Grid split: `step_matrix = submatrix[:, :4]` (top 4 rows), `note_matrix = submatrix[:4, 4:8]`, `loop_matrix = submatrix[4:8, 4:8]`. **`submatrix` is `[cols, rows]`**, not the usual `[rows, cols]`.
- `STEPS_PER_PAGE = 32` module const. `STEP_LENGTH` / `PAGE_LENGTH` per-instance. Default 1/16.
- `_pitch_for_note_button(x, y)`: when a Drum Rack exists + pitch_offset=0, reads `drum_group_device.visible_drum_pads` so the selector follows Live's drum-rack window. Otherwise falls back to `NOTE_SELECTOR_BASE_PITCH (36) + offset + index`.
- **Drum-rack colors on selector**: filled cells render the pad's own color (translated from `pad.chains[0].color` via `CLIP_COLOR_TABLE` / `find_nearest_color`). Selected pad always wins with `NoteSelected`. Empty stays `NoteEmpty`. Dynamic colors bypass skin via `_set_grid_light_palette(x, y, palette)`.
- Created clips default to `_page_length * DEFAULT_CLIP_PAGES`. Create-from-scratch also calls `slot.fire()` (Push-2 style).

### Melodic sequencer specifics

- `STEPS_PER_PAGE = 8`, `DEFAULT_CLIP_PAGES = 8`. Per-instance `STEP_LENGTH`/`PAGE_LENGTH`.
- **Row 0 is dual-purpose**: with shift held, morphs into page selector + preview toggle at `(7, 7)`; without shift, behaves as pitch row 0 (`pitch_for_row(0) = root + 12`).
  - LED: `_update_pitch_leds` and `_update_loop_leds` are mutually exclusive on row 0 (each ONLY writes when its mode is active) — writing from both produced a visible color mix.
  - Press: `_on_grid_matrix_value` checks `y == PREVIEW_TOGGLE_Y and _device_shift_held` for the page/preview branch.
  - Audition: `_update_audition_translations` iterates `start_row = 1 if shift held else 0`. `set_device_shift_held` re-calls it if preview is on, and clears `_held_grid_buttons`.
- Scales: `_current_scale()` returns from `MELODIC_SCALES[_scale_index]`. Slot 1 (`SCALE_CYCLE_SLOT`) cycles. Slot 0 (`CHROMATIC_SLOT`) toggles `_chromatic_mode`. Toggling does NOT move existing notes (only row→pitch mapping changes); audition translations are rebuilt indirectly via `_pitch_for_row`.
- `_held_grid_buttons` dedupes note-on bursts so sustained press toggles once.
- `_ensure_clip` calls `slot.fire()` on create-from-scratch (Push-2 style).

### Chord pad mode

8×8 grid that triggers chord roots — visually a chord wheel.

- **Columns 0..7** = scale degrees (I, ii, iii, IV, V, vi, vii°, I+1oct).
- **Rows 0..7** = octave shift. `DEFAULT_ROW = 4` is the unshifted reference (matches melodic's y=0-top convention: y=0 is highest pitch, y=7 is lowest).
- **Per-pad audition** uses the standard translation pattern (`set_identifier(pitch)` + `AUDITION_CHANNEL` + `script_forwarding = non_consuming`). Each pad emits exactly one MIDI note — the chord ROOT.
- **Getting a real chord from one pad** is downstream of the script. Two paths:
  1. Drop Live's stock **Chord** MIDI effect on the armed track. Fixed-interval voicings expand every incoming root note into a chord. Simple, no extras to install — but interval set is fixed (not per-degree).
  2. Listen to `Event.CHORD_TRIGGERED` (payload `degree`, `root_pitch`, `chord_pitches`, `velocity`) — a future LP Chord M4L companion can play *diatonic* chords. Not wired to the existing dispatcher because `chord_pitches` is variable-length and the wire protocol only carries 3 packed args.
- **Why not just send the chord from the script?** A MIDI Remote Script's only path from a pad press to a Live track is the 1-1 translation. `_send_midi` writes to the *controller's* input (LEDs, etc.) and never loops back to a track. There is no public API for "play this note on track N" from the script side.

Scene-button slots (top → bottom):
- `0` Capture MIDI  ·  `1` Cycle key  ·  `2` Cycle scale  ·  `3` Cycle chord type  ·  `4` Cycle inversion  ·  `5-6` free  ·  `7` device shift.

Arrows transpose the layout: ↑↓ = ±octave, ←→ = ±semitone (both move `_pitch_offset`, which the audition translation rebuild re-applies on next refresh).

LED palette is intentionally distinct from the sequencers: AMBER for degrees 0 and 7 (tonic + octave), BLUE for diatonic 3rd/5th, dim GREEN for other scale tones; non-default rows get the `*Dim` variant so the eye still finds the `DEFAULT_ROW` anchor. Held pads override to WHITE.

### Edit mode

5th sub-mode of `_stop_solo_mute_modes`. Entered via **double-tap on shift** in session main mode; exited via **single tap** (returns to `_pre_edit_mode`).

**Bottom row layout while edit is active**:

| slot 0 | slot 1 | slot 2 | slot 3 | slot 4 | slot 5-6 | slot 7 |
|--------|--------|--------|--------|--------|----------|--------|
| **Delete** (red) | **Duplicate** (green) | **Move** (blue) | **Color Cycle** (yellow) | **Stop All** (orange) | dim | **Undo** (white, +shift = redo) |

- Slots 0-3 are **hold-modifiers**: pad must be held while tapping a clip/scene.
- Slots 4 and 7 are **single-tap actions**: pressing fires immediately, no target needed.
- Undo / redo discriminator: `EditModeComponent._undo_or_redo` checks `self._shift_button.is_pressed()` at press time. Hold shift > `SHIFT_LOCK_TAP_THRESHOLD` to avoid exiting edit mode on shift release (a short shift+undo would tap-out of edit).

Each modifier renders half-intensity when available, full when held. Move gets a 3rd state (`MoveArmed`, WHITE) once a source has been captured.

**Actions** (modifier held + tap clip/scene):
- **Delete**: `clip_slot.delete_clip()` for clips with content; `song.delete_scene(idx)` for scenes (blocked if only one scene remains — Live requires at least one).
- **Duplicate**: `track.duplicate_clip_slot(scene_idx)` (Ableton Ctrl+D — duplicates into the next scene). For scenes: `song.duplicate_scene(idx)`.
- **Move**: 1st tap captures the source (clip slot or scene), 2nd tap completes. Clip move = `duplicate_clip_to(target) + source.delete_clip()` (target must be empty + track-compatible). **Scene move is a no-op in v1** — insert-then-delete index dance is error-prone; the user described move primarily for clips.
- **Color Cycle**: `clip.color_index = (clip.color_index + 1) % 70` (Live's 70-entry palette wraps). Same wrap on `scene.color_index`. Pad shows yellow-half idle, full yellow when held.

**Single-tap actions** (slot press, no target):
- **Stop All Clips** (slot 4): `song.stop_all_clips()`. Orange LED. Fires on press only — release is ignored.
- **Undo / Redo** (slot 7): `song.undo()` by default, `song.redo()` if the shift button is held at the moment of press. Both gated by `song.can_undo` / `song.can_redo`. White-half LED.

**Move source lifecycle**:
- Released Blue before 2nd tap → cancel (`_move_source = None`, emits `EDIT_MOVE_CANCELLED`).
- Component disabled (e.g., main mode changed) → cancel.
- Successful 2nd tap → consume.
- Mismatched source kind (e.g., scene source then clip target) → silently discard.

**Coexistence with shift+tap copy**: while edit mode is active, `ClipSlotComponentWithCopy._on_launch_button_pressed` checks `edit_mode.is_active()` BEFORE `is_button_pressed(copy_shift)`, so the copy gesture is short-circuited. Holding shift in edit mode is unnecessary anyway — the user releases shift after the double-tap; modifiers are red/green/blue.

**Press without modifier in edit mode**: silently ignored (no accidental launches).

**Wiring**: `EditModeComponent` is created before `_create_stop_solo_mute_modes` and registered as the 5th mode with `AddLayerMode(self._edit_mode, Layer(modifier_matrix=bottom_row))`. The edit-mode reference is propagated to every clip slot and scene via `session.set_edit_mode_component(...)` (including new scenes via `_create_scene`).

**Cycle button (shift LED)**: with `cycle_mode_button` removed from the Layer, `__on_stop_solo_mute_mode_changed` listens for sub-mode changes and `_update_shift_button_led` writes the LED color (from `_STOP_SOLO_MUTE_LED_COLORS`). Sequencer modes still drive the same button via `Control.Shift` — `_update_shift_button_led` no-ops when not in session main mode.

### Clip & scene copy

Shift registered twice on `SessionComponentWithCopy.set_modifier_button(..., "copy_shift", clip_slots_only=...)` so it propagates to clip slots **and** scenes. `_create_scene` is overridden so new scenes also get shift + both handlers. Both handlers expose `clear_clipboard()`, called from `__on_shift_button_value` on release.

### Notification event bus

Full guide: **`docs/notifications.md`** (cookbook, wire protocol, troubleshooting, `.amxd` contract).

Components never call `show_message` directly — they emit semantic events on an `EventBus`; subscribers translate them. Adding a channel = writing one more subscriber.

**Layers**: emit (`event_bus.py`/`events.py`) → subscribe (`StatusBarSubscriber` owns wording in `_FORMATTERS`; `M4LSubscriber` maps via `_MAPPING`) → transport (`notification_dispatcher.py` discovers LP Notify device, binds params by name, bumps `seq` last for reliable `live.observer` fire).

**Wire protocol** (`Msg.*` in `notification_catalog.py`): integer IDs, append-only. Strings stay inside the `.amxd` patch.

**To add a notification**:
1. `Event.XXX` in `events.py` with payload-shape comment.
2. Emit via `self._emit(Event.XXX, ...)`.
3. Entry in `status_bar_subscriber._FORMATTERS`.
4. (Optional M4L) `Msg.XXX` in `notification_catalog.py` (append!) + entry in `m4l_subscriber._MAPPING`.

**Kill switches**: skip the M4L subscribe = M4L silent; pass `event_bus=None` = emits become no-ops.

## Conventions and gotchas

- **Matrix coordinate quirks**: `ButtonMatrixElement.submatrix[cols, rows]` is `[x, y]`; `matrix.get_button(y, x)` is `(row, col)`. Both forms appear — don't swap blindly.
- **`_log`** writes to Ableton's `Log.txt`. Tags: `[Launchpad Mini MK3]`, `[DrumStepSequencer]`, `[MelodicStepSequencer]`, `[ChordPad]`. `install.sh` clears the log per install.
- **`show_message` from components is forbidden** — emit a bus event, let `StatusBarSubscriber` choose wording. Same for M4L: never reference `Msg.*` or `device.parameters` from a component.
- **`request_rebuild_midi_map()`** must be called after changing button identifiers/channels or `script_forwarding` (audition translations, leaving sequencer mode, etc.).
- **Color sources are split**: `skin.py` for standard pipeline (`set_light`); sequencer pads + chord pads bypass skin and write raw palette indices (`DRUM_SEQUENCER_COLOR_VALUES` / `MELODIC_COLOR_VALUES` / `CHORD_COLOR_VALUES`). Wrong color = palette dict is source of truth.
- **Shift button is `scene_launch_buttons_raw[7]`** (scene buttons stored top-to-bottom via `range(89, 18, -10)`, so 7 = bottom).
- **`detail_clip` vs `highlighted_clip_slot`**: sequencers prefer `song.view.detail_clip` if valid MIDI; else highlighted slot. `_ensure_clip` creates an empty MIDI clip only if track allows. **Drum sequencer auto-fires the new clip** on create-from-scratch (Push-2 style).
- **Loop auto-extension is gated by `_clip_just_created`**. Set True ONLY in `_ensure_clip`'s create-from-scratch branch; cleared on clip change, leaving sequencer mode, or any user loop-scoping gesture. `_ensure_loop_contains_time` is the SINGLE gate — it no-ops when False. Consequence: opening an existing clip + adding a note past `loop_end` writes the note but leaves the loop untouched (note silent in current pass). Don't bypass without a strong reason.
- **User button** cycles six modes in order (`session → drum_sequence → drum_64_sequence → drum_4_track_sequence → melodic_sequence → chord_mode → session`). Drums/Keys are NOT mode switches — they're owned by `TransportComponent`. They remain in `BackgroundComponent`'s nop layer so the layout-enquire round-trip still fires.
- **`SessionOverviewComponent`** uses the same `clip_launch_matrix` as launch. `_restore_clip_launch_matrix` resets identifiers when leaving a sequencer mode.
- **Decompiled source uses Python 3.7 conventions** (`from __future__`, old-style `super()`). Match that style for files originating from Live bundle; new files don't have to.
- **`support_momentary_mode_cycling=False`** on `_stop_solo_mute_modes` is what makes shift cycle vs hold work. Don't flip it.

## Launchpad Pro MK3 package

`pro/` is a native-UX port of the Mini script: same Programmer-mode takeover, same shared components, but the Mini's button-scarcity workarounds are deleted from the wiring (no User hold-to-select, no double-tap edit entry, no shift lock, no stop-solo-mute tap-cycle, no `_seq_shift_button`). Active main modes mirror the Mini's ergonomic pass: `session` / `drum_sequence` / `melodic_sequence` (chord + drum variants constructed but unreachable).

**Button map** (session · sequencer):

| Button (CC) | Session | Sequencer modes |
|---|---|---|
| 8×8 grid | clips, **all 8 rows** (no bottom-row sacrifice) | step grid / selectors (unchanged) |
| Scenes 89→19 | **all 8 launch scenes** (slot 7 freed) | slot 4 = Cycle; slots 0-3/5/6 disabled via `configure_slots` (free for future) |
| Shift (90) | hold + clip/scene = copy/paste | `set_device_shift_held` (grid resolutions, triplets, melodic row 0) |
| Clear (60) | hold + tap = delete | hold = `set_action_modifier("delete")` (drum) |
| Duplicate (50) | hold + tap = duplicate | hold = action-modifier duplicate; Shift+Duplicate = `double_loop()` |
| Quantise (40) | reserved v1 | `quantize_selected()` |
| Play (20) / Record (10) | transport; Shift+Record = Capture MIDI (everywhere) | idem |
| RecArm/Mute/Solo/StopClip (1/2/3/8) | toggle track-row mode (arm/mute/solo/stop); Shift+ = Undo/Redo/—/Stop All (all modes) | combos only |
| Track row (101-108) | track select (arm-on-2nd-press) or selected role | inert |
| Session (93) | launch/overview (double-click = overview) | preview-hold; Shift+Session = toggle pin |
| Note (94) / Sequencer (97) | switch to melodic / drum (press active mode's button → back to session) | idem |
| Arrows (80/70 ↑↓, 91/92 ←→) | session navigation | same roles as Mini (velocity/pitch/nudge/pages) |

Inert in v1 (LED dark, swallowed by background): Chord (95), Custom (96), Projects (98), Fixed Length (30), Volume/Pan/Sends/Device (4-7 — button faders need the DAW fader layout). Planned extension pattern for drum variants + chord: **Shift+Sequencer → grid overlay panel**, one pad per variant.

**Pro-specific wiring patterns**: `EditModeComponent` runs **standalone** (`set_standalone(True)`, always enabled in session; `is_active()` = modifier held, so bare presses still launch). Dedicated buttons use direct value listeners + raw CC LEDs (`_update_modifier_leds` / `_update_mixer_function_leds`) — the same pattern as the Mini's transport, no Layer competition. The track-row mixer modes are a plain `ModesComponent` whose `selected_mode` is set by the function-button listeners (shift-combo checked first).

**Hardware bytes still to validate on device** (suspect these first if something is dark):
1. Programmer-mode entry `F0 00 20 29 02 0E 0E 01 F7` — if grid LEDs don't respond to Note On ch 0, this is wrong.
2. Live preferences must bind the **3rd port pair** (`MIDIIN3/MIDIOUT3 (LPProMK3 MIDI)` on Windows). Wrong pair = clips work, LEDs dark.
3. LED writes on CC 101-108 / CC 1-8 (`B0 65 05` test).
4. Feedback (cmd 10) / sleep (cmd 9) commands — assumed Novation-wide; harmless if ignored, remove from `_enter_programmer_mode` if they cause trouble.
5. Setup button behavior (must not silently exit Programmer mode).

## Porting to other Launchpads

Device-specific hardware bytes are isolated behind the overlay seams (see [Repo layout](#repo-layout--overlay-assembly)):
- `mini/device_profile.py` · `pro/device_profile.py` — replace wholesale (USB IDs, SysEx command bytes, button CCs, LED indices). Keep the same public symbol names.
- `programmer_mode.py` — Novation-wide (status bytes, LED + audition channels). Same on Mini MK3 / X / Pro MK3.
- `palette.py` — shared color dicts + `send_pad_color()` helper. Palette indices 0-127 are firmware-standard across the Launchpad family.

Adding a device = new overlay dir (5 files: `__init__.py`, `sysex_ids.py`, `device_profile.py`, `elements.py`, wiring) + an `install_device` line in `install.sh`. `pro/` is the reference port; the diff between `mini/launchpad_mini_mk3.py` and `pro/launchpad_pro_mk3.py` shows exactly which decisions are UX vs hardware.

## Development workflow

No way to run this outside Live — Ableton owns the Python runtime. Loop:

1. Edit `.py` files (shared at repo root, device-specific in `mini/` / `pro/`).
2. Run `./install.sh [--mini|--pro|--all]` (assembles + copies to the Windows-side MIDI Remote Scripts dirs, deletes `Log.txt` once to give a clean read).
3. User restarts Ableton Live (full restart — reloading control surface is not enough).
4. If broken, read log via paths below.

Stay quiet about restart instructions — the user knows.

### Paths

- Source: `/home/mahed/projects/launchpad-mini-mk3-script/`
- Install targets: `/mnt/c/ProgramData/Ableton/Live 12 Suite/Resources/MIDI Remote Scripts/Launchpad_Mini_MK3/` and `.../Launchpad_Pro_MK3/`
- Ableton log: `/mnt/c/Users/mahed/AppData/Roaming/Ableton/Live 12.3/Preferences/Log.txt`

All hard-coded in `install.sh`. No fallback discovery — update if Live version changes.

### Sanity check

```bash
python3 -m py_compile *.py mini/*.py pro/*.py
```

Catches syntax errors. Cannot validate Ableton API (modules not importable here). No test suite, no linting.

### MIDI port reminder

For sequencer LEDs to render, each script must be bound to its device's DAW/script port pair:
- **Mini**: `MIDIIN2 (LPMiniMK3 MIDI)` / `MIDIOUT2 (LPMiniMK3 MIDI)`.
- **Pro**: the 3rd pair — typically `MIDIIN3 (LPProMK3 MIDI)` / `MIDIOUT3 (LPProMK3 MIDI)` on Windows.

Wrong port: launch grid works but Programmer-mode LEDs stay dark. Clip launching works but sequencer pads dark → suspect port mapping.
