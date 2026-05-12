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

`TransportComponent` binds the **Drums** button (CC 96) to play/stop and the **Keys** button (CC 97) to session record. It stays live in `session` AND `drum_sequence` main modes (only `melodic_sequence` disables it). Enable/disable is driven by `__on_main_mode_changed` (`self._transport.set_enabled(not melodic_mode)`) — NOT by `_set_session_components_enabled`. The `session` and `drum_sequence` branches of `_set_mode_button_lights` therefore leave drums/keys untouched (transport owns them); the `melodic_sequence` branch still forces them OFF as a safety belt.

The **Session button** (CC 95) gets an extra Push-style momentary-preview behavior while `_main_modes == "drum_sequence"` (see `__on_session_mode_button_value` in `launchpad_mini_mk3.py`): press latches main mode to `session`, release decides — tap (≤ `SESSION_HOLD_THRESHOLD`s) keeps session, hold reverts to `drum_sequence`. No interference with the standard `session_modes` `cycle_mode_button` because that uses `.pressed` (transition not_pressed→pressed) and session_modes' Button State is freshly constructed at `set_enabled(True)` with `_is_pressed=False`; the release that follows simply transitions False→False, no event fired. In `session` or `melodic_sequence` modes the listener is a no-op and the button keeps its `session_modes` semantics.

The shift button is overloaded three ways: **press to cycle** the bottom-row mode, **hold + tap clip slot** to copy/paste a clip, **hold + tap scene button** to copy/paste a scene. Release clears both clipboards (`__on_shift_button_value`).

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
| `transport_component.py` | `TransportComponent` — Drums button = global play/stop toggle, Keys button = session record toggle. Active in session AND drum_sequence main modes; disabled in melodic_sequence. |
| `session_with_copy.py` | `SessionComponentWithCopy` + `SceneComponentWithCopy`. Propagates the shift button and the two copy handlers to every clip slot / scene (including dynamically created ones via `_create_scene`). |
| `notifying_background.py` | `BackgroundComponent` that fires a `value` event instead of swallowing it — used to refresh the layout switch when Drums/Keys mode buttons are pressed. |
| `drum_step_sequencer.py` | `DrumStepSequencerComponent`. 4×8 step grid (top), 4×4 drum-pad selector (bottom-left), 4×4 cyclable matrix (bottom-right: loop pages OR velocity selector). Owns its own LED rendering, audition translations, runtime step-grid resolution (1/4–1/32), and the scene-button control row. |
| `melodic_step_sequencer.py` | `MelodicStepSequencerComponent`. 7×8 pitch×step grid + 1 bottom row (7 page pads + 1 preview-toggle pad). Scale-aware pitch rows. |
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

**Drum sequencer** layout (page +/- removed — the bottom-right 4×4 page selector already does navigation; octave/semitone moved to the top arrows; the four resolutions then reset and shift sit on the top six slots; slot 6 cycles the bottom-right 4×4 between loop and velocity modes; slot 7 is the shared device shift / stop-solo-mute button owned by `_stop_solo_mute_modes` in session mode and intentionally left untouched by the drum sequencer):

| idx | function | LED skin key |
|---|---|---|
| 0 | grid 1/4 | `Grid` or `GridSelected` |
| 1 | grid 1/8 | `Grid` or `GridSelected` |
| 2 | grid 1/16 (default) | `Grid` or `GridSelected` |
| 3 | grid 1/32 | `Grid` or `GridSelected` |
| 4 | reset pitch offset | `DrumSequencer.Control.Reset` |
| 5 | shift / show status | `DrumSequencer.Control.Shift` |
| 6 | cycle bottom-right mode | `CycleLoop` (aqua) or `CycleVelocity` (yellow) |
| 7 | (untouched — device shift) | (driven by `_stop_solo_mute_modes` / disabled) |

Slot indices come from `GRID_FIRST_SLOT`/`GRID_LAST_SLOT`/`RESET_SLOT`/`SHIFT_SLOT`/`CYCLE_SLOT` constants in `drum_step_sequencer.py`. Grid slots are driven by `GRID_OPTIONS` (module-level tuple of `(step_length_in_beats, label)`); the active resolution lights up `GridSelected` (bright), the others light up `Grid` (dim). `STEP_LENGTH`/`PAGE_LENGTH` used to be module constants but are now per-instance (`self._step_length`, `self._page_length`) since they change at runtime via `_set_step_length`. Existing notes are NOT remapped on grid change — only the step-to-time alignment changes, so a 1/16 note already in the clip starts in step 0 at 1/16, step 0 at 1/32 (because both windows start at beat 0), or some non-step-0 column if the start time isn't aligned to the new grid. Pages, loop scoping, and clip-creation lengths all scale with `self._page_length`.

