import time
import logging
from concurrent.futures import Future
from command_feedback import CommandFeedback
from threading import Lock
from ui_events import UIEventLoop, InputEvent
from ui_case_light import CaseLightMixin
from ui_mmu import MMUViewMixin
from ui_screws_tilt import ScrewsTiltMixin
from ui_bed_mesh import BedMeshMixin
from ui_file_preview import FilePreviewMixin

from encoder import Encoder
from gpiozero import Button, Device
from gpiozero.pins.lgpio import LGPIOFactory
from printerInterface import PrinterData
from t5uic1_driver import T5UIC1Display
from lcd_atlas import ICON_FOLDER, ICON_MCU, ICON_MACHINE, ICON_HOST, ICON_SOFTWARE, ICON_POWER

def _MAX(lhs, rhs):
    if lhs > rhs:
        return lhs
    else:
        return rhs


class select_t:
    def __init__(self):
        self.now = 0
        self.last = 0

    def set(self, v):
        self.now = self.last = v

    def reset(self):
        self.set(0)

    def changed(self):
        c = (self.now != self.last)
        if c:
            self.last = self.now
            return c

    def dec(self):
        if (self.now):
            self.now -= 1
        return self.changed()

    def inc(self, v):
        if (self.now < (v - 1)):
            self.now += 1
        else:
            self.now = (v - 1)
        return self.changed()


