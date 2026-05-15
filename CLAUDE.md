# CLAUDE.md

Internal reference. Read `README.md` first for the feature tour — this file focuses on architecture, wiring, and non-obvious gotchas.

## What this is

Custom Ableton Live 12 MIDI Remote Script for the **Novation Launchpad Mini MK3**. Replaces the factory `Launchpad_Mini_MK3` script (decompiled copy under `midi-remote-scripts/Launchpad_Mini_MK3/` for reference) and adds:

- 4-mode bottom row (Select/Arm, Stop, Solo, Mute) cycled by the bottom-right scene button (the "shift" button)
- clip and scene copy-paste while shift is held
- Push-style drum step sequencer
- Launchpad95-style melodic step sequencer
- direct Programmer-mode LED rendering for the sequencers

Built on Novation's official framework (`NovationBase`) — every component subclasses or composes a Novation/Ableton v2 control-surface primitive.

## Mode hierarchy

Three nested layers run simultaneously:

1. **`_main_modes`** (User button) — `session`, `drum_sequence`, `melodic_sequence`. `__on_main_mode_changed` swaps subsystems and rewrites mode-button LEDs.
2. **`_session_modes`** (Session button) — `launch` / `overview`. Only meaningful in `session` main mode.
3. **`_stop_solo_mute_modes`** (shift button = `scene_launch_buttons_raw[7]`) — `select` / `stop` / `solo` / `mute`. `select` uses `ChannelStripComponentWithArmToggle` (smart arm-on-second-press). Only meaningful in `session` main mode.

`TransportComponent` (Drums = play/stop, Keys = session record) stays live in **every** main mode — enabled via `__on_main_mode_changed`, not `_set_session_components_enabled`. No `_set_mode_button_lights` branch touches Drums/Keys.

**Session button extra behavior in sequencer modes** (`__on_session_mode_button_value`): press latches `_main_modes` to `session` and remembers return mode in `_session_preview_return_mode`; release tap (≤`SESSION_HOLD_THRESHOLD`) keeps session, hold reverts. Doesn't fight `session_modes.cycle_mode_button` because that uses `.pressed` (False→False on release fires nothing).

**Shift button is overloaded 5 ways**:
- session: press cycles bottom-row mode; hold+tap clip = copy/paste; hold+tap scene = copy/paste; release clears clipboards (`__on_shift_button_value`)
- sequencer modes: modifier. While "effective" (held or locked), shift-gated controls render lit and accept input — grid-resolution slots 0-3, triplet slot 4, and (melodic only) the top row (page selector + preview toggle). Otherwise `DefaultButton.Disabled` and presses ignored. Each sequencer exposes `set_device_shift_held(bool)`.
- **shift lock**: double-tap (each release within `SHIFT_LOCK_TAP_THRESHOLD` ≈ 0.3s, gap ≤ `SHIFT_DOUBLE_TAP_WINDOW` ≈ 0.35s) toggles sticky `_shift_locked`. **Sequencer modes only** — gated on `_main_modes.selected_mode in ("drum_sequence", "melodic_sequence")` because session-mode uses the button for cycling. Long press resets the detector. Clipboards still clear on physical release. Feedback: `show_message` + slot 7 LED lights `Control.Shift` (AMBER) while effective.

## File map

