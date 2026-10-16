from lcd_resources import ICON_ACCELERATION, ICON_BRIGHTNESS, ICON_BUZZER, ICON_CLICK_TONE, ICON_CORNER_SPEED, ICON_CRUISE_RATIO, ICON_DIM_BRIGHTNESS, ICON_ENCODER_TONE, ICON_FLOW, ICON_IDLE_DIM, ICON_LIGHT, ICON_LIVE_JOG, ICON_MOTION, ICON_MOTOR_OFF, ICON_PREHEAT_PROFILE, ICON_VELOCITY, ICON_VOLUME
from graphite_theme import show_icon as show_theme_icon
from lcd_resources import ICON_POWER_BUTTON_NORMAL, ICON_POWER_BUTTON_CANCEL, ICON_POWER_BUTTON_OFF
from lcd_resources import ICON_INFO_UPDATE_SELECTED, ICON_INFO_UPDATE_NORMAL
from lcd_resources import ICON_FAN_FIRST, ICON_FAN_LAST, ICON_LIBRARY_ID, ICON_CHECKBOX_EMPTY, ICON_CHECKBOX_CHECKED
import display_settings
import copy
import textwrap
from software_update import SoftwareUpdate
from info_qr import PROJECT_URL, draw_project_qr, extra_info_rows
from shared_artwork import PICTURE_ID as SHARED_PICTURE_ID
from system_info import wifi_signal_text
import time
import logging
from concurrent.futures import Future
from command_feedback import CommandFeedback
from threading import Lock
from ui_events import UIEventLoop, InputEvent
from ui_case_light import CaseLightMixin
from ui_maintenance import MaintenanceViewMixin
from ui_power import PowerShortcutMixin
from ui_mmu import MMUViewMixin
from ui_buzzer import BuzzerViewMixin
import buzzer_control
from buzzer_control import Settings as BuzzerSettings
from ui_screws_tilt import ScrewsTiltMixin
from ui_bed_mesh import BedMeshMixin
from ui_file_preview import FilePreviewMixin
from ui_print_focus import PrintFocusMixin
from power_lifecycle import PowerMonitor
from uart_startup import PanelProbe

from encoder import Encoder
from gpiozero import Button, Device
from gpiozero.pins.lgpio import LGPIOFactory
from printerInterface import PrinterData
from t5uic1_driver import T5UIC1Display, T5UIC1ProtocolError
from lcd_resources import ICON_FOLDER, ICON_MCU, ICON_MACHINE, ICON_HOST, ICON_SOFTWARE, ICON_POWER, ICON_DISPLAY_NORMAL, ICON_DISPLAY_SELECTED, ICON_MMU_HOME_NORMAL, ICON_MMU_HOME_SELECTED

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
            self.now = max(0,self.now-getattr(self,"batch_steps",1))
        return self.changed()

    def inc(self, v):
        if (self.now < (v - 1)):
            self.now = min(v-1,self.now+getattr(self,"batch_steps",1))
        else:
            self.now = (v - 1)
        return self.changed()