class DWIN_LCD(MMUViewMixin, CaseLightMixin, ScrewsTiltMixin, BedMeshMixin, FilePreviewMixin):

    TROWS = 6
    MROWS = TROWS - 1  # Total rows, and other-than-Back
    TITLE_HEIGHT = 30  # Title bar height
    MLINE = 53         # Menu line height
    LBLX = 60          # Menu item label X
    MENU_CHR_W = 8
    STAT_CHR_W = 10


    MSG_STOP_PRINT = "Stop Print"
    MSG_PAUSE_PRINT = "Pausing..."

    DWIN_SCROLL_UP = 2
    DWIN_SCROLL_DOWN = 3

    SELECTIONS = ('select_page', 'select_file', 'select_print', 'select_prepare',
                  'select_control', 'select_axis', 'select_temp',
                  'select_motion', 'select_tune', 'select_PLA', 'select_ABS', 'select_light')

    index_file = MROWS
    index_prepare = MROWS
    index_control = MROWS
    index_temp = MROWS
    index_tune = MROWS

    MainMenu = 0
    SelectFile = 1
    Prepare = 2
    Control = 3
    Leveling = 4
    PrintProcess = 5
    AxisMove = 6
    TemperatureID = 7
    Motion = 8
    Info = 9
    Tune = 10
    PLAPreheat = 11
    ABSPreheat = 12

    # Last Process ID
    Last_Prepare = 21

    # Back Process ID
    Back_Main = 22

    # Date variable ID
    Move_X = 24
    Move_Y = 25
    Move_Z = 26
    Extruder = 27
    ETemp = 28
    Homeoffset = 29
    BedTemp = 30
    FanSpeed = 31
    PrintSpeed = 32

    Print_window = 33
    ProbeWizardID = 36
    MotionValue = 35
    CaseLight = 37
    CaseLightBrightness = 38
    ScrewsTiltMenu = 39
    ScrewsTiltResult = 40
    BedMeshScreen = 41
    MeshProfiles = 42
    BedMeshMenu = 43
    MMUMenu = 44
    FilePreview = 45
    PowerConfirm = 46

    MINUNITMULT = 10

    ENCODER_DIFF_NO = 0  # no state
    ENCODER_DIFF_CW = 1  # clockwise rotation
    ENCODER_DIFF_CCW = 2  # counterclockwise rotation
    ENCODER_DIFF_ENTER = 3   # click
    ENCODER_WAIT_ENTER = 300
    ENCODER_ACCEL_START_STEPS_PER_SEC = 10
    ENCODER_ACCEL_FULL_STEPS_PER_SEC = 46
    ENCODER_FAST_MULTIPLIER = 250
    ENCODER_ACCEL_EXPONENT = 2.75
    _encoder_move_value = 1


    dwin_zoffset = 0.0
    last_zoffset = 0.0

    # ICON ID
    ICON = 0x09

    ICON_LOGO = 0
    ICON_Print_0 = 1
    ICON_Print_1 = 2
    ICON_Prepare_0 = 3
    ICON_Prepare_1 = 4
    ICON_Control_0 = 5
    ICON_Control_1 = 6
    ICON_Leveling_0 = 7
    ICON_Leveling_1 = 8
    ICON_HotendTemp = 9
    ICON_BedTemp = 10
    ICON_Speed = 11
    ICON_Zoffset = 12
    ICON_Back = 13
    ICON_File = 14
    ICON_PrintTime = 15
    ICON_RemainTime = 16
    ICON_Setup_0 = 17
    ICON_Setup_1 = 18
    ICON_Pause_0 = 19
    ICON_Pause_1 = 20
    ICON_Continue_0 = 21
    ICON_Continue_1 = 22
    ICON_Stop_0 = 23
    ICON_Stop_1 = 24
    ICON_Bar = 25
    ICON_More = 26

    ICON_Axis = 27
    ICON_CloseMotor = 28
    ICON_Homing = 29
    ICON_SetHome = 30
    ICON_PLAPreheat = 31
    ICON_ABSPreheat = 32
    ICON_Cool = 33
    ICON_Language = 34

    ICON_MoveX = 35
    ICON_MoveY = 36
    ICON_MoveZ = 37
    ICON_Extruder = 38

    ICON_Temperature = 40
    ICON_Motion = 41
    ICON_WriteEEPROM = 42
    ICON_ReadEEPROM = 43
    ICON_ResumeEEPROM = 44
    ICON_Info = 45
    ICON_CaseLight = ICON_Motion

    ICON_SetEndTemp = 46
    ICON_SetBedTemp = 47
    ICON_FanSpeed = 48
    ICON_SetPLAPreheat = 49
    ICON_SetABSPreheat = 50

    ICON_MaxSpeed = 51
    ICON_MaxAccelerated = 52
    ICON_MaxJerk = 53
    ICON_Step = 54
    ICON_PrintSize = 55
    ICON_Version = 56
    ICON_Contact = 57
    ICON_StockConfiguraton = 58
    ICON_MaxSpeedX = 59
    ICON_MaxSpeedY = 60
    ICON_MaxSpeedZ = 61
    ICON_MaxSpeedE = 62
    ICON_MaxAccX = 63
    ICON_MaxAccY = 64
    ICON_MaxAccZ = 65
    ICON_MaxAccE = 66
    ICON_MaxSpeedJerkX = 67
    ICON_MaxSpeedJerkY = 68
    ICON_MaxSpeedJerkZ = 69
    ICON_MaxSpeedJerkE = 70
    ICON_StepX = 71
    ICON_StepY = 72
    ICON_StepZ = 73
    ICON_StepE = 74
    ICON_Setspeed = 75
    ICON_SetZOffset = 76
    ICON_Rectangle = 77
    ICON_BLTouch = 78
    ICON_TempTooLow = 79
    ICON_AutoLeveling = 80
    ICON_TempTooHigh = 81
    ICON_NoTips_C = 82
    ICON_NoTips_E = 83
    ICON_Continue_C = 84
    ICON_Continue_E = 85
    ICON_Cancel_C = 86
    ICON_Cancel_E = 87
    ICON_Confirm_C = 88
    ICON_Confirm_E = 89
    ICON_Info_0 = 90
    ICON_Info_1 = 91

    MENU_CHAR_LIMIT = 24
    STATUS_Y = 360

    MOTION_CASE_RATE = 1
    MOTION_CASE_ACCEL = 2
    MOTION_CASE_JERK = MOTION_CASE_ACCEL + 0
    MOTION_CASE_STEPS = MOTION_CASE_JERK + 1
    MOTION_CASE_TOTAL = MOTION_CASE_STEPS

    PREPARE_CASE_MOVE = 1
    PREPARE_CASE_DISA = 2
    PREPARE_CASE_HOME = 3
    PREPARE_CASE_ZOFF = PREPARE_CASE_HOME + 1
    PREPARE_CASE_PLA = PREPARE_CASE_ZOFF + 1
    PREPARE_CASE_ABS = PREPARE_CASE_PLA + 1
    PREPARE_CASE_COOL = PREPARE_CASE_ABS + 1
    PREPARE_CASE_TOTAL = PREPARE_CASE_COOL

    CONTROL_CASE_TEMP = 1
    CONTROL_CASE_MOVE = 2
    CONTROL_CASE_INFO = 3
    CONTROL_CASE_TOTAL = 3

    TUNE_CASE_SPEED = 1
    TUNE_CASE_TEMP = (TUNE_CASE_SPEED + 1)
    TUNE_CASE_BED = (TUNE_CASE_TEMP + 1)
    TUNE_CASE_FAN = (TUNE_CASE_BED + 0)
    TUNE_CASE_ZOFF = (TUNE_CASE_FAN + 1)
    TUNE_CASE_TOTAL = TUNE_CASE_ZOFF

    TEMP_CASE_TEMP = (0 + 1)
    TEMP_CASE_BED = (TEMP_CASE_TEMP + 1)
    TEMP_CASE_FAN = (TEMP_CASE_BED + 0)
    TEMP_CASE_PLA = (TEMP_CASE_FAN + 1)
    TEMP_CASE_ABS = (TEMP_CASE_PLA + 1)
    TEMP_CASE_TOTAL = TEMP_CASE_ABS

    PREHEAT_CASE_TEMP = (0 + 1)
    PREHEAT_CASE_BED = (PREHEAT_CASE_TEMP + 1)
    PREHEAT_CASE_SAVE = (PREHEAT_CASE_BED + 1)
    PREHEAT_CASE_TOTAL = PREHEAT_CASE_SAVE

    # Dwen serial screen initialization
    # Passing parameters: serial port number
    # DWIN screen uses serial port 1 to send
    def __init__(self, USARTx, encoder_pins, button_pin, octoPrint_API_Key,
                 moonraker_url='http://127.0.0.1:7125', request_timeout=5.0, settings_path=None,
                 power_device='Printer', power_on_hold_ms=2000):
        self._closed = False
        self._uart_epoch = 0
        self._uart_online = False
        self._next_uart_retry = 0
        self._next_uart_probe = 0
        self._uart_probe_failures = 0
        self.encoder = self.button = self.lcd = self.pd = None
        self._settings = (USARTx, encoder_pins, button_pin, octoPrint_API_Key,
                          moonraker_url, request_timeout, settings_path, power_device, power_on_hold_ms)
        self._input_lock = Lock()
        self._producer_value = 0
        self._last_press = float('-inf')
        self._last_encoder_time = None
        self._encoder_event = self.ENCODER_DIFF_NO
        self._encoder_move_value = 1
        self._live_jog = False
        self._live_jog_future = None
        self._live_jog_pending = None
        self._info_scroll = 0
        self._power_focus = False
        self._power_origin = None
        self._power_confirm_yes = True
        self._loop = UIEventLoop(self._initialize, self._process_input,
                                 self._ui_tick, self._close_resources)
        self._loop.start()

    def _initialize(self):
        USARTx, encoder_pins, button_pin, api_key, url, timeout, settings_path, power_device, power_on_hold_ms = self._settings
        Device.pin_factory = LGPIOFactory()
        for name in self.SELECTIONS:
            setattr(self, name, select_t())
        self.encoder = Encoder(encoder_pins[0], encoder_pins[1])
        self.power_on_hold_ms = max(0, int(power_on_hold_ms))
        hold_time = max(0.001, self.power_on_hold_ms / 1000.0)
        self.button = Button(button_pin, pull_up=True, bounce_time=0.05,
                             hold_time=hold_time, hold_repeat=False)
        self.next_rts_update_ms = 0
        self.last_cardpercentValue = 101
        self.checkkey = self.MainMenu
        self.pd = PrinterData(api_key, url, timeout, settings_path=settings_path,
                              power_device=power_device)
        self.pd.init_Webservices()
        self._configure_menus()
        self._offline = bool(self.pd.connection_error)
        self._ensure_uart()
        # Enable producers only after all UI/backend resources are initialized.
        with self._input_lock:
            self._producer_value = self.encoder.getValue()
            self.encoder.callback = self.encoder_has_data
        self.button.when_pressed = self._button_pressed
        self.button.when_held = self._button_held

    def _uart_failed(self):
        if (getattr(self, 'checkkey', None) == self.PowerConfirm
                and getattr(self, '_power_origin', None) == self.MMUMenu):
            self.checkkey = self.MMUMenu
            self._power_origin = None
        if getattr(self, 'checkkey', None) == self.MMUMenu:
            self._power_focus = False
            self._mmu_canvas_page = None
        self._uart_online = False
        self._uart_epoch += 1
        self._next_uart_retry = time.monotonic() + 5
        self._next_uart_probe = 0
        self._uart_probe_failures = 0
        if self.lcd is not None:
            self.lcd.close()
        self.lcd = None
        logging.warning('LCD UART unavailable; retrying in 5 seconds')

    def _ensure_uart(self):
        if self._uart_online:
            return True
        if self._closed or time.monotonic() < self._next_uart_retry:
            return False
        try:
            self.lcd = T5UIC1Display(self._settings[0], handshake_timeout=1.0,
                                 handshake_attempts=1)
            self._configure_menus()
            self.HMI_Init()
            self.HMI_StartFrame(False)
            if getattr(self, 'checkkey', None) == self.BedMeshScreen:
                self.Draw_Bed_Mesh()
            elif getattr(self, 'checkkey', None) == self.MeshProfiles:
                self.Draw_Mesh_Profiles()
            elif getattr(self, 'checkkey', None) == self.BedMeshMenu:
                self.Draw_Bed_Mesh_Menu()
            if getattr(self, 'checkkey', None) == self.MMUMenu:
                self._mmu_canvas_page = None
                self.Draw_MMU_Menu()
            if getattr(self, 'checkkey', None) == self.FilePreview:
                self.Draw_File_Preview()
            self.lcd.update()
            if self.pd.connection_error and self.checkkey != self.MMUMenu:
                self._show_message('Moonraker unavailable')
            self._uart_online = True
            self._uart_epoch += 1
            self._uart_probe_failures = 0
            self._next_uart_probe = time.monotonic() + 2.0
            logging.info('LCD UART connected; current screen restored')
            return True
        except (OSError, TimeoutError):
            self._uart_failed()
            return False

    def _ui_tick(self):
        if not self._uart_online:
            # Keep status current while the panel is disconnected.
            self.pd.update_variable()
            self.pd.bed_mesh.update()
            self.pd.mmu_session.update()
            self._ensure_uart()
            return
        try:
            now = time.monotonic()
            if now >= getattr(self, '_next_uart_probe', 0):
                self._next_uart_probe = now + 2.0
                if self.lcd.handshake(timeout=0.5):
                    self._uart_probe_failures = 0
                else:
                    self._uart_probe_failures = getattr(self, '_uart_probe_failures', 0) + 1
                    logging.warning('LCD liveness probe failed (%d/2)',
                                    self._uart_probe_failures)
                    if self._uart_probe_failures >= 2:
                        logging.warning('LCD liveness lost; reconnecting')
                        self._uart_failed()
                        return
            if getattr(self, 'checkkey', None) == self.FilePreview:
                if not getattr(self, '_pending_start', None) and not getattr(self, '_start_error_visible', False):
                    self._poll_file_preview()
                if time.monotonic() < getattr(self, '_preview_status_at', 0):
                    return
                self._preview_status_at = time.monotonic() + 2.0
            elif getattr(self, 'checkkey', None) == self.SelectFile:
                self._poll_thumbnail_preload()
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.02 if self._thumbnail_cache.has_work() else 2.0)
                if time.monotonic() < getattr(self, '_file_status_at', 0):
                    return
                self._file_status_at = time.monotonic() + 2.0
            elif hasattr(self, '_loop'):
                self._loop.set_interval(2.0)
            self.EachMomentUpdate()
        except OSError:
            if self.lcd is not None and getattr(self.lcd, '_closed', False):
                self._uart_failed()
            else:
                raise

    def _action(self, label, callback, expected=None, confirmation_timeout=300.0,
                on_accept=None):
        if getattr(self, '_action_feedback', None) is not None:
            return None
        try:
            future = callback()
        except ValueError as error:
            logging.warning('LCD action %s rejected: %s', label, error)
            future = Future()
            future.set_exception(error)
        if isinstance(future, Future):
            self._action_feedback = CommandFeedback(
                future, label, self.pd.state.epoch, expected, confirmation_timeout)
            self._action_on_accept = on_accept
        return future

    def _restore_action_screen(self):
        screens = {self.Prepare: self.Draw_Prepare_Menu, self.Control: self.Draw_Control_Menu,
                   self.TemperatureID: self.Draw_Temperature_Menu, self.Tune: self.Draw_Tune_Menu,
                   self.Motion: self.Draw_Motion_Menu, self.AxisMove: self.Draw_Move_Menu,
                   self.CaseLight: self.Draw_Case_Light_Menu}
        if self.checkkey == self.Last_Prepare and self.pd.ishomed():
            self.CompletedHoming()
        elif self.checkkey in screens:
            screens[self.checkkey]()
        else:
            self.HMI_StartFrame(False)
        self.lcd.update()

    def _poll_action(self):
        feedback = getattr(self, '_action_feedback', None)
        if feedback is None:
            return False
        phase = feedback.update(self.pd.state, bool(self.pd.connection_error))
        if phase == 'accepted':
            self._action_feedback = None
            on_accept = getattr(self, '_action_on_accept', None)
            self._action_on_accept = None
            if on_accept is not None:
                on_accept()
            self.HMI_AudioFeedback(True)
            self._restore_action_screen()
            return False
        if phase == 'error':
            self._action_on_accept = None
            self.pd.last_command_error = None
        self._show_message(feedback.message)
        return True

    def _configure_menus(self):
        caps = self.pd.capabilities
        recovery = self.pd.jog_recovery_required
        preset_revision = getattr(self.pd, 'preset_revision', 0)
        if getattr(self, '_menu_preset_revision', preset_revision) != preset_revision and getattr(self, 'checkkey', self.MainMenu) in (self.PLAPreheat, self.ABSPreheat):
            self.checkkey = self.TemperatureID
            self.select_temp.reset()
            self._active_preset = 0
        if (getattr(self, '_menu_capabilities', None) == caps
                and getattr(self, '_menu_recovery', False) == recovery
                and getattr(self, '_menu_preset_revision', -1) == preset_revision):
            return False
        self._menu_capabilities = caps
        self._menu_recovery = recovery
        self._menu_preset_revision = preset_revision
        heat = self.pd.HAS_HOTEND or self.pd.HAS_HEATED_BED
        self._menus = {
            'prepare': [('MOVE', 'Move', self.ICON_Axis), ('DISA', 'Disable steppers', self.ICON_CloseMotor),
                        ('HOME', 'Home', self.ICON_Homing), ('ZOFF', 'Runtime Z offset', self.ICON_Zoffset)],
            'tune': [('SPEED', 'Print speed', self.ICON_Speed)],
            'temperature': [], 'preheat': [], 'control': [],
        }
        for menu in ('tune', 'temperature', 'preheat'):
            if self.pd.HAS_HOTEND:
                self._menus[menu].append(('TEMP', 'Hotend temp', self.ICON_HotendTemp))
            if self.pd.HAS_HEATED_BED:
                self._menus[menu].append(('BED', 'Bed temp', self.ICON_BedTemp))
            if self.pd.HAS_FAN and menu != 'preheat':
                self._menus[menu].append(('FAN', 'Fan speed', self.ICON_FanSpeed))
        self._menus['tune'].append(('ZOFF', 'Runtime Z offset', self.ICON_Zoffset))
        if caps.screws_tilt_adjust:
            self._menus['prepare'].append(('SCREWS', 'Screws Tilt Adjust', self.ICON_SetEndTemp))
        if heat:
            for index, preset in enumerate(self.pd.material_preset):
                key = 'PRESET:' + str(index)
                self._menus['prepare'].append((key, 'Preheat ' + preset.name, self.ICON_PLAPreheat))
            self._menus['prepare'].append(('COOL', 'Cooldown', self.ICON_Cool))
        if self.pd.HAS_HOTEND:
            for index, preset in enumerate(self.pd.material_preset):
                key = 'PRESET:' + str(index)
                self._menus['temperature'].append((key, preset.name + ' settings', self.ICON_PLAPreheat))
        self._menus['preheat'].append(('SAVE', 'Save settings', self.ICON_WriteEEPROM))
        if heat or self.pd.HAS_FAN:
            self._menus['control'].append(('TEMP', 'Temperature', self.ICON_Temperature))
        self._menus['control'].append(('MOVE', 'Motion', self.ICON_Motion))
        if caps.probe and 'manual_probe' in self.pd.state.objects:
            self._menus['control'].append(('PROBE', 'Probe calibration', self.ICON_Zoffset))
        if recovery:
            self._menus['control'].append(('RECOVERY', 'Restore jog state', self.ICON_Homing))
        # Klipper exposes configured macros as "gcode_macro <name>" objects.
        # M355 commands are valid only when that compatibility macro exists.
        if any(name.lower() == 'gcode_macro m355' for name in self.pd.state.objects):
            self._menus['control'].append(('LIGHT', 'Case Light', self.ICON_CaseLight))
        self._menus['control'].append(('INFO', 'Info', self.ICON_Info))
        prefixes = {'prepare': 'PREPARE', 'temperature': 'TEMP', 'tune': 'TUNE',
                    'preheat': 'PREHEAT', 'control': 'CONTROL'}
        keys = ('MOVE', 'DISA', 'HOME', 'ZOFF', 'COOL', 'SPEED', 'TEMP', 'BED', 'FAN',
                'SAVE', 'INFO', 'PROBE', 'RECOVERY', 'LIGHT', 'SCREWS', 'MESH')
        for menu, prefix in prefixes.items():
            for key in keys:
                setattr(self, prefix + '_CASE_' + key, -1)
            for index, (key, _, _) in enumerate(self._menus[menu], 1):
                setattr(self, prefix + '_CASE_' + key, index)
            setattr(self, prefix + '_CASE_TOTAL', len(self._menus[menu]))
        return True

    def _menu_navigation(self, menu, selection, index_name, draw):
        event = self.get_encoder_state()
        if event not in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            return False
        if event == self.ENCODER_DIFF_CW:
            selection.inc(1 + len(self._menus[menu]))
        else:
            selection.dec()
        bottom = getattr(self, index_name, self.MROWS)
        if selection.now > bottom:
            bottom = selection.now
        elif selection.now < bottom - self.MROWS:
            bottom = selection.now + self.MROWS
        setattr(self, index_name, max(self.MROWS, bottom))
        draw()
        self.lcd.update()
        return True

    def _draw_capability_menu(self, name, selection, bottom=None, profile=None):
        self.Clear_Main_Window()
        title = name.title() if profile is None else self.pd.material_preset[profile].name + ' settings'
        self.Draw_Title(title)
        start = max(0, (bottom or self.MROWS) - self.MROWS)
        entries = [('BACK', 'Back', self.ICON_Back)] + self._menus[name]
        for logical in range(start, min(len(entries), start + self.TROWS)):
            key, label, icon = entries[logical]
            row = logical - start
            self.Draw_Menu_Line(row, icon, label)
            if logical == selection.now:
                self.Draw_Menu_Cursor(row)
            value = None
            preset = self.pd.material_preset[profile] if profile is not None else None
            if name in ('temperature', 'tune', 'preheat'):
                if key == 'TEMP':
                    value = preset.hotend_temp if preset else self.pd.thermalManager['temp_hotend'][0]['target']
                elif key == 'BED':
                    value = preset.bed_temp if preset else self.pd.thermalManager['temp_bed']['target']
                elif key == 'FAN':
                    value = self.pd.thermalManager['fan_speed'][0]
                elif key == 'SPEED':
                    value = self.pd.feedrate_percentage
                elif key == 'ZOFF':
                    self.lcd.draw_signed_scaled_float_text(self.lcd.font8x16, self.lcd.Color_Bg_Black,
                                               2, 2, 202, self.MBASE(row), self.pd.BABY_Z_VAR * 100)
                if value is not None:
                    self.lcd.draw_integer_text(True, True, 0, self.lcd.font8x16,
                                          self.lcd.Color_White, self.lcd.Color_Bg_Black,
                                          3, 216, self.MBASE(row), value)

    def _open_thermal_editor(self, key, row, profile=None):
        preset = self.pd.material_preset[profile] if profile is not None else None
        values = self.pd.HMI_ValueStruct
        if key == 'TEMP':
            self.checkkey = self.ETemp
            values.E_Temp = preset.hotend_temp if preset else self.pd.thermalManager['temp_hotend'][0]['target']
            value = values.E_Temp
        elif key == 'BED':
            self.checkkey = self.BedTemp
            values.Bed_Temp = preset.bed_temp if preset else self.pd.thermalManager['temp_bed']['target']
            value = values.Bed_Temp
        else:
            self.checkkey = self.FanSpeed
            values.Fan_speed = self.pd.thermalManager['fan_speed'][0]
            value = values.Fan_speed
        self.lcd.draw_integer_text(True, True, 0, self.lcd.font8x16,
                               self.lcd.Color_White, self.lcd.Select_Color,
                               3, 216, self.MBASE(row), value)

    def lcdExit(self):
        self._loop.close()

    def wait(self):
        self._loop.wait()

    def _close_resources(self):
        if self._closed:
            return
        self._closed = True
        for resource in (self.button, self.encoder, self.pd):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    logging.exception('LCD resource cleanup failed')
        if self.lcd is not None:
            self.lcd.close()

    def _show_message(self, message):
        self.Clear_Main_Window()
        self.lcd.draw_text(False, True, self.lcd.DWIN_FONT_STAT,
                             self.lcd.Color_White, self.lcd.Color_Bg_Black,
                             10, 50, message)
        self.lcd.update()

    def _enqueue_input(self, kind, value, accelerated_value=0, rate=0.0):
        feedback = getattr(self, '_action_feedback', None)
        if (self.pd is None or self._closed or not getattr(self, '_uart_online', True)
                or (feedback is not None and not (feedback.phase == 'error' and kind == 'press'))):
            return
        snapshot = self.pd.subscription.snapshot()
        if snapshot['state'] != 'ready' and getattr(self, 'checkkey', None) != self.MMUMenu:
            return
        if not self._loop.post(InputEvent(kind, value, snapshot['epoch'], getattr(self, '_uart_epoch', 0), accelerated_value, rate)):
            logging.warning('LCD input queue full or closed; input discarded')

    def encoder_has_data(self, value):
        # GPIO thread: capture rotation only; never draw or execute UI handlers.
        with self._input_lock:
            delta = value - self._producer_value
            self._producer_value = value
            if not delta:
                return
            now = time.monotonic()
            multiplier = 1
            rate = 0.0
            last_encoder_time = getattr(self, '_last_encoder_time', None)
            if last_encoder_time is not None:
                elapsed = now - last_encoder_time
                if elapsed > 0:
                    rate = abs(delta) / elapsed
                    if rate > self.ENCODER_ACCEL_START_STEPS_PER_SEC:
                        span = (self.ENCODER_ACCEL_FULL_STEPS_PER_SEC
                                - self.ENCODER_ACCEL_START_STEPS_PER_SEC)
                        normalized = min(1.0, (rate - self.ENCODER_ACCEL_START_STEPS_PER_SEC) / span)
                        multiplier = max(1, round(
                            1 + (self.ENCODER_FAST_MULTIPLIER - 1)
                            * normalized ** self.ENCODER_ACCEL_EXPONENT))
            self._last_encoder_time = now
            self._enqueue_input('rotate', delta, delta * multiplier, rate)

    def _button_pressed(self):
        # A zero hold time makes the press edge itself request printer power.
        if getattr(self, 'power_on_hold_ms', 2000) == 0:
            self._request_power_on()
        # Capture a press edge once; rotation while held must not create Enter.
        with self._input_lock:
            now = time.monotonic()
            if now - self._last_press >= self.ENCODER_WAIT_ENTER / 1000:
                self._last_press = now
                self._enqueue_input('press', 1)

    def _request_power_on(self):
        # Power control must remain available while Klipper and/or the LCD UART are offline.
        if self.pd is None or self._closed:
            return
        if not self._loop.post(InputEvent('power_on', 1, 0, 0)):
            logging.warning('LCD input queue full or closed; power-on request discarded')

    def _button_held(self):
        if getattr(self, 'power_on_hold_ms', 2000) > 0:
            self._request_power_on()

    def _sync_input_state(self, event):
        previous_epoch = self.pd.state.epoch
        self.pd.update_variable()
        if self._mmu_power_popup_stale():
            self._restore_power_origin()
            self.lcd.update()
            return False
        if getattr(self, 'checkkey', None) == self.MMUMenu and not self.pd.state.ready:
            self._poll_mmu()
            return True  # Offline MMU navigation remains read-only.
        if (self.pd.connection_error or not self.pd.state.ready
                or self.pd.state.epoch != event.epoch):
            return False
        changed = self._configure_menus()
        if previous_epoch != self.pd.state.epoch or changed:
            # Input was captured against an older menu/capability model.
            for name in self.SELECTIONS:
                getattr(self, name).reset()
            self.index_prepare = self.index_tune = self.MROWS
            self._offline = False
            self.HMI_StartFrame(False)
            self.lcd.update()
            return False
        return True

    def _encoder_acceleration_cap(self):
        screen = getattr(self, 'checkkey', None)
        if screen in (self.Move_X, self.Move_Y, self.Move_Z, self.Extruder):
            return 250
        if screen == self.MotionValue:
            return 100
        if screen in (self.ETemp, self.BedTemp):
            return 10
        if screen in (self.PrintSpeed, self.FanSpeed):
            return 5
        if screen == self.Homeoffset:
            return 10
        return 1

    def _live_jog_speed(self, axis):
        """Map handwheel rotation rate directly onto the configured axis velocity."""
        rate = max(0.0, float(getattr(self, '_encoder_jog_rate', 0.0)))
        toolhead = self.pd.state.status.get('toolhead', {})
        limit = float(toolhead.get('max_velocity', 1.0))
        if axis == 'Z':
            limit = min(limit, float(
                self.pd.state.settings.get('printer', {}).get('max_z_velocity', limit)))
        elif axis == 'E':
            hotend = self.pd.capabilities.active_hotend
            settings = self.pd.state.settings.get(hotend.name, {}) if hotend is not None else {}
            limit = float(settings.get('max_extrude_only_velocity', limit))
        # Full measured handwheel rate reaches the configured Klipper limit.
        normalized = min(1.0, rate / self.ENCODER_ACCEL_FULL_STEPS_PER_SEC)
        return max(1.0, limit * 60.0 * normalized)

    def _queue_live_jog(self, axis, distance, speed):
        pending = self._live_jog_pending
        if pending is None:
            self._live_jog_pending = [axis, distance, speed]
        elif pending[0] == axis and pending[1] * distance > 0:
            pending[1] += distance
            pending[2] = speed
        else:
            # A handwheel reversal or axis change supersedes queued motion.
            self._live_jog_pending = [axis, distance, speed]
        if self._live_jog_future is not None:
            return
        self._flush_live_jog()

    def _flush_live_jog(self):
        if self._live_jog_future is not None:
            done = self._live_jog_future
            if not done.done():
                return
            self._live_jog_future = None
            if done.cancelled() or done.exception() is not None:
                # Live jog is best-effort handwheel input.  A rejected segment
                # is dropped locally; the next encoder event is re-clamped
                # against fresh authoritative position.
                self._live_jog_pending = None
                return
        pending = self._live_jog_pending
        if pending is None or abs(pending[1]) < 1e-9:
            self._live_jog_pending = None
            return
        axis, distance, speed = pending
        self._live_jog_pending = None
        try:
            future = self.pd.moveRelative(axis, distance, speed)
        except ValueError:
            # Limits and transient state changes are silent for handwheel input.
            return
        if isinstance(future, Future):
            self._live_jog_future = future
            snapshot = self.pd.subscription.snapshot()
            future.add_done_callback(lambda _done: self._loop.post(InputEvent(
                'live_jog_flush', 0, snapshot['epoch'], getattr(self, '_uart_epoch', 0))))

    def _process_input(self, event):
        if event.kind == 'power_on':
            if not self._closed:
                self.pd.power_on_if_off()
            return
        if (not getattr(self, '_uart_online', True)
                or event.ui_epoch != getattr(self, '_uart_epoch', 0)):
            return
        snapshot = self.pd.subscription.snapshot()
        if ((snapshot['state'] != 'ready' and getattr(self, 'checkkey', None) != self.MMUMenu) or snapshot['epoch'] != event.epoch
                or self._closed):
            return
        if event.kind == 'live_jog_flush':
            self._flush_live_jog()
            return
        if event.kind == 'rotate':
            direction = self.ENCODER_DIFF_CCW if event.value > 0 else self.ENCODER_DIFF_CW
            count = abs(event.value)
        elif event.kind == 'press':
            direction, count = self.ENCODER_DIFF_ENTER, 1
        else:
            return
        if not self._sync_input_state(event):
            return
        self._encoder_jog_rate = event.rate if event.kind == 'rotate' else 0.0
        acceleration_cap = self._encoder_acceleration_cap() if event.kind == 'rotate' else 1
        if acceleration_cap > 1:
            count = 1
            raw_count = max(1, abs(event.value))
            accelerated_count = abs(event.accelerated_value or event.value)
            effective_multiplier = max(1, accelerated_count // raw_count)
            self._encoder_move_value = raw_count * min(acceleration_cap, effective_multiplier)
        else:
            self._encoder_move_value = 1
        lcd = getattr(self, 'lcd', None)
        if lcd is not None:
            lcd._defer_updates = True
        try:
            for _ in range(count):
                current = self.pd.subscription.snapshot()
                if ((current['state'] != 'ready' and getattr(self, 'checkkey', None) != self.MMUMenu)
                        or current['epoch'] != event.epoch):
                    break
                self._encoder_event = direction
                self._dispatch_input()
                if getattr(self, '_action_feedback', None):
                    self._poll_action()
                    break
        except OSError:
            if self.lcd is not None and getattr(self.lcd, '_closed', False):
                self._uart_failed()
            else:
                raise
        finally:
            self._encoder_event = self.ENCODER_DIFF_NO
            self._encoder_move_value = 1
            if (lcd is not None and self.lcd is lcd
                    and not getattr(lcd, '_closed', False)):
                lcd._defer_updates = False
                lcd.update()

    def MBASE(self, L):
        return 49 + self.MLINE * L

    def HMI_ShowBoot(self, mesg=None):
        if mesg:
            self.lcd.draw_text(
                False, False, self.lcd.DWIN_FONT_STAT,
                self.lcd.Color_White, self.lcd.Color_Bg_Black,
                10, 50,
                mesg
            )
        for t in range(0, 100, 2):
            self.lcd.show_icon(self.ICON, self.ICON_Bar, 15, 260)
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 15 + t * 242 / 100, 260, 257, 280)
            self.lcd.update()
            time.sleep(.020)

    def HMI_Init(self):
        # Virtual display areas are owned exclusively by the managed atlas
        # driver. Legacy language-JPEG caching used area 1 and could overwrite
        # an atlas after a panel power-cycle/reconnect.
        pass

    def _present_print_state(self):
        status = self.pd.status
        self.last_status = status
        self._print_error_visible = False
        self.pd.HMI_flag.done_confirm_flag = False
        self.pd.HMI_flag.pause_flag = self.pd.printingIsPaused()
        if (self.checkkey == self.MMUMenu or
                (self.checkkey == self.PowerConfirm and getattr(self, '_power_origin', None) == self.MMUMenu)):
            return
        mmu = self.pd.mmu_session.state
        if status == 'paused' and mmu and mmu.locked and mmu.reason:
            self.Enter_MMU_Menu('recover')
            return
        if status in ('printing', 'paused', 'pausing'):
            self.Goto_PrintProcess()
        elif status == 'complete':
            if getattr(self, '_acknowledged_terminal', None) == self._terminal_key():
                self.Goto_MainMenu()
                return
            self.Goto_PrintProcess()
            self.pd.HMI_flag.done_confirm_flag = True
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 250,
                                    self.lcd.DWIN_WIDTH - 1, self.STATUS_Y)
            self.lcd.show_icon(self.ICON, self.ICON_Confirm_E, 86, 283)
        elif status == 'error':
            if getattr(self, '_acknowledged_terminal', None) == self._terminal_key():
                self.Goto_MainMenu()
                return
            self._print_error_visible = True
            message = self.pd.job_Info['print_stats'].get('message') or 'Print failed'
            self._show_message(str(message))
        else:
            # Idle/standby updates must not tear down the screen the user is
            # currently interacting with. Startup/reconnect begins on
            # MainMenu, where drawing it is still required.
            if self.checkkey == self.MainMenu:
                self.Goto_MainMenu()

    def _terminal_key(self):
        return (self.pd.state.epoch, self.pd.status, self.pd.file_name,
                self.pd.job_Info['print_stats'].get('print_duration', 0))

    def HMI_StartFrame(self, with_update):
        self._present_print_state()
        if not self._print_error_visible:
            self.Draw_Status_Area(with_update)

    def _home_entries(self):
        entries = [('PRINT', 'Print', self.ICON_Print_0, self.ICON_Print_1),
                   ('PREPARE', 'Prepare', self.ICON_Prepare_0, self.ICON_Prepare_1),
                   ('CONTROL', 'Control', self.ICON_Control_0, self.ICON_Control_1)]
        if self.pd.HAS_ONESTEP_LEVELING:
            entries.append(('LEVEL', 'Leveling', self.ICON_Leveling_0, self.ICON_Leveling_1))
        entries.append(('MMU', 'MMU', None, None))
        entries.append(('INFO', 'Info', self.ICON_Info_0, self.ICON_Info_1))
        return tuple(entries)

    def _draw_home_page(self):
        entries = self._home_entries()
        self.select_page.set(min(self.select_page.now, len(entries)-1))
        page = self.select_page.now // 4
        # Clear only navigation: the logo/MMU and live dashboard stay in place.
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 126, 271, self.STATUS_Y-1)
        for index in range(page*4, min(len(entries), page*4+4)):
            key, label, normal, selected = entries[index]
            slot = index % 4
            x, y = (17 if slot % 2 == 0 else 145), (130 if slot < 2 else 246)
            active = index == self.select_page.now
            if key == 'MMU':
                self.Draw_MMU_Home_Icon(x, y, active)
            else:
                self.lcd.show_icon(self.ICON, selected if active else normal, x, y)
            if active:
                self.lcd.draw_rectangle(0, self.lcd.Color_White, x, y, x+109, y+99)
            self._draw_menu_text(label, x+(109-len(label)*8)//2, y+71)
        pages = (len(entries)+3)//4
        if pages > 1:
            self.lcd.draw_text(False, False, self.lcd.font6x12, self.lcd.Color_White,
                                 self.lcd.Color_Bg_Black, 127, 347, str(page+1)+'/'+str(pages))

    def HMI_MainMenu(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        entries = self._home_entries()
        self.select_page.set(min(self.select_page.now, len(entries)-1))
        previous = self.select_page.now
        if event == self.ENCODER_DIFF_CW:
            self.select_page.inc(len(entries))
        elif event == self.ENCODER_DIFF_CCW:
            self.select_page.dec()
        elif event == self.ENCODER_DIFF_ENTER:
            key = entries[self.select_page.now][0]
            if key == 'PRINT':
                self.checkkey = self.SelectFile
                self._file_directory = ''
                self._file_paths = ()
                self.select_file.reset()
                self._refresh_file_snapshot()
                self.Draw_Print_File_Menu()
            elif key == 'PREPARE':
                self.checkkey = self.Prepare
                self.select_prepare.reset()
                self.index_prepare = self.MROWS
                self.Draw_Prepare_Menu()
            elif key == 'CONTROL':
                self.checkkey = self.Control
                self.select_control.reset()
                self.index_control = self.MROWS
                self.Draw_Control_Menu()
            elif key == 'LEVEL':
                self.checkkey = self.Leveling
                self.HMI_Leveling()
            elif key == 'MMU':
                self.Enter_MMU_Menu()
            elif key == 'INFO':
                self._info_origin = self.MainMenu
                self.checkkey = self.Info
                self.Draw_Info_Menu()
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW) and previous != self.select_page.now:
            self._draw_home_page()
        self.lcd.update()

    def _refresh_file_snapshot(self):
        paths = self.pd.GetDirectory(getattr(self, '_file_directory', ''))
        if self.pd.file_error or self.pd._files_loading or self.pd._directory_loading:
            return False
        previous = getattr(self, '_file_paths', ())
        selected = (previous[self.select_file.now - 1]
                    if 0 < self.select_file.now <= len(previous) else None)
        self._file_paths = paths
        self.select_file.set(paths.index(selected) + 1 if selected in paths else 0)
        self.index_file = max(self.MROWS, self.select_file.now)
        self._file_view_epoch = self.pd.state.epoch
        self._file_view_revision = self.pd.state.file_revision
        self._file_view_sort_revision = self.pd.file_sort_revision
        self._sync_thumbnail_cache()
        if hasattr(self, '_loop'):
            self._loop.set_interval(.02)
        return True

    def _enter_file_directory(self, directory, select=None):
        self._file_directory = directory
        self._file_paths = ()
        self.select_file.reset()
        self.index_file = self.MROWS
        if self._refresh_file_snapshot() and select in self._file_paths:
            self.select_file.set(self._file_paths.index(select) + 1)
            self.index_file = max(self.MROWS, self.select_file.now)
        self.Draw_Print_File_Menu()
        self.lcd.update()

    def HMI_SelectFile(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO or getattr(self, '_pending_start', None):
            return
        if event == self.ENCODER_DIFF_ENTER and self.select_file.now == 0:
            directory = getattr(self, '_file_directory', '')
            if directory:
                self._enter_file_directory(directory.rpartition('/')[0], directory + '/')
            else:
                self.Goto_MainMenu()
            return
        if (self.pd.state.epoch != getattr(self, '_file_view_epoch', -1)
                or self.pd.state.file_revision != getattr(self, '_file_view_revision', -1)
                or self.pd.file_sort_revision != getattr(self, '_file_view_sort_revision', -1)):
            self._refresh_file_snapshot()
            self.Redraw_SD_List()
            # Do not apply an Enter captured against the previous list.
            return
        count = len(getattr(self, '_file_paths', ()))
        if event == self.ENCODER_DIFF_CW:
            self.select_file.inc(count + 1)
        elif event == self.ENCODER_DIFF_CCW:
            self.select_file.dec()
        elif event == self.ENCODER_DIFF_ENTER:
            path = self._file_paths[self.select_file.now - 1]
            if path.endswith('/'):
                self._enter_file_directory(path[:-1])
                return
            self._open_file_preview(path)
            return
        self.index_file = max(self.MROWS, self.select_file.now,
                              min(self.index_file, self.select_file.now + self.MROWS))
        self.Redraw_SD_List()
        self.lcd.update()

    def _poll_print_start(self):
        pending = getattr(self, '_pending_start', None)
        if not pending:
            return False
        future, epoch, started = pending
        error = None
        if epoch != self.pd.state.epoch:
            error = 'Connection changed; check printer'
        elif future.done():
            if future.cancelled():
                error = 'Print start cancelled'
            elif future.exception():
                error = 'Print start failed; check log'
            elif self.pd.status in ('printing', 'paused', 'error'):
                self._pending_start = None
                self._present_print_state()
                return False
            elif time.monotonic() - started > 30:
                error = 'Start unconfirmed; check printer'
        if not error and time.monotonic() - started > 30:
            future.cancel()  # Only cancels work that has not started.
            error = 'Start unconfirmed; check printer'
        if error:
            self._pending_start = None
            self.pd.last_command_error = None
            self._show_message(error)
            self._start_error_visible = True
        return True

    def HMI_Prepare(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self._menu_navigation('prepare', self.select_prepare, 'index_prepare', self.Draw_Prepare_Menu):
            return
        if (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if (self.select_prepare.now == 0):  # Back
                self.select_page.set(1)
                self.Goto_MainMenu()

            elif self.select_prepare.now == self.PREPARE_CASE_MOVE:  # Axis move
                self.checkkey = self.AxisMove
                self.select_axis.reset()
                self.Draw_Move_Menu()
            elif self.select_prepare.now == self.PREPARE_CASE_SCREWS:
                self.checkkey = self.ScrewsTiltMenu
                self._screws_selection = 0
                self.Draw_Screws_Menu()
            elif self.select_prepare.now == self.PREPARE_CASE_DISA:  # Disable steppers
                self._action("Disable steppers", lambda: self.pd.sendGCode("M84"))
            elif self.select_prepare.now == self.PREPARE_CASE_HOME:  # Homing
                self.checkkey = self.Last_Prepare
                self.index_prepare = self.MROWS
                self.pd.current_position.homing()
                self.pd.HMI_flag.home_flag = True
                self.Popup_Window_Home()
                self._action("Home", lambda: self.pd.sendGCodeObserved("G28"),
                             self.pd.ishomed, confirmation_timeout=600)
            elif self.select_prepare.now == self.PREPARE_CASE_ZOFF:  # Z-offset
                self._open_zoffset(-4, self.PREPARE_CASE_ZOFF + self.MROWS - self.index_prepare)

            elif self.select_prepare.now > 0 and self._menus['prepare'][self.select_prepare.now - 1][0].startswith('PRESET:'):
                profile = int(self._menus['prepare'][self.select_prepare.now - 1][0].split(':', 1)[1])
                name = self.pd.material_preset[profile].name
                self._action('Preheat ' + name, lambda profile=profile: self.pd.preheat_preset(profile))

            elif self.select_prepare.now == self.PREPARE_CASE_COOL:  # Cool
                self._action('Cooldown', self.pd.cooldown)

        self.lcd.update()

    def HMI_Control(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self._menu_navigation('control', self.select_control, 'index_control', self.Draw_Control_Menu):
            return
        if (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if (self.select_control.now == 0):  # Back
                self.select_page.set(2)
                self.Goto_MainMenu()
            if (self.select_control.now == self.CONTROL_CASE_TEMP):  # Temperature
                self.checkkey = self.TemperatureID
                self.pd.HMI_ValueStruct.show_mode = -1
                self.select_temp.reset()
                self.Draw_Temperature_Menu()
            if (self.select_control.now == self.CONTROL_CASE_MOVE):  # Motion
                self.checkkey = self.Motion
                self.select_motion.reset()
                self.Draw_Motion_Menu()
            if self.select_control.now == self.CONTROL_CASE_PROBE:
                self.checkkey = self.ProbeWizardID
                self._probe_selection = 0
                self.Draw_Probe_Wizard()
            if self.select_control.now == self.CONTROL_CASE_RECOVERY:
                self._action('Restore jog state', self.pd.restore_jog_state)
            if self.select_control.now == self.CONTROL_CASE_LIGHT:
                self.checkkey = self.CaseLight
                self.select_light.reset()
                self._case_light_query_pending = True
                self.pd.query_case_light()
                self.Draw_Case_Light_Menu()
            if (self.select_control.now == self.CONTROL_CASE_INFO):  # Info
                self._info_origin = self.Control
                self.checkkey = self.Info
                self.Draw_Info_Menu()

        self.lcd.update()

    def HMI_Info(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        items = self._info_items()
        max_scroll = max(0, len(items) - 11)
        if event == self.ENCODER_DIFF_CW:
            self._info_scroll = min(max_scroll, getattr(self, '_info_scroll', 0) + 1)
            self.Draw_Info_Menu()
        elif event == self.ENCODER_DIFF_CCW:
            self._info_scroll = max(0, getattr(self, '_info_scroll', 0) - 1)
            self.Draw_Info_Menu()
        elif event == self.ENCODER_DIFF_ENTER:
            self._info_scroll = 0
            if getattr(self, '_info_origin', self.MainMenu) == self.Control:
                self.checkkey = self.Control
                self.select_control.set(self.CONTROL_CASE_INFO)
                self.Draw_Control_Menu()
            else:
                self.select_page.set(next(i for i, entry in enumerate(self._home_entries()) if entry[0] == 'INFO'))
                self.Goto_MainMenu()
        self.lcd.update()

    def HMI_Printing(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        if (self.pd.HMI_flag.done_confirm_flag):
            if (encoder_diffState == self.ENCODER_DIFF_ENTER):
                self.pd.HMI_flag.done_confirm_flag = False
                self._acknowledged_terminal = self._terminal_key()
                self.Goto_MainMenu()
            return

        if (encoder_diffState == self.ENCODER_DIFF_CW):
            if (self.select_print.inc(3)):
                if self.select_print.now == 0:
                    self.ICON_Tune()
                elif self.select_print.now == 1:
                    self.ICON_Tune()
                    if (self.pd.printingIsPaused()):
                        self.ICON_Continue()
                    else:
                        self.ICON_Pause()
                elif self.select_print.now == 2:
                    if (self.pd.printingIsPaused()):
                        self.ICON_Continue()
                    else:
                        self.ICON_Pause()
                    self.ICON_Stop()
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            if (self.select_print.dec()):
                if self.select_print.now == 0:
                    self.ICON_Tune()
                    if (self.pd.printingIsPaused()):
                        self.ICON_Continue()
                    else:
                        self.ICON_Pause()
                elif self.select_print.now == 1:
                    if (self.pd.printingIsPaused()):
                        self.ICON_Continue()
                    else:
                        self.ICON_Pause()
                    self.ICON_Stop()
                elif self.select_print.now == 2:
                    self.ICON_Stop()
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if self.select_print.now == 0:  # Tune
                self.checkkey = self.Tune
                self.pd.HMI_ValueStruct.show_mode = 0
                self.select_tune.reset()
                self.index_tune = self.MROWS
                self.Draw_Tune_Menu()
            elif self.select_print.now == 1:  # Pause
                if (self.pd.HMI_flag.pause_flag):
                    self._action("Resume", self.pd.resume_job,
                             lambda: self.pd.status == "printing",
                             confirmation_timeout=60)
                else:
                    self.pd.HMI_flag.select_flag = True
                    self.checkkey = self.Print_window
                    self.Popup_window_PauseOrStop()
            elif self.select_print.now == 2:  # Stop
                self.pd.HMI_flag.select_flag = True
                self.checkkey = self.Print_window
                self.Popup_window_PauseOrStop()
        self.lcd.update()

    # Pause and Stop window */
    def HMI_PauseOrStop(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        if (encoder_diffState == self.ENCODER_DIFF_CW):
            self.Draw_Select_Highlight(False)
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.Draw_Select_Highlight(True)
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if (self.select_print.now == 1):  # pause window
                if (self.pd.HMI_flag.select_flag):
                    self.pd.HMI_flag.pause_action = True
                    self._action("Pause", self.pd.pause_job, self.pd.printingIsPaused,
                                 confirmation_timeout=60)
                self.Goto_PrintProcess()
            elif (self.select_print.now == 2):  # stop window
                if (self.pd.HMI_flag.select_flag):
                    self._action("Cancel", self.pd.cancel_job,
                                 lambda: self.pd.status == "cancelled",
                                 confirmation_timeout=60)
                else:
                    self.Goto_PrintProcess()  # cancel stop
        self.lcd.update()

    # Tune  */
    def HMI_Tune(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        if self._menu_navigation('tune', self.select_tune, 'index_tune', self.Draw_Tune_Menu):
            return
        if (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if self.select_tune.now == 0:  # Back
                self.select_print.set(0)
                self.Goto_PrintProcess()
            elif self.select_tune.now == self.TUNE_CASE_SPEED:  # Print speed
                self.checkkey = self.PrintSpeed
                self.pd.HMI_ValueStruct.print_speed = self.pd.feedrate_percentage
                self.lcd.draw_integer_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
                    3, 216, self.MBASE(self.TUNE_CASE_SPEED + self.MROWS - self.index_tune),
                    self.pd.feedrate_percentage
                )
            elif self._menus['tune'][self.select_tune.now - 1][0] in ('TEMP', 'BED', 'FAN'):
                key = self._menus['tune'][self.select_tune.now - 1][0]
                self._open_thermal_editor(key, self.select_tune.now + self.MROWS - self.index_tune)
            elif self.select_tune.now == self.TUNE_CASE_ZOFF:   #z offset
                self._open_zoffset(0, self.TUNE_CASE_ZOFF + self.MROWS - self.index_tune)

        self.lcd.update()

    def HMI_PrintSpeed(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.print_speed += self._encoder_move_value

        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.print_speed = max(1, self.pd.HMI_ValueStruct.print_speed - self._encoder_move_value)

        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            self.checkkey = self.Tune
            self.encoderRate = True
            self._action("Print speed", lambda: self.pd.set_feedrate(self.pd.HMI_ValueStruct.print_speed))

        self.lcd.draw_integer_text(
            True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
            3, 216, self.MBASE(self.select_tune.now + self.MROWS - self.index_tune),
            self.pd.HMI_ValueStruct.print_speed
        )

    def HMI_AxisMove(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self.pd.PREVENT_COLD_EXTRUSION:
            # popup window resume
            if (self.pd.HMI_flag.ETempTooLow_flag):
                if (encoder_diffState == self.ENCODER_DIFF_ENTER):
                    self.pd.HMI_flag.ETempTooLow_flag = False
                    self.Draw_Move_Menu()
                    self.lcd.update()
                return
        # Avoid flicker by updating only the previous menu
        live_index = 4 + int(self.pd.HAS_HOTEND)
        if (encoder_diffState == self.ENCODER_DIFF_CW):
            if (self.select_axis.inc(live_index + 1)):
                self.Draw_Move_Menu()
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            if self.select_axis.dec():
                self.Draw_Move_Menu()
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if self.select_axis.now == 0:  # Back
                self.checkkey = self.Prepare
                self.select_prepare.set(1)
                self.index_prepare = self.MROWS
                self.Draw_Prepare_Menu()

            elif self.select_axis.now == 1:  # axis move
                self.checkkey = self.Move_X
                self.pd.HMI_ValueStruct.Move_X_scale = self.pd.state.status['gcode_move']['position'][0] * self.MINUNITMULT
                self.lcd.draw_scaled_float_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
                    3, 1, 216, self.MBASE(1),
                    self.pd.HMI_ValueStruct.Move_X_scale
                )
            elif self.select_axis.now == 2:  # Y axis move
                self.checkkey = self.Move_Y
                self.pd.HMI_ValueStruct.Move_Y_scale = self.pd.state.status['gcode_move']['position'][1] * self.MINUNITMULT
                self.lcd.draw_scaled_float_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
                    3, 1, 216, self.MBASE(2),
                    self.pd.HMI_ValueStruct.Move_Y_scale
                )
            elif self.select_axis.now == 3:  # Z axis move
                self.checkkey = self.Move_Z
                self.pd.HMI_ValueStruct.Move_Z_scale = self.pd.state.status['gcode_move']['position'][2] * self.MINUNITMULT
                self.lcd.draw_scaled_float_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
                    3, 1, 216, self.MBASE(3),
                    self.pd.HMI_ValueStruct.Move_Z_scale
                )
            elif self.select_axis.now == 4 and self.pd.HAS_HOTEND:  # Extruder
                # window tips
                if self.pd.PREVENT_COLD_EXTRUSION:
                    if not self.pd.state.status.get(self.pd.capabilities.active_hotend.name, {}).get('can_extrude', False):
                        self.pd.HMI_flag.ETempTooLow_flag = True
                        self.Popup_Window_ETempTooLow()
                        self.lcd.update()
                        return
                self.checkkey = self.Extruder
                self.pd.last_E_scale = self.pd.state.status['gcode_move']['position'][3] * self.MINUNITMULT
                self.pd.HMI_ValueStruct.Move_E_scale = self.pd.state.status['gcode_move']['position'][3] * self.MINUNITMULT
                self.lcd.draw_signed_scaled_float_text(
                    self.lcd.font8x16, self.lcd.Select_Color, 3, 1, 216, self.MBASE(4),
                    self.pd.HMI_ValueStruct.Move_E_scale
                )
            elif self.select_axis.now == live_index:
                self._live_jog = not getattr(self, '_live_jog', False)
                self.Draw_Move_Menu()
        self.lcd.update()

    def HMI_Move_X(self):
        encoder_diffState = self.get_encoder_state()
        previous_scale = self.pd.HMI_ValueStruct.Move_X_scale
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            self.checkkey = self.AxisMove
            self.lcd.draw_scaled_float_text(
                True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
                3, 1, 216, self.MBASE(1),
                self.pd.HMI_ValueStruct.Move_X_scale
            )
            if not getattr(self, '_live_jog', False):
                self._action("Jog X", lambda: self.pd.moveAbsolute('X', self.pd.HMI_ValueStruct.Move_X_scale / self.MINUNITMULT, 5000))
            self.lcd.update()
            return
        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Move_X_scale += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Move_X_scale -= self._encoder_move_value

        if self.pd.HMI_ValueStruct.Move_X_scale < (self.pd.X_MIN_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_X_scale = (self.pd.X_MIN_POS) * self.MINUNITMULT

        if self.pd.HMI_ValueStruct.Move_X_scale > (self.pd.X_MAX_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_X_scale = (self.pd.X_MAX_POS) * self.MINUNITMULT

        if getattr(self, '_live_jog', False) and encoder_diffState in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            applied = (self.pd.HMI_ValueStruct.Move_X_scale - previous_scale) / self.MINUNITMULT
            if applied:
                self._queue_live_jog('X', applied, self._live_jog_speed('X'))
        self.lcd.draw_scaled_float_text(
            True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
            3, 1, 216, self.MBASE(1), self.pd.HMI_ValueStruct.Move_X_scale)
        self.lcd.update()

    def HMI_Move_Y(self):
        encoder_diffState = self.get_encoder_state()
        previous_scale = self.pd.HMI_ValueStruct.Move_Y_scale
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            self.checkkey = self.AxisMove
            self.lcd.draw_scaled_float_text(
                True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
                3, 1, 216, self.MBASE(2),
                self.pd.HMI_ValueStruct.Move_Y_scale
            )

            if not self._live_jog:
                self._action("Jog Y", lambda: self.pd.moveAbsolute('Y', self.pd.HMI_ValueStruct.Move_Y_scale / self.MINUNITMULT, 5000))
            self.lcd.update()
            return
        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Move_Y_scale += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Move_Y_scale -= self._encoder_move_value

        if self.pd.HMI_ValueStruct.Move_Y_scale < (self.pd.Y_MIN_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_Y_scale = (self.pd.Y_MIN_POS) * self.MINUNITMULT

        if self.pd.HMI_ValueStruct.Move_Y_scale > (self.pd.Y_MAX_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_Y_scale = (self.pd.Y_MAX_POS) * self.MINUNITMULT

        if self._live_jog and encoder_diffState in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            applied = (self.pd.HMI_ValueStruct.Move_Y_scale - previous_scale) / self.MINUNITMULT
            if applied:
                self._queue_live_jog('Y', applied, self._live_jog_speed('Y'))
        self.lcd.draw_scaled_float_text(
            True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
            3, 1, 216, self.MBASE(2), self.pd.HMI_ValueStruct.Move_Y_scale)
        self.lcd.update()

    def HMI_Move_Z(self):
        encoder_diffState = self.get_encoder_state()
        previous_scale = self.pd.HMI_ValueStruct.Move_Z_scale
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            self.checkkey = self.AxisMove
            self.lcd.draw_scaled_float_text(
                True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
                3, 1, 216, self.MBASE(3),
                self.pd.HMI_ValueStruct.Move_Z_scale
            )
            if not self._live_jog:
                self._action("Jog Z", lambda: self.pd.moveAbsolute('Z', self.pd.HMI_ValueStruct.Move_Z_scale / self.MINUNITMULT, 600))
            self.lcd.update()
            return
        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Move_Z_scale += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Move_Z_scale -= self._encoder_move_value

        if self.pd.HMI_ValueStruct.Move_Z_scale < (self.pd.Z_MIN_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_Z_scale = (self.pd.Z_MIN_POS) * self.MINUNITMULT

        if self.pd.HMI_ValueStruct.Move_Z_scale > (self.pd.Z_MAX_POS) * self.MINUNITMULT:
            self.pd.HMI_ValueStruct.Move_Z_scale = (self.pd.Z_MAX_POS) * self.MINUNITMULT

        if self._live_jog and encoder_diffState in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            applied = (self.pd.HMI_ValueStruct.Move_Z_scale - previous_scale) / self.MINUNITMULT
            if applied:
                self._queue_live_jog('Z', applied, self._live_jog_speed('Z'))
        self.lcd.draw_scaled_float_text(
            True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
            3, 1, 216, self.MBASE(3), self.pd.HMI_ValueStruct.Move_Z_scale)
        self.lcd.update()

    def HMI_Move_E(self):
        encoder_diffState = self.get_encoder_state()
        previous_scale = self.pd.HMI_ValueStruct.Move_E_scale
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        elif (encoder_diffState == self.ENCODER_DIFF_ENTER):
            self.checkkey = self.AxisMove
            self.lcd.draw_signed_scaled_float_text(
                self.lcd.font8x16, self.lcd.Color_Bg_Black, 3, 1, 216,
                self.MBASE(4), self.pd.HMI_ValueStruct.Move_E_scale
            )
            if not self._live_jog:
                self._action("Jog E", lambda: self.pd.moveAbsolute('E', self.pd.HMI_ValueStruct.Move_E_scale / self.MINUNITMULT, 300))
            self.lcd.update()
            return
        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Move_E_scale += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Move_E_scale -= self._encoder_move_value

        if ((self.pd.HMI_ValueStruct.Move_E_scale - self.pd.last_E_scale) > (self.pd.EXTRUDE_MAXLENGTH) * self.MINUNITMULT):
            self.pd.HMI_ValueStruct.Move_E_scale = self.pd.last_E_scale + (self.pd.EXTRUDE_MAXLENGTH) * self.MINUNITMULT
        elif ((self.pd.last_E_scale - self.pd.HMI_ValueStruct.Move_E_scale) > (self.pd.EXTRUDE_MAXLENGTH) * self.MINUNITMULT):
            self.pd.HMI_ValueStruct.Move_E_scale = self.pd.last_E_scale - (self.pd.EXTRUDE_MAXLENGTH) * self.MINUNITMULT
        if self._live_jog and encoder_diffState in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            applied = (self.pd.HMI_ValueStruct.Move_E_scale - previous_scale) / self.MINUNITMULT
            if applied:
                self._queue_live_jog('E', applied, self._live_jog_speed('E'))
        self.lcd.draw_signed_scaled_float_text(self.lcd.font8x16, self.lcd.Select_Color, 3, 1, 216, self.MBASE(4), self.pd.HMI_ValueStruct.Move_E_scale)
        self.lcd.update()

    def HMI_Temperature(self):
        event = self.get_encoder_state()
        if self._menu_navigation('temperature', self.select_temp, 'index_temp', self.Draw_Temperature_Menu):
            return
        if event != self.ENCODER_DIFF_ENTER:
            return
        if self.select_temp.now == 0:
            self.checkkey = self.Control
            self.select_control.set(self.CONTROL_CASE_TEMP)
            self.Draw_Control_Menu()
        else:
            key = self._menus['temperature'][self.select_temp.now - 1][0]
            if key.startswith('PRESET:'):
                profile = int(key.split(':', 1)[1])
                self._active_preset = profile
                self.checkkey = self.PLAPreheat
                self.select_PLA.reset()
                self.pd.HMI_ValueStruct.show_mode = -2
                self._draw_capability_menu('preheat', self.select_PLA, profile=profile)
            else:
                self.pd.HMI_ValueStruct.show_mode = -1
                self._open_thermal_editor(key, self.select_temp.now)
        self.lcd.update()

    def _preset_hmi(self, profile=None):
        profile = getattr(self, '_active_preset', 0) if profile is None else profile
        if not 0 <= profile < len(self.pd.material_preset):
            self.checkkey = self.TemperatureID
            self.select_temp.reset()
            self.Draw_Temperature_Menu()
            self.lcd.update()
            return
        selection = self.select_PLA
        draw = lambda: self._draw_capability_menu('preheat', selection, profile=profile)
        if self._menu_navigation('preheat', selection, 'index_preset', draw):
            return
        if self.get_encoder_state() != self.ENCODER_DIFF_ENTER:
            return
        if selection.now == 0:
            self.checkkey = self.TemperatureID
            self.pd.HMI_ValueStruct.show_mode = -1
            self.Draw_Temperature_Menu()
        else:
            key = self._menus['preheat'][selection.now - 1][0]
            if key == 'SAVE':
                future = self.pd.save_settings()
                if isinstance(future, Future):
                    self._action('Save presets', lambda: future, on_accept=draw)
                else:
                    self.HMI_AudioFeedback(future)
            else:
                self._open_thermal_editor(key, selection.now, profile)
        self.lcd.update()

    def HMI_PLAPreheatSetting(self):
        self._preset_hmi()

    def HMI_ABSPreheatSetting(self):
        self._preset_hmi()

    def HMI_FanSpeed(self):
        event = self.get_encoder_state()
        mode = self.pd.HMI_ValueStruct.show_mode
        if mode == -1:
            row = self.TEMP_CASE_FAN
        else:
            row = self.TUNE_CASE_FAN + self.MROWS - self.index_tune
        if event == self.ENCODER_DIFF_ENTER:
            value = self.pd.HMI_ValueStruct.Fan_speed
            if mode != -2:
                self._action("Fan speed", lambda: self.pd.setFanSpeed(value))
                self.checkkey = self.TemperatureID if mode == -1 else self.Tune
                self.Draw_Temperature_Menu() if mode == -1 else self.Draw_Tune_Menu()
        elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            value = self.pd.HMI_ValueStruct.Fan_speed + (self._encoder_move_value if event == self.ENCODER_DIFF_CW else -self._encoder_move_value)
            self.pd.HMI_ValueStruct.Fan_speed = max(0, min(100, value))
            self.lcd.draw_integer_text(True, True, 0, self.lcd.font8x16,
                                   self.lcd.Color_White, self.lcd.Select_Color,
                                   3, 216, self.MBASE(row), self.pd.HMI_ValueStruct.Fan_speed)
        self.lcd.update()

    def HMI_ETemp(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self.pd.HMI_ValueStruct.show_mode == -1:
            temp_line = self.TEMP_CASE_TEMP
        elif self.pd.HMI_ValueStruct.show_mode == -2:
            temp_line = self.PREHEAT_CASE_TEMP
        else:
            temp_line = self.TUNE_CASE_TEMP + self.MROWS - self.index_tune

        if (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if (self.pd.HMI_ValueStruct.show_mode == -1):  # temperature
                self.checkkey = self.TemperatureID
                self.lcd.draw_integer_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
                    3, 216, self.MBASE(temp_line),
                    self.pd.HMI_ValueStruct.E_Temp
                )
            elif (self.pd.HMI_ValueStruct.show_mode == -2):
                self.checkkey = self.PLAPreheat
                profile = getattr(self, '_active_preset', 0)
                self.pd.material_preset[profile].hotend_temp = self.pd.HMI_ValueStruct.E_Temp
                self.lcd.draw_integer_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
                    3, 216, self.MBASE(temp_line),
                    self.pd.material_preset[profile].hotend_temp
                )
                return
            else:  # tune
                self.checkkey = self.Tune
                self.lcd.draw_integer_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
                    3, 216, self.MBASE(temp_line),
                    self.pd.HMI_ValueStruct.E_Temp
                )
            self._action("Hotend target", lambda: self.pd.setExtTemp(self.pd.HMI_ValueStruct.E_Temp))
            return

        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.E_Temp += self._encoder_move_value

        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.E_Temp -= self._encoder_move_value

        # E_Temp limit
        if self.pd.HMI_ValueStruct.E_Temp > self.pd.MAX_E_TEMP:
            self.pd.HMI_ValueStruct.E_Temp = self.pd.MAX_E_TEMP
        if self.pd.HMI_ValueStruct.E_Temp < self.pd.MIN_E_TEMP:
            self.pd.HMI_ValueStruct.E_Temp = self.pd.MIN_E_TEMP
        heater = self.pd.capabilities.active_hotend
        if heater and 0 < self.pd.HMI_ValueStruct.E_Temp < heater.minimum:
            self.pd.HMI_ValueStruct.E_Temp = heater.minimum if encoder_diffState == self.ENCODER_DIFF_CW else 0
        # E_Temp value
        self.lcd.draw_integer_text(
            True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
            3, 216, self.MBASE(temp_line),
            self.pd.HMI_ValueStruct.E_Temp
        )

    def HMI_BedTemp(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return

        if self.pd.HMI_ValueStruct.show_mode == -1:
            bed_line = self.TEMP_CASE_BED
        elif self.pd.HMI_ValueStruct.show_mode == -2:
            bed_line = self.PREHEAT_CASE_BED
        else:
            bed_line = self.TUNE_CASE_BED + self.MROWS - self.index_tune

        if (encoder_diffState == self.ENCODER_DIFF_ENTER):
            if (self.pd.HMI_ValueStruct.show_mode == -1):  # temperature
                self.checkkey = self.TemperatureID
                self.lcd.draw_integer_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
                    3, 216, self.MBASE(bed_line),
                    self.pd.HMI_ValueStruct.Bed_Temp
                )
            elif (self.pd.HMI_ValueStruct.show_mode == -2):
                self.checkkey = self.PLAPreheat
                profile = getattr(self, '_active_preset', 0)
                self.pd.material_preset[profile].bed_temp = self.pd.HMI_ValueStruct.Bed_Temp
                self.lcd.draw_integer_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
                    3, 216, self.MBASE(bed_line),
                    self.pd.material_preset[profile].bed_temp
                )
                return
            else:  # tune
                self.checkkey = self.Tune
                self.lcd.draw_integer_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black,
                    3, 216, self.MBASE(bed_line),
                    self.pd.HMI_ValueStruct.Bed_Temp
                )
            self._action("Bed target", lambda: self.pd.setBedTemp(self.pd.HMI_ValueStruct.Bed_Temp))
            return

        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self.pd.HMI_ValueStruct.Bed_Temp += self._encoder_move_value

        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self.pd.HMI_ValueStruct.Bed_Temp -= self._encoder_move_value

        # Bed_Temp limit
        if self.pd.HMI_ValueStruct.Bed_Temp > self.pd.BED_MAX_TARGET:
            self.pd.HMI_ValueStruct.Bed_Temp = self.pd.BED_MAX_TARGET
        if self.pd.HMI_ValueStruct.Bed_Temp < self.pd.MIN_BED_TEMP:
            self.pd.HMI_ValueStruct.Bed_Temp = self.pd.MIN_BED_TEMP
        heater = self.pd.capabilities.bed
        if heater and 0 < self.pd.HMI_ValueStruct.Bed_Temp < heater.minimum:
            self.pd.HMI_ValueStruct.Bed_Temp = heater.minimum if encoder_diffState == self.ENCODER_DIFF_CW else 0
        # Bed_Temp value
        self.lcd.draw_integer_text(
            True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
            3, 216, self.MBASE(bed_line),
            self.pd.HMI_ValueStruct.Bed_Temp
        )


    def HMI_Motion(self):
        event = self.get_encoder_state()
        settings = self.pd.motion_settings()
        if event == self.ENCODER_DIFF_CW:
            self.select_motion.inc(len(settings) + 1)
        elif event == self.ENCODER_DIFF_CCW:
            self.select_motion.dec()
        elif event == self.ENCODER_DIFF_ENTER:
            if self.select_motion.now == 0:
                self.checkkey = self.Control
                self.select_control.set(self.CONTROL_CASE_MOVE)
                self.Draw_Control_Menu()
                self.lcd.update()
                return
            if self.select_motion.now > len(settings):
                self.select_motion.reset()
            else:
                field, _, _, _, value = settings[self.select_motion.now - 1]
                self._motion_field, self._motion_target = field, value
                self.checkkey = self.MotionValue
        if event != self.ENCODER_DIFF_NO:
            self.Draw_Motion_Menu()
            self.lcd.update()

    def HMI_MotionValue(self):
        event = self.get_encoder_state()
        setting = next((item for item in self.pd.motion_settings()
                        if item[0] == self._motion_field), None)
        if setting is None:
            self.checkkey = self.Motion
            self.select_motion.reset()
        elif event == self.ENCODER_DIFF_ENTER:
            self._action("Motion limit", lambda: self.pd.set_motion_limit(self._motion_field, self._motion_target))
            self.checkkey = self.Motion
        elif event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            step = setting[3]
            change = step * self._encoder_move_value if event == self.ENCODER_DIFF_CW else -step * self._encoder_move_value
            previous = self._motion_target
            minimum = min(step, previous) if self._motion_field in ('max_velocity', 'max_accel') else 0
            self._motion_target = round(max(minimum, self._motion_target + change), 6)
            if self._motion_field == 'minimum_cruise_ratio':
                self._motion_target = min(max(.99, previous), self._motion_target)
        if event != self.ENCODER_DIFF_NO:
            self.Draw_Motion_Menu()
            self.lcd.update()

    def _probe_options(self):
        wizard = self.pd.probe_wizard
        if wizard.pending:
            return ()
        if wizard.phase == 'active':
            return (('Raise 0.1', lambda: wizard.testz(.1)),
                    ('Lower 0.1', lambda: wizard.testz(-.1)),
                    ('Raise 0.01', lambda: wizard.testz(.01)),
                    ('Lower 0.01', lambda: wizard.testz(-.01)),
                    ('Accept', wizard.accept), ('Abort', wizard.abort))
        if wizard.phase == 'accepted':
            return (('Save: restart Klipper', wizard.save), ('Leave unsaved', self._leave_probe))
        if wizard.phase in ('error', 'interrupted', 'saved'):
            return (('Back; check printer', self._leave_probe),)
        return (('Start at current XY', wizard.start), ('Back', self._leave_probe))

    def _leave_probe(self):
        self.checkkey = self.Control
        self.Draw_Control_Menu()

    def Draw_Probe_Wizard(self):
        self.Clear_Main_Window()
        self.Draw_Title('Probe calibration')
        wizard = self.pd.probe_wizard
        self.lcd.draw_text(False, False, self.lcd.font6x12, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, 8, 35, wizard.message[:42])
        options = self._probe_options()
        self._probe_selection = max(0, min(getattr(self, '_probe_selection', 0), max(0, len(options) - 1)))
        for row, (label, _) in enumerate(options):
            self.Draw_Menu_Line(row, self.ICON_Zoffset, label)
            if row == self._probe_selection:
                self.Draw_Menu_Cursor(row)
        self.lcd.update()

    def HMI_Probe_Wizard(self):
        wizard = self.pd.probe_wizard
        wizard.update()
        options = self._probe_options()
        self._probe_selection = max(0, min(getattr(self, '_probe_selection', 0), max(0, len(options) - 1)))
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_CW and options:
            self._probe_selection = min(len(options) - 1, self._probe_selection + 1)
        elif event == self.ENCODER_DIFF_CCW:
            self._probe_selection = max(0, self._probe_selection - 1)
        elif event == self.ENCODER_DIFF_ENTER and options:
            try:
                options[self._probe_selection][1]()
            except ValueError as error:
                wizard.message = str(error)
        if self.checkkey == self.ProbeWizardID:
            self.Draw_Probe_Wizard()

    def _open_zoffset(self, mode, row):
        self.checkkey = self.Homeoffset
        self.pd.HMI_ValueStruct.show_mode = mode
        self._zoffset_target = self.pd.BABY_Z_VAR * 100
        self.lcd.draw_signed_scaled_float_text(self.lcd.font8x16, self.lcd.Select_Color,
                                   2, 2, 202, self.MBASE(row), self._zoffset_target)

    def HMI_Zoffset(self):
        encoder_diffState = self.get_encoder_state()
        if (encoder_diffState == self.ENCODER_DIFF_NO):
            return
        if not hasattr(self, '_zoffset_target'):
            self._zoffset_target = self.pd.HMI_ValueStruct.offset_value
        zoff_line = 0
        if self.pd.HMI_ValueStruct.show_mode == -4:
            zoff_line = self.PREPARE_CASE_ZOFF + self.MROWS - self.index_prepare
        else:
            zoff_line = self.TUNE_CASE_ZOFF + self.MROWS - self.index_tune

        if (encoder_diffState == self.ENCODER_DIFF_ENTER): #if (applyencoder(encoder_diffstate, offset_value))
            self._action("Runtime Z offset", lambda: self.pd.setZOffset(self._zoffset_target / 100.0))

            self.checkkey = self.Prepare if self.pd.HMI_ValueStruct.show_mode == -4 else self.Tune
            self.lcd.draw_signed_scaled_float_text(
                self.lcd.font8x16, self.lcd.Color_Bg_Black, 2, 2, 202, self.MBASE(zoff_line),
                self._zoffset_target
            )

            self.lcd.update()
            return

        elif (encoder_diffState == self.ENCODER_DIFF_CW):
            self._zoffset_target += self._encoder_move_value
        elif (encoder_diffState == self.ENCODER_DIFF_CCW):
            self._zoffset_target -= self._encoder_move_value

        if (self._zoffset_target < (self.pd.Z_PROBE_OFFSET_RANGE_MIN) * 100):
            self._zoffset_target = self.pd.Z_PROBE_OFFSET_RANGE_MIN * 100
        elif (self._zoffset_target > (self.pd.Z_PROBE_OFFSET_RANGE_MAX) * 100):
            self._zoffset_target = self.pd.Z_PROBE_OFFSET_RANGE_MAX * 100

        self.last_zoffset = self.dwin_zoffset
        self.dwin_zoffset = self._zoffset_target / 100.0

        self.lcd.draw_signed_scaled_float_text(
            self.lcd.font8x16, self.lcd.Select_Color, 2, 2, 202,
            self.MBASE(zoff_line),
            self._zoffset_target
        )
        self.lcd.update()

    # --------------------------------------------------------------#
    # --------------------------------------------------------------#

    def Draw_Status_Area(self, with_update):
        if getattr(self, 'checkkey', None) == self.MMUMenu:
            return
        # Compact dashboard: temperatures / speed / fan, bed / flow / Z offset,
        # then interpolated live X/Y/Z positions.
        self.lcd.draw_rectangle(
            1, self.lcd.Color_Bg_Black, 0, self.STATUS_Y,
            self.lcd.DWIN_WIDTH, self.lcd.DWIN_HEIGHT - 1)

        y1, y2, y3 = 382, 416, 458
        # Temperature fields need enough width for "actual/target". Keep them
        # in a wider left column and compact the two telemetry columns.
        x1, x2, x3 = 6, 116, 202
        value1, value2, value3 = 26, 137, 223

        if self.pd.HAS_HOTEND:
            self.lcd.show_icon(self.ICON, self.ICON_HotendTemp, x1, y1 - 1)
            self.lcd.draw_integer_text(True, True, 0, self.lcd.DWIN_FONT_STAT,
                self.lcd.Color_White, self.lcd.Color_Bg_Black, 3, value1, y1,
                self.pd.thermalManager['temp_hotend'][0]['celsius'])
            self.lcd.draw_text(False, False, self.lcd.DWIN_FONT_STAT,
                self.lcd.Color_White, self.lcd.Color_Bg_Black,
                value1 + 3 * self.STAT_CHR_W, y1, "/")
            self.lcd.draw_integer_text(True, True, 0, self.lcd.DWIN_FONT_STAT,
                self.lcd.Color_White, self.lcd.Color_Bg_Black, 3,
                value1 + 4 * self.STAT_CHR_W, y1,
                self.pd.thermalManager['temp_hotend'][0]['target'])

        # Match the established dashboard behavior: alternate speed override
        # and instantaneous Klipper toolhead velocity in the same field.
        phase = int(time.monotonic() / 2.0) & 1
        self.lcd.show_icon(self.ICON, self.ICON_Speed, x2, y1 - 1)
        if phase:
            speed_text = '{:.0f}%'.format(self.pd.feedrate_percentage)
        else:
            speed_text = '{:.0f}mm/s'.format(abs(self.pd.live_velocity))
        self.lcd.draw_text(False, True, self.lcd.DWIN_FONT_STAT,
            self.lcd.Color_White, self.lcd.Color_Bg_Black, value2, y1, speed_text)

        if self.pd.HAS_FAN:
            self.lcd.show_icon(self.ICON, self.ICON_FanSpeed, x3, y1 - 1)
            self.lcd.draw_integer_text(True, True, 0, self.lcd.DWIN_FONT_STAT,
                self.lcd.Color_White, self.lcd.Color_Bg_Black, 3,
                value3, y1, self.pd.dashboard_fan_pwm)

        if self.pd.HAS_HEATED_BED:
            self.lcd.show_icon(self.ICON, self.ICON_BedTemp, x1, y2 - 1)
            self.lcd.draw_integer_text(True, True, 0, self.lcd.DWIN_FONT_STAT,
                self.lcd.Color_White, self.lcd.Color_Bg_Black, 3, value1, y2,
                self.pd.thermalManager['temp_bed']['celsius'])
            self.lcd.draw_text(False, False, self.lcd.DWIN_FONT_STAT,
                self.lcd.Color_White, self.lcd.Color_Bg_Black,
                value1 + 3 * self.STAT_CHR_W, y2, "/")
            self.lcd.draw_integer_text(True, True, 0, self.lcd.DWIN_FONT_STAT,
                self.lcd.Color_White, self.lcd.Color_Bg_Black, 3,
                value1 + 4 * self.STAT_CHR_W, y2,
                self.pd.thermalManager['temp_bed']['target'])

        # The extrusion field alternates between M221 flow override and
        # instantaneous volumetric flow so both fit without sacrificing XYZ.
        self.lcd.show_icon(self.ICON, self.ICON_StepE, x2, y2 - 1)
        if phase:
            flow_text = '{:.0f}%'.format(self.pd.flow_percentage)
        else:
            flow_text = '{:.1f}mm3/s'.format(self.pd.volumetric_flow)
        self.lcd.draw_text(False, True, self.lcd.DWIN_FONT_STAT,
            self.lcd.Color_White, self.lcd.Color_Bg_Black, value2, y2, flow_text)

        if self.pd.HAS_ZOFFSET_ITEM:
            self.lcd.show_icon(self.ICON, self.ICON_Zoffset, x3, y2 - 1)
            self.lcd.draw_signed_scaled_float_text(
                self.lcd.DWIN_FONT_STAT, self.lcd.Color_Bg_Black,
                2, 2, value3, y2, self.pd.BABY_Z_VAR * 100)

        positions = self.pd.live_position
        for icon, xpos, value_x, position in (
                (self.ICON_MaxSpeedX, x1, value1, positions[0]),
                (self.ICON_MaxSpeedY, x2, value2, positions[1]),
                (self.ICON_MaxSpeedZ, x3, value3, positions[2])):
            self.lcd.show_icon(self.ICON, icon, xpos, y3 - 3)
            self.lcd.draw_signed_scaled_float_text(
                self.lcd.DWIN_FONT_STAT, self.lcd.Color_Bg_Black,
                3, 1, value_x, y3, position * 10)

    def _draw_power_icon(self, selected=False, clear=False):
        if clear:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Blue, 241, 2, 268, 29)
        self.lcd.draw_atlas_icon(ICON_POWER, 244, 5)
        if selected:
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 241, 2, 267, 28)

    def Draw_Title(self, title):
        self.lcd.draw_text(False, False, self.lcd.DWIN_FONT_HEAD, self.lcd.Color_White, self.lcd.Color_Bg_Blue, 14, 4, title)
        self._draw_power_icon(getattr(self, '_power_focus', False))

    def Draw_Popup_Bkgd_105(self):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Window, 14, 105, 258, 374)

    def Draw_More_Icon(self, line):
        self.lcd.show_icon(self.ICON, self.ICON_More, 226, self.MBASE(line) - 3)

    def Draw_Menu_Cursor(self, line):
        self.lcd.draw_rectangle(1, self.lcd.Rectangle_Color, 0, self.MBASE(line) - 18, 14, self.MBASE(line + 1) - 20)

    def Draw_Menu_Icon(self, line, icon):
        self.lcd.show_icon(self.ICON, icon, 26, self.MBASE(line) - 3)

    def Draw_Menu_Line(self, line, icon=False, label=False):
        if (label):
            self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black, self.LBLX, self.MBASE(line) - 1, label)
        if (icon):
            self.Draw_Menu_Icon(line, icon)
        self.lcd.draw_line(self.lcd.Line_Color, 16, self.MBASE(line) + 33, 256, self.MBASE(line) + 34)

    # The "Back" label is always on the first line
    def Draw_Back_Label(self):
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, self.LBLX, self.MBASE(0), 'Back')

    # Draw "Back" line at the top
    def Draw_Back_First(self, is_sel=True):
        self.Draw_Menu_Line(0, self.ICON_Back)
        self.Draw_Back_Label()
        if (is_sel):
            self.Draw_Menu_Cursor(0)

    def _draw_menu_text(self, text, x, y):
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, x, y, text)

    def draw_move_en(self, line):
        self._draw_menu_text('Move', self.LBLX, line)

    def draw_max_en(self, line):
        self._draw_menu_text('Max', self.LBLX, line)

    def draw_max_accel_en(self, line):
        self._draw_menu_text('Max Acceleration', self.LBLX, line)

    def draw_speed_en(self, inset, line):
        self._draw_menu_text('Speed', self.LBLX + inset, line)

    def draw_jerk_en(self, line):
        self._draw_menu_text('Jerk', self.LBLX + 27, line)

    def draw_steps_per_mm(self, line):
        self._draw_menu_text('Steps-per-mm', self.LBLX, line)

    # Display an SD item
    def Draw_SDItem(self, item, row=0):
        path = self._file_paths[item]
        is_dir = path.endswith('/')
        label = path.rstrip('/').rsplit('/', 1)[-1]
        self.Draw_Menu_Line(row, False if is_dir else self.ICON_File, label)
        if is_dir:
            self.lcd.draw_atlas_icon(ICON_FOLDER, 26, self.MBASE(row) - 7)

    def Draw_Select_Highlight(self, sel):
        self.pd.HMI_flag.select_flag = sel
        if sel:
            c1 = self.lcd.Select_Color
            c2 = self.lcd.Color_Bg_Window
        else:
            c1 = self.lcd.Color_Bg_Window
            c2 = self.lcd.Select_Color
        self.lcd.draw_rectangle(0, c1, 25, 279, 126, 318)
        self.lcd.draw_rectangle(0, c1, 24, 278, 127, 319)
        self.lcd.draw_rectangle(0, c2, 145, 279, 246, 318)
        self.lcd.draw_rectangle(0, c2, 144, 278, 247, 319)

    def Draw_Popup_Bkgd_60(self):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Window, 14, 60, 258, 330)

    def Draw_Printing_Screen(self):
        self.Draw_Title('Tune')
        self._draw_menu_text('Pause', 41, 188)
        self._draw_menu_text('Stop', 176, 188)

    def Draw_Print_ProgressBar(self, Percentrecord=None):
        if Percentrecord is None:
            Percentrecord = self.pd.getPercent()
        self.lcd.show_icon(self.ICON, self.ICON_Bar, 15, 93)
        self.lcd.draw_rectangle(1, self.lcd.BarFill_Color, 16 + Percentrecord * 240 / 100, 93, 256, 113)
        self.lcd.draw_integer_text(True, True, 0, self.lcd.font8x16, self.lcd.Percent_Color, self.lcd.Color_Bg_Black, 3, 109, 133, Percentrecord)
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Percent_Color, self.lcd.Color_Bg_Black, 133, 133, "%")

    def _draw_print_time(self, seconds, x):
        # Format completed minutes, not rounded fractional hours/minutes.
        minutes = max(0, int(seconds)) // 60
        text = '{:02d}:{:02d}'.format(minutes // 60, minutes % 60)
        self.lcd.draw_text(False, True, self.lcd.font8x16, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, x, 212, text)

    def Draw_Print_ProgressElapsed(self):
        self._draw_print_time(self.pd.duration(), 42)

    def Draw_Print_ProgressRemain(self):
        self._draw_print_time(self.pd.remain(), 176)

    def Draw_Print_File_Menu(self):
        self.Clear_Title_Bar()
        directory = getattr(self, '_file_directory', '')
        self.Draw_Title(('Print: /' + directory)[-32:] if directory else 'Print file')
        self.Redraw_SD_List()

    def Draw_Prepare_Menu(self):
        self._draw_capability_menu('prepare', self.select_prepare, self.index_prepare)

    def Draw_Control_Menu(self):
        self._draw_capability_menu('control', self.select_control, getattr(self, 'index_control', self.MROWS))

    def _draw_info_row(self, label, value, y):
        self._draw_menu_text(label, 8, y)
        text = T5UIC1Display._panel_text(value)[:17]
        color = self.lcd.Color_White
        if label == 'Network':
            state = text.strip().lower()
            if state == 'online':
                color = 0x07E0
            elif state == 'offline':
                color = 0xF800
        self.lcd.draw_text(False, False, self.lcd.font8x16, color,
                             self.lcd.Color_Bg_Black, 120, y, text)

    def _draw_info_section(self, label, y):
        text = T5UIC1Display._panel_text(label)[:24]
        palette = {
            'MACHINE': (0x07FF, ICON_MACHINE),
            'HOST': (0xF81F, ICON_HOST),
            'SOFTWARE': (0xA81F, ICON_SOFTWARE),
        }
        key = text.upper()
        if key.startswith('MCU'):
            color, icon = 0x07E0, ICON_MCU
        else:
            color, icon = palette.get(key, (self.lcd.Color_White, None))
        if icon is not None:
            self.lcd.draw_atlas_icon(icon, 8, y - 2)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Info, 8, y - 2)
        self.lcd.draw_text(False, False, self.lcd.font10x20, color,
                             self.lcd.Color_Bg_Black, 40, y, key)
        self.lcd.draw_rectangle(1, color, 40, y + 21, 255, y + 22)

    def _info_items(self):
        info = self.pd.system_info
        cpu = info.get('host_cpu')
        temp = info.get('host_temp')
        items = [
            ('section', 'Machine', None),
            ('row', 'Size', self.pd.MACHINE_SIZE),
            ('row', 'Network', info.get('network', 'Unknown')),
            ('row', 'IP', info.get('ip', 'Unavailable')),
            ('section', 'Host', None),
            ('row', 'CPU', 'N/A' if cpu is None else '{:.0f}%'.format(cpu)),
            ('row', 'CPU temp', 'N/A' if temp is None else '{:.1f} C'.format(temp)),
            ('section', 'Software', None),
            ('row', 'KlipperDWIN', info.get('klipperdwin', 'Unavailable')),
            ('row', 'Klipper', self.pd.SHORT_BUILD_VERSION),
            ('row', 'Moonraker', info.get('moonraker', 'Unavailable')),
            ('row', 'Mainsail', info.get('mainsail', 'Unavailable')),
            ('wide', '', 'github.com/sezgynus/KlipperDWIN'),
        ]
        mcus = info.get('mcus') or ()
        if not mcus:
            items.extend((('section', 'MCU', None), ('row', 'Status', 'Unavailable')))
        for mcu in mcus:
            name = str(mcu.get('name', 'mcu'))
            load = mcu.get('load')
            temperature = mcu.get('temperature')
            items.extend((
                ('section', 'MCU: ' + name, None),
                ('row', 'Status', 'Connected'),
                ('row', 'Load', 'N/A' if load is None else '{:.1f}%'.format(load)),
                ('row', 'Temp', 'N/A' if temperature is None else '{:.1f} C'.format(temperature)),
            ))
        return items

    def Draw_Info_Menu(self):
        self.pd.refresh_system_info()
        self.Clear_Main_Window()
        self.Draw_Title('Info')
        self.Draw_Back_First()
        items = self._info_items()
        visible_count = 11
        max_scroll = max(0, len(items) - visible_count)
        self._info_scroll = max(0, min(getattr(self, '_info_scroll', 0), max_scroll))
        y = 92
        for kind, label, value in items[self._info_scroll:self._info_scroll + visible_count]:
            if kind == 'section':
                self._draw_info_section(label, y)
            elif kind == 'wide':
                text = T5UIC1Display._panel_text(value)[:31]
                self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                                     self.lcd.Color_Bg_Black, 8, y, text)
            else:
                self._draw_info_row(label, value, y)
            y += 24
        if self._info_scroll:
            self._draw_menu_text('^', 256, 76)
        if self._info_scroll < max_scroll:
            self._draw_menu_text('v', 256, 328)

    def Draw_Tune_Menu(self):
        self._draw_capability_menu('tune', self.select_tune, self.index_tune)

    def Draw_Temperature_Menu(self):
        self._draw_capability_menu('temperature', self.select_temp, self.index_temp)

    def Draw_Motion_Menu(self):
        self.Clear_Main_Window()
        self.Draw_Title('Motion (runtime)')
        self.Draw_Back_First(self.select_motion.now == 0)
        settings = self.pd.motion_settings()
        if self.select_motion.now > len(settings):
            self.select_motion.reset()
        for row, (field, _, label, _, value) in enumerate(settings, 1):
            self.Draw_Menu_Line(row, self.ICON_Motion, label)
            editing = self.checkkey == self.MotionValue and self._motion_field == field
            if editing:
                value = self._motion_target
            if self.select_motion.now == row:
                self.Draw_Menu_Cursor(row)
            text = '{:g}'.format(value)
            if len(text) > 9:
                text = '{:.3g}'.format(value)
            if len(text) > 9:
                text = '#' * 9
            self.lcd.draw_text(False, True, self.lcd.font8x16, self.lcd.Color_White,
                                 self.lcd.Select_Color if editing else self.lcd.Color_Bg_Black,
                                 168, self.MBASE(row), text.rjust(9))

    def Draw_Move_Menu(self):
        self.Clear_Main_Window()
        self.Draw_Title('Move')
        self.draw_move_en(self.MBASE(1))
        self.say_x(36, self.MBASE(1))  # "Move X"
        self.draw_move_en(self.MBASE(2))
        self.say_y(36, self.MBASE(2))  # "Move Y"
        self.draw_move_en(self.MBASE(3))
        self.say_z(36, self.MBASE(3))  # "Move Z"
        if self.pd.HAS_HOTEND:
            self._draw_menu_text('Extruder', self.LBLX, self.MBASE(4))

        live_row = 4 + int(self.pd.HAS_HOTEND)
        self.Draw_Menu_Line(live_row, self.ICON_Axis, 'Live jog')
        self.lcd.draw_text(False, True, self.lcd.font8x16, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, 224, self.MBASE(live_row),
                             '[X]' if getattr(self, '_live_jog', False) else '[ ]')

        self.Draw_Back_First(self.select_axis.now == 0)
        if (self.select_axis.now):
            self.Draw_Menu_Cursor(self.select_axis.now)

        # Match editor/jog command space, including offsets and transforms.
        position = self.pd.state.status['gcode_move']['position']
        for index in range(3 + int(self.pd.HAS_HOTEND)):
            value = position[index] * self.MINUNITMULT
            if index == 3:
                self.lcd.draw_signed_scaled_float_text(self.lcd.font8x16, self.lcd.Color_Bg_Black,
                                           3, 1, 216, self.MBASE(4), value)
            else:
                self.lcd.draw_scaled_float_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White,
                    self.lcd.Color_Bg_Black, 3, 1, 216, self.MBASE(index + 1), value)

        # Draw separators and icons
        for i in range(3 + int(self.pd.HAS_HOTEND)):
            self.Draw_Menu_Line(i + 1, self.ICON_MoveX + i)
        if self.select_axis.now == live_row:
            self.Draw_Menu_Cursor(live_row)

    # --------------------------------------------------------------#
    # --------------------------------------------------------------#

    def Goto_MainMenu(self):
        self.checkkey = self.MainMenu
        self.Clear_Main_Window()
        self._draw_power_icon(getattr(self, '_power_focus', False))

        if self.pd.mmu is None:
            self.lcd.show_icon(self.ICON, self.ICON_LOGO, 71, 52)
        else:
            self.Draw_MMU_Status()
        self._drawn_mmu_state = self.pd.mmu

        self._draw_home_page()

    def Goto_PrintProcess(self):
        self.checkkey = self.PrintProcess
        self.Clear_Main_Window()
        self.Draw_Printing_Screen()

        self.ICON_Tune()
        if (self.pd.printingIsPaused()):
            self.ICON_Continue()
        else:
            self.ICON_Pause()
        self.ICON_Stop()

        # Copy into filebuf string before entry
        name = self.pd.file_name
        if name:
            npos = _MAX(0, self.lcd.DWIN_WIDTH - len(name) * self.MENU_CHR_W) / 2
            self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Black, npos, 60, name)

        self.lcd.show_icon(self.ICON, self.ICON_PrintTime, 17, 193)
        self.lcd.show_icon(self.ICON, self.ICON_RemainTime, 150, 191)

        self.Draw_Print_ProgressBar()
        self.Draw_Print_ProgressElapsed()
        self.Draw_Print_ProgressRemain()

    # --------------------------------------------------------------#
    # --------------------------------------------------------------#

    def Clear_Title_Bar(self):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Blue, 0, 0, self.lcd.DWIN_WIDTH, 30)

    def Clear_Menu_Area(self):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 31, self.lcd.DWIN_WIDTH, self.STATUS_Y)

    def Clear_Main_Window(self):
        self.Clear_Title_Bar()
        self.Clear_Menu_Area()

    def Clear_Popup_Area(self):
        self.Clear_Title_Bar()
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 31, self.lcd.DWIN_WIDTH, self.lcd.DWIN_HEIGHT)

    def Popup_window_PauseOrStop(self):
        self.Clear_Main_Window()
        self.Draw_Popup_Bkgd_60()
        if(self.select_print.now == 1):
            self.lcd.draw_text(
                False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
                (272 - 8 * 11) / 2, 150,
                self.MSG_PAUSE_PRINT
            )
        elif (self.select_print.now == 2):
            self.lcd.draw_text(
                False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
                (272 - 8 * 10) / 2, 150,
                self.MSG_STOP_PRINT
            )
        self.lcd.show_icon(self.ICON, self.ICON_Confirm_E, 26, 280)
        self.lcd.show_icon(self.ICON, self.ICON_Cancel_E, 146, 280)
        self.Draw_Select_Highlight(True)

    def Popup_Window_Home(self, parking=False):
        self.Clear_Main_Window()
        self.Draw_Popup_Bkgd_60()
        self.lcd.show_icon(self.ICON, self.ICON_BLTouch, 101, 105)
        if parking:
            self.lcd.draw_text(
                False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
                (272 - 8 * (7)) / 2, 230, "Parking")
        else:
            self.lcd.draw_text(
                False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
                (272 - 8 * (10)) / 2, 230, "Homing XYZ")

        self.lcd.draw_text(
            False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
            (272 - 8 * 23) / 2, 260, "Please wait until done.")

    def Popup_Window_ETempTooLow(self):
        self.Clear_Main_Window()
        self.Draw_Popup_Bkgd_60()
        self.lcd.show_icon(self.ICON, self.ICON_TempTooLow, 102, 105)
        self.lcd.draw_text(
            False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color,
            self.lcd.Color_Bg_Window, 20, 235,
            "Nozzle is too cold"
        )
        self.lcd.show_icon(self.ICON, self.ICON_Confirm_E, 86, 280)

    def Erase_Menu_Cursor(self, line):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, self.MBASE(line) - 18, 14, self.MBASE(line + 1) - 20)

    def Erase_Menu_Text(self, line):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, self.LBLX, self.MBASE(line) - 14, 271, self.MBASE(line) + 28)

    def Move_Highlight(self, ffrom, newline):
        self.Erase_Menu_Cursor(newline - ffrom)
        self.Draw_Menu_Cursor(newline)

    def Add_Menu_Line(self):
        self.Move_Highlight(1, self.MROWS)
        self.lcd.draw_line(self.lcd.Line_Color, 16, self.MBASE(self.MROWS + 1) - 20, 256, self.MBASE(self.MROWS + 1) - 19)

    def Scroll_Menu(self, dir):
        self.lcd.move_area(1, dir, self.MLINE, self.lcd.Color_Bg_Black, 0, 31, self.lcd.DWIN_WIDTH, 349)
        if dir == self.DWIN_SCROLL_DOWN:
            self.Move_Highlight(-1, 0)
        elif dir == self.DWIN_SCROLL_UP:
            self.Add_Menu_Line()

    # Redraw the first set of SD Files
    def Redraw_SD_List(self):
        if not hasattr(self, '_file_paths'):
            self._refresh_file_snapshot()
        self.Clear_Menu_Area()
        entries = ('Back',) + getattr(self, '_file_paths', ())
        start = max(0, self.index_file - self.MROWS)
        for logical in range(start, min(len(entries), start + self.TROWS)):
            row = logical - start
            if logical == 0:
                self.Draw_Menu_Line(row, self.ICON_Back, 'Back')
            else:
                self.Draw_SDItem(logical - 1, row)
            if logical == self.select_file.now:
                self.Draw_Menu_Cursor(row)
        if len(entries) == 1:
            self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                                 self.lcd.Color_Bg_Black, 20, self.MBASE(2),
                                 'File list unavailable' if self.pd.file_error else 'Loading files...' if self.pd._files_loading or self.pd._directory_loading else 'No files')

    def CompletedHoming(self):
        self.pd.HMI_flag.home_flag = False
        if (self.checkkey == self.Last_Prepare):
            self.checkkey = self.Prepare
            self.select_prepare.now = self.PREPARE_CASE_HOME
            self.index_prepare = self.MROWS
            self.Draw_Prepare_Menu()
        elif (self.checkkey == self.Back_Main):
            # dwin_zoffset = TERN0(HAS_BED_PROBE, probe.offset.z)
            # planner.finish_and_disable()
            self.Goto_MainMenu()

    def say_x(self, inset, line):
        self._draw_menu_text('X', self.LBLX + inset, line)

    def say_y(self, inset, line):
        self._draw_menu_text('Y', self.LBLX + inset, line)

    def say_z(self, inset, line):
        self._draw_menu_text('Z', self.LBLX + inset, line)

    def say_e(self, inset, line):
        self._draw_menu_text('E', self.LBLX + inset, line)

    # --------------------------------------------------------------#
    # --------------------------------------------------------------#

    def ICON_Print(self):
        if self.select_page.now == 0:
            self.lcd.show_icon(self.ICON, self.ICON_Print_1, 17, 130)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 17, 130, 126, 229)
            self._draw_menu_text('Print', 57, 201)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Print_0, 17, 130)
            self._draw_menu_text('Print', 57, 201)

    def ICON_Prepare(self):
        if self.select_page.now == 1:
            self.lcd.show_icon(self.ICON, self.ICON_Prepare_1, 145, 130)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 145, 130, 254, 229)
            self._draw_menu_text('Prepare', 175, 201)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Prepare_0, 145, 130)
            self._draw_menu_text('Prepare', 175, 201)

    def ICON_Control(self):
        if self.select_page.now == 2:
            self.lcd.show_icon(self.ICON, self.ICON_Control_1, 17, 246)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 17, 246, 126, 345)
            self._draw_menu_text('Control', 48, 318)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Control_0, 17, 246)
            self._draw_menu_text('Control', 48, 318)

    def ICON_Leveling(self, show):
        if show:
            self.lcd.show_icon(self.ICON, self.ICON_Leveling_1, 145, 246)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 145, 246, 254, 345)
            self._draw_menu_text('Leveling', 182, 318)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Leveling_0, 145, 246)
            self._draw_menu_text('Leveling', 182, 318)

    def ICON_StartInfo(self, show):
        if show:
            self.lcd.show_icon(self.ICON, self.ICON_Info_1, 145, 246)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 145, 246, 254, 345)
            self._draw_menu_text('Info', 186, 318)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Info_0, 145, 246)
            self._draw_menu_text('Info', 186, 318)

    def ICON_Tune(self):
        if (self.select_print.now == 0):
            self.lcd.show_icon(self.ICON, self.ICON_Setup_1, 8, 252)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 8, 252, 87, 351)
            self._draw_menu_text('Tune', 31, 325)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Setup_0, 8, 252)
            self._draw_menu_text('Tune', 31, 325)

    def ICON_Continue(self):
        if (self.select_print.now == 1):
            self.lcd.show_icon(self.ICON, self.ICON_Continue_1, 96, 252)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 96, 252, 175, 351)
            self._draw_menu_text('Continue', 121, 325)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Continue_0, 96, 252)
            self._draw_menu_text('Continue', 121, 325)

    def ICON_Pause(self):
        if (self.select_print.now == 1):
            self.lcd.show_icon(self.ICON, self.ICON_Pause_1, 96, 252)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 96, 252, 175, 351)
            self._draw_menu_text('Pause', 116, 325)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Pause_0, 96, 252)
            self._draw_menu_text('Pause', 116, 325)

    def ICON_Stop(self):
        if (self.select_print.now == 2):
            self.lcd.show_icon(self.ICON, self.ICON_Stop_1, 184, 252)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 184, 252, 263, 351)
            self._draw_menu_text('Stop', 209, 325)
        else:
            self.lcd.show_icon(self.ICON, self.ICON_Stop_0, 184, 252)
            self._draw_menu_text('Stop', 209, 325)

    def Item_Prepare_Move(self, row):
        self.draw_move_en(self.MBASE(row))  # "Move >"
        self.Draw_Menu_Line(row, self.ICON_Axis)
        self.Draw_More_Icon(row)

    def Item_Prepare_Disable(self, row):
        self._draw_menu_text('Disable steppers', self.LBLX, self.MBASE(row))  # Disable Stepper"
        self.Draw_Menu_Line(row, self.ICON_CloseMotor)

    def Item_Prepare_Home(self, row):
        self._draw_menu_text('Auto home', self.LBLX, self.MBASE(row))  # Auto Home"
        self.Draw_Menu_Line(row, self.ICON_Homing)

    def Item_Prepare_Offset(self, row):
        if self.pd.HAS_BED_PROBE:
            self._draw_menu_text('Z offset', self.LBLX, self.MBASE(row))  # "Z-Offset"
            self.lcd.draw_signed_scaled_float_text(self.lcd.font8x16, self.lcd.Color_Bg_Black, 2, 2, 202, self.MBASE(row), self.pd.BABY_Z_VAR * 100)
        else:
            self._draw_menu_text('Set home', self.LBLX, self.MBASE(row))  # "..."
        self.Draw_Menu_Line(row, self.ICON_SetHome)

    def Item_Prepare_PLA(self, row):
        self._draw_menu_text('Preheat PLA', self.LBLX, self.MBASE(row))
        self.Draw_Menu_Line(row, self.ICON_PLAPreheat)

    def Item_Prepare_ABS(self, row):
        self._draw_menu_text('Preheat ABS', self.LBLX, self.MBASE(row))
        self.Draw_Menu_Line(row, self.ICON_ABSPreheat)

    def Item_Prepare_Cool(self, row):
        self._draw_menu_text('Cooldown', self.LBLX, self.MBASE(row))  # "Cooldown"
        self.Draw_Menu_Line(row, self.ICON_Cool)

    # --------------------------------------------------------------#
    # --------------------------------------------------------------#

    def EachMomentUpdate(self):
        self._poll_case_light_query()
        # variable update
        update = self.pd.update_variable()
        if not self.pd.connection_error and self._configure_menus():
            for name in self.SELECTIONS:
                getattr(self, name).reset()
            self.index_prepare = self.index_tune = self.index_control = self.MROWS
            self._offline = True
        self._poll_mmu()
        if self.checkkey == self.MMUMenu:
            self._offline = bool(self.pd.connection_error)
            if self.last_status != self.pd.status:
                self._present_print_state()
            return
        if self._poll_action():
            return
        self._poll_screws_tilt()
        self._poll_bed_mesh()
        if self.pd.connection_error and self.checkkey in (self.BedMeshScreen, self.MeshProfiles):
            self._offline = True
            return
        if self.pd.connection_error:
            if not self._offline:
                self._show_message('Moonraker unavailable')
            self._offline = True
            return
        self.pd.probe_wizard.update()
        if self.checkkey == self.Info and self.pd.refresh_system_info():
            self.Draw_Info_Menu()
            self.lcd.update()
        if self._poll_print_start() or getattr(self, '_start_error_visible', False):
            return
        if self.checkkey == self.SelectFile and (
                self.pd._files_loading or self.pd._directory_loading
                or self.pd.state.epoch != getattr(self, '_file_view_epoch', -1)
                or self.pd.state.file_revision != getattr(self, '_file_view_revision', -1)
                or self.pd.file_sort_revision != getattr(self, '_file_view_sort_revision', -1)):
            if self._refresh_file_snapshot():
                self.Redraw_SD_List()
        if self.pd.last_command_error:
            self._offline = True
            self._show_message('Command failed; check log')
            self.pd.last_command_error = None
            return
        if getattr(self, '_offline', False):
            self._offline = False
            self.HMI_StartFrame(False)
            if self.checkkey == self.FilePreview:
                self.Draw_File_Preview()
        # An active numeric move editor owns its value until confirmation
        # when live jog is disabled.  Only live-jog editors follow external
        # position updates while idle.
        if (update and getattr(self, '_live_jog', False)
                and getattr(self, '_live_jog_future', None) is None
                and getattr(self, '_live_jog_pending', None) is None):
            position = self.pd.state.status['gcode_move']['position']
            active_moves = {
                self.Move_X: ('Move_X_scale', 0, self.MBASE(1), False),
                self.Move_Y: ('Move_Y_scale', 1, self.MBASE(2), False),
                self.Move_Z: ('Move_Z_scale', 2, self.MBASE(3), False),
                self.Extruder: ('Move_E_scale', 3, self.MBASE(4), True),
            }
            active = active_moves.get(self.checkkey)
            if active is not None:
                attr, index, row, signed = active
                scale = position[index] * self.MINUNITMULT
                if getattr(self.pd.HMI_ValueStruct, attr) != scale:
                    setattr(self.pd.HMI_ValueStruct, attr, scale)
                    if attr == 'Move_E_scale':
                        self.pd.last_E_scale = scale
                    if signed:
                        self.lcd.draw_signed_scaled_float_text(
                            self.lcd.font8x16, self.lcd.Select_Color,
                            3, 1, 216, row, scale)
                    else:
                        self.lcd.draw_scaled_float_text(
                            True, True, 0, self.lcd.font8x16,
                            self.lcd.Color_White, self.lcd.Select_Color,
                            3, 1, 216, row, scale)
        if self.last_status != self.pd.status:
            self._present_print_state()
        if getattr(self, '_print_error_visible', False):
            return

        if self.checkkey == self.PrintProcess:
            if not self.pd.HMI_flag.done_confirm_flag:
                if self.pd.HMI_flag.pause_flag != self.pd.printingIsPaused():
                    self.pd.HMI_flag.pause_flag = self.pd.printingIsPaused()
                    if self.pd.HMI_flag.pause_flag:
                        self.ICON_Continue()
                    else:
                        self.ICON_Pause()
            self.Draw_Print_ProgressBar()
            self.Draw_Print_ProgressElapsed()
            self.Draw_Print_ProgressRemain()
        elif update and self.checkkey == self.Tune:
            self.Draw_Tune_Menu()
        elif update and self.checkkey == self.Motion:
            self.Draw_Motion_Menu()
        elif update and self.checkkey == self.BedMeshMenu:
            self.Draw_Bed_Mesh_Menu()
        elif self.checkkey == self.ProbeWizardID:
            self.Draw_Probe_Wizard()

        if self.pd.HMI_flag.home_flag:
            if self.pd.ishomed():
                self.CompletedHoming()

        if update:
            if self.checkkey == self.MainMenu:
                mmu_state = self.pd.mmu
                if mmu_state != getattr(self, '_drawn_mmu_state', None):
                    self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 4, 31, 268, 125)
                    if mmu_state is None:
                        self.lcd.show_icon(self.ICON, self.ICON_LOGO, 71, 52)
                    else:
                        self.Draw_MMU_Status()
                    self._drawn_mmu_state = mmu_state
            self.Draw_Status_Area(update)
        self.lcd.update()

    def _power_at_first_item(self):
        selections = {
            self.MainMenu: 'select_page', self.SelectFile: 'select_file',
            self.Prepare: 'select_prepare', self.Control: 'select_control',
            self.AxisMove: 'select_axis', self.TemperatureID: 'select_temp',
            self.Motion: 'select_motion', self.Tune: 'select_tune',
            self.PLAPreheat: 'select_PLA', self.ABSPreheat: 'select_ABS',
            self.CaseLight: 'select_light',
        }
        name = selections.get(self.checkkey)
        if name is not None:
            return getattr(self, name).now == 0
        custom = {
            self.BedMeshMenu: '_mesh_menu_selection',
            self.MeshProfiles: '_mesh_profile_selection',
            self.ScrewsTiltMenu: '_screws_selection',
            self.FilePreview: '_preview_choice',
            self.Info: '_info_scroll',
        }
        if self.checkkey == self.MMUMenu:
            return (not self.pd.connection_error and getattr(self, '_mmu_selection', 0) == 0
                    and getattr(self, '_mmu_edit', None) is None)
        attr = custom.get(self.checkkey)
        return attr is not None and getattr(self, attr, 0) == 0

    def _draw_power_confirmation(self):
        self.Clear_Popup_Area()
        self.lcd.draw_text(False, False, self.lcd.DWIN_FONT_HEAD, self.lcd.Color_White,
                           self.lcd.Color_Bg_Blue, 14, 4, 'Power')
        self.Draw_Popup_Bkgd_105()
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Popup_Text_Color,
                           self.lcd.Color_Bg_Window, 42, 150, 'Turn off printer?')
        for yes, label, x in ((True, 'Yes', 42), (False, 'No', 164)):
            color = self.lcd.Select_Color if self._power_confirm_yes == yes else self.lcd.Color_Bg_Window
            self.lcd.draw_rectangle(0, color, x - 12, 224, x + 52, 264)
            self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Popup_Text_Color,
                               self.lcd.Color_Bg_Window, x, 236, label)

    def _restore_power_origin(self):
        origin = self._power_origin
        self._power_origin = None
        self._power_focus = False
        self.checkkey = origin if origin is not None else self.MainMenu
        if self.checkkey == self.MMUMenu:
            # The power popup overwrote the cached full-screen MMU canvas.
            self._mmu_canvas_page = None
        redraw = {
            self.MainMenu: self.Goto_MainMenu,
            self.SelectFile: self.Draw_Print_File_Menu,
            self.Prepare: self.Draw_Prepare_Menu,
            self.Control: self.Draw_Control_Menu,
            self.AxisMove: self.Draw_Move_Menu,
            self.TemperatureID: self.Draw_Temperature_Menu,
            self.Motion: self.Draw_Motion_Menu,
            self.Info: self.Draw_Info_Menu,
            self.Tune: self.Draw_Tune_Menu,
            self.MMUMenu: self.Draw_MMU_Menu,
            self.BedMeshMenu: self.Draw_Bed_Mesh_Menu,
            self.BedMeshScreen: self.Draw_Bed_Mesh,
            self.MeshProfiles: self.Draw_Mesh_Profiles,
            self.FilePreview: self.Draw_File_Preview,
        }.get(self.checkkey)
        if redraw is not None:
            redraw()
        else:
            self._restore_action_screen()

    def _handle_power_navigation(self):
        if self._mmu_power_popup_stale():
            self._restore_power_origin()
            return True
        event = self.get_encoder_state()
        if self.checkkey == self.PowerConfirm:
            if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                self._power_confirm_yes = not self._power_confirm_yes
                self._draw_power_confirmation()
            elif event == self.ENCODER_DIFF_ENTER:
                if self._power_confirm_yes:
                    self.pd.power_off_if_on()
                    self._show_message('Powering off...')
                else:
                    self._restore_power_origin()
            return True
        if getattr(self, '_power_focus', False):
            if event == self.ENCODER_DIFF_CW:
                self._power_focus = False
                self._draw_power_icon(False, clear=True)
            elif event == self.ENCODER_DIFF_ENTER:
                self._power_origin = self.checkkey
                self._power_origin_epoch = self.pd.state.epoch
                self._power_confirm_yes = True
                self._power_focus = False
                self.checkkey = self.PowerConfirm
                self._draw_power_confirmation()
            return True
        if event == self.ENCODER_DIFF_CCW and self._power_at_first_item():
            self._power_focus = True
            self._draw_power_icon(True, clear=True)
            return True
        return False

    def _dispatch_input(self):
        feedback = getattr(self, '_action_feedback', None)
        if feedback is not None:
            if feedback.phase == 'error' and self.get_encoder_state() == self.ENCODER_DIFF_ENTER:
                self._action_feedback = None
                self._restore_action_screen()
            return
        if getattr(self, '_pending_start', None):
            return
        if getattr(self, '_start_error_visible', False):
            if self.get_encoder_state() == self.ENCODER_DIFF_ENTER:
                self._start_error_visible = False
                self.Goto_MainMenu()
                self.lcd.update()
            return
        if getattr(self, '_print_error_visible', False):
            if self.get_encoder_state() == self.ENCODER_DIFF_ENTER:
                self._acknowledged_terminal = self._terminal_key()
                self._print_error_visible = False
                self.Goto_MainMenu()
                self.lcd.update()
            return
        if self._handle_power_navigation():
            return
        if self.checkkey == self.MainMenu:
            self.HMI_MainMenu()
        elif self.checkkey == self.SelectFile:
            self.HMI_SelectFile()
        elif self.checkkey == self.Prepare:
            self.HMI_Prepare()
        elif self.checkkey == self.Control:
            self.HMI_Control()
        elif self.checkkey == self.PrintProcess:
            self.HMI_Printing()
        elif self.checkkey == self.Print_window:
            self.HMI_PauseOrStop()
        elif self.checkkey == self.AxisMove:
            self.HMI_AxisMove()
        elif self.checkkey == self.TemperatureID:
            self.HMI_Temperature()
        elif self.checkkey == self.Motion:
            self.HMI_Motion()
        elif self.checkkey in (self.ScrewsTiltMenu, self.ScrewsTiltResult):
            self.HMI_Screws_Tilt()
        elif self.checkkey == self.FilePreview:
            self.HMI_File_Preview()
        elif self.checkkey == self.MMUMenu:
            self.HMI_MMU_Menu()
        elif self.checkkey == self.BedMeshMenu:
            self.HMI_Bed_Mesh_Menu()
        elif self.checkkey == self.BedMeshScreen:
            self.HMI_Bed_Mesh()
        elif self.checkkey == self.MeshProfiles:
            self.HMI_Mesh_Profiles()
        elif self.checkkey == self.ProbeWizardID:
            self.HMI_Probe_Wizard()
        elif self.checkkey == self.MotionValue:
            self.HMI_MotionValue()
        elif self.checkkey == self.Info:
            self.HMI_Info()
        elif self.checkkey == self.Tune:
            self.HMI_Tune()
        elif self.checkkey == self.PLAPreheat:
            self.HMI_PLAPreheatSetting()
        elif self.checkkey == self.ABSPreheat:
            self.HMI_ABSPreheatSetting()
        elif self.checkkey == self.Move_X:
            self.HMI_Move_X()
        elif self.checkkey == self.Move_Y:
            self.HMI_Move_Y()
        elif self.checkkey == self.Move_Z:
            self.HMI_Move_Z()
        elif self.checkkey == self.Extruder:
            self.HMI_Move_E()
        elif self.checkkey == self.ETemp:
            self.HMI_ETemp()
        elif self.checkkey == self.Homeoffset:
            self.HMI_Zoffset()
        elif self.checkkey == self.BedTemp:
            self.HMI_BedTemp()
        elif self.checkkey == self.FanSpeed:
            self.HMI_FanSpeed()
        elif self.checkkey == self.PrintSpeed:
            self.HMI_PrintSpeed()
        elif self.checkkey == self.CaseLight:
            self.HMI_Case_Light()
        elif self.checkkey == self.CaseLightBrightness:
            self.HMI_Case_Light_Brightness()

    def get_encoder_state(self):
        # Input is an immutable queued event, not a sample of current GPIO levels.
        return self._encoder_event

    def HMI_AudioFeedback(self, success=True):
        if (success):
            self.pd.buzzer.tone(100, 659)
            self.pd.buzzer.tone(10, 0)
            self.pd.buzzer.tone(100, 698)
        else:
            self.pd.buzzer.tone(40, 440)
