# Launchpad Mini MK3 / Pro MK3 - Custom Ableton Live Remote Scripts

Custom MIDI remote scripts for the **Novation Launchpad Mini MK3** and **Launchpad Pro MK3** that extend the default Ableton Live 12 controllers with advanced features: **clip & scene copy-paste**, **smart arm toggle**, a **4-mode bottom row**, and **drum/melodic step sequencers** inspired by Push and Launchpad95.

Both devices share the same component core; the feature tour below describes the Mini. The Pro port maps the same features onto its dedicated hardware buttons — see [Launchpad Pro MK3](#launchpad-pro-mk3) below.

---

## Features

### Smart Arm/Select Toggle

The default bottom-row mode turns the 8 pads into track selectors with integrated arm control:

- **Click an unselected track** &rarr; selects it (green LED)
- **Click the already-selected track** &rarr; toggles arm on/off (red LED when armed)
- Respects Ableton's **Exclusive Arm** preference (arms one track, disarms the rest)
- Works with **multi-track selection** (arms/disarms all selected tracks together)

| LED Color | State |
|-----------|-------|
| Green | Selected, not armed |
| Red | Selected and armed |
| Grey | Not selected |

### 4-Mode Bottom Row Cycling

Press the **shift button** (bottom-right scene button) to cycle through four modes for the bottom row of pads:

| # | Mode | Function | Shift Button Color |
|---|------|----------|--------------------|
| 1 | **Select/Arm** | Select track / toggle arm | Aqua |
| 2 | **Stop** | Stop clip on track | Green |
| 3 | **Solo** | Solo track | Blue |
| 4 | **Mute** | Mute track | Orange |

Select/Arm is the **default mode** and always appears first when cycling.

### Clip Copy-Paste

Duplicate clips across your session without touching the mouse:

1. **Hold** the shift button (bottom-right)
2. **Click a clip** to copy it to the clipboard
3. **Click an empty slot** to paste it there
4. **Release** shift to clear the clipboard

Rules:
- You can paste the same clip **multiple times** before releasing shift
- Cannot overwrite existing clips (paste only to empty slots)
- Validates **audio/MIDI track compatibility** (audio clips only paste to audio tracks)
- Cannot copy clips that are currently recording
- Group track slots are skipped

### Scene Copy-Paste

Duplicate entire scenes with all their clips and properties:

1. **Hold** the shift button (bottom-right)
2. **Click a scene button** (right column) to copy that scene
3. **Click another scene button** to paste &mdash; a new scene is inserted at that position
4. **Release** shift to clear the clipboard

What gets copied:
- All clips across every track (skips incompatible track types)
- Scene name and color
- Tempo and time signature (if set)

You can paste the same scene multiple times before releasing shift.

### Session Launch & Overview Modes

Toggle between two session views using the **session mode button** (top row):

| Mode | Description | Button Color |
|------|-------------|--------------|
| **Launch** | Standard 8x8 clip launch grid | Pale green |
| **Overview** | Session overview with navigation | Blue |

In **Overview mode**, the arrow buttons become active:
- **Up / Down** &rarr; scroll scenes
- **Left / Right** &rarr; scroll tracks

### Drum Step Sequencer

Press the **User** mode button once from Session mode to enter the Drum Step Sequencer.

The grid is split into three zones:

| Zone | Pads | Function |
|------|------|----------|
| Top 4 rows | 32 pads | Toggle steps for the selected drum sound |
| Bottom-left 4x4 | 16 pads | Select/play drum sounds |
| Bottom-right 4x4 | 16 pads | Select, scope, or range the clip pages |

Behavior:
- Step pads add/remove MIDI notes in the selected MIDI clip.
- The bottom-left drum pads are playable and also select the active drum lane.
- The sequencer follows the selected clip or creates a MIDI clip in the highlighted slot.
- LEDs are rendered directly in Launchpad Programmer mode for reliable feedback.

Page/loop behavior:
- Tap a page pad once to view that page.
- Double-tap a page pad to scope the clip loop to that single page.
- Hold one page pad and press another page pad to scope the loop across the page range, Push-style.

### Melodic Step Sequencer

Press the **User** mode button twice from Session mode to enter the Melodic Step Sequencer. The User button cycles:

```text
Session -> Drum Step Sequencer -> Melodic Step Sequencer -> Session
```

The melodic layout uses the top 7 rows as a 7x8 melodic step grid and the bottom row as page controls:

| Zone | Pads | Function |
|------|------|----------|
| Top 7 rows | 56 pads | Toggle notes by pitch row and time column |
| Bottom row, pads 1-7 | 7 pads | Select/scope clip pages |
| Bottom row, pad 8 | 1 pad | Toggle Preview mode |

Behavior:
- In piano-roll mode, pressing a grid pad writes/removes the note at that step.
- In preview mode, pressing a grid pad plays the note without writing to the clip.
- The bottom-right pad toggles piano-roll/preview mode.
- Notes follow the song root note and a major/minor scale fallback.

Page/loop behavior:
- Tap a page pad once to view that page.
- Double-tap a page pad to scope the clip loop to that single page.
- Hold one page pad and press another page pad to scope the loop across the page range, Push-style.

### Sequencer Side Controls

In Drum and Melodic sequencer modes, the right-side scene buttons become navigation controls:

| Scene button | Function |
|--------------|----------|
| 1 | Previous page |
| 2 | Next page |
| 3 | Octave down |
| 4 | Octave up |
| 5 | Semitone down |
| 6 | Semitone up |
| 7 | Reset pitch offset |
| 8 | Show page/octave/semitone status |

These controls are active only in sequencer modes. Session mode keeps the normal scene/bottom-row behavior.

---

## Button Layout

```
 [  UP  ] [ DOWN ] [ LEFT ] [RIGHT ] [     ] [     ] [     ] [SESSION]   <- Top row
 +-------+-------+-------+-------+-------+-------+-------+-------+---+
 |       |       |       |       |       |       |       |       | S |
 |       |       |  8x8 Clip Launch / Session Overview Grid      | C |
 |       |       |       |       |       |       |       |       | E |
 |       |       |       |       |       |       |       |       | N |
 |       |       |       |       |       |       |       |       | E |
 |       |       |       |       |       |       |       |       |   |
 |       |       |       |       |       |       |       |       | L |
 +-------+-------+-------+-------+-------+-------+-------+-------+ A +
 | Trk 1 | Trk 2 | Trk 3 | Trk 4 | Trk 5 | Trk 6 | Trk 7 | Trk 8 |   <- Bottom row
 +-------+-------+-------+-------+-------+-------+-------+-------+ U +
                                                                  | N |
                                                                  | C |
                                                                  | H |
                                                                  +---+
                                                              [SHIFT]   <- Shift / Mode cycle
```

- **8x8 Grid**: Launch clips (or view session overview)
- **Right column** (scene buttons): Launch scenes / copy scenes (with shift held)
- **Bottom row**: Track control &mdash; changes based on active mode (select, stop, solo, mute)
- **Shift button** (bottom-right): Cycle modes + hold for copy-paste
- **Session button** (top-right area): Toggle Launch / Overview mode
- **Arrow buttons**: Navigate session grid (active in Overview mode)

---

## Installation

### Prerequisites

- **Ableton Live 12 Suite**
- **Novation Launchpad Mini MK3**

### Steps

1. Copy all root `.py` files **plus** the device overlay's `.py` files (`mini/` for the Mini, `pro/` for the Pro — see [Project Structure](#project-structure)) flat into Ableton's MIDI Remote Scripts folder:

   **Windows:**
   ```
   C:\ProgramData\Ableton\Live 12 Suite\Resources\MIDI Remote Scripts\Launchpad_Mini_MK3\
   ```

   **macOS:**
   ```
   /Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts/Launchpad_Mini_MK3/
   ```

   > This replaces the default Launchpad Mini MK3 script. To revert, delete the folder and reinstall/repair Ableton Live.

2. **Close** Ableton Live completely if it's open

3. **Relaunch** Ableton Live

4. Go to **Preferences &rarr; Link/Tempo/MIDI**

5. Set **Control Surface** to `Launchpad Mini MK3`

6. Recommended ports for the sequencer/direct LED feedback:

   - **Input**: `MIDIIN2 (LPMiniMK3 MIDI)`
   - **Output**: `MIDIOUT2 (LPMiniMK3 MIDI)`

   If those ports are not visible, try `LPMiniMK3 MIDI`, but the sequencer Programmer-mode feedback may not behave correctly.

### WSL Install Script

If you develop on WSL, you can use the included `install.sh` script. Edit the `SOURCE_DIR` / destination paths to match your setup, then run:

```bash
./install.sh           # installs both devices
./install.sh --mini    # Launchpad Mini MK3 only
./install.sh --pro     # Launchpad Pro MK3 only
```

The script assembles the shared root files + the device overlay (`mini/` or `pro/`) flat into each device's MIDI Remote Scripts folder — `Launchpad_Mini_MK3` (replaces the factory Mini script) and `Launchpad_Pro_MK3_Custom` (coexists with the factory Pro script). For a manual install, reproduce that: copy all root `.py` files **plus** the overlay's `.py` files into one flat folder.

---

## Launchpad Pro MK3

The Pro port keeps the same modes and sequencers but uses the Pro's dedicated buttons instead of the Mini's hold/double-tap gestures:

- **Shift** (real button) — copy-paste modifier in session, shift layer in sequencers. No more double-taps or shift lock.
- **Clear / Duplicate** — hold + tap to delete/duplicate clips & scenes (session) or steps/pads/pages (drum sequencer). Shift+Duplicate doubles the loop.
- **Quantise** — quantize selection in sequencer modes. **Shift+Record** — Capture MIDI.
- **Play / Record** — dedicated transport.
- **Note / Chord / Custom / Sequencer buttons** — plain press = the **native firmware modes** (Note, Chord with its 16 saveable chord slots, Custom Modes, hardware step sequencer), with played notes flowing straight into the armed track. **Shift+button = the custom script modes**: Shift+Note = melodic sequencer, Shift+Chord = chord pads, Shift+Sequencer = drum sequencer (again while in a drum mode = picker panel to choose between the three variants: classic 4×8, 64-step single pad, 4-track × 16 steps).
- **Track-select row + Record Arm/Mute/Solo/Stop Clip** — mixer modes below the grid, so the full 8×8 grid stays clips and all 8 scene buttons launch scenes. Shift+Record Arm = Undo, Shift+Mute = Redo, Shift+Stop Clip = Stop All Clips.
- **Returning from native modes** — the script is hands-off while a native mode runs; press **Session on the device** to come back to the custom script.

**The Pro script installs as a separate control surface** (`Launchpad Pro MK3 Custom`) — the factory `Launchpad Pro MK3` script is left untouched and both coexist in Live's Control Surface list.

Ports: bind the **first** port pair (`LPProMK3 MIDI` on Windows) — that's the Pro's MIDI interface where Programmer-mode LEDs live. Do **not** bind `MIDIIN3` (that's the DAW interface, used by the factory script).

---

## Project Structure

Shared components live at the repo root; device-specific modules live in `mini/` and `pro/` (same module names, assembled flat at install time).

| File | Description |
|------|-------------|
| `mini/__init__.py` · `pro/__init__.py` | Entry points &mdash; controller capabilities and MIDI ports |
| `mini/launchpad_mini_mk3.py` · `pro/launchpad_pro_mk3.py` | Main control surface classes, mode setup, component wiring |
| `mini/elements.py` · `pro/elements.py` | Hardware button/pad definitions (MIDI notes, SysEx elements) |
| `skin.py` | LED color scheme (merges custom colors with Novation base skin) |
| `mini/sysex_ids.py` · `pro/sysex_ids.py` | Device family code and model ID constants |
| `mini/device_profile.py` · `pro/device_profile.py` | Per-device seam: USB IDs, SysEx command bytes, button CCs, LED indices |
| `channel_strip_with_arm_toggle.py` | Smart arm toggle on track selection buttons |
| `clip_copy_component.py` | Clip clipboard management and paste validation |
| `scene_copy_component.py` | Scene clipboard management with full property duplication |
| `drum_step_sequencer.py` | Push-style drum sequencer, drum pad preview, page scoping |
| `melodic_step_sequencer.py` | Melodic sequencer, preview mode, pitch/page navigation |
| `clip_slot_with_copy.py` | Shift-key detection on individual clip slots |
| `session_with_copy.py` | Extended session and scene components with copy-paste integration |
| `notifying_background.py` | Background component that emits events on mode button changes |
| `install.sh` | Installation script for WSL/Windows deployment |

---

## How It Works

This script extends Novation's official Ableton controller framework (`NovationBase`). It overrides and adds components on top of the standard Launchpad Mini MK3 behavior:

- **Component architecture**: Each feature (arm toggle, clip copy, scene copy, sequencers) is a self-contained component that plugs into the session
- **Shift button**: The bottom-right scene launch button serves double duty &mdash; it cycles the bottom-row modes on press and enables copy-paste when held
- **Clipboard lifecycle**: Both clip and scene clipboards are cleared automatically when the shift button is released
- **Color feedback**: Button colors update in real-time via listeners on track arm state, selection, and mode changes
- **Programmer mode**: Sequencers switch the Launchpad into Programmer mode and render pad LEDs directly to avoid Session-mode LED conflicts
- **MIDI forwarding**: Drum pad preview uses Live MIDI forwarding. Melodic preview is isolated behind a Preview mode so it does not conflict with step-coordinate mapping

---

## Compatibility

- Ableton Live **12** (built on the v2 control surface API)
- Novation **Launchpad Mini MK3**