class PetrelDisplay(PrintFocusMixin, PowerShortcutMixin, BuzzerViewMixin, MMUViewMixin, CaseLightMixin, MaintenanceViewMixin, ScrewsTiltMixin, BedMeshMixin, FilePreviewMixin):

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
    DisplayMenu = 47
    MaintenanceMenu = 48
    BuzzerMenu = 49

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
    ICON = ICON_LIBRARY_ID

    ICON_LOGO = 0
    ICON_MMU_0 = ICON_MMU_HOME_NORMAL
    ICON_MMU_1 = ICON_MMU_HOME_SELECTED
    ICON_Display_0 = ICON_DISPLAY_NORMAL
    ICON_Display_1 = ICON_DISPLAY_SELECTED
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
    ICON_CloseMotor = ICON_MOTOR_OFF
    ICON_Homing = 29
    ICON_SetHome = 30
    ICON_PLAPreheat = ICON_PREHEAT_PROFILE
    ICON_ABSPreheat = 32
    ICON_Cool = 33
    ICON_Language = 34

    ICON_MoveX = 35
    ICON_MoveY = 36
    ICON_MoveZ = 37
    ICON_Extruder = 38

    ICON_Temperature = 40
    ICON_Motion = ICON_MOTION
    ICON_WriteEEPROM = 42
    ICON_ReadEEPROM = 43
    ICON_ResumeEEPROM = 44
    ICON_Info = 45
    ICON_CaseLight = ICON_LIGHT

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
    ICON_StepE = ICON_FLOW
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
    ICON_Maintenance_0 = 90
    ICON_Maintenance_1 = 91
    ICON_Info_0 = 92
    ICON_Info_1 = 93

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
                 power_device='Printer', power_on_hold_ms=2000,
                 emulator=False, emulator_socket=None, screenshot_directory=None, emulator_font=None,
                 remote=False, remote_port=8088):
        self._closed = False
        self._uart_epoch = 0
        self._uart_online = False
        self._next_uart_retry = 0
        self._next_uart_probe = 0
        self._panel_probe = None
        self._uart_fast_until = 0
        self._uart_start_signal = None
        self._uart_probe_failures = 0
        self._boot_active = True
        self._boot_files_started = (None, 0)
        self._boot_progress = -1
        self.encoder = self.button = self.lcd = self.pd = None
        self._emulator_options = (bool(emulator or remote), emulator_socket, screenshot_directory, emulator_font)
        self._remote_options = (bool(remote), remote_port)
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
                                 self._ui_tick, self._close_resources, interval=.5)
        self._loop.start()

    def _initialize(self):
        enabled, socket_path, output, font = self._emulator_options
        if enabled:
            from dwin_emulator.runtime import Emulator, ScreenshotServer
            self._emulator = Emulator(enabled=True, font_path=font)
            self._screenshot_server = ScreenshotServer(self._emulator, socket_path, output)
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
        self._power_monitor = PowerMonitor(self.pd.client, self.pd.power_device)
        self._relay_status = None
        self._relay_off_serial = 0
        self._panel_backend_epoch = self.pd.subscription.snapshot()['epoch']
        self._configure_menus()
        self._offline = bool(self.pd.connection_error)
        self._poll_panel_power()
        self._ensure_uart()
        # Enable producers only after all UI/backend resources are initialized.
        with self._input_lock:
            self._producer_value = self.encoder.getValue()
            self.encoder.callback = self.encoder_has_data
        self.button.when_pressed = self._button_pressed
        self.button.when_released = self._button_released
        self.button.when_held = self._button_held
        if self._remote_options[0]:
            from dwin_emulator.remote import RemoteDisplayServer
            self._remote_display = RemoteDisplayServer(
                self._emulator, self._remote_input, port=self._remote_options[1])

    def _uart_failed(self):
        self._power_hold_started = None
        if getattr(self, '_boot_active', False):
            self._boot_progress = -1
        if (getattr(self, 'checkkey', None) == self.PowerConfirm
                and getattr(self, '_power_origin', None) == self.MMUMenu):
            self.checkkey = self.MMUMenu
            self._power_origin = None
        if getattr(self, 'checkkey', None) in (self.MMUMenu, self.Tune, self.TuneEdit, self.PrintErrorDetails):
            self._power_focus = False
            self._mmu_canvas_page = None
        self._uart_online = False
        self._uart_epoch += 1
        now = time.monotonic()
        self._next_uart_retry = now + (.15 if now < getattr(self, '_uart_fast_until', 0) else 5)
        self._next_uart_probe = 0
        self._uart_probe_failures = 0
        if self.lcd is not None:
            self.lcd.close()
        self.lcd = None
        probe = getattr(self, '_panel_probe', None)
        if probe is not None:
            probe.close()
            self._panel_probe = None
        logging.warning('LCD UART unavailable; reconnect scheduled')

    def _reset_power_ui(self):
        """A relay cycle starts a new UI session; never replay old input/actions."""
        self.checkkey = self.MainMenu
        self._boot_active = True
        self._boot_files_started = (None, 0)
        self._boot_progress = -1
        for name in self.SELECTIONS:
            selection = getattr(self, name, None)
            if selection is not None:
                selection.reset()
        self._power_focus = False
        self._power_origin = None
        self._info_scroll = 0
        self._case_light_live_pending = None
        self._case_light_live_refresh = False
        self._case_light_live_epoch = None
        self._case_light_live_future = None
        self._display_selection = 0
        self._display_edit = False
        self._display_save_message = ''
        if hasattr(self, '_display_saved'):
            self._display_values = list(self._display_saved)
        self._mmu_canvas_page = None
        self._mmu_edit = None
        self._mmu_confirmation = None
        self._mmu_map_draft = None
        self._mmu_endless_draft = None
        self._mmu_spool_draft = None
        self._action_feedback = None
        self._stop_waiting = False
        self._pending_start = None
        self._start_error_visible = False
        self._acknowledged_terminal = None
        self.index_prepare = self.index_tune = self.index_control = self.MROWS
        self._live_jog_pending = None
        self._live_jog_future = None
        self._encoder_event = self.ENCODER_DIFF_NO
        self.last_status = None
        self.last_cardpercentValue = 101
        self.next_rts_update_ms = 0

    def _ui_lifecycle(self):
        reader = getattr(self.pd.subscription, 'lifecycle', None)
        if callable(reader):
            value = reader()
            if isinstance(value, dict) and 'epoch' in value:
                return value
        # Test doubles and legacy subscriptions retain their normal snapshot.
        return self.pd.subscription.snapshot()

    def _poll_panel_power(self):
        monitor = getattr(self, '_power_monitor', None)
        if monitor is None:
            return
        status = monitor.poll()
        snapshot = self._ui_lifecycle()
        device = self.pd.power_device.casefold()
        notified = snapshot.get('power_devices', {}).get(device)
        if monitor.available is False:
            notified = None
        serial = snapshot.get('power_off_serial', {}).get(device, 0)
        if (notified in ('on', 'off') and
                (notified != getattr(self, '_power_notification', None)
                 or serial != self._relay_off_serial)):
            status = notified
            monitor.status = notified
            self._power_notification = notified
        epoch = snapshot['epoch']
        event_cycle = serial != self._relay_off_serial
        transition = (status in ('on', 'off') and status != self._relay_status
                      and (status == 'off' or self._relay_status is not None))
        # Klipper's epoch covers cycles missed while its WebSocket was down.
        backend_cycle = (snapshot['state'] == 'ready' and epoch != self._panel_backend_epoch
                         and not getattr(self, '_boot_active', False))
        if event_cycle or transition or backend_cycle:
            probe = getattr(self, '_panel_probe', None)
            if probe is not None:
                probe.close()
                self._panel_probe = None
            self._reset_power_ui()
            if self.lcd is not None:
                self.lcd.close()
                self.lcd = None
            self._uart_online = False
            self._uart_epoch += 1
            self._next_uart_retry = 0
            self._uart_probe_failures = 0
            logging.info('Printer power/session changed; starting fresh panel session')
        self._relay_off_serial = serial
        if status in ('on', 'off'):
            self._relay_status = status
        if snapshot['state'] == 'ready':
            self._panel_backend_epoch = epoch
        if hasattr(self, '_uart_start_signal'):
            available = True if notified in ('on', 'off') else monitor.available
            signal = (('power', serial) if available is True and status == 'on' else
                      ('backend', epoch) if available is False and snapshot['state'] == 'ready' else None)
            if signal != self._uart_start_signal:
                self._uart_start_signal = signal
                if signal is not None and not self._uart_online:
                    self._uart_fast_until = time.monotonic() + 10
                    self._next_uart_retry = 0
                    if hasattr(self, '_loop'):
                        self._loop.set_interval(.05)
                    probe = getattr(self, '_panel_probe', None)
                    if probe is not None:
                        probe.accelerate()

    def _ensure_uart(self):
        if getattr(self, '_relay_status', None) == 'off':
            return False
        if self._uart_online:
            return True
        if self._closed or time.monotonic() < self._next_uart_retry:
            return False
        try:
            options = {}
            if hasattr(self, '_panel_probe'):
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.05)
                if self._panel_probe is None:
                    self._panel_probe = PanelProbe(self._settings[0])
                    if time.monotonic() < self._uart_fast_until:
                        self._panel_probe.accelerate()
                port = self._panel_probe.poll()
                if port is None:
                    return False
                self._panel_probe.close()
                self._panel_probe = None
                options['connected_serial'] = port
            if getattr(self, '_emulator', None) is not None:
                options['packet_observer'] = self._emulator
            if getattr(self, '_boot_active', False):
                options['startup_progress'] = lambda lcd, value: self._draw_boot_progress(value, lcd)
            self.lcd = T5UIC1Display(self._settings[0], handshake_timeout=1.0,
                                 handshake_attempts=1, **options)
            async_flash = (getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH',
                                   None) is True)
            if async_flash:
                # Do not hold the UI owner during Flash reads. The defaults
                # remain usable until the verified panel records arrive.
                if not hasattr(self, '_display_values'):
                    self._display_values = [100, 0, 10]
                    self._display_saved = (100, 0, 10)
                if not hasattr(self, '_buzzer_values'):
                    self._buzzer_values = self._buzzer_saved = BuzzerSettings()
                self._panel_flash_lcd = self.lcd
                if not getattr(self, '_display_load_complete', False):
                    self._display_load_future = self.lcd.begin_flash_read(
                        self.lcd.DISPLAY_SETTINGS_ADDRESS,
                        self.lcd.DISPLAY_SETTINGS_SIZE)
                if not getattr(self, '_buzzer_load_complete', False):
                    self._buzzer_load_future = self.lcd.begin_flash_read(
                        buzzer_control.ADDRESS, buzzer_control.RECORD_SIZE)
                if getattr(self, '_display_save_future', None) is not None:
                    self._display_save_future = None
                    self._display_save_message = 'Not saved. Press to retry'
                if getattr(self, '_buzzer_save_future', None) is not None:
                    self._buzzer_save_future = None
                    self._buzzer_save_error = True
            else:
                if not hasattr(self, '_display_values'):
                    try:
                        values = self.lcd.load_display_settings()
                    except (OSError, TimeoutError, T5UIC1ProtocolError):
                        logging.warning('Unable to read display settings', exc_info=True)
                        values = None
                    if isinstance(values, tuple) and len(values) == 2:
                        values = values + (10,)
                    if not isinstance(values, tuple) or len(values) != 3:
                        values = None
                    self._display_values = list(values or (100, 0, 10))
                    self._display_saved = tuple(values or (100, 0, 10))
                if not hasattr(self, '_buzzer_values'):
                    try:
                        values = self.lcd.load_buzzer_settings()
                    except (OSError, TimeoutError, T5UIC1ProtocolError):
                        logging.warning('Buzzer settings unavailable; sounds disabled')
                        values = None
                    self._buzzer_values = values if isinstance(values, BuzzerSettings) else BuzzerSettings()
                    self._buzzer_saved = self._buzzer_values
            self._display_last_activity = time.monotonic()
            self._display_dimmed = False
            self.lcd.set_backlight(display_settings.raw_brightness(self._display_values[0]))
            self._configure_menus()
            if getattr(self, '_boot_active', False):
                self._draw_boot_progress(70)
            else:
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
            elif getattr(self, 'checkkey', None) == self.Tune:
                self.Draw_Tune_Menu()
            elif getattr(self, 'checkkey', None) == self.TuneEdit:
                self._focus_edit_draw()
            elif getattr(self, 'checkkey', None) == self.PrintErrorDetails:
                self._focus_error_draw()
            if getattr(self, 'checkkey', None) == self.FilePreview:
                self.Draw_File_Preview()
            if getattr(self, 'checkkey', None) == self.DisplayMenu:
                self.Draw_Display_Menu()
            if getattr(self, 'checkkey', None) == self.MaintenanceMenu:
                self.Draw_Maintenance_Menu()
            if getattr(self, 'checkkey', None) == self.BuzzerMenu:
                self.Draw_Buzzer_Menu()
            self.lcd.update()
            if (self.pd.connection_error and self.checkkey != self.MMUMenu
                    and not getattr(self, '_boot_active', False)):
                self._show_message('Moonraker unavailable')
            self._uart_online = True
            if hasattr(self, '_loop'):
                self._loop.set_interval(.5)
            self._uart_epoch += 1
            self._uart_probe_failures = 0
            self._next_uart_probe = time.monotonic() + 2.0
            if getattr(self, '_boot_active', False):
                self._poll_boot()
            logging.info('LCD UART connected; %s', 'boot readiness pending'
                         if getattr(self, '_boot_active', False) else 'current screen restored')
            return True
        except (OSError, TimeoutError):
            self._uart_failed()
            return False

    def _draw_progress_track(self, lcd, x, y, width, value):
        # Text-free managed caps work on panels without opcode 0x08.
        from lcd_resources import ICON_PROGRESS_TRACK, ICON_PROGRESS_FILL
        def capsule(length, color, icon):
            length = min(width, max(8, length))
            show_theme_icon(lcd, self.ICON, icon, x, y)
            if length > 8:
                show_theme_icon(lcd, self.ICON, icon, x + length - 8, y)
                lcd.draw_rectangle(1, color, x + 4, y, x + length - 5, y + 7)
        capsule(width, 0x39C8, ICON_PROGRESS_TRACK)
        filled = max(0, min(width, round(width * value / 100)))
        if filled:
            capsule(filled, 0x063B, ICON_PROGRESS_FILL)

    def _draw_boot_progress(self, value, lcd=None, message=None):
        lcd = self.lcd if lcd is None else lcd
        message = message or {40: 'Preparing display assets', 70: 'Waiting for printer...',
                              80: 'Reading printer status', 90: 'Preparing menus',
                              100: 'Starting interface'}.get(value, 'Starting display')
        message = message[:27]
        value = max(getattr(self, '_boot_progress', -1), min(100, value))
        if (value == getattr(self, '_boot_progress', -1)
                and message == getattr(self, '_boot_message', None)
                and lcd is getattr(self, '_boot_animation_lcd', None)):
            return
        if lcd is getattr(self, '_boot_animation_lcd', None) and getattr(self, '_boot_animation_running', False):
            lcd.configure_animation(0, False, getattr(self, '_boot_animation_active_library', self.ICON), 250, 254, self._boot_animation_x, 320, 10)
        self._boot_progress, self._boot_message = value, message
        # Restore original splash pixels; no solid-color patches over the artwork.
        lcd.copy_cache(0, 16, 284, 255, 344, 16, 284, background=True, enhanced=False)
        self._draw_progress_track(lcd, 24, 292, 224, value)
        x = (272 - (len(message)*8 + 24)) // 2
        lcd.draw_text(False, False, lcd.font8x16, 0xE75E, 0,
                      x+24, 322, message)
        library = getattr(lcd, '_boot_animation_library', self.ICON)
        self._boot_animation_running = value < 100 and library is not None
        if self._boot_animation_running:
            lcd.configure_animation(0, True, library, 250, 254, x, 320, 10)
        self._boot_animation_active_library = library
        self._boot_animation_x, self._boot_animation_lcd = x, lcd
        lcd.update()

    def _poll_boot(self):
        snapshot = self.pd.subscription.snapshot()
        if snapshot['state'] != 'ready':
            self.pd.update_variable()
            self._draw_boot_progress(70)
            return
        self._draw_boot_progress(80)
        self.pd.update_variable()
        snapshot = self.pd.subscription.snapshot()
        if (snapshot['state'] != 'ready' or self.pd.connection_error
                or not self.pd.state.ready or self.pd.state.epoch != snapshot['epoch']):
            self._draw_boot_progress(80, message='Waiting for printer data')
            return
        self.pd.prefetch_files()
        epoch, started = getattr(self, '_boot_files_started', (None, 0))
        if epoch != snapshot['epoch']:
            started = time.monotonic()
            self._boot_files_started = (snapshot['epoch'], started)
        if ((self.pd._files_loading is True or self.pd._directory_loading is True)
                and time.monotonic() - started < 5.0):
            self._draw_boot_progress(90, message='Preparing file list')
            return
        self._draw_boot_progress(90)
        self._configure_menus()
        self.pd.mmu_session.update()
        self._draw_boot_progress(100)
        self._boot_active = False
        self._uart_epoch += 1
        self._offline = False
        self._panel_backend_epoch = snapshot['epoch']
        self.HMI_StartFrame(False)
        self._display_last_activity = time.monotonic()
        self.lcd.update()

    def _poll_panel_flash(self):
        """Collect completed Flash futures on the same UART-owning UI thread."""
        if getattr(self, '_panel_flash_lcd', None) is not self.lcd:
            return
        changed = False
        for kind in ('display_load', 'buzzer_load', 'display_save', 'buzzer_save'):
            attr = '_' + kind + '_future'
            future = getattr(self, attr, None)
            if future is None or not future.done():
                continue
            setattr(self, attr, None)
            try:
                raw = future.result()
                if kind == 'display_load':
                    values = display_settings.decode(raw)
                    if isinstance(values, tuple) and len(values) == 2:
                        values = values + (10,)
                    if isinstance(values, tuple) and len(values) == 3:
                        old = self._display_saved
                        if (tuple(self._display_values) == old
                                and not getattr(self, '_display_edit', False)
                                and getattr(self, '_display_save_future', None) is None):
                            self._display_values = list(values)
                            if not getattr(self, '_display_dimmed', False):
                                self.lcd.set_backlight(display_settings.raw_brightness(values[0]))
                        self._display_saved = values
                    self._display_load_complete = True
                elif kind == 'buzzer_load':
                    settings = BuzzerSettings.decode(raw)
                    if isinstance(settings, BuzzerSettings):
                        if (self._buzzer_values == self._buzzer_saved
                                and getattr(self, '_buzzer_save_future', None) is None):
                            self._buzzer_values = settings
                        self._buzzer_saved = settings
                    self._buzzer_load_complete = True
                elif kind == 'display_save':
                    self._display_saved = self._display_save_target
                    self._display_edit = False
                    self._display_save_message = ''
                else:
                    self._buzzer_saved = self._buzzer_save_target
                    self._buzzer_save_error = False
                    self._display_save_message = ''
            except Exception as error:
                if kind == 'display_save':
                    self._display_edit = True
                    self._display_save_message = 'Not saved. Press to retry'
                elif kind == 'buzzer_save':
                    self._buzzer_save_error = True
                    self._display_save_message = 'Not saved. Press to retry'
                else:
                    logging.warning('Could not read panel %s: %s', kind, error)
            changed = True
        if changed:
            if getattr(self, 'checkkey', None) == self.DisplayMenu:
                self.Draw_Display_Menu()
                self.lcd.update()
            elif getattr(self, 'checkkey', None) == self.BuzzerMenu:
                self.Draw_Buzzer_Menu()
                self.lcd.update()

    def _ui_tick(self):
        self._poll_panel_power()
        self._sync_case_light_tracking()
        if not self._uart_online:
            # Keep status current while the panel is disconnected.
            self.pd.update_variable()
            self.pd.bed_mesh.update()
            self.pd.mmu_session.update()
            self._ensure_uart()
            return
        try:
            if getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True:
                self.lcd.poll_flash_tasks()
                self._poll_panel_flash()
                if self.lcd.flash_busy() and hasattr(self, '_loop'):
                    self._loop.set_interval(.05)
            if self._power_hold_tick():
                return
            now = time.monotonic()
            incremental_probe = (getattr(self.lcd,
                                          'SUPPORTS_NONBLOCKING_LIVENESS', None) is True)
            if now >= getattr(self, '_next_uart_probe', 0):
                self._next_uart_probe = now + 2.0
                if incremental_probe:
                    self.lcd.begin_liveness_probe(timeout=0.5)
                else:
                    result = self.lcd.handshake(timeout=0.5)
                    if result:
                        self._uart_probe_failures = 0
                    else:
                        self._uart_probe_failures = getattr(self, '_uart_probe_failures', 0) + 1
            if incremental_probe:
                result = self.lcd.poll_liveness_probe()
                if result is True:
                    self._uart_probe_failures = 0
                elif result is False:
                    self._uart_probe_failures = getattr(self, '_uart_probe_failures', 0) + 1
            if getattr(self, '_uart_probe_failures', 0):
                if self._uart_probe_failures >= 2:
                    logging.warning('LCD liveness lost; reconnecting')
                    self._uart_failed()
                    return
            if self._power_popup_tick():
                return
            if getattr(self, '_boot_active', False):
                self._poll_boot()
                return
            if (getattr(self, 'checkkey', None) == self.MMUMenu
                    and getattr(self, '_mmu_page', None) == 'home'):
                view = getattr(self, '_mmu_filament_view', None)
                state = getattr(self, '_mmu_animation_state', None)
                animating = bool(view is not None and state is not None
                                 and view.animating(state, now))
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.05 if animating else .5)
                if now < getattr(self, '_mmu_status_at', 0):
                    if animating:
                        self._mmu_animation_tick()
                    return
                self._mmu_status_at = now + .5
            elif getattr(self, 'checkkey', None) == self.FilePreview:
                if not getattr(self, '_pending_start', None) and not getattr(self, '_start_error_visible', False):
                    self._poll_file_preview()
                if time.monotonic() < getattr(self, '_preview_status_at', 0):
                    return
                self._preview_status_at = time.monotonic() + .5
            elif getattr(self, 'checkkey', None) == self.SelectFile:
                self._poll_thumbnail_preload()
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.02 if self._thumbnail_cache.has_work() else .5)
                if time.monotonic() < getattr(self, '_file_status_at', 0):
                    return
                self._file_status_at = time.monotonic() + .5
            elif hasattr(self, '_loop'):
                blink = bool(getattr(self, '_quiet_blinks', {}))
                loading = self.checkkey == self.PrintProcess and hasattr(self, '_thumbnail_cache') and self._thumbnail_cache.has_work()
                self._loop.set_interval(.1 if blink else (.05 if loading else .5))
            if getattr(self, '_mesh_pending_points', None) is not None:
                if self.checkkey == self.BedMeshScreen:
                    if hasattr(self, '_loop'):
                        self._loop.set_interval(.02)
                    self._advance_mesh_render()
                else:
                    self._mesh_pending_points = None
            if incremental_probe and getattr(self.lcd, '_liveness_deadline', None) is not None:
                if hasattr(self, '_loop'):
                    self._loop.set_interval(.05)
            self._display_idle_tick()
            if self._draw_header_clock():
                self.lcd.update()
            self.EachMomentUpdate()
        except OSError:
            if self.lcd is not None and getattr(self.lcd, '_closed', False):
                self._uart_failed()
            else:
                raise

    def _action(self, label, callback, expected=None, confirmation_timeout=300.0,
                on_accept=None, silent=False):
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
            self._action_silent = silent
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
        silent = getattr(self, '_action_silent', False)
        phase = feedback.update(self.pd.state, bool(self.pd.connection_error))
        if phase == 'accepted':
            self._stop_waiting = False
            self._action_feedback = None
            on_accept = getattr(self, '_action_on_accept', None)
            self._action_on_accept = None
            if on_accept is not None:
                on_accept()
            if not silent:
                self.HMI_AudioFeedback(True)
                self._restore_action_screen()
            self._action_silent = False
            return False
        if phase == 'waiting' and silent:
            return False
        if phase == 'error':
            self._stop_waiting = False
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
        self._menus['preheat'].append(('CANCEL', 'Discard changes', self.ICON_Back))
        if heat or self.pd.HAS_FAN:
            self._menus['control'].append(('TEMP', 'Temperature', self.ICON_Temperature))
        self._menus['control'].append(('MOVE', 'Motion', self.ICON_Motion))
        if recovery:
            self._menus['control'].append(('RECOVERY', 'Restore jog state', self.ICON_Homing))
        if caps.case_light:
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
        # Coalesced detents have a single final menu position. Avoid drawing
        # each intermediate row/window on the UART owner thread.
        steps = max(1, int(getattr(self, '_menu_batch_steps', 1)))
        target = selection.now + (steps if event == self.ENCODER_DIFF_CW else -steps)
        target = max(0, min(len(self._menus[menu]), target))
        if target == selection.now:
            return True
        selection.set(target)
        bottom = getattr(self, index_name, self.MROWS)
        if selection.now > bottom:
            bottom = selection.now
        elif selection.now < bottom - self.MROWS:
            bottom = selection.now + self.MROWS
        setattr(self, index_name, max(self.MROWS, bottom))
        draw()
        self.lcd.update()
        return True

    def _menu_checkbox_painter(self, checked):
        def draw(row):
            x, y = 232, self.MBASE(row) - 3
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, x, y, x + 19, y + 19)
            show_theme_icon(self.lcd, self.ICON,
                ICON_CHECKBOX_CHECKED if checked else ICON_CHECKBOX_EMPTY, x, y)
        draw.checkbox = True
        return draw

    def _draw_list_menu(self, title, entries, selection, start=None):
        # Entries: label, icon, displayed value signature, optional row painter.
        frame = (id(self.lcd), title, tuple((e[0], e[1]) for e in entries))
        old = getattr(self, '_list_render', None)
        valid = old is not None and old['frame'] == frame
        if start is None:
            start = old['start'] if valid else 0
            start = max(0, min(start, selection), selection - self.MROWS)
        visible = range(start, min(len(entries), start + self.TROWS))
        previous_values = old['values'] if valid else {}
        delta = start - old['start'] if valid else 0
        if not valid or abs(delta) >= self.TROWS:
            self.Clear_Main_Window()
            self.Draw_Title(title)
            previous_values = {}
        elif old['selection'] != selection or delta:
            self.Erase_Menu_Cursor(old['selection'] - old['start'])
            if delta:
                self.lcd.move_area(1,
                    self.DWIN_SCROLL_UP if delta > 0 else self.DWIN_SCROLL_DOWN,
                    abs(delta) * self.MLINE, self.lcd.Color_Bg_Black,
                    0, 31, 271, 348)
        values = {}
        for logical in visible:
            label, icon, value, painter = entries[logical]
            row = logical - start
            values[logical] = value
            preserved = valid and logical in range(old['start'], old['start'] + self.TROWS)
            if not preserved or logical not in previous_values or previous_values[logical] != value:
                checkbox_only = (preserved and logical in previous_values
                                 and getattr(painter, 'checkbox', False))
                if not checkbox_only:
                    self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                        16, 31 + row * self.MLINE, 271, 83 + row * self.MLINE)
                    if icon or label:
                        self.Draw_Menu_Line(row, icon, label)
                if painter is not None:
                    painter(row)
        if not valid or delta or old['selection'] != selection:
            self.Draw_Menu_Cursor(selection - start)
        self._list_render = dict(frame=frame, start=start, selection=selection, values=values)

    def _draw_capability_menu(self, name, selection, bottom=None, profile=None):
        title = name.title() if profile is None else self.pd.material_preset[profile].name + ' settings'
        entries = [('Back', self.ICON_Back, None, None)]
        preset = self.pd.material_preset[profile] if profile is not None else None
        for key, label, icon in self._menus[name]:
            value, painter = None, None
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
                    value = self.pd.BABY_Z_VAR * 100
                    painter = lambda row, v=value: self.lcd.draw_signed_scaled_float_text(
                        self.lcd.font8x16, self.lcd.Color_Bg_Black, 2, 2, 202, self.MBASE(row), v)
                if value is not None and painter is None:
                    painter = lambda row, v=value: self.lcd.draw_integer_text(
                        True, True, 0, self.lcd.font8x16, self.lcd.Color_White,
                        self.lcd.Color_Bg_Black, 3, 216, self.MBASE(row), v)
            entries.append((label, icon, value, painter))
        self._draw_list_menu(title, entries, selection.now, max(0, (bottom or self.MROWS) - self.MROWS))

    def _invalidate_list_row(self, row):
        """A direct editor write replaces the normal cached viewport row."""
        render = getattr(self, '_list_render', None)
        if render is not None:
            render['values'].pop(row + render['start'], None)
        return row

    def _open_thermal_editor(self, key, row, profile=None):
        # Menu selections are logical indices; drawing uses viewport rows.
        render = getattr(self, '_list_render', None)
        self._thermal_edit_row = row - (render['start'] if render else 0)
        self._invalidate_list_row(self._thermal_edit_row)
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
                               3, 216, self.MBASE(self._thermal_edit_row), value)

    def lcdExit(self):
        self._loop.close()

    def wait(self):
        self._loop.wait()

    def _close_resources(self):
        if self._closed:
            return
        self._closed = True
        for resource in (getattr(self, '_remote_display', None),
                         getattr(self, '_buzzer_player', None),
                         getattr(self, '_screenshot_server', None),
                         getattr(self, '_emulator', None),
                         getattr(self, '_power_monitor', None), self.button, self.encoder, self.pd):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    logging.exception('LCD resource cleanup failed')
        if self.lcd is not None:
            self.lcd.close()
        probe = getattr(self, '_panel_probe', None)
        if probe is not None:
            probe.close()

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
            return False
        snapshot = self.pd.subscription.snapshot()
        if snapshot['state'] != 'ready' and getattr(self, 'checkkey', None) != self.MMUMenu:
            return False
        accepted = self._loop.post(InputEvent(
            kind, value, snapshot['epoch'], getattr(self, '_uart_epoch', 0),
            accelerated_value, rate))
        if not accepted:
            logging.warning('LCD input queue full or closed; input discarded')
        return accepted

    def _remote_input(self, kind, value):
        # The HTTP thread may ONLY post ordinary epoch-bound events. No GPIO
        # simulation, direct UI calls, long-press power, or Moonraker access.
        if kind == 'press' and value == 1:
            return self._enqueue_input('press', 1)
        if kind == 'rotate' and type(value) is int and 0 < abs(value) <= 6:
            return self._enqueue_input('rotate', value, value)
        return False

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
        if getattr(self, 'power_on_hold_ms', 2000) == 0 and getattr(self, '_relay_status', None) != 'on':
            self._request_power_on()
        self._power_button_down()

    def _request_power_on(self):
        # Power control must remain available while Klipper and/or the LCD UART are offline.
        if self.pd is None or self._closed:
            return
        if not self._loop.post(InputEvent('power_on', 1, 0, 0)):
            logging.warning('LCD input queue full or closed; power-on request discarded')

    def _button_held(self):
        if (getattr(self, 'power_on_hold_ms', 2000) > 0
                and not getattr(self, '_button_can_power_off', False)):
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
        if getattr(self, '_boot_active', False):
            return
        if (not getattr(self, '_uart_online', True)
                or event.ui_epoch != getattr(self, '_uart_epoch', 0)):
            return
        snapshot = self._ui_lifecycle()
        if ((snapshot['state'] != 'ready' and getattr(self, 'checkkey', None) != self.MMUMenu) or snapshot['epoch'] != event.epoch
                or self._closed):
            if event.kind == 'button_release' and getattr(self, '_power_hold_started', None) is not None:
                self._clear_power_hold()
                self.lcd.update()
            return
        if event.kind == 'case_light_status':
            self._poll_case_light_state()
            return
        if event.kind == 'case_light_flush':
            self._poll_case_light_live()
            return
        if event.kind == 'live_jog_flush':
            self._flush_live_jog()
            return
        if self._power_button_input(event):
            return
        if event.kind == 'rotate' and getattr(self, '_power_hold_started', None) is not None:
            return
        if event.kind == 'rotate':
            direction = self.ENCODER_DIFF_CCW if event.value > 0 else self.ENCODER_DIFF_CW
            count = abs(event.value)
        elif event.kind == 'press':
            direction, count = self.ENCODER_DIFF_ENTER, 1
        else:
            return
        if self._display_activity():
            return
        if not self._sync_input_state(event):
            return
        self._buzzer_feedback(event.kind)
        self._encoder_jog_rate = event.rate if event.kind == 'rotate' else 0.0
        acceleration_cap = self._encoder_acceleration_cap() if event.kind == 'rotate' else 1
        if event.kind == 'rotate' and getattr(self, 'checkkey', None) == self.CaseLightBrightness:
            # Apply coalesced physical detents once, without acceleration.
            self._encoder_move_value = count
            count = 1
        elif acceleration_cap > 1:
            count = 1
            raw_count = max(1, abs(event.value))
            accelerated_count = abs(event.accelerated_value or event.value)
            effective_multiplier = max(1, accelerated_count // raw_count)
            self._encoder_move_value = raw_count * min(acceleration_cap, effective_multiplier)
        else:
            self._encoder_move_value = 1
        self._rotation_steps = abs(event.value) if event.kind == 'rotate' else 1
        self._menu_batch_steps = self._rotation_steps
        if event.kind == 'rotate':
            if acceleration_cap == 1:
                self._encoder_move_value = self._rotation_steps
            count = 1  # One bounded handler invocation per physical input batch.
        for name in self.SELECTIONS:
            selection = getattr(self, name, None)
            if isinstance(selection, select_t):
                selection.batch_steps = self._rotation_steps
        lcd = getattr(self, 'lcd', None)
        if lcd is not None:
            lcd._defer_updates = True
        try:
            for _ in range(count):
                current = self._ui_lifecycle()
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
            self._menu_batch_steps = self._rotation_steps = 1
            for name in self.SELECTIONS:
                selection = getattr(self, name, None)
                if isinstance(selection, select_t): selection.batch_steps = 1
            if (lcd is not None and self.lcd is lcd
                    and not getattr(lcd, '_closed', False)):
                lcd._defer_updates = False
                lcd.update()
            self._sync_case_light_tracking()

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
            show_theme_icon(self.lcd, self.ICON, self.ICON_Bar, 15, 260)
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 15 + t * 242 / 100, 260, 257, 280)
            self.lcd.update()
            time.sleep(.020)

    def _present_print_state(self):
        status = self.pd.status
        self.last_status = status
        self._print_error_visible = False
        self.pd.HMI_flag.done_confirm_flag = False
        self.pd.HMI_flag.pause_flag = self.pd.printingIsPaused()
        if (self.checkkey == self.MMUMenu or
                (self.checkkey == self.PowerConfirm and getattr(self, '_power_origin', None) == self.MMUMenu)):
            return
        if status in ('printing', 'paused', 'pausing'):
            if self.checkkey == self.PrintProcess:
                self._focus_print_tick()
            elif self.checkkey not in (self.Tune, self.TuneEdit, self.PrintErrorDetails, self.Print_window):
                self.Goto_PrintProcess()
        elif status == 'complete':
            if getattr(self, '_acknowledged_terminal', None) == self._terminal_key():
                self.Goto_MainMenu()
                return
            self.Goto_PrintProcess()
            self.pd.HMI_flag.done_confirm_flag = True
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
        if len(self._leveling_menu_entries()) > 1:
            entries.append(('LEVEL', 'Leveling', self.ICON_Leveling_0, self.ICON_Leveling_1))
        entries.append(('MMU', 'MMU', self.ICON_MMU_0, self.ICON_MMU_1))
        entries.append(('DISPLAY', 'Display', self.ICON_Display_0, self.ICON_Display_1))
        entries.append(('MAINTENANCE', 'Maintenance', self.ICON_Maintenance_0, self.ICON_Maintenance_1))
        entries.append(('INFO', 'Info', self.ICON_Info_0, self.ICON_Info_1))
        return tuple(entries)

    def _draw_home_page(self, previous=None):
        entries = self._home_entries()
        self.select_page.set(min(self.select_page.now, len(entries)-1))
        page = self.select_page.now // 4
        partial = previous is not None and previous // 4 == page
        if not partial:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 126, 271, self.STATUS_Y-1)
        indices = (previous, self.select_page.now) if partial else range(
            page*4, min(len(entries), page*4+4))
        for index in indices:
            key, label, normal, selected = entries[index]
            slot = index % 4
            x, y = (17 if slot % 2 == 0 else 145), (130 if slot < 2 else 246)
            active = index == self.select_page.now
            if partial:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, x, y, x+109, y+99)
            show_theme_icon(self.lcd, self.ICON, selected if active else normal, x, y)
            # Demo selection is built into the rounded selected tile asset.
            self._draw_menu_text(label, x+(109-len(label)*8)//2, y+71)
        pages = (len(entries)+3)//4
        if pages > 1 and not partial:
            spacing = min(18, 256 // pages)
            first_x = 136 - (pages - 1) * spacing // 2
            for number in range(pages):
                draw = self.lcd.fill_circle if number == page else self.lcd.draw_circle
                draw(self.lcd.Color_White if number == page else 0x8410,
                     first_x + number * spacing, 354, 4)

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
            elif key == 'DISPLAY':
                self.checkkey = self.DisplayMenu
                self.Draw_Display_Menu()
            elif key == 'MAINTENANCE':
                # Discovery has already run at Klipper READY; this is only
                # an entry safety check, never a capability API request.
                from maintenance_session import idle
                if idle(self.pd.state):
                    self.checkkey = self.MaintenanceMenu
                    self.Draw_Maintenance_Menu()
            elif key == 'INFO':
                self._info_origin = self.MainMenu
                self.checkkey = self.Info
                self.Draw_Info_Menu()
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW) and previous != self.select_page.now:
            self._draw_home_page(previous)
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
            elif self.select_prepare.now == self.PREPARE_CASE_DISA:  # Disable steppers
                self._action("Disable steppers", lambda: self.pd.sendGCode("M84"), silent=True)
            elif self.select_prepare.now == self.PREPARE_CASE_HOME:  # Homing
                self.checkkey = self.Last_Prepare
                self.index_prepare = self.MROWS
                self.pd.current_position.homing()
                self.pd.HMI_flag.home_flag = True
                self.Popup_Window_Home()
                self._action("Home", lambda: self.pd.sendGCodeObserved("G28"),
                             self.pd.ishomed, confirmation_timeout=600, silent=True,
                             on_accept=self._restore_action_screen)
            elif self.select_prepare.now == self.PREPARE_CASE_ZOFF:  # Z-offset
                self._open_zoffset(-4, self.PREPARE_CASE_ZOFF + self.MROWS - self.index_prepare)

            elif self.select_prepare.now > 0 and self._menus['prepare'][self.select_prepare.now - 1][0].startswith('PRESET:'):
                profile = int(self._menus['prepare'][self.select_prepare.now - 1][0].split(':', 1)[1])
                name = self.pd.material_preset[profile].name
                self._action('Preheat ' + name, lambda profile=profile: self.pd.preheat_preset(profile), silent=True)

            elif self.select_prepare.now == self.PREPARE_CASE_COOL:  # Cool
                self._action('Cooldown', self.pd.cooldown, silent=True)

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
            if self.select_control.now == self.CONTROL_CASE_RECOVERY:
                self._action('Restore jog state', self.pd.restore_jog_state, silent=True)
            if self.select_control.now == self.CONTROL_CASE_LIGHT:
                self.checkkey = self.CaseLight
                self.select_light.reset()
                self._sync_case_light_tracking()
                self._poll_case_light_state(redraw=False)
                self.Draw_Case_Light_Menu()
            if (self.select_control.now == self.CONTROL_CASE_INFO):  # Info
                self._info_origin = self.Control
                self.checkkey = self.Info
                self.Draw_Info_Menu()

        self.lcd.update()

    def _display_activity(self):
        self._display_last_activity = time.monotonic()
        if getattr(self, '_display_dimmed', False):
            self._display_dimmed = False
            self.lcd.set_backlight(display_settings.raw_brightness(self._display_values[0]))
            return True  # First interaction wakes without activating a hidden action.
        return False

    def _display_idle_tick(self):
        values = getattr(self, '_display_values', None)
        if (values and values[1] and not getattr(self, '_display_dimmed', False)
                and time.monotonic() - self._display_last_activity >= values[1] * 60
                and not getattr(self, '_display_edit', False)):
            self.lcd.set_backlight(display_settings.raw_brightness(min(values[0], values[2])))
            self._display_dimmed = True

    def Draw_Display_Menu(self):
        selection = getattr(self, '_display_selection', 0)
        if selection >= 5 and not self._buzzer_enabled():
            self._display_selection = selection = 4
            self._display_edit = False
        values = getattr(self, '_display_values', [100, 0, 10])
        entries = [('Back', self.ICON_Back, None, None)]
        for row, label, icon, text in (
                (1, 'Brightness', ICON_BRIGHTNESS, str(values[0]) + '%'),
                (2, 'Idle dim', ICON_IDLE_DIM, str(values[1]) + ' min' if values[1] else 'Off'),
                (3, 'Dim brightness', ICON_DIM_BRIGHTNESS, str(values[2]) + '%')):
            editing = getattr(self, '_display_edit', False) and selection == row
            painter = lambda row, text=text, editing=editing: self.lcd.draw_text(
                True, False, self.lcd.font8x16, self.lcd.Color_White,
                self.lcd.Select_Color if editing else self.lcd.Color_Bg_Black,
                196, self.MBASE(row) - 1, text)
            entries.append((label, icon, (text, editing), painter))
        for row, (label, text, editable) in enumerate(self._buzzer_rows(), 4):
            text = text[:11]
            editing = getattr(self, '_display_edit', False) and selection == row
            painter = lambda row, text=text, editing=editing: self.lcd.draw_text(
                True, False, self.lcd.font8x16, self.lcd.Color_White,
                self.lcd.Select_Color if editing else self.lcd.Color_Bg_Black,
                max(172, 260 - len(text) * 8), self.MBASE(row) - 1, text)
            entries.append((label, {'Buzzer': ICON_BUZZER,'Volume': ICON_VOLUME,'Click tone': ICON_CLICK_TONE,'Encoder tone': ICON_ENCODER_TONE}[label], (text, editing), painter))
        self._display_selection = min(selection, len(entries) - 1)
        title = 'Display - not saved' if getattr(self, '_display_save_message', '') else 'Display'
        self._draw_list_menu(title, entries, self._display_selection)

    def HMI_Display_Menu(self):
        event = self.get_encoder_state()
        if (getattr(self, '_display_save_future', None) is not None
                or getattr(self, '_buzzer_save_future', None) is not None):
            # Do not accept another editor value while Flash ACK is pending.
            return
        if self._buzzer_display_input(event):
            return
        selection = getattr(self, '_display_selection', 0)
        editing = getattr(self, '_display_edit', False)
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            delta = getattr(self,"_rotation_steps",1)*(1 if event == self.ENCODER_DIFF_CW else -1)
            if editing:
                index = selection - 1
                self._display_values[index] = max(0, min(60 if index == 1 else 100,
                                                       self._display_values[index] + delta))
                if index == 0:
                    self.lcd.set_backlight(display_settings.raw_brightness(self._display_values[0]))
            else:
                self._display_selection = max(0, min(3 + len(self._buzzer_rows()), selection + delta))
            self._display_save_message = ''
        elif event == self.ENCODER_DIFF_ENTER:
            if selection == 0:
                self.select_page.set(next(i for i, entry in enumerate(self._home_entries())
                                          if entry[0] == 'DISPLAY'))
                self.Goto_MainMenu()
                self.lcd.update()
                return
            if editing:
                try:
                    values = tuple(self._display_values)
                    if values != self._display_saved:
                        if getattr(self.lcd, 'SUPPORTS_NONBLOCKING_FLASH', None) is True:
                            record = display_settings.encode(*values)
                            self._display_save_target = values
                            self._panel_flash_lcd = self.lcd
                            self._display_save_future = self.lcd.begin_flash_write_verified(
                                self.lcd.DISPLAY_SETTINGS_ADDRESS, record)
                            self._display_save_message = 'Saving...'
                        else:
                            self.lcd.save_display_settings(*values)
                            self._display_saved = values
                            self._display_edit = False
                            self._display_save_message = ''
                    else:
                        self._display_edit = False
                        self._display_save_message = ''
                except (OSError, TimeoutError, T5UIC1ProtocolError):
                    self._display_save_message = 'Not saved. Press to retry'
            else:
                self._display_edit = True
        else:
            return
        self.Draw_Display_Menu()
        self.lcd.update()

    def HMI_Info(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO:
            return
        items = self._info_items()
        max_scroll = max(0, len(items) + extra_info_rows() - 11)
        current = getattr(self, '_info_scroll', 0)
        if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
            self._software_updater().cancel_confirmation()
        if event == self.ENCODER_DIFF_CW:
            self._info_scroll = min(max_scroll, current + getattr(self,"_rotation_steps",1))
            if self._info_scroll == current:
                return
            self.Draw_Info_Menu()
        elif event == self.ENCODER_DIFF_CCW:
            self._info_scroll = max(0, current - getattr(self,"_rotation_steps",1))
            if self._info_scroll == current:
                return
            self.Draw_Info_Menu()
        elif event == self.ENCODER_DIFF_ENTER:
            if items and items[-1][0] == 'update' and current == max_scroll:
                self._software_updater().start()
                self.Draw_Info_Menu()
                self.lcd.update()
                return
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
        self._focus_print_input()

    def HMI_PauseOrStop(self):
        self._focus_stop_input()

    def HMI_Tune(self):
        self._focus_tune_input()

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
            self._action("Print speed", lambda: self.pd.set_feedrate(self.pd.HMI_ValueStruct.print_speed), silent=True)

        self._invalidate_list_row(self.select_tune.now + self.MROWS - self.index_tune)
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
                self._invalidate_list_row(1)
                self.pd.HMI_ValueStruct.Move_X_scale = self.pd.state.status['gcode_move']['position'][0] * self.MINUNITMULT
                self.lcd.draw_scaled_float_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
                    3, 1, 216, self.MBASE(1),
                    self.pd.HMI_ValueStruct.Move_X_scale
                )
            elif self.select_axis.now == 2:  # Y axis move
                self.checkkey = self.Move_Y
                self._invalidate_list_row(2)
                self.pd.HMI_ValueStruct.Move_Y_scale = self.pd.state.status['gcode_move']['position'][1] * self.MINUNITMULT
                self.lcd.draw_scaled_float_text(
                    True, True, 0, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Select_Color,
                    3, 1, 216, self.MBASE(2),
                    self.pd.HMI_ValueStruct.Move_Y_scale
                )
            elif self.select_axis.now == 3:  # Z axis move
                self.checkkey = self.Move_Z
                self._invalidate_list_row(3)
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
                self._invalidate_list_row(4)
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
                self._action("Jog X", lambda: self.pd.moveAbsolute('X', self.pd.HMI_ValueStruct.Move_X_scale / self.MINUNITMULT, 5000), silent=True)
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
                self._action("Jog Y", lambda: self.pd.moveAbsolute('Y', self.pd.HMI_ValueStruct.Move_Y_scale / self.MINUNITMULT, 5000), silent=True)
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
                self._action("Jog Z", lambda: self.pd.moveAbsolute('Z', self.pd.HMI_ValueStruct.Move_Z_scale / self.MINUNITMULT, 600), silent=True)
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
                self._action("Jog E", lambda: self.pd.moveAbsolute('E', self.pd.HMI_ValueStruct.Move_E_scale / self.MINUNITMULT, 300), silent=True)
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
            if key == 'CANCEL':
                self.pd.discard_preset_edits(profile)
                draw()
            elif key == 'SAVE':
                future = self.pd.save_settings()
                if isinstance(future, Future):
                    self._action('Save presets', lambda: future, silent=True,
                                 on_accept=lambda: draw() if self.checkkey in (self.PLAPreheat, self.ABSPreheat)
                                 and getattr(self, '_active_preset', 0) == profile else None)
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
        row = getattr(self, '_thermal_edit_row', row)
        if event == self.ENCODER_DIFF_ENTER:
            value = self.pd.HMI_ValueStruct.Fan_speed
            if mode != -2:
                self._action("Fan speed", lambda: self.pd.setFanSpeed(value), silent=True)
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

        temp_line = getattr(self, '_thermal_edit_row', temp_line)
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
            self._action("Hotend target", lambda: self.pd.setExtTemp(self.pd.HMI_ValueStruct.E_Temp), silent=True)
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

        bed_line = getattr(self, '_thermal_edit_row', bed_line)
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
            self._action("Bed target", lambda: self.pd.setBedTemp(self.pd.HMI_ValueStruct.Bed_Temp), silent=True)
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
            self._action("Motion limit", lambda: self.pd.set_motion_limit(self._motion_field, self._motion_target), silent=True)
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
        if wizard.phase == 'active':
            return tuple((step, lambda step=step: wizard.testz(step))
                         for step in ('--', '-', '+', '++')) + (('Cancel', wizard.abort), ('Accept', wizard.accept))
        if wizard.phase == 'accepted':
            return (('Save', wizard.save), ('Continue', self._leave_probe))
        if wizard.phase in ('error', 'interrupted'):
            if self.pd.state.ready and not self.pd.connection_error and not wizard.active():
                return (('Retry', wizard.start), ('Back', self._leave_probe))
            return (('Back', self._leave_probe),)
        if wizard.phase == 'saved':
            return (('Back', self._leave_probe),)
        return (('Start', wizard.start), ('Back', self._leave_probe))

    def _leave_probe(self):
        self._drawn_probe_wizard = None
        self._return_to_mesh_menu()

    def _probe_button(self, label, box, selected):
        x, y, width, height = box
        self.lcd.draw_rectangle(1, 0x03B5, x, y, x+width, y+height)
        self.lcd.draw_rectangle(0, self.lcd.Color_White if selected else 0x03B5,
                                x-2, y-2, x+width+2, y+height+2)
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                           0x03B5, x+(width-len(label)*8)//2, y+(height-16)//2, label)

    def Draw_Probe_Wizard(self):
        wizard = self.pd.probe_wizard
        manual = self.pd.state.status.get('manual_probe', {})
        options = self._probe_options()
        selected = max(0, min(getattr(self, '_probe_selection', 0), len(options)-1))
        self._probe_selection = selected
        layout = ('active' if wizard.phase == 'active' else 'accepted' if wizard.phase == 'accepted'
                  else 'error' if wizard.phase in ('error', 'interrupted')
                  else 'saved' if wizard.phase == 'saved' else 'start')
        values = tuple(manual.get(key) for key in ('z_position_lower', 'z_position', 'z_position_upper'))
        error = wizard.message if layout == 'error' or getattr(self, '_probe_ui_error', None) else None
        if getattr(self, '_probe_ui_error', None): error = self._probe_ui_error
        signature = (layout, values, selected, error)
        previous = getattr(self, '_drawn_probe_wizard', None)
        if signature == previous:
            return
        full = previous is None or previous[0] != layout
        if full:
            self.Clear_Main_Window()
            self.Draw_Title('Probe calibration')
        if layout == 'active':
            if full or previous[1] != values:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 72, 263, 148)
                def value_text(value):
                    return '{:.3f}'.format(value) if isinstance(value, (int, float)) else '---'
                for value, x, width, font, y in (
                        (values[0], 8, 68, self.lcd.font8x16, 96),
                        (values[1], 84, 104, self.lcd.font14x28, 86),
                        (values[2], 196, 68, self.lcd.font8x16, 96)):
                    label = value_text(value)
                    char_width = 14 if x == 84 else 8
                    self.lcd.draw_text(False, False, font, self.lcd.Color_White,
                                       self.lcd.Color_Bg_Black, x+max(0,(width-len(label)*char_width)//2), y, label)
                self.lcd.draw_text(False, False, self.lcd.font6x12, self.lcd.Color_White,
                                   self.lcd.Color_Bg_Black, 130, 123, 'mm')
            boxes = ((12,174,52,44), (77,174,52,44), (142,174,52,44), (207,174,52,44),
                     (26,294,99,40), (146,294,99,40))
        else:
            boxes = ((26,294,99,40), (146,294,99,40))
            if full:
                label = {'start': 'Ready to calibrate', 'accepted': 'Offset accepted',
                         'saved': 'Saved', 'error': 'Calibration interrupted'}[layout]
                self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                                   self.lcd.Color_Bg_Black, (272-len(label)*8)//2, 110, label)
        for index, (label, _) in enumerate(options):
            if full or selected != previous[2] and index in (selected, previous[2]):
                self._probe_button(label, boxes[index], index == selected)
        if error:
            import textwrap
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 235, 263, 280)
            for line, text in enumerate(textwrap.wrap(T5UIC1Display._panel_text(error), 40)[:3]):
                self.lcd.draw_text(False, False, self.lcd.font6x12, self.lcd.Color_White,
                                   self.lcd.Color_Bg_Black, 12, 238+line*14, text)
        elif previous and previous[3]:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 8, 235, 263, 280)
        self._drawn_probe_wizard = signature
        self.lcd.update()

    def HMI_Probe_Wizard(self):
        wizard = self.pd.probe_wizard
        wizard.update()
        options = self._probe_options()
        self._probe_selection = max(0, min(getattr(self, '_probe_selection', 0), max(0, len(options) - 1)))
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_CW and options:
            self._probe_selection = min(len(options) - 1, self._probe_selection + getattr(self,"_rotation_steps",1))
        elif event == self.ENCODER_DIFF_CCW:
            self._probe_selection = max(0, self._probe_selection - getattr(self,"_rotation_steps",1))
        elif event == self.ENCODER_DIFF_ENTER and options and not wizard.pending:
            try:
                self._probe_ui_error = None
                options[self._probe_selection][1]()
            except ValueError as error:
                self._probe_ui_error = str(error)
        if self.checkkey == self.ProbeWizardID:
            self.Draw_Probe_Wizard()

    def _open_zoffset(self, mode, row):
        self._zoffset_edit_row = self._invalidate_list_row(row)
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

        zoff_line = getattr(self, '_zoffset_edit_row', zoff_line)
        if (encoder_diffState == self.ENCODER_DIFF_ENTER): #if (applyencoder(encoder_diffstate, offset_value))
            self._action("Runtime Z offset", lambda: self.pd.setZOffset(self._zoffset_target / 100.0), silent=True)

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

    def _draw_status_field(self, method, *args):
        # Compare the values that the LCD actually displays, not raw telemetry.
        args = list(args)
        if method == 'show_icon':
            key = (method, args[-2], args[-1])
        else:
            key = (method, args[-3], args[-2])
        cache = self._status_render
        previous = cache.get(key)
        value = list(args)
        if method == 'draw_integer_text':
            value[-1] = T5UIC1Display._format_scaled_decimal(
                self.lcd, args[-1], args[-4], 0, False)
        elif method == 'draw_signed_scaled_float_text':
            value[-1] = T5UIC1Display._format_scaled_decimal(
                self.lcd, args[-1], args[2], args[3], True)
        value = tuple(value)
        if previous == value:
            return
        if method == 'draw_text' and previous is not None:
            x, y = args[-3:-1]
            # Erase a shrinking string, leaving adjacent icons untouched.
            right = min(271,
                        x + max(len(previous[-1]), len(args[-1])) * (T5UIC1Display.FONT_SIZES[args[2]][0] if isinstance(args[2], int) else self.STAT_CHR_W) - 1)
            self.lcd.draw_rectangle(1, args[4],
                                    x, y, right, y + (T5UIC1Display.FONT_SIZES[args[2]][1] if isinstance(args[2], int) else 20) - 1)
            # Long telemetry text can reach the next column. Restore only
            # the fields touched by the erasure when they are drawn below.
            for other in list(cache):
                if other != key and x < other[1] <= right and y - 1 <= other[2] <= y + 19:
                    del cache[other]
        if method == 'show_icon':
            show_theme_icon(self.lcd, *args)
        else:
            getattr(self.lcd, method)(*args)
        cache[key] = value

    def _sync_fan_animation(self, visible, force=False):
        percent = max(0, min(100, round(self.pd.thermalManager['fan_speed'][0])))
        interval = max(1, min(255, round(100 / percent))) if visible and percent else 0
        key = (id(self.lcd), getattr(self, '_uart_epoch', 0), interval)
        if not force and key == getattr(self, '_fan_animation_key', None):
            return
        previous = getattr(self, '_fan_animation_key', None)
        if interval and (force or previous is None or not previous[2]):
            self.lcd.draw_rectangle(1, 0x18C4, 200, 380, 219, 399)
        if interval or (previous is not None and previous[2]):
            self.lcd.configure_animation(1, bool(interval), self.ICON,
                ICON_FAN_FIRST, ICON_FAN_LAST, 200, 380, interval or 1,
                restart_from_first=force or previous is None or not previous[2])
        self._fan_animation_key = key
        if visible and not interval:
            self.lcd.draw_rectangle(1, 0x18C4, 200, 380, 219, 399)
            # Match the opaque native animation path, including its backing.
            self.lcd.show_icon(self.ICON, ICON_FAN_FIRST, 200, 380, background=True)

    def Draw_Status_Area(self, with_update):
        if getattr(self, 'checkkey', None) in (self.MMUMenu, self.Tune, self.TuneEdit, self.PrintErrorDetails):
            self._sync_fan_animation(False)
            self._status_render = {}
            return
        # Compact dashboard: temperatures / speed / fan, bed / flow / Z offset,
        # then interpolated live X/Y/Z positions.
        layout = (id(self.lcd), self.pd.HAS_HOTEND, self.pd.HAS_FAN,
                  self.pd.HAS_HEATED_BED, self.pd.HAS_ZOFFSET_ITEM)
        redraw = layout != getattr(self, '_status_layout', None) or not with_update
        if redraw:
            self._status_layout = layout
            self._status_render = {}
            self.lcd.draw_rectangle(1, 0x18C4, 0,
                self.STATUS_Y, self.lcd.DWIN_WIDTH - 1, self.lcd.DWIN_HEIGHT - 1)

            self.lcd.draw_line(self.lcd.Line_Color, 12, 363, 259, 363)
        y1, y2, y3 = 380, 414, 448
        # Temperature fields need enough width for "actual/target". Keep them
        # in a wider left column and compact the two telemetry columns.
        x1, x2, x3 = 4, 102, 200
        value1, value2, value3 = 28, 126, 224

        if self.pd.HAS_HOTEND:
            self._draw_status_field('show_icon', self.ICON, self.ICON_HotendTemp, x1, y1)
            self._draw_status_field('draw_integer_text', True, True, 0, self.lcd.font8x16,
                self.lcd.Color_White, 0x18C4, 3, value1, y1,
                self.pd.thermalManager['temp_hotend'][0]['celsius'])
            self._draw_status_field('draw_text', False, False, self.lcd.font8x16,
                self.lcd.Color_White, 0x18C4,
                value1 + 3 * 8, y1, "/")
            self._draw_status_field('draw_integer_text', True, True, 0, self.lcd.font8x16,
                self.lcd.Color_White, 0x18C4, 3,
                value1 + 4 * 8, y1,
                self.pd.thermalManager['temp_hotend'][0]['target'])

        # Match the established dashboard behavior: alternate speed override
        # and instantaneous Klipper toolhead velocity in the same field.
        phase = int(time.monotonic() / 2.0) & 1
        self._draw_status_field('show_icon', self.ICON, self.ICON_Speed, x2, y1)
        if phase:
            speed_text = '{:.0f}%'.format(self.pd.feedrate_percentage)
        else:
            speed_text = '{:.0f}mm/s'.format(abs(self.pd.live_velocity))
        self._draw_status_field('draw_text', False, True, self.lcd.font8x16,
            self.lcd.Color_White, 0x18C4, value2, y1, speed_text)

        if self.pd.HAS_FAN:
            self._sync_fan_animation(True, force=redraw)
            percent = max(0, min(100, round(self.pd.thermalManager['fan_speed'][0])))
            self._draw_status_field('draw_text', False, True, self.lcd.font8x16,
                self.lcd.Color_White, 0x18C4, value3, y1, '{:3d}%'.format(percent))

        if self.pd.HAS_HEATED_BED:
            self._draw_status_field('show_icon', self.ICON, self.ICON_BedTemp, x1, y2)
            self._draw_status_field('draw_integer_text', True, True, 0, self.lcd.font8x16,
                self.lcd.Color_White, 0x18C4, 3, value1, y2,
                self.pd.thermalManager['temp_bed']['celsius'])
            self._draw_status_field('draw_text', False, False, self.lcd.font8x16,
                self.lcd.Color_White, 0x18C4,
                value1 + 3 * 8, y2, "/")
            self._draw_status_field('draw_integer_text', True, True, 0, self.lcd.font8x16,
                self.lcd.Color_White, 0x18C4, 3,
                value1 + 4 * 8, y2,
                self.pd.thermalManager['temp_bed']['target'])

        # The extrusion field alternates between M221 flow override and
        # instantaneous volumetric flow so both fit without sacrificing XYZ.
        self._draw_status_field('show_icon', self.ICON, self.ICON_StepE, x2, y2)
        if phase:
            flow_text = '{:.0f}%'.format(self.pd.flow_percentage)
        else:
            flow_text = ('{:.1f}mm3/s' if abs(self.pd.volumetric_flow) < 100 else '{:.0f}mm3/s').format(self.pd.volumetric_flow)
        self._draw_status_field('draw_text', False, True, self.lcd.font8x16,
            self.lcd.Color_White, 0x18C4, value2, y2, flow_text)

        if self.pd.HAS_ZOFFSET_ITEM:
            self._draw_status_field('show_icon', self.ICON, self.ICON_Zoffset, x3, y2)
            self._draw_status_field('draw_signed_scaled_float_text',
                self.lcd.font8x16, 0x18C4,
                2, 2, value3, y2, self.pd.BABY_Z_VAR * 100)

        positions = self.pd.live_position
        for icon, xpos, value_x, position in (
                (self.ICON_MaxSpeedX, x1, value1, positions[0]),
                (self.ICON_MaxSpeedY, x2, value2, positions[1]),
                (self.ICON_MaxSpeedZ, x3, value3, positions[2])):
            self._draw_status_field('show_icon', self.ICON, icon, xpos, y3)
            self._draw_status_field('draw_signed_scaled_float_text',
                self.lcd.font8x16, 0x18C4,
                3, 1, value_x, y3, position * 10)

    def Draw_Title(self, title):
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White, self.lcd.Color_Bg_Blue, 14, 6, title)
        self._draw_header_clock()

    def _draw_header_clock(self):
        value = time.strftime('%H:%M', time.localtime())
        key = (id(self.lcd), value)
        if key == getattr(self, '_header_clock_drawn', None):
            return False
        self.lcd.draw_text(False, True, self.lcd.font8x16, self.lcd.Color_White,
                           self.lcd.Color_Bg_Blue, 224, 6, value)
        self._header_clock_drawn = key
        return True

    def Draw_Popup_Bkgd_105(self):
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Window, 14, 105, 258, 374)

    def Draw_More_Icon(self, line):
        show_theme_icon(self.lcd, self.ICON, self.ICON_More, 226, self.MBASE(line) - 3)

    def Draw_Menu_Cursor(self, line):
        self.lcd.draw_rectangle(1, self.lcd.Rectangle_Color, 4, self.MBASE(line) - 13, 7, self.MBASE(line + 1) - 25)

    def Draw_Menu_Icon(self, line, icon):
        show_theme_icon(self.lcd, self.ICON, icon, 26, self.MBASE(line) - 3)

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
            show_theme_icon(self.lcd, self.ICON, ICON_FOLDER, 26, self.MBASE(row) - 7)

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
        self.Draw_Title('Paused' if self.pd.printingIsPaused() else 'Printing')
        self._draw_menu_text('Elapsed', 41, 188)
        self._draw_menu_text('Remaining', 170, 188)

    def Draw_Print_ProgressBar(self, Percentrecord=None):
        if Percentrecord is None:
            Percentrecord = self.pd.getPercent()
        self._draw_progress_track(self.lcd, 24, 99, 224, Percentrecord)
        text = '%d%%' % Percentrecord
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 104, 122, 167, 141)
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                           self.lcd.Color_Bg_Black, (272-len(text)*8)//2, 123, text)

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
        self.Redraw_SD_List()

    def Draw_Prepare_Menu(self):
        self._draw_capability_menu('prepare', self.select_prepare, self.index_prepare)

    def Draw_Control_Menu(self):
        self._draw_capability_menu('control', self.select_control, getattr(self, 'index_control', self.MROWS))

    def _draw_info_row(self, label, value, y):
        self._draw_menu_text(label, 8, y)
        self._draw_info_value(label, value, y)

    def _draw_info_value(self, label, value, y, clear=False):
        text = T5UIC1Display._panel_text(value)[:17]
        if clear:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 120, y, 255, y + 15)
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
            'HOST': (0x4C7F, ICON_HOST),
            'SOFTWARE': (0x03DF, ICON_SOFTWARE),
        }
        key = text.upper()
        if key.startswith('MCU'):
            color, icon = 0x063B, ICON_MCU
        else:
            color, icon = palette.get(key, (self.lcd.Color_White, None))
        if icon is not None:
            show_theme_icon(self.lcd, self.ICON, icon, 8, y - 2)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Info, 8, y - 2)
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Color_White,
                             self.lcd.Color_Bg_Black, 40, y+2, key)
        self.lcd.draw_rectangle(1, self.lcd.Line_Color, 40, y + 21, 255, y + 21)

    def _draw_info_update_button(self, y, selected):
        updater = self._software_updater()
        backing = 0x063B if selected else 0x2967
        foreground = 0x10C4 if selected else self.lcd.Color_White
        label = T5UIC1Display._panel_text(updater.label)[:25]
        token = (id(self.lcd), y, bool(selected), label)
        previous = getattr(self, '_info_update_render', None)
        if previous is None or previous[:3] != token[:3]:
            icon = ICON_INFO_UPDATE_SELECTED if selected else ICON_INFO_UPDATE_NORMAL
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 32, y-4, 239, y+23)
            show_theme_icon(self.lcd, self.ICON, icon, 32, y - 4)
        elif previous[3] != label:
            # Interior only: preserve curved edges when the updater label changes.
            self.lcd.draw_rectangle(1, backing, 46, y, 226, y + 19)
        if previous is None or previous != token:
            self.lcd.draw_text(False, False, self.lcd.font8x16, foreground,
                               backing, (272 - len(label) * 8) // 2, y + 2, label)
        self._info_update_render = token
        message = (updater.phase, updater.message)
        if getattr(self, '_info_update_message', None) == (y, message):
            return
        self._info_update_message = (y, message)
        if y - 48 >= 92:
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                    23, y - 48, 249, y - 8)
        if not updater.message or updater.phase in ('checking', 'updating', 'restarting', 'recovering'):
            return
        color = {'current': 0x07E0, 'available': 0xFFE0, 'dirty': 0xFFE0,
                 'confirm_recovery': 0xFFE0}.get(updater.phase, 0xF800)
        lines = textwrap.wrap(T5UIC1Display._panel_text(updater.message), width=28)[:2]
        first_y = y - (40 if len(lines) > 1 else 32)
        for index, text in enumerate(lines):
            line_y = first_y + index * 16
            if line_y >= 92:
                self.lcd.draw_text(False, False, self.lcd.font8x16, color,
                                   self.lcd.Color_Bg_Black,
                                   (272 - len(text) * 8) // 2, line_y, text)

    def _refresh_info_update_button(self):
        items = self._info_items()
        for index, (kind, _, _) in enumerate(items):
            if kind != 'update':
                continue
            y = 92 + (index + extra_info_rows() - getattr(self, '_info_scroll', 0)) * 24
            if 92 <= y < 356:
                self._draw_info_update_button(
                    y, getattr(self, '_info_scroll', 0)
                    == max(0, len(items) + extra_info_rows() - 11))
                self.lcd.update()
            break

    def _software_updater(self):
        if not hasattr(self, '_software_update'):
            self._software_update = SoftwareUpdate(self.pd)
        return self._software_update

    def _info_items(self):
        info = self.pd.system_info
        cpu = info.get('host_cpu')
        ram = info.get('host_ram')
        temp = info.get('host_temp')
        items = [
            ('section', 'Machine', None),
            ('row', 'Size', self.pd.MACHINE_SIZE),
            ('row', 'Network', info.get('network', 'Unknown')),
            ('row', 'Wi-Fi', info.get('wifi_ssid', 'Unavailable')),
            ('row', 'RSSI', wifi_signal_text(info.get('wifi_rssi'))),
            ('row', 'IP', info.get('ip', 'Unavailable')),
            ('section', 'Host', None),
            ('row', 'CPU', 'N/A' if cpu is None else '{:.0f}%'.format(cpu)),
            ('row', 'RAM', 'N/A' if ram is None else '{:.0f}%'.format(ram)),
            ('row', 'CPU temp', 'N/A' if temp is None else '{:.1f} C'.format(temp)),

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
        items.extend([
            ('section', 'Software', None),
            ('row', 'Petrel', info.get('petrel', 'Unavailable')),
            ('row', 'Klipper', self.pd.SHORT_BUILD_VERSION),
            ('row', 'Moonraker', info.get('moonraker', 'Unavailable')),
            ('row', 'Mainsail', info.get('mainsail', 'Unavailable')),
            ('qr', 'Scan for project info', PROJECT_URL),
            ('update', '', None),
        ])
        return items

    def Draw_Info_Menu(self):
        self.lcd.ensure_cached_picture(SHARED_PICTURE_ID)
        self.pd.refresh_system_info()
        items = self._info_items()
        max_scroll = max(0, len(items) + extra_info_rows() - 11)
        self._info_scroll = max(0, min(getattr(self, '_info_scroll', 0), max_scroll))
        previous = getattr(self, '_info_render_scroll', None)
        delta = self._info_scroll - previous if previous is not None else 0
        old_items = getattr(self, '_info_render_items', ())
        same_layout = (previous is not None and
                       getattr(self, '_info_render_lcd', None) is self.lcd and
                       [(kind, label) for kind, label, _ in old_items] ==
                       [(kind, label) for kind, label, _ in items])
        distance = abs(delta) * 24
        incremental = same_layout and 0 < distance < 266
        stationary = same_layout and delta == 0
        band = (356 - distance, 356) if delta > 0 else (90, 90 + distance)
        if incremental:
            # Moving the viewport can evict the update control entirely. Its
            # screen-space cache cannot survive a scroll out and back to the
            # same coordinates, even when label, selection and message match.
            self._info_update_render = None
            self._info_update_message = None
            self.lcd.move_area(1, self.DWIN_SCROLL_UP if delta > 0 else self.DWIN_SCROLL_DOWN,
                               distance, self.lcd.Color_Bg_Black, 0, 90, 271, 355)
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 90, 255, 91)
            # Scroll indicators belong to the fixed frame, not the moving list.
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 256, 92, 271, 359)
            if (previous == max_scroll) != (self._info_scroll == max_scroll):
                self.Erase_Menu_Cursor(0)
                if self._info_scroll < max_scroll:
                    self.Draw_Menu_Cursor(0)
        elif not stationary:
            self.Clear_Main_Window()
            self._info_update_render = None
            self._info_update_message = None
            self.Draw_Title('Info')
            self.Draw_Back_First(self._info_scroll < max_scroll)
        for index, (kind, label, value) in enumerate(items):
            if stationary or kind != 'qr':
                continue
            y = 92 + (index - self._info_scroll) * 24
            qr_top = y + 24
            draw_project_qr(self.lcd, qr_top,
                            top=max(92, band[0]) if incremental else 92,
                            bottom=min(356, band[1]) if incremental else 356)
        for index, (kind, label, value) in enumerate(items):
            y = 92 + (index + (extra_info_rows() if kind == 'update' else 0) - self._info_scroll) * 24
            if not 92 <= y < 356:
                if incremental and kind == 'update' and y == 356:
                    self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 32, 352, 239, 355)
                continue
            exposed = incremental and (band[0] <= y < band[1] or
                                       (kind == 'section' and y == 92))
            if (stationary or (incremental and not exposed)) and kind != 'update':
                if (kind == 'row' and
                        T5UIC1Display._panel_text(value)[:17] !=
                        T5UIC1Display._panel_text(old_items[index][2])[:17]):
                    self._draw_info_value(label, value, y, clear=True)
                continue
            if kind == 'qr':
                self._draw_menu_text(label, 48, y)
            elif kind == 'update':
                self._draw_info_update_button(y, self._info_scroll == max_scroll)
            elif kind == 'section':
                self._draw_info_section(label, y)
            else:
                self._draw_info_row(label, value, y)
        if not stationary:
            # The list ends at 355; the dashboard starts at STATUS_Y (360).
            # Pixels in this fixed gutter never participate in move_area.
            # Clear old QR fragments here, including those from earlier renders.
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                    0, 356, 255, self.STATUS_Y - 1)
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 256, 76, 271, 89)
            if self._info_scroll:
                self._draw_menu_text('^', 256, 76)
            if self._info_scroll < max_scroll:
                self._draw_menu_text('v', 256, 328)
        self._info_render_scroll = self._info_scroll
        self._info_render_items = items
        self._info_render_lcd = self.lcd

    def Draw_Tune_Menu(self):
        self._focus_tune_open()

    def Draw_Temperature_Menu(self):
        self._draw_capability_menu('temperature', self.select_temp, self.index_temp)

    def Draw_Motion_Menu(self):
        settings = self.pd.motion_settings()
        if self.select_motion.now > len(settings):
            self.select_motion.reset()
        entries = [('Back', self.ICON_Back, None, None)]
        for field, _, label, _, value in settings:
            editing = self.checkkey == self.MotionValue and self._motion_field == field
            if editing:
                value = self._motion_target
            text = '{:g}'.format(value)
            if len(text) > 9:
                text = '{:.3g}'.format(value)
            if len(text) > 9:
                text = '#' * 9
            painter = lambda row, text=text, editing=editing: self.lcd.draw_text(
                False, True, self.lcd.font8x16, self.lcd.Color_White,
                self.lcd.Select_Color if editing else self.lcd.Color_Bg_Black,
                168, self.MBASE(row), text.rjust(9))
            entries.append((label, {'max_velocity': ICON_VELOCITY,'max_accel': ICON_ACCELERATION,'square_corner_velocity': ICON_CORNER_SPEED,'minimum_cruise_ratio': ICON_CRUISE_RATIO}[field], (text, editing), painter))
        self._draw_list_menu('Motion (runtime)', entries, self.select_motion.now)

    def Draw_Move_Menu(self):
        position = self.pd.state.status['gcode_move']['position']
        entries = [('Back', self.ICON_Back, None, None)]
        for index, label in enumerate(('Move X', 'Move Y', 'Move Z', 'Extruder')[:3 + int(self.pd.HAS_HOTEND)]):
            value = position[index] * self.MINUNITMULT
            def painter(row, v=value, index=index):
                if index == 3:
                    self.lcd.draw_signed_scaled_float_text(self.lcd.font8x16,
                        self.lcd.Color_Bg_Black, 3, 1, 216, self.MBASE(row), v)
                else:
                    self.lcd.draw_scaled_float_text(True, True, 0, self.lcd.font8x16,
                        self.lcd.Color_White, self.lcd.Color_Bg_Black, 3, 1, 216, self.MBASE(row), v)
            entries.append((label, self.ICON_MoveX + index, value, painter))
        live = bool(getattr(self, '_live_jog', False))
        entries.append(('Live jog', ICON_LIVE_JOG, live,
            self._menu_checkbox_painter(live)))
        self._draw_list_menu('Move', entries, self.select_axis.now)

    # --------------------------------------------------------------#
    # --------------------------------------------------------------#

    def Goto_MainMenu(self):
        self.checkkey = self.MainMenu
        self.Clear_Main_Window()

        if self.pd.mmu is None:
            show_theme_icon(self.lcd, self.ICON, self.ICON_LOGO, 71, 48)
        else:
            self.Draw_MMU_Status()
        self._drawn_mmu_state = copy.deepcopy(self.pd.mmu)

        self._draw_home_page()

    def Goto_PrintProcess(self):
        self._focus_print_open()

    def Clear_Title_Bar(self):
        self._info_render_scroll = None
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Blue, 0, 0, self.lcd.DWIN_WIDTH - 1, 30)
        self._header_clock_drawn = None
        self._draw_header_clock()

    def Clear_Menu_Area(self):
        self._list_render = None
        self._display_drawn_message = None
        self._file_drawn_message = None
        self._home_mmu_layout = None
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 31, self.lcd.DWIN_WIDTH - 1, self.STATUS_Y)

    def Clear_Main_Window(self):
        self._info_render_scroll = None
        self._screws_result_cache = None
        self.Clear_Title_Bar()
        self.Clear_Menu_Area()

    def Clear_Popup_Area(self):
        self._info_render_scroll = None
        # Popup overwrites previously cached screw graphics; power-cancel
        # must repaint all four corners when returning to that screen.
        self._screws_result_cache = None
        self._sync_fan_animation(False)
        self._list_render = None
        self._status_layout = None
        self.Clear_Title_Bar()
        self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 0, 31, self.lcd.DWIN_WIDTH - 1, self.lcd.DWIN_HEIGHT - 1)

    def Popup_window_PauseOrStop(self):
        self._focus_stop_draw()

    def Popup_Window_Home(self, parking=False):
        self.Clear_Main_Window()
        self.Draw_Popup_Bkgd_60()
        show_theme_icon(self.lcd, self.ICON, self.ICON_BLTouch, 101, 105)
        if parking:
            self.lcd.draw_text(
                False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
                (272 - 8 * (7)) / 2, 230, "Parking")
        else:
            self.lcd.draw_text(
                False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color, self.lcd.Color_Bg_Window,
                (272 - 8 * (10)) / 2, 230, "Homing XYZ")


    def Popup_Window_ETempTooLow(self):
        self.Clear_Main_Window()
        self.Draw_Popup_Bkgd_60()
        show_theme_icon(self.lcd, self.ICON, self.ICON_TempTooLow, 102, 105)
        self.lcd.draw_text(
            False, True, self.lcd.font8x16, self.lcd.Popup_Text_Color,
            self.lcd.Color_Bg_Window, 20, 235,
            "Nozzle is too cold"
        )
        show_theme_icon(self.lcd, self.ICON, self.ICON_Confirm_E, 86, 280)

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
        entries = [('Back', self.ICON_Back, None, None)]
        for index, path in enumerate(self._file_paths):
            entries.append(('', False, path,
                lambda row, index=index: self.Draw_SDItem(index, row)))
        directory = getattr(self, '_file_directory', '')
        self._draw_list_menu(('Print: /' + directory)[-32:] if directory else 'Print file',
                             entries, self.select_file.now, max(0, self.index_file - self.MROWS))
        message = ('File list unavailable' if self.pd.file_error else 'No files') if (
            len(entries) == 1 and (self.pd.file_error or not (self.pd._files_loading or self.pd._directory_loading))) else ''
        if message != getattr(self, '_file_drawn_message', None):
            if getattr(self, '_file_drawn_message', None):
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 20, self.MBASE(2), 271, self.MBASE(2) + 16)
            if message:
                self._draw_menu_text(message, 20, self.MBASE(2))
            self._file_drawn_message = message

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
            show_theme_icon(self.lcd, self.ICON, self.ICON_Print_1, 17, 130)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 17, 130, 126, 229)
            self._draw_menu_text('Print', 57, 201)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Print_0, 17, 130)
            self._draw_menu_text('Print', 57, 201)

    def ICON_Prepare(self):
        if self.select_page.now == 1:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Prepare_1, 145, 130)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 145, 130, 254, 229)
            self._draw_menu_text('Prepare', 175, 201)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Prepare_0, 145, 130)
            self._draw_menu_text('Prepare', 175, 201)

    def ICON_Control(self):
        if self.select_page.now == 2:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Control_1, 17, 246)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 17, 246, 126, 345)
            self._draw_menu_text('Control', 48, 318)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Control_0, 17, 246)
            self._draw_menu_text('Control', 48, 318)

    def ICON_Leveling(self, show):
        if show:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Leveling_1, 145, 246)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 145, 246, 254, 345)
            self._draw_menu_text('Leveling', 182, 318)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Leveling_0, 145, 246)
            self._draw_menu_text('Leveling', 182, 318)

    def ICON_StartInfo(self, show):
        if show:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Info_1, 145, 246)
            self.lcd.draw_rectangle(0, self.lcd.Color_White, 145, 246, 254, 345)
            self._draw_menu_text('Info', 186, 318)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Info_0, 145, 246)
            self._draw_menu_text('Info', 186, 318)

    def _draw_print_control_label(self, label, x):
        self._draw_menu_text(label, x + (80 - len(label) * 8) // 2, 325)

    def ICON_Tune(self):
        if (self.select_print.now == 0):
            show_theme_icon(self.lcd, self.ICON, self.ICON_Setup_1, 8, 252)
            self._draw_print_control_label('Tune', 8)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Setup_0, 8, 252)
            self._draw_print_control_label('Tune', 8)

    def ICON_Continue(self):
        if (self.select_print.now == 1):
            show_theme_icon(self.lcd, self.ICON, self.ICON_Continue_1, 96, 252)
            self._draw_print_control_label('Continue', 96)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Continue_0, 96, 252)
            self._draw_print_control_label('Continue', 96)

    def ICON_Pause(self):
        if (self.select_print.now == 1):
            show_theme_icon(self.lcd, self.ICON, self.ICON_Pause_1, 96, 252)
            self._draw_print_control_label('Pause', 96)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Pause_0, 96, 252)
            self._draw_print_control_label('Pause', 96)

    def ICON_Stop(self):
        if (self.select_print.now == 2):
            show_theme_icon(self.lcd, self.ICON, self.ICON_Stop_1, 184, 252)
            self._draw_print_control_label('Stop', 184)
        else:
            show_theme_icon(self.lcd, self.ICON, self.ICON_Stop_0, 184, 252)
            self._draw_print_control_label('Stop', 184)

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
        self._poll_case_light_live()
        self._sync_case_light_tracking()
        self._poll_case_light_state()
        # variable update
        update = self.pd.update_variable()
        self._poll_maintenance_ui()
        self._focus_tick_quiet()
        if not self.pd.connection_error and self.checkkey not in (self.SelectFile, self.FilePreview):
            self.pd.prefetch_files()
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
        self.pd.probe_wizard.update()
        if self.pd.connection_error and self.checkkey in (self.BedMeshScreen, self.MeshProfiles):
            self._offline = True
            return
        if self.pd.connection_error:
            if not self._offline:
                self._show_message('Moonraker unavailable')
            self._offline = True
            return
        self.pd.probe_wizard.update()
        info_update = False
        if self.checkkey == self.Info:
            info_update = self._software_updater().poll()
        if self.checkkey == self.Info:
            system_changed = self.pd.refresh_system_info()
            if system_changed:
                self.Draw_Info_Menu()
                self.lcd.update()
            elif info_update:
                self._refresh_info_update_button()
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
            self._focus_print_tick()
        elif self.checkkey == self.Tune:
            self._focus_tune_tick()
        elif self.checkkey in (self.TuneEdit, self.PrintErrorDetails):
            self._focus_tick_quiet()
        elif update and self.checkkey == self.TemperatureID:
            self.Draw_Temperature_Menu()
        elif update and self.checkkey == self.AxisMove:
            self.Draw_Move_Menu()
        elif update and self.checkkey == self.Motion:
            self.Draw_Motion_Menu()
        elif update and self.checkkey == self.BedMeshMenu:
            self.Draw_Bed_Mesh_Menu()
        elif self.checkkey == self.ProbeWizardID:
            self.Draw_Probe_Wizard()

        if self.pd.HMI_flag.home_flag:
            if self.pd.ishomed():
                self.CompletedHoming()

        if self.checkkey == self.MainMenu:
            mmu_state = self.pd.mmu
            if (mmu_state is None) != (getattr(self, '_drawn_mmu_state', None) is None):
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 4, 31, 268, 125)
                self._home_mmu_layout = None
                if mmu_state is None:
                    show_theme_icon(self.lcd, self.ICON, self.ICON_LOGO, 71, 48)
            if mmu_state is not None and mmu_state != getattr(self, '_drawn_mmu_state', None):
                self.Draw_MMU_Status()
            self._drawn_mmu_state = copy.deepcopy(mmu_state)
        self.Draw_Status_Area(True)
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
            self.DisplayMenu: '_display_selection',
            self.BuzzerMenu: '_buzzer_selection',
            self.MaintenanceMenu: '_maintenance_selection',
        }
        if self.checkkey == self.MMUMenu:
            return (not self.pd.connection_error and getattr(self, '_mmu_selection', 0) == 0
                    and getattr(self, '_mmu_edit', None) is None)
        attr = custom.get(self.checkkey)
        return attr is not None and getattr(self, attr, 0) == 0

    def _draw_power_confirmation(self, buttons_only=False):
        if not buttons_only:
            self.Clear_Popup_Area()
            self.Draw_Title('Power')
            self.Draw_Popup_Bkgd_105()
        if getattr(self, '_power_hold_popup', False):
            blocked = getattr(self, '_power_blocked', None)
            if not buttons_only:
                self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Popup_Text_Color,
                    self.lcd.Color_Bg_Window, (272 - len(blocked or 'Power off printer?') * 8) // 2,
                    150, blocked or 'Power off printer?')
            choices = ((False, 'Cancel', 28, 104),) if blocked else ((False, 'Cancel', 28, 104), (True, 'Power off', 140, 104))
            for yes, label, x, width in choices:
                fill = (0xB986 if yes else 0x19E9) if self._power_confirm_yes == yes else self.lcd.Color_Bg_Window
                icon = (ICON_POWER_BUTTON_OFF if yes else ICON_POWER_BUTTON_CANCEL) if self._power_confirm_yes == yes else ICON_POWER_BUTTON_NORMAL
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Window, x, 224, x+width-1, 259)
                show_theme_icon(self.lcd, self.ICON, icon, x, 224)
                self.lcd.draw_text(False, False, self.lcd.font8x16,
                    0xFBAE if yes and not self._power_confirm_yes else self.lcd.Popup_Text_Color,
                    fill, x + (width - len(label) * 8) // 2, 234, label)
            return
        self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Popup_Text_Color,
                           self.lcd.Color_Bg_Window, 42, 150, 'Turn off printer?')
        for yes, label, x in ((True, 'Yes', 42), (False, 'No', 164)):
            color = 0x063B if self._power_confirm_yes == yes else self.lcd.Color_Bg_Window
            self.lcd.draw_rectangle(0, color, x - 12, 224, x + 52, 264)
            self.lcd.draw_text(False, False, self.lcd.font8x16, self.lcd.Popup_Text_Color,
                               self.lcd.Color_Bg_Window, x, 236, label)

    def _restore_power_origin(self):
        # Both the hold capsule and confirmation can overwrite cached rows.
        self._list_render = None
        self._info_render_scroll = None
        origin = self._power_origin
        self._power_origin = None
        self._power_focus = False
        self._power_hold_popup = False
        self._power_blocked = None
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
            self.DisplayMenu: self.Draw_Display_Menu,
            self.BuzzerMenu: self.Draw_Buzzer_Menu,
            self.MaintenanceMenu: self.Draw_Maintenance_Menu,
            self.Tune: self.Draw_Tune_Menu,
            self.MMUMenu: self.Draw_MMU_Menu,
            self.BedMeshMenu: self.Draw_Bed_Mesh_Menu,
            self.BedMeshScreen: self.Draw_Bed_Mesh,
            self.MeshProfiles: self.Draw_Mesh_Profiles,
            self.FilePreview: self.Draw_File_Preview,
            self.PrintProcess: self.Goto_PrintProcess,
            self.TuneEdit: self._focus_edit_draw,
            self.PrintErrorDetails: self._focus_error_draw,
            self.ScrewsTiltMenu: self.Draw_Screws_Menu,
            self.ScrewsTiltResult: self.Draw_Screws_Result,
            self.ProbeWizardID: self.Draw_Probe_Wizard,
        }.get(self.checkkey)
        if self._restore_power_editor():
            return
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
            if getattr(self, '_power_hold_popup', False):
                if getattr(self, '_power_shutdown_requested', False):
                    return True
                self._power_blocked = self._power_block_reason()
                if event in (self.ENCODER_DIFF_CW, self.ENCODER_DIFF_CCW):
                    selection = event == self.ENCODER_DIFF_CW and not self._power_blocked
                    if selection != self._power_confirm_yes:
                        self._power_confirm_yes = selection
                        self._draw_power_confirmation(buttons_only=True)
                elif event == self.ENCODER_DIFF_ENTER:
                    if self._power_confirm_yes and not self._power_blocked:
                        self._power_off_future = self.pd.power_off_if_on()
                        self._power_shutdown_requested = True
                        self._show_message('Powering off...')
                    else:
                        self._restore_power_origin()
                return True
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
        return False

    def _dispatch_input(self):
        if self.checkkey == self.PowerConfirm and getattr(self, '_power_hold_popup', False):
            self._handle_power_navigation()
            return
        editors = (self.Move_X, self.Move_Y, self.Move_Z, self.Extruder,
                   self.PrintSpeed, self.ETemp, self.BedTemp, self.FanSpeed,
                   self.Homeoffset, self.CaseLightBrightness)
        cached = getattr(self, '_list_render', None)
        if cached and self.checkkey in editors:
            cached['values'].pop(cached['selection'], None)
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
        elif self.checkkey == self.MaintenanceMenu:
            self.HMI_Maintenance_Menu()
        elif self.checkkey == self.BuzzerMenu:
            self.HMI_Buzzer_Menu()
        elif self.checkkey == self.DisplayMenu:
            self.HMI_Display_Menu()
        elif self.checkkey == self.Info:
            self.HMI_Info()
        elif self.checkkey == self.Tune:
            self.HMI_Tune()
        elif self.checkkey == self.TuneEdit:
            self._focus_edit_input()
        elif self.checkkey == self.PrintErrorDetails:
            self._focus_error_input()
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