| File | Responsibility |
|------|---------------|
| `__init__.py` | Capabilities, port declarations, `create_instance`. |
| `launchpad_mini_mk3.py` | Top-level `NovationBase`. Owns modes, wiring, Programmer-mode SysEx, mode-button LEDs. |
| `elements.py` | Hardware layer. Adds `drums_mode_button`/`keys_mode_button`/`user_mode_button` + `Session_Button_Color_Element`. |
| `skin.py` | Skin: `Mode.Session.*`, `Mixer.TrackSelected`, full `DrumSequencer.*` / `MelodicSequencer.*` palettes. Merged via `merge_skins`. |
| `sysex_ids.py` | `LP_MINI_MK3_FAMILY_CODE = (19, 1)`, `LP_MINI_MK3_ID = 13`. |
| `device_profile.py` | **Mini-MK3-specific seam.** USB vendor/product, SysEx command bytes (Programmer mode entry, LED feedback, sleep), mode/arrow button CCs, and mode-button LED palette indices. Swap this file wholesale when porting to another Launchpad. |
| `programmer_mode.py` | Novation-wide Programmer-mode MIDI conventions: `NOTE_ON_STATUS`, `MIDI_CC_STATUS`, `PROGRAMMER_LED_CHANNEL`, `AUDITION_CHANNEL`. Same on Mini MK3 / X / Pro MK3. |
| `palette.py` | Shared `DRUM_SEQUENCER_COLOR_VALUES` / `MELODIC_COLOR_VALUES` dicts + `send_pad_color()` helper. Indices 0-127 are the Launchpad firmware palette, identical across models. |
| `channel_strip_with_arm_toggle.py` | Click unselected → select; click selected → toggle arm. Honors `song.exclusive_arm`. |
| `clip_copy_component.py` | Clip clipboard. Validates audio/MIDI; uses `duplicate_clip_to`. |
| `scene_copy_component.py` | Inserts new scene at target index, duplicates non-empty slots, copies name/color/tempo/time-sig. |
| `clip_slot_with_copy.py` | Intercepts `_on_launch_button_pressed`, routes to clip copy when shift held. |
| `transport_component.py` | Drums = play/stop, Keys = session record. Active in every main mode. |
| `session_with_copy.py` | Propagates shift + copy handlers to every clip slot/scene (incl. via `_create_scene`). |
| `notifying_background.py` | `BackgroundComponent` that fires `value` instead of swallowing — refreshes layout switch on Drums/Keys press. |
| `drum_step_sequencer.py` | 4×8 step grid + 4×4 drum-pad selector + 4×4 loop/grid selector. Step-hold gestures (velocity/nudge/extend). Owns LED rendering + audition. |
| `melodic_step_sequencer.py` | 7×8 pitch×step grid + dual-purpose row 0 (page selector + preview toggle when shift held). |
| `event_bus.py` / `events.py` | Tiny sync pubsub. `Event.*` string constants are the contract between emitters and subscribers. |
| `notification_catalog.py` | `Msg.*` integer wire IDs for LP Notify M4L device. **Append-only.** Plus `GRID_RESOLUTION_INDICES`, `MODE_ID_*`. |
| `status_bar_subscriber.py` | Single owner of every user-visible `show_message` wording (`_FORMATTERS` table). |
| `m4l_subscriber.py` | Maps events to `(msg_id, args)`, forwards to dispatcher. No-op without LP Notify device. |
| `notification_dispatcher.py` | Discovers LP Notify device on any track, binds params by name, writes `msg_id/arg1-3/seq` on `send()`. |
| `install.sh` | WSL→Windows install. Paths hard-coded for `mahed`'s machine. |

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
- **`_log`** writes to Ableton's `Log.txt`. Tags: `[Launchpad Mini MK3]`, `[DrumStepSequencer]`, `[MelodicStepSequencer]`. `install.sh` clears the log per install.
- **`show_message` from components is forbidden** — emit a bus event, let `StatusBarSubscriber` choose wording. Same for M4L: never reference `Msg.*` or `device.parameters` from a component.
- **`request_rebuild_midi_map()`** must be called after changing button identifiers/channels or `script_forwarding` (audition translations, leaving sequencer mode, etc.).
- **Color sources are split**: `skin.py` for standard pipeline (`set_light`); sequencer pads bypass skin and write raw palette indices (`DRUM_SEQUENCER_COLOR_VALUES` / `MELODIC_COLOR_VALUES`). Wrong color = palette dict is source of truth.
- **Shift button is `scene_launch_buttons_raw[7]`** (scene buttons stored top-to-bottom via `range(89, 18, -10)`, so 7 = bottom).
- **`detail_clip` vs `highlighted_clip_slot`**: sequencers prefer `song.view.detail_clip` if valid MIDI; else highlighted slot. `_ensure_clip` creates an empty MIDI clip only if track allows. **Drum sequencer auto-fires the new clip** on create-from-scratch (Push-2 style).
- **Loop auto-extension is gated by `_clip_just_created`**. Set True ONLY in `_ensure_clip`'s create-from-scratch branch; cleared on clip change, leaving sequencer mode, or any user loop-scoping gesture. `_ensure_loop_contains_time` is the SINGLE gate — it no-ops when False. Consequence: opening an existing clip + adding a note past `loop_end` writes the note but leaves the loop untouched (note silent in current pass). Don't bypass without a strong reason.
- **User button** cycles three modes (`session → drum → melodic → session`). Drums/Keys are NOT mode switches — they're owned by `TransportComponent`. They remain in `BackgroundComponent`'s nop layer so the layout-enquire round-trip still fires.
- **`SessionOverviewComponent`** uses the same `clip_launch_matrix` as launch. `_restore_clip_launch_matrix` resets identifiers when leaving a sequencer mode.
- **Decompiled source uses Python 3.7 conventions** (`from __future__`, old-style `super()`). Match that style for files originating from Live bundle; new files don't have to.
- **`support_momentary_mode_cycling=False`** on `_stop_solo_mute_modes` is what makes shift cycle vs hold work. Don't flip it.

## Porting to other Launchpads

Device-specific hardware bytes are isolated behind three seams:
- `device_profile.py` — Mini-MK3-specific. Replace wholesale (USB IDs, SysEx command bytes, mode/arrow CCs, mode-button LED indices).
- `programmer_mode.py` — Novation-wide (status bytes, LED + audition channels). Same on Mini MK3 / X / Pro MK3.
- `palette.py` — shared color dicts + `send_pad_color()` helper. Palette indices 0-127 are firmware-standard across the Launchpad family.

`elements.py` is decompiled from Ableton's bundle and will need its own per-device replacement when forking. The shift-as-`scene_launch_buttons_raw[7]` overload (`_create_stop_solo_mute_modes`) is a Mini-MK3 UX choice — Pro MK3 has a dedicated Shift button and would wire differently.

## Development workflow

No way to run this outside Live — Ableton owns the Python runtime. Loop:

1. Edit `.py` files at repo root.
2. Run `./install.sh` (copies to Windows-side MIDI Remote Scripts dir, deletes `Log.txt` to give a clean read).
3. User restarts Ableton Live (full restart — reloading control surface is not enough).
4. If broken, read log via paths below.

Stay quiet about restart instructions — the user knows.

### Paths

- Source: `/home/mahed/projects/launchpad-mini-mk3-script/`
- Install target: `/mnt/c/ProgramData/Ableton/Live 12 Suite/Resources/MIDI Remote Scripts/Launchpad_Mini_MK3/`
- Ableton log: `/mnt/c/Users/mahed/AppData/Roaming/Ableton/Live 12.3/Preferences/Log.txt`

Both hard-coded in `install.sh`. No fallback discovery — update if Live version changes.

### Sanity check

```bash
python3 -m py_compile *.py
```

Catches syntax errors. Cannot validate Ableton API (modules not importable here). No test suite, no linting.

### MIDI port reminder

For sequencer LEDs to render, script must be bound to `MIDIIN2 (LPMiniMK3 MIDI)` / `MIDIOUT2 (LPMiniMK3 MIDI)`. Non-`MIDIIN2` ports work for launch grid but not Programmer-mode LEDs. Clip launching works but sequencer pads dark → suspect port mapping.