### Bottom-right 4×4 modes (drum sequencer)

`self._bottom_right_mode` switches the bottom-right quadrant between two modes (Push-2 style); slot 6 (`CYCLE_SLOT`) toggles — note slot 7 stays untouched because it's the device-shared shift / stop-solo-mute button (`scene_launch_buttons_raw[7]`). `_update_bottom_right_leds` and `_on_grid_matrix_value` both branch on the current mode.

- **`loop`** (default): 16 pages, see "Loop scoping pattern" below. Cycle LED = aqua.
- **`velocity`**: 16 cells map to `BOTTOM_RIGHT_VELOCITIES` (a tuple of 16 velocities from 8 → 127). The first 14 cells (vel 8–104) are **playable**: `_update_audition_translations` translates each one to `(selected_pitch, channel=cell_index+2)`, giving 14 distinct `(channel, identifier)` forwarding keys on channels 2–15. All 14 cells route to the selected drum's pitch, so pressing any cell triggers the drum on the track; channel-based key uniqueness means the matrix value listener can still tell which cell was pressed so the right velocity slice becomes the default. **Cells 14 and 15** (vel 120 and 127) deliberately stay in default exclusive state — they only set `self._default_velocity`, they don't audition. **Caveat for all cells**: Live's translation map doesn't allow forcing a fixed velocity per cell, so the velocity actually heard on the audition cells is the hardware press velocity. The cell value only drives the highlighted LED and `self._default_velocity` (used when toggling new notes via `_toggle_step`). Existing notes' velocities are not touched. Cycle LED = yellow.

The asymmetry (14 audition cells + 2 silent cells) is the cleanest available trade-off: channel 0 is owned by the device's raw pad notes (every untranslated pad registers `(0, original_id)` there, including top-step pads with ids 51-88 that overlap with drum pitches at 51+), and channel 1 is owned by the bottom-left drum-pad selector (every drum pitch is registered as `(1, pitch)`). Using either channel for a velocity cell forces dropping one bottom-left selector cell or accepting a registry collision; sacrificing the two least-used velocities is less disruptive.

`DEFAULT_VELOCITY` is still a module constant for the initial value but is no longer the live source of truth — use `self._default_velocity`. `_update_audition_translations` is re-called whenever `_selected_pitch` changes (`_select_note_by_grid_position` and `_on_selected_drum_pad_changed`) so the velocity cells follow the active drum. When the user toggles back to loop mode, any in-flight loop press state (`_loop_press_points`, `_loop_range_active`) is reset so a leftover hold can't accidentally scope a range after the mode switch.

**Melodic sequencer** still uses indices 2–5 for octave/semitone (no arrow mapping there yet):

| idx | function | LED skin key |
|---|---|---|
| 0 | page − | `MelodicSequencer.Control.Page` |
| 1 | page + | `MelodicSequencer.Control.Page` |
| 2 | octave − (−12) | `MelodicSequencer.Control.Octave` |
| 3 | octave + (+12) | `MelodicSequencer.Control.Octave` |
| 4 | semitone − | `MelodicSequencer.Control.Semitone` |
| 5 | semitone + | `MelodicSequencer.Control.Semitone` |
| 6 | reset pitch offset | `MelodicSequencer.Control.Reset` |
| 7 | shift / show status | `MelodicSequencer.Control.Shift` |

Pressing 7 only triggers `_show_navigation_message()` in the current implementation — there is no chord/shift functionality yet despite the name.

### Top-row arrow buttons in `drum_sequence`

The four arrow buttons (`up_button`/`down_button`/`left_button`/`right_button`, CC 91–94) are reused as pitch-offset controls for the drum-pad selector while `_main_modes == "drum_sequence"`. The parent control surface owns these listeners directly (`__on_up_button_value` etc. in `launchpad_mini_mk3.py`) and delegates to `DrumStepSequencerComponent.adjust_pitch_offset(delta)` — a public wrapper around the private `_adjust_pitch_offset`. Mapping: ↑ = +12, ↓ = −12, ← = −1, → = +1. In any other main mode the listeners are a no-op so `session_navigation` keeps its standard arrow behavior in session overview. LEDs are set in `_set_mode_button_lights` (`LED_ARROW_OCTAVE` / `LED_ARROW_SEMITONE`) and turned off when leaving drum_sequence so a stale octave color doesn't linger.

### Drum sequencer specifics

