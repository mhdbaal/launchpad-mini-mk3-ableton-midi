# Launchpad Pro MK3 hardware element layer.
#
# Subclasses the shared novation LaunchpadElements with the Pro's CC map
# (arrows split between the left column and the top row, Session on 93)
# and adds the dedicated buttons the Mini doesn't have. Deliberately
# omitted vs the factory elements: button faders, print-to-clip and the
# *_with_shift ComboElements — shift combos are handled in the wiring
# (direct value listeners checking shift_button.is_pressed()), matching
# how this codebase wires the sequencer control buttons.
#
# Only Programmer-mode controls are needed; musical audition is translated
# from the grid by the active software sequencer.
from __future__ import absolute_import, print_function, unicode_literals
from ableton.v2.base import depends
from ableton.v2.control_surface.elements import ButtonMatrixElement
from novation.launchpad_elements import SESSION_WIDTH, LaunchpadElements, create_button
from . import device_profile as profile
from . import sysex_ids as ids


class Elements(LaunchpadElements):
    model_id = ids.LP_PRO_MK3_ID
    default_layout = ids.SESSION_LAYOUT_BYTES

    @depends(skin=None)
    def __init__(self, skin=None, *a, **k):
        super(Elements, self).__init__(
            *a, arrow_button_identifiers=(
                profile.UP_BUTTON_CC,
                profile.DOWN_BUTTON_CC,
                profile.LEFT_BUTTON_CC,
                profile.RIGHT_BUTTON_CC),
            session_mode_button_identifier=profile.SESSION_BUTTON_CC, **k)
        # Left column modifiers + transport.
        self.shift_button = create_button(profile.SHIFT_BUTTON_CC, "Shift_Button")
        self.clear_button = create_button(profile.CLEAR_BUTTON_CC, "Clear_Button")
        self.duplicate_button = create_button(profile.DUPLICATE_BUTTON_CC, "Duplicate_Button")
        self.quantize_button = create_button(profile.QUANTIZE_BUTTON_CC, "Quantize_Button")
        self.fixed_length_button = create_button(profile.FIXED_LENGTH_BUTTON_CC, "Fixed_Length_Button")
        self.play_button = create_button(profile.PLAY_BUTTON_CC, "Play_Button")
        self.record_button = create_button(profile.RECORD_BUTTON_CC, "Record_Button")
        # Top-row mode buttons (Session comes from the base class).
        self.note_mode_button = create_button(profile.NOTE_BUTTON_CC, "Note_Mode_Button")
        self.chord_mode_button = create_button(profile.CHORD_BUTTON_CC, "Chord_Mode_Button")
        self.custom_mode_button = create_button(profile.CUSTOM_BUTTON_CC, "Custom_Mode_Button")
        self.sequencer_mode_button = create_button(profile.SEQUENCER_BUTTON_CC, "Sequencer_Mode_Button")
        self.projects_button = create_button(profile.PROJECTS_BUTTON_CC, "Projects_Button")
        # Function row below the grid (CC 1-8). Volume/Pan/Sends/Device are
        # created so the background can swallow them, but stay inert in v1
        # (button faders require the DAW-mode fader layout).
        self.record_arm_button = create_button(profile.RECORD_ARM_BUTTON_CC, "Record_Arm_Button")
        self.mute_button = create_button(profile.MUTE_BUTTON_CC, "Mute_Button")
        self.solo_button = create_button(profile.SOLO_BUTTON_CC, "Solo_Button")
        self.volume_button = create_button(profile.VOLUME_BUTTON_CC, "Volume_Button")
        self.pan_button = create_button(profile.PAN_BUTTON_CC, "Pan_Button")
        self.sends_button = create_button(profile.SENDS_BUTTON_CC, "Sends_Button")
        self.device_button = create_button(profile.DEVICE_BUTTON_CC, "Device_Button")
        self.stop_clip_button = create_button(profile.STOP_CLIP_BUTTON_CC, "Stop_Clip_Button")
        # Track select row (directly below the grid, CC 101-108).
        self.track_select_buttons_raw = [
            create_button(profile.TRACK_SELECT_FIRST_CC + index,
                          "Track_Select_Button_{}".format(index))
            for index in range(SESSION_WIDTH)]
        self.track_select_buttons = ButtonMatrixElement(
            rows=[self.track_select_buttons_raw],
            name="Track_Select_Buttons")
