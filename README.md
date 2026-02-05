# Launchpad Mini MK3 - Custom Ableton Live Remote Script

A custom MIDI remote script for the **Novation Launchpad Mini MK3** that extends the default Ableton Live 12 controller with advanced features: **clip & scene copy-paste**, **smart arm toggle**, and a **4-mode bottom row**.

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

1. Copy all `.py` files from this repository to Ableton's MIDI Remote Scripts folder:

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

6. Set **Input** and **Output** to `LPMiniMK3 MIDI`

### WSL Install Script

If you develop on WSL, you can use the included `install.sh` script. Edit the `SOURCE_DIR` and `DEST_DIR` paths to match your setup, then run:

```bash
./install.sh
```

---

## Project Structure

| File | Description |
|------|-------------|
| `__init__.py` | Entry point &mdash; registers controller capabilities and MIDI ports |
| `launchpad_mini_mk3.py` | Main control surface class, mode setup, component wiring |
| `elements.py` | Hardware button/pad definitions (MIDI notes, SysEx elements) |
| `skin.py` | LED color scheme (merges custom colors with Novation base skin) |
| `sysex_ids.py` | Device family code and model ID constants |
| `channel_strip_with_arm_toggle.py` | Smart arm toggle on track selection buttons |
| `clip_copy_component.py` | Clip clipboard management and paste validation |
| `scene_copy_component.py` | Scene clipboard management with full property duplication |
| `clip_slot_with_copy.py` | Shift-key detection on individual clip slots |
| `session_with_copy.py` | Extended session and scene components with copy-paste integration |
| `notifying_background.py` | Background component that emits events on mode button changes |
| `install.sh` | Installation script for WSL/Windows deployment |

---

## How It Works

This script extends Novation's official Ableton controller framework (`NovationBase`). It overrides and adds components on top of the standard Launchpad Mini MK3 behavior:

- **Component architecture**: Each feature (arm toggle, clip copy, scene copy) is a self-contained component that plugs into the session
- **Shift button**: The bottom-right scene launch button serves double duty &mdash; it cycles the bottom-row modes on press and enables copy-paste when held
- **Clipboard lifecycle**: Both clip and scene clipboards are cleared automatically when the shift button is released
- **Color feedback**: Button colors update in real-time via listeners on track arm state, selection, and mode changes

---

## Compatibility

- Ableton Live **12** (built on the v2 control surface API)
- Novation **Launchpad Mini MK3**