- Grid split: `step_matrix = submatrix[:, :4]` (top 4 rows), `note_matrix = submatrix[:4, 4:8]` (bottom-left 4×4), `loop_matrix = submatrix[4:8, 4:8]` (bottom-right 4×4). **`submatrix` indexing is `[cols, rows]`**, not the usual `[rows, cols]`.
- `STEPS_PER_PAGE = 32` is a module constant. `STEP_LENGTH` / `PAGE_LENGTH` are per-instance (`self._step_length`, `self._page_length`) since the user can switch the step-grid resolution at runtime via the scene-button slots 0-3 (1/4, 1/8, 1/16, 1/32). Default is 1/16 → step=0.25 beats, page=8 beats. A 1/32 grid gives a 1-measure page in 4/4.
- `_pitch_for_note_button(x, y)`: when a Drum Rack device exists on the track and pitch_offset is zero, the selector reads `drum_group_device.visible_drum_pads` directly so the layout follows Live's drum rack window. Otherwise it falls back to `NOTE_SELECTOR_BASE_PITCH (36) + pitch_offset + index`.
- Created clips default to one page (`self._page_length * DEFAULT_CLIP_PAGES`), so 8 beats at 1/16 or 4 beats at 1/32. Creating a clip from scratch via a step press also calls `slot.fire()` to start playback immediately (Push-2 style — see the `_ensure_clip` gotcha in "Conventions and gotchas" below).

### Melodic sequencer specifics

- `STEPS_PER_PAGE = 8`, `DEFAULT_CLIP_PAGES = 8`, so a fresh clip is 8 pages × 2 beats = 16 beats.
- Pitch rows use the song's `root_note` and scale. Only `Major`/`Minor` are distinguished today; anything else falls back to the major scale (`_current_scale` substring-matches "minor" in `song.scale_name`). Rows go top-to-bottom = high pitch to low (`degree = 6 - y`).
- The bottom row mixes 7 page pads (x=0..6) and one preview-toggle pad at `(7, 7)`. Preview mode swaps the top 7 rows from piano-roll editing to live audition (via audition translations); page pads stay live in both modes.
- `_held_grid_buttons` deduplicates note-on bursts so a sustained press only toggles once.

### Clip & scene copy

- The shift button is registered twice on `SessionComponentWithCopy.set_modifier_button(..., "copy_shift", clip_slots_only=...)` so it is propagated to both clip slots **and** scenes. The custom subclass stashes a reference in `self._copy_shift_button` and forwards it to every scene.
- `_create_scene` is overridden so newly instantiated scenes (after track add/remove) also receive the shift button and both handlers.
- Both handlers expose `clear_clipboard()`. The top-level `__on_shift_button_value` listener calls both on release.

## Conventions and gotchas

- **Matrix coordinate quirks.** `ButtonMatrixElement.submatrix[cols, rows]` is `[x, y]`; `matrix.get_button(y, x)` is `(row, col)`. Both forms appear in the sequencers — don't swap them blindly.
- **`_log` writes to Ableton's `Log.txt`** (`<Live prefs>/Log.txt`). Each sequencer prefixes its own tag (`[DrumStepSequencer]`, `[MelodicStepSequencer]`); the control surface prefixes `[Launchpad Mini MK3]`. Useful when iterating; `install.sh` clears the log on each install for the WSL path.
- **`show_message`** displays in Live's status bar (bottom-left of the main window). Use it for any user-visible feedback that isn't an LED.
- **`request_rebuild_midi_map()`** must be called after changing button identifiers/channels or `script_forwarding` (audition translations, leaving sequencer mode, etc.) — otherwise the new mapping won't take effect until a manual map rebuild.
- **Color sources are split.** `skin.py` is used by the standard component pipeline (session grid, mixer, mode buttons via `set_light`). Sequencer pads bypass the skin entirely and write raw palette indices (see `DRUM_SEQUENCER_COLOR_VALUES` / `MELODIC_COLOR_VALUES`). If a sequencer pad shows the wrong color, the palette dict — not the skin — is the source of truth.
- **The shift button is `scene_launch_buttons_raw[7]`.** The scene buttons are stored top-to-bottom (`range(89, 18, -10)`), so index 7 is the bottom one. This is wired by hand in `_create_stop_solo_mute_modes`.
- **`detail_clip` vs `highlighted_clip_slot`.** Sequencers prefer `song.view.detail_clip` if it is a valid MIDI clip; otherwise they fall back to the highlighted slot. `_ensure_clip` will create an empty MIDI clip in the highlighted slot only if the track can hold MIDI. **Drum sequencer auto-fires the new clip.** When a step press creates the clip from scratch, `_ensure_clip` calls `slot.fire()` immediately so the clip starts playing (Push-2 style — instant audible feedback for the first step). Live's session-view semantics handle the transport: if the song wasn't playing, `fire()` starts global playback; if it was, the clip is queued at the next launch quantization. Only the create-from-scratch path fires; pressing a step on an existing clip does not.
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
