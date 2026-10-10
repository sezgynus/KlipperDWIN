import copy
import logging
import math
import re
import time
import uuid
from urllib.parse import quote
from collections.abc import Mapping
from concurrent.futures import Future
from threading import Lock
from background_reads import ReadWorker, ReadPending
from operation_guards import motion_dispatch_guard
from motion_settings import PARAMETERS, validate as validate_motion
from moonraker_client import MoonrakerClient, MoonrakerError
from moonraker_subscription import MoonrakerSubscription
from probe_wizard import ProbeWizard
from screws_tilt import ScrewsTiltSession
from bed_mesh import BedMeshSession
from mmu_control import MMUSession
from preset_store import PresetStore
from printer_state import PrinterState
from printer_capabilities import PrinterCapabilities
from system_info import host_metrics, network_info, updater_version

class xyze_t:
    x = 0.0
    y = 0.0
    z = 0.0
    e = 0.0
    home_x = False
    home_y = False
    home_z = False

    def homing(self):
        self.home_x = False
        self.home_y = False
        self.home_z = False


class AxisEnum:
    X_AXIS = 0
    A_AXIS = 0
    Y_AXIS = 1
    B_AXIS = 1
    Z_AXIS = 2
    C_AXIS = 2
    E_AXIS = 3
    X_HEAD = 4
    Y_HEAD = 5
    Z_HEAD = 6
    E0_AXIS = 3
    E1_AXIS = 4
    E2_AXIS = 5
    E3_AXIS = 6
    E4_AXIS = 7
    E5_AXIS = 8
    E6_AXIS = 9
    E7_AXIS = 10
    ALL_AXES = 0xFE
    NO_AXIS = 0xFF


class HMI_value_t:
    E_Temp = 0
    Bed_Temp = 0
    Fan_speed = 0
    print_speed = 100
    Max_Feedspeed = 0.0
    Max_Acceleration = 0.0
    Max_Jerk = 0.0
    Max_Step = 0.0
    Move_X_scale = 0.0
    Move_Y_scale = 0.0
    Move_Z_scale = 0.0
    Move_E_scale = 0.0
    offset_value = 0.0
    show_mode = 0  # -1: Temperature control    0: Printing temperature


class HMI_Flag_t:
    language = 0
    pause_flag = False
    pause_action = False
    print_finish = False
    done_confirm_flag = False
    select_flag = False
    home_flag = False
    heat_flag = False  # 0: heating done  1: during heating
    ETempTooLow_flag = False
    leveling_offset_flag = False
    feedspeed_axis = AxisEnum()
    acc_axis = AxisEnum()
    jerk_axis = AxisEnum()
    step_axis = AxisEnum()


class buzz_t:
    def tone(self, t, n):
        pass


class material_preset_t:
    def __init__(self, name, hotend_temp=0, bed_temp=0, mainsail_id=None, mainsail_raw=None):
        self.name = str(name)
        self.hotend_temp = hotend_temp
        self.bed_temp = bed_temp
        self.mainsail_id = mainsail_id
        self.mainsail_raw = copy.deepcopy(mainsail_raw) if mainsail_raw is not None else None

    @classmethod
    def from_mainsail(cls, preset, preset_id=None):
        if not isinstance(preset, Mapping) or not str(preset.get('name', '')).strip():
            raise ValueError('Invalid Mainsail preset')
        hotend = bed = 0.0
        values = preset.get('values', {})
        if not isinstance(values, Mapping):
            raise ValueError('Invalid Mainsail preset values')
        for device, setting in values.items():
            if not isinstance(setting, Mapping) or not setting.get('bool', False):
                continue
            value = setting.get('value')
            if isinstance(value, bool):
                raise ValueError('Invalid Mainsail preset value')
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError('Invalid Mainsail preset value')
            if not math.isfinite(value):
                raise ValueError('Invalid Mainsail preset value')
            if value.is_integer():
                value = int(value)
            if device == 'extruder':
                hotend = value
            elif device == 'heater_bed':
                bed = value
        return cls(str(preset['name']).strip(), hotend, bed, preset_id, preset)


class PrinterData:
    Z_PROBE_OFFSET_RANGE_MIN = -20
    Z_PROBE_OFFSET_RANGE_MAX = 20

    buzzer = buzz_t()

    BABY_Z_VAR = 0
    feedrate_percentage = 100
    flow_percentage = 100
    live_velocity = 0.0
    live_extruder_velocity = 0.0
    volumetric_flow = 0.0
    live_position = (0.0, 0.0, 0.0)
    dashboard_fan_pwm = 0
    temphot = 0
    tempbed = 0

    HMI_ValueStruct = HMI_value_t()
    HMI_flag = HMI_Flag_t()

    current_position = xyze_t()

    thermalManager = {
        'temp_bed': {'celsius': 0, 'target': 0},
        'temp_hotend': [{'celsius': 0, 'target': 0}],
        'fan_speed': [0]
    }

    material_preset = [
        material_preset_t('PLA', 200, 60),
        material_preset_t('ABS', 210, 100)
    ]
    files = None
    MACHINE_SIZE = 'unknown'
    SHORT_BUILD_VERSION = "unknown"
    CORP_WEBSITE_E = "github.com/sezgynus/KlipperDWIN"

    def __init__(self, API_Key='', URL='http://127.0.0.1:7125', timeout=5.0, settings_path=None,
                 power_device='Printer'):
        self.client = MoonrakerClient(URL, API_Key, timeout)
        self._read_worker = ReadWorker(timeout)
        self._read_jobs = {}
        self._settings_save = None
        self._files_loading = self._directory_loading = False
        self._file_retry_at = 0.0
        self._directory_retry_at = {}
        self.power_device = str(power_device).strip() or 'Printer'
        # Keep read-only Spoolman telemetry off the serialized printer-command
        # transport. A telemetry timeout must never cancel or delay user commands.
        self.spoolman_client = MoonrakerClient(URL, API_Key, timeout, queue_size=16)
        self._jog_lock = Lock()
        self._jog_restore = None
        self._jog_state_name = '_DWIN_JOG_' + uuid.uuid4().hex
        self.state = PrinterState()
        self.capabilities = PrinterCapabilities()
        self._apply_capabilities(self.capabilities)
        self.status = None
        self.connection_error = None
        self.last_command_error = None
        self.absolute_moves = True
        self.absolute_extrude = True
        self.flow_percentage = 100
        self.live_velocity = 0.0
        self.live_extruder_velocity = 0.0
        self.volumetric_flow = 0.0
        self.live_position = (0.0, 0.0, 0.0)
        self.dashboard_fan_pwm = 0
        self.mmu = None
        self.mmu_session = MMUSession(self)
        self._spoolman_percentages = {}
        self._spoolman_futures = {}
        self._spoolman_refresh_at = {}
        self.file_name = ''
        self.job_Info = {'virtual_sdcard': {'is_active': False, 'progress': 0},
                         'print_stats': {'state': 'standby', 'print_duration': 0,
                                         'filename': ''}}
        self.current_position = xyze_t()
        self.HMI_ValueStruct = HMI_value_t()
        self.HMI_flag = HMI_Flag_t()
        self.thermalManager = copy.deepcopy(type(self).thermalManager)
        self.material_preset = []
        self.preset_store = PresetStore(settings_path)
        self.settings_error = None
        self.mainsail_presets_error = None
        self.presets_from_mainsail = False
        self.preset_revision = 0
        self.system_info = {
            'klipperdwin': 'Unavailable',
            'moonraker': 'Unavailable',
            'mainsail': 'Unavailable',
            'network': 'Unknown',
            'ip': 'Unavailable',
            'host_cpu': None,
            'host_temp': None,
            'mcus': (),
        }
        self._system_info_refresh_at = 0.0
        self._system_info_refresh_interval = 5.0
        self._preset_refresh_at = 0.0
        self._preset_refresh_interval = 5.0
        self.refresh_mainsail_presets(force=True)
        try:
            saved = self.preset_store.load()
            if saved is not None and not self.presets_from_mainsail and not self.material_preset:
                self.material_preset = [material_preset_t(**item) for item in saved]
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            self.settings_error = str(error)
            logging.warning('Cannot load presets from %s: %s', self.preset_store.path, error)
        if not self.material_preset and not self.presets_from_mainsail:
            self.material_preset = copy.deepcopy(type(self).material_preset)
        self.files = []
        self.file_error = None
        self._files_loaded = False
        self._file_epoch = -1
        self._file_revision = -1
        self.file_sort = ('modified', True)
        self.file_sort_revision = 0
        self._file_sort_refresh_at = 0.0
        self._directory_cache = {}
        self.subscription = MoonrakerSubscription(URL, API_Key, timeout)
        self.probe_wizard = ProbeWizard(self)
        self.screws_tilt = ScrewsTiltSession(self)
        self.bed_mesh = BedMeshSession(self)

    def _read(self, key, work, stamp=None):
        if stamp is None:
            stamp = self.subscription.snapshot().get('epoch', 0) if hasattr(self, 'subscription') else 0
        job = self._read_jobs.get(key)
        if job is not None and job[0] != stamp:
            job[1].cancel()
            self._read_jobs.pop(key)
            job = None
        if job is None:
            if len(self._read_jobs) >= 32:
                oldest = next(iter(self._read_jobs))
                self._read_jobs.pop(oldest)[1].cancel()
            job = (stamp, self._read_worker.submit(work))
            self._read_jobs[key] = job
        if not job[1].done():
            raise ReadPending()
        self._read_jobs.pop(key)
        return job[1].result()

    def refresh_system_info(self, force=False):
        """Refresh component versions and host IPv4 without mutating printer state."""
        now = time.monotonic()
        if not force and now < self._system_info_refresh_at:
            return False

        previous = dict(self.system_info)
        status, address = network_info()
        current = dict(previous)
        current['network'] = status
        current['ip'] = address
        cpu, temperature = host_metrics()
        current['host_cpu'] = cpu
        current['host_temp'] = temperature
        mcus = []
        if self.state.ready:
            temperatures = []
            for object_name, value in self.state.status.items():
                if (not (object_name.startswith('temperature_sensor ') or
                         object_name.startswith('temperature_fan ')) or
                        not isinstance(value, Mapping)):
                    continue
                setting = next((item for key, item in self.state.settings.items()
                                if key.lower() == object_name.lower()), {})
                if not isinstance(setting, Mapping) or setting.get('sensor_type') != 'temperature_mcu':
                    continue
                # Klipper defaults temperature_mcu sensors to the primary MCU.
                sensor_mcu = setting.get('sensor_mcu', 'mcu')
                if not isinstance(sensor_mcu, str):
                    continue
                try:
                    temperature = float(value.get('temperature'))
                    if math.isfinite(temperature):
                        temperatures.append((sensor_mcu, temperature))
                except (TypeError, ValueError):
                    pass
            for object_name, value in self.state.status.items():
                if object_name != 'mcu' and not object_name.startswith('mcu '):
                    continue
                if not isinstance(value, Mapping):
                    continue
                stats = value.get('last_stats', {})
                load = None
                if isinstance(stats, Mapping):
                    try:
                        task_avg = float(stats.get('mcu_task_avg'))
                        task_stddev = float(stats.get('mcu_task_stddev'))
                        if math.isfinite(task_avg) and math.isfinite(task_stddev):
                            # Match Mainsail's MCU load calculation exactly.
                            ratio = task_avg + (3.0 * task_stddev) / 0.0025
                            load = max(0.0, min(100.0, ratio * 100.0))
                    except (TypeError, ValueError):
                        pass
                temperature = None
                for sensor_mcu, sensor_temperature in temperatures:
                    if object_name.endswith(sensor_mcu):
                        temperature = sensor_temperature
                        break
                mcus.append({'name': object_name, 'load': load,
                             'temperature': temperature,
                             'version': str(value.get('mcu_version') or '')})
            current['mcus'] = tuple(mcus)
        try:
            response = self._read('system_info', lambda: self.client.get('/machine/update/status'))
            versions = response.get('result', {}).get('version_info', {})
            if not isinstance(versions, Mapping):
                raise ValueError('Invalid update-manager status')
            current['klipperdwin'] = updater_version(versions, 'KlipperDWIN', full=True)
            current['moonraker'] = updater_version(versions, 'moonraker', full=True)
            current['mainsail'] = updater_version(versions, 'mainsail')
        except ReadPending:
            return False
        except (MoonrakerError, KeyError, TypeError, ValueError) as error:
            logging.debug('Cannot refresh component versions: %s', error)
        self._system_info_refresh_at = now + self._system_info_refresh_interval
        self.system_info = current
        return current != previous

    @staticmethod
    def _preset_signature(presets):
        return tuple((item.mainsail_id, item.name, item.hotend_temp, item.bed_temp)
                     for item in presets)

    def refresh_mainsail_presets(self, force=False):
        now = time.monotonic()
        if self._settings_save is not None:
            return False
        if not force and now < self._preset_refresh_at:
            return False
        try:
            mainsail = self._read('presets', lambda: self.client.get('/server/database/item?namespace=mainsail&key=presets.presets'))
            self._preset_refresh_at = now + self._preset_refresh_interval
            values = mainsail.get('result', {}).get('value', {})
            if not isinstance(values, Mapping):
                raise ValueError('Invalid Mainsail preset database')
            presets = []
            for preset_id, item in values.items():
                try:
                    presets.append(material_preset_t.from_mainsail(item, preset_id))
                except (ValueError, TypeError) as error:
                    logging.warning('Ignoring invalid Mainsail preset %s: %s', preset_id, error)
            if not presets:
                changed = bool(self.material_preset)
                if changed:
                    self.material_preset = []
                    self.preset_revision += 1
                self.presets_from_mainsail = True
                self.mainsail_presets_error = None
                return changed
            changed = self._preset_signature(presets) != self._preset_signature(self.material_preset)
            if changed:
                self.material_preset = presets
                self.preset_revision += 1
            self.presets_from_mainsail = True
            self.mainsail_presets_error = None
            return changed
        except ReadPending:
            return False
        except (MoonrakerError, KeyError, ValueError, TypeError) as error:
            self._preset_refresh_at = now + self._preset_refresh_interval
            self.mainsail_presets_error = str(error)
            logging.warning('Cannot refresh Mainsail presets: %s', error)
            return False

    def _apply_capabilities(self, caps):
        self.HAS_HOTEND = caps.active_hotend is not None
        self.HOTENDS = len(caps.hotends)
        self.HAS_HEATED_BED = caps.bed is not None
        self.HAS_FAN = caps.fan
        self.HAS_BED_PROBE = caps.probe
        self.HAS_PREHEAT = caps.has_heaters
        self.HAS_ZOFFSET_ITEM = True
        self.HAS_ONESTEP_LEVELING = caps.bed_mesh
        self.PREVENT_COLD_EXTRUSION = True
        hotend = caps.active_hotend
        self.EXTRUDE_MINTEMP = hotend.min_extrude_temp if hotend else 0
        self.EXTRUDE_MAXLENGTH = hotend.max_extrude_distance if hotend else 0
        self.MAX_E_TEMP = hotend.maximum if hotend else 0
        self.MIN_E_TEMP = 0
        self.BED_MAX_TARGET = caps.bed.maximum if caps.bed else 0
        self.MIN_BED_TEMP = 0
        self.X_MIN_POS, self.Y_MIN_POS, self.Z_MIN_POS = caps.axis_minimum
        self.X_MAX_POS, self.Y_MAX_POS, self.Z_MAX_POS = caps.axis_maximum
        self.MACHINE_SIZE = 'x'.join('{:g}'.format(value) for value in caps.build_size)

    def close(self):
        self.subscription.close()
        self._read_worker.close()
        self.spoolman_client.close()
        self.client.close()

    def check_command_results(self):
        from queue import Empty
        while True:
            try:
                path, future = self.client.command_results.get_nowait()
            except Empty:
                return
            if future.cancelled():
                continue
            error = future.exception()
            if error:
                self.last_command_error = str(error)
                logging.error('LCD command %s failed: %s', path, error)

    # ------------- Klipper Function ----------

    def ishomed(self):
        if not self.connection_error and self.current_position.home_x and self.current_position.home_y and self.current_position.home_z:
            return True
        else:
            return False

    # ------------- Moonraker transport ----------

    def getREST(self, path):
        return self.client.get(path)

    def postREST(self, path, json, cleanup=None, report_error=True, dispatch_guard=None):
        snapshot = self.subscription.snapshot()
        if (self.connection_error or not self.state.ready or snapshot['state'] != 'ready'
                or snapshot['epoch'] != self.state.epoch):
            from concurrent.futures import Future
            future = Future()
            future.cleanup_complete = cleanup is not None
            future.set_exception(MoonrakerError('Printer connection is not ready'))
            self.last_command_error = 'Printer connection is not ready'
            return future
        epoch = snapshot['epoch']

        def guard():
            current = self.subscription.snapshot()
            return current['state'] == 'ready' and current['epoch'] == epoch

        def operation_guard():
            return guard() and (dispatch_guard is None or dispatch_guard())

        return self.client.post(path, json, guard=operation_guard, cleanup=cleanup, cleanup_guard=guard, report_error=report_error) if cleanup is not None else self.client.post(path, json, guard=operation_guard, report_error=report_error)

    def power_on_if_off(self):
        """Turn on the configured Moonraker power device only when it is off."""
        payload = {'device': self.power_device, 'action': 'on'}

        def device_is_off():
            result = self.client.get('/machine/device_power/devices').get('result', {})
            devices = result.get('devices', []) if isinstance(result, dict) else []
            target = next((item for item in devices
                           if str(item.get('device', '')).casefold() == self.power_device.casefold()), None)
            if target is None:
                raise MoonrakerError('Configured power device was not found')
            if target.get('status') != 'off':
                raise MoonrakerError('Configured power device is not off')
            payload['device'] = target['device']
            return True

        # This intentionally bypasses postREST(): Moonraker must be able to
        # switch the PSU on while Klipper itself is offline.
        return self.client.post('/machine/device_power/device', payload,
                                guard=device_is_off, report_error=False)

    def power_off_if_on(self):
        """Turn off the configured Moonraker power device only when it is on."""
        payload = {'device': self.power_device, 'action': 'off'}

        def device_is_on():
            result = self.client.get('/machine/device_power/devices').get('result', {})
            devices = result.get('devices', []) if isinstance(result, dict) else []
            target = next((item for item in devices
                           if str(item.get('device', '')).casefold() == self.power_device.casefold()), None)
            if target is None:
                raise MoonrakerError('Configured power device was not found')
            if target.get('status') != 'on':
                raise MoonrakerError('Configured power device is not on')
            payload['device'] = target['device']
            return True

        return self.client.post('/machine/device_power/device', payload,
                                guard=device_is_on, report_error=False)

    def init_Webservices(self):
        # Bootstrap and reconnection run on the subscription thread.
        return self.update_variable()

    def refresh_file_sort(self, force=False):
        now = time.monotonic()
        if not force and now < self._file_sort_refresh_at:
            return False
        try:
            response = self._read('file_sort', lambda: self.client.get('/server/database/item?namespace=mainsail&key=view.gcodefiles'))
            self._file_sort_refresh_at = now + 5.0
            values = response.get('result', {}).get('value', {})
            if not isinstance(values, Mapping):
                raise ValueError('Invalid file sort settings')
            field = values.get('sortBy', 'modified')
            descending = values.get('sortDesc', True)
            if field not in ('filename', 'modified', 'size') or not isinstance(descending, bool):
                field, descending = 'modified', True
            preference = (field, descending)
        except ReadPending:
            return False
        except (MoonrakerError, KeyError, TypeError, ValueError, AttributeError):
            self._file_sort_refresh_at = now + 5.0
            preference = ('modified', True)
        if preference == self.file_sort:
            return False
        self.file_sort = preference
        self.file_sort_revision += 1
        self._sort_files()
        return True

    def _sort_files(self, entries=None):
        items = self.files if entries is None else entries
        field, descending = self.file_sort
        # Deterministic ties and full paths preserve distinct nested files.
        items.sort(key=lambda item: (item['path'].casefold(), item['path']))
        def value(item):
            if field == 'filename':
                return item['path'].rstrip('/').rsplit('/', 1)[-1].casefold()
            number = item.get(field)
            if isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number):
                return (True, number)
            return (False, 0)
        items.sort(key=value, reverse=descending)

    def GetFiles(self, refresh=False):
        self.refresh_file_sort()
        if not self._files_loaded or refresh:
            if time.monotonic() < self._file_retry_at and not refresh:
                return tuple(item['path'] for item in self.files)
            self._files_loaded = False
            self._files_loading = True
            try:
                files = self._read('files', lambda: self.getREST('/server/files/list'),
                                   (self.state.epoch, self.state.file_revision))['result']
                if not isinstance(files, list) or not all(
                        isinstance(item, dict) and isinstance(item.get('path'), str)
                        and item['path'] for item in files):
                    raise ValueError('Invalid file list')
                paths = [item['path'] for item in files]
                if len(paths) != len(set(paths)):
                    raise ValueError('Duplicate file paths')
                self.files = list(files)
                self._sort_files()
                self.file_error = None
                self._files_loaded = True
                self._files_loading = False
                self._file_retry_at = 0.0
            except ReadPending:
                pass
            except (MoonrakerError, KeyError, TypeError, ValueError) as exc:
                self.file_error = str(exc)
                self._files_loaded = False
                self._files_loading = False
                self._file_retry_at = time.monotonic() + 5
        return tuple(item['path'] for item in self.files)

    def GetDirectory(self, directory=''):
        self._directory_loading = False
        self.GetFiles()
        if self.file_error or self._files_loading:
            return ()
        if directory and any(part in ('', '.', '..') for part in directory.split('/')):
            raise ValueError('Invalid directory path')
        key = (self.state.epoch, self.state.file_revision, directory)
        try:
            if key not in self._directory_cache:
                if time.monotonic() < self._directory_retry_at.get(key, 0):
                    return ()
                self._directory_loading = True
                response = self._read(('directory', directory),
                    lambda: self.getREST('/server/files/directory?path=' + quote('gcodes/' + directory, safe='')), key)
                data = response['result']
                entries = []
                for group, name_key, is_dir in (('dirs', 'dirname', True), ('files', 'filename', False)):
                    for item in data[group]:
                        name = item[name_key]
                        if not isinstance(name, str) or not name or '/' in name or name in ('.', '..'):
                            raise ValueError('Invalid directory entry')
                        if name.startswith('.') or (not is_dir and not name.lower().endswith('.gcode')):
                            continue
                        path = (directory + '/' if directory else '') + name
                        entries.append(dict(item, path=path + ('/' if is_dir else ''), isDirectory=is_dir))
                if len({item['path'] for item in entries}) != len(entries):
                    raise ValueError('Duplicate directory entries')
                # Keep only the current revision, retaining directories visited in it.
                self._directory_cache = {k: v for k, v in self._directory_cache.items() if k[:2] == key[:2]}
                self._directory_cache[key] = entries
                self._directory_loading = False
                self._directory_retry_at.pop(key, None)
            entries = list(self._directory_cache[key])
            self._sort_files(entries)
            entries.sort(key=lambda item: not item['isDirectory'])
            return tuple(item['path'] for item in entries)
        except ReadPending:
            return ()
        except (MoonrakerError, KeyError, TypeError, ValueError) as error:
            self._directory_loading = False
            self._directory_retry_at[key] = time.monotonic() + 5
            self.file_error = str(error)
            self._files_loaded = False
            return ()

    @staticmethod
    def _spool_remaining_percent(spool):
        try:
            remaining = float(spool['remaining_weight'])
            initial = float(spool.get('initial_weight') or 0)
            if initial <= 0:
                used = float(spool.get('used_weight') or 0)
                initial = remaining + used
            if (not math.isfinite(remaining) or not math.isfinite(initial)
                    or initial <= 0 or remaining < 0):
                return None
            return max(0, min(100, int(round(remaining * 100.0 / initial))))
        except (KeyError, TypeError, ValueError):
            return None

    def _poll_spoolman_percentages(self, spool_ids):
        now = time.monotonic()
        changed = False
        valid_ids = {int(sid) for sid in spool_ids
                     if isinstance(sid, (int, float)) and int(sid) > 0}

        for sid, future in list(self._spoolman_futures.items()):
            if not future.done():
                continue
            del self._spoolman_futures[sid]
            self._spoolman_refresh_at[sid] = now + 15.0
            try:
                response = future.result()
                spool = response['result']
                percent = self._spool_remaining_percent(spool)
            except (KeyError, TypeError, ValueError, MoonrakerError):
                percent = None
            if percent is None:
                # Never present an old percentage as current after a failed refresh.
                if sid in self._spoolman_percentages:
                    del self._spoolman_percentages[sid]
                    changed = True
            elif self._spoolman_percentages.get(sid) != percent:
                self._spoolman_percentages[sid] = percent
                changed = True

        for sid in list(self._spoolman_percentages):
            if sid not in valid_ids:
                del self._spoolman_percentages[sid]
                changed = True
        for sid in list(self._spoolman_refresh_at):
            if sid not in valid_ids:
                del self._spoolman_refresh_at[sid]

        for sid in valid_ids:
            if sid in self._spoolman_futures or now < self._spoolman_refresh_at.get(sid, 0):
                continue
            self._spoolman_futures[sid] = self.spoolman_client.post(
                '/server/spoolman/proxy',
                {'request_method': 'GET', 'path': '/v1/spool/%d' % sid},
                report_error=False)
        return changed

    def update_variable(self):
        self.check_command_results()
        if self._settings_save is not None and self._settings_save.done():
            try:
                self._settings_save.result()
                self.settings_error = None
            except Exception as error:
                self.settings_error = str(error)
            self._settings_save = None
            self._preset_refresh_at = 0.0
        presets_changed = self.refresh_mainsail_presets()
        sort_changed = self.refresh_file_sort() if self._files_loaded else False
        try:
            state = PrinterState.from_snapshot(self.subscription.snapshot())
            if not state.ready:
                self.state = state
                self._files_loaded = False
                self.connection_error = state.error or 'Klipper is not ready'
                return False
            data = state.status
            caps = PrinterCapabilities.from_state(state)
            gcm = data['gcode_move']
            toolhead = data['toolhead']
            # Validate required fields before committing the snapshot.
            job = {'virtual_sdcard': data['virtual_sdcard'], 'print_stats': data['print_stats']}
            print_state = job['print_stats']['state']
            position = toolhead['position']
            x, y, z, e = position[:4]
            origin = gcm['homing_origin'][2]
            absolute_moves = gcm['absolute_coordinates']
            absolute_extrude = gcm['absolute_extrude']
            speed_percent = float(gcm.get('speed_factor', 1.0)) * 100
            flow_percent = float(gcm.get('extrude_factor', 1.0)) * 100
            if not math.isfinite(speed_percent) or speed_percent <= 0:
                raise ValueError('Invalid feedrate percentage')
            if not math.isfinite(flow_percent) or flow_percent <= 0:
                raise ValueError('Invalid flow percentage')
            motion = data.get('motion_report', {})
            live_position = motion.get('live_position', position)
            if not isinstance(live_position, (list, tuple)) or len(live_position) < 3:
                raise ValueError('Invalid live position')
            live_xyz = tuple(float(value) for value in live_position[:3])
            live_velocity = float(motion.get('live_velocity', 0.0))
            live_extruder_velocity = float(motion.get('live_extruder_velocity', 0.0))
            if (not all(math.isfinite(value) for value in live_xyz)
                    or not math.isfinite(live_velocity)
                    or not math.isfinite(live_extruder_velocity)):
                raise ValueError('Invalid live motion telemetry')
            hotend_settings = state.settings.get(caps.active_hotend.name, {}) if caps.active_hotend else {}
            filament_diameter = float(hotend_settings.get('filament_diameter', 1.75))
            if not math.isfinite(filament_diameter) or filament_diameter <= 0:
                raise ValueError('Invalid filament diameter')
            filament_area = math.pi * (filament_diameter * 0.5) ** 2
            volumetric_flow = live_extruder_velocity * filament_area
            thermal = copy.deepcopy(self.thermalManager)
            for obj, target in [(caps.active_hotend.name if caps.active_hotend else None, thermal['temp_hotend'][0]),
                                ('heater_bed' if caps.bed else None, thermal['temp_bed'])]:
                if obj is None:
                    target['celsius'] = target['target'] = 0
                else:
                    target['celsius'] = int(data[obj]['temperature'])
                    target['target'] = int(data[obj]['target'])
            thermal['fan_speed'][0] = int(data['fan']['speed'] * 100) if caps.fan else 0
            mmu = None
            spoolman_changed = False
            if 'mmu' in data:
                try:
                    raw_mmu = data['mmu']
                    num_gates = int(raw_mmu.get('num_gates', 0))
                    gate = int(raw_mmu.get('gate', -1))
                    colors = raw_mmu.get('gate_color_rgb', [])
                    statuses = raw_mmu.get('gate_status', [])
                    spool_ids = tuple(raw_mmu.get('gate_spool_id', [])[:num_gates])
                    spoolman_changed = self._poll_spoolman_percentages(spool_ids)
                    if num_gates < 1 or len(colors) < num_gates or len(statuses) < num_gates:
                        raise ValueError('Invalid MMU status')
                    normalized_colors = []
                    for color in colors[:num_gates]:
                        if (not isinstance(color, (list, tuple)) or len(color) != 3
                                or not all(isinstance(value, (int, float)) and math.isfinite(value)
                                           for value in color)):
                            raise ValueError('Invalid MMU gate color')
                        # Happy Hare publishes gate_color_rgb as normalized RGB floats.
                        normalized_colors.append(tuple(max(0.0, min(1.0, float(value)))
                                                       for value in color))
                    unit_name = 'MMU'
                    machine = data.get('mmu_machine', {})
                    # Happy Hare reports the selected unit as "unit" on current
                    # releases and "unit_selected" on older controller status.
                    unit_index = int(raw_mmu.get('unit',
                                                 raw_mmu.get('unit_selected', 0)))
                    unit_info = machine.get('unit_%d' % unit_index, {})
                    if isinstance(unit_info, Mapping):
                        unit_name = str(unit_info.get('display_name') or
                                        unit_info.get('name') or 'MMU')
                    exit_led_object = 'unit%d_mmu_exit_leds' % unit_index
                    exit_led_data = data.get(exit_led_object, {}).get('color_data', ())
                    exit_led_rgb = ()
                    if len(exit_led_data) >= num_gates:
                        normalized_leds = []
                        for led_color in exit_led_data[:num_gates]:
                            if (not isinstance(led_color, (list, tuple)) or len(led_color) < 3
                                    or not all(isinstance(value, (int, float)) and math.isfinite(value)
                                               for value in led_color[:3])):
                                normalized_leds = []
                                break
                            normalized_leds.append(tuple(max(0.0, min(1.0, float(value)))
                                                         for value in led_color[:3]))
                        exit_led_rgb = tuple(normalized_leds)
                    mmu = {'num_gates': num_gates, 'gate': gate,
                           'gate_status': tuple(int(value) for value in statuses[:num_gates]),
                           'gate_color_rgb': tuple(normalized_colors),
                           'gate_spool_id': spool_ids,
                           'remaining_percent': tuple(
                               self._spoolman_percentages.get(int(sid))
                               if isinstance(sid, (int, float)) and int(sid) > 0 else None
                               for sid in spool_ids),
                           'exit_led_rgb': exit_led_rgb,
                           'name': unit_name,
                           'filament': str(raw_mmu.get('filament', 'Unknown'))}
                except (KeyError, TypeError, IndexError, ValueError, OverflowError) as exc:
                    # Optional MMU telemetry must not make the core printer UI offline.
                    logging.warning('Ignoring invalid MMU status: %s', exc)
                    mmu = None
                    spoolman_changed = False
        except (MoonrakerError, KeyError, TypeError, IndexError, ValueError) as exc:
            self.connection_error = str(exc)
            return False
        self.connection_error = None
        changed = state != self.state or spoolman_changed or presets_changed or sort_changed
        self.state = state
        self.capabilities = caps
        self._apply_capabilities(caps)
        self.SHORT_BUILD_VERSION = state.software_version
        if state.epoch != self._file_epoch:
            self._files_loaded = False
            self.files = []
            self._file_epoch = state.epoch
        if state.file_revision != self._file_revision:
            self._files_loaded = False
            self._file_revision = state.file_revision
        self.thermalManager = thermal
        self.feedrate_percentage = round(speed_percent)
        self.flow_percentage = round(flow_percent)
        self.live_velocity = live_velocity
        self.live_extruder_velocity = live_extruder_velocity
        self.volumetric_flow = volumetric_flow
        self.live_position = live_xyz
        self.dashboard_fan_pwm = round(data['fan']['speed'] * 255) if caps.fan else 0
        self.mmu = mmu
        self.absolute_moves = absolute_moves
        self.absolute_extrude = absolute_extrude
        self.current_position.x, self.current_position.y, self.current_position.z, self.current_position.e = x, y, z, e
        homed = toolhead.get('homed_axes', '')
        self.current_position.home_x = 'x' in homed
        self.current_position.home_y = 'y' in homed
        self.current_position.home_z = 'z' in homed
        self.BABY_Z_VAR = origin
        self.HMI_ValueStruct.offset_value = origin * 100
        self.job_Info = job
        self.file_name = job['print_stats'].get('filename', '')
        self.status = print_state
        self.HMI_flag.print_finish = print_state == 'complete'
        return changed

    def printingIsPaused(self):
        return self.job_Info['print_stats']['state'] == "paused" or self.job_Info['print_stats']['state'] == "pausing"

    def getPercent(self):
        # Paused/terminal jobs retain their statistics even when SD execution stops.
        if self.job_Info['print_stats']['state'] == 'standby':
            return 0
        return max(0, min(100, self.job_Info['virtual_sdcard']['progress'] * 100))

    def duration(self):
        if self.job_Info['print_stats']['state'] == 'standby':
            return 0
        return self.job_Info['print_stats'].get('print_duration', 0)

    def remain(self):
        if self.status in ('complete', 'cancelled', 'error'):
            return 0
        percent = self.getPercent()
        duration = self.duration()
        if percent:
            total = duration / (percent / 100)
            return total - duration
        return 0

    def openAndPrintFile(self, path):
        if self.jog_recovery_required:
            raise ValueError('Restore jog state before starting a print')
        if (not isinstance(path, str) or not self._files_loaded or self.file_error
                or path not in {item['path'] for item in self.files}):
            raise ValueError('Selected file is no longer available')
        if self.status in ('printing', 'paused', 'pausing'):
            raise ValueError('A print is already active')
        return self.postREST('/printer/print/start', json={'filename': path})

    def cancel_job(self): #fixed
        return self.postREST('/printer/print/cancel', json=None)

    def pause_job(self): #fixed
        return self.postREST('/printer/print/pause', json=None)

    def resume_job(self): #fixed
        if self.jog_recovery_required:
            raise ValueError('Restore jog state before resuming')
        return self.postREST('/printer/print/resume', json=None)

    def set_feedrate(self, fr):
        fr = float(fr)
        if not math.isfinite(fr) or fr <= 0:
            raise ValueError('Feedrate percentage must be positive')
        return self.sendGCode('M220 S{:g}'.format(fr))

    def motion_settings(self):
        if not self.state.ready:
            return ()
        toolhead = self.state.status.get('toolhead', {})
        available = []
        for field, argument, label, step in PARAMETERS:
            if field in toolhead:
                try:
                    value = validate_motion(field, toolhead[field])
                except (TypeError, ValueError):
                    continue
                available.append((field, argument, label, step, value))
        return tuple(available)

    def set_motion_limit(self, field, value):
        setting = next((item for item in self.motion_settings() if item[0] == field), None)
        if setting is None:
            raise ValueError('Motion setting is unavailable')
        value = validate_motion(field, value)
        return self.sendGCode('SET_VELOCITY_LIMIT {}={:g}'.format(setting[1], value))

    def home(self, homeZ=False): #fixed using gcode
        script = 'G28 X Y'
        if homeZ:
            script += (' Z')
        return self.sendGCode(script)

    def _jog(self, axis, value, speed, absolute):
        if self.jog_recovery_required:
            raise ValueError('Restore the preceding jog state before moving')
        axis = str(axis).upper()
        if axis not in ('X', 'Y', 'Z', 'E'):
            raise ValueError('Invalid jog axis')
        value, speed = float(value), float(speed)
        if not math.isfinite(value) or not math.isfinite(speed) or speed <= 0:
            raise ValueError('Invalid jog value or speed')
        state = self.state
        if not state.ready or self.connection_error:
            raise ValueError('Printer is unavailable')
        if state.status['print_stats']['state'] in ('printing', 'paused', 'pausing'):
            raise ValueError('Jogging is unavailable during a print')
        toolhead = state.status['toolhead']
        # Use command-space position before transforms such as bed mesh.
        position = state.status['gcode_move']['position']
        index = 'XYZE'.index(axis)
        current = float(position[index])
        if not math.isfinite(current):
            raise ValueError('Invalid printer position')
        delta = value - current if absolute else value
        target = current + delta
        if axis == 'E':
            heater = self.capabilities.active_hotend
            if heater is None or not state.status.get(heater.name, {}).get('can_extrude', False):
                raise ValueError('Extruder is unavailable or too cold')
            if abs(delta) > heater.max_extrude_distance:
                raise ValueError('Extrusion exceeds configured distance')
        else:
            if axis.lower() not in toolhead.get('homed_axes', ''):
                raise ValueError('Axis must be homed before jogging')
            if not self.capabilities.axis_minimum[index] <= target <= self.capabilities.axis_maximum[index]:
                raise ValueError('Jog exceeds configured axis range')
        max_velocity = float(toolhead['max_velocity'])
        if axis == 'Z':
            max_velocity = min(max_velocity, float(state.settings.get('printer', {}).get('max_z_velocity', max_velocity)))
        if not math.isfinite(max_velocity) or max_velocity <= 0:
            raise ValueError('Invalid configured velocity')
        speed = min(speed, max_velocity * 60)
        if delta == 0:
            return None
        # Klipper saves/restores feed and extrusion factors as well as G90/M82.
        # Relative displacement avoids changing the G92/work origin.
        name = self._jog_state_name
        restore = 'RESTORE_GCODE_STATE NAME={} MOVE=0'.format(name)
        script = '\n'.join(('SAVE_GCODE_STATE NAME=' + name, 'G91', 'M83',
                            'M220 S100', 'M221 S100',
                            'G1 {}{:g} F{:g}'.format(axis, delta, speed), restore))
        with self._jog_lock:
            self._jog_restore = restore
        try:
            dispatch_guard = motion_dispatch_guard(self, owner='jog', position=True,
                                                   extrusion=heater.name if axis == 'E' else None)
            future = self.sendGCode(script, cleanup=restore, report_error=False, dispatch_guard=dispatch_guard)
        except Exception:
            # Submission failed before sending anything.
            with self._jog_lock:
                self._jog_restore = None
            raise
        if isinstance(future, Future):
            future.add_done_callback(lambda done: self._jog_finished(done, restore))
        return future

    @property
    def jog_recovery_required(self):
        with self._jog_lock:
            return self._jog_restore is not None

    def _jog_finished(self, future, restore):
        if future.cancelled() or getattr(future, 'cleanup_complete', False):
            with self._jog_lock:
                if self._jog_restore == restore:
                    self._jog_restore = None

    def restore_jog_state(self):
        with self._jog_lock:
            restore = self._jog_restore
        if restore is None:
            raise ValueError('No jog state needs recovery')
        if self.status in ('printing', 'paused', 'pausing'):
            raise ValueError('Stop the print before restoring jog state')
        future = self.postREST('/printer/gcode/script', json={'script': restore})
        def recovered(done):
            if not done.cancelled() and done.exception() is None:
                self._jog_finished(done, restore)
        future.add_done_callback(recovered)
        return future

    def moveRelative(self, axis, distance, speed):
        return self._jog(axis, distance, speed, False)

    def moveAbsolute(self, axis, position, speed):
        return self._jog(axis, position, speed, True)

    def clear_gcode_responses(self):
        from queue import Empty
        while True:
            try:
                self.subscription.gcode_responses.get_nowait()
            except Empty:
                return

    def pop_gcode_response(self):
        from queue import Empty
        try:
            return self.subscription.gcode_responses.get_nowait()
        except Empty:
            return None

    def query_case_light(self):
        self.clear_gcode_responses()
        return self.sendGCode('M355')

    def sendGCodeObserved(self, gcode):
        """Dispatch long-running G-Code without waiting for its completion response.

        The returned Future completes when the JSON-RPC notification is written to the
        live Moonraker WebSocket. Physical completion must be confirmed from subscribed
        printer state by the caller.
        """
        snapshot = self.subscription.snapshot()
        if (self.connection_error or not self.state.ready or snapshot['state'] != 'ready'
                or snapshot['epoch'] != self.state.epoch):
            future = Future()
            future.set_exception(MoonrakerError('Printer connection is not ready'))
            return future
        if self.jog_recovery_required:
            raise ValueError('Restore jog state before sending motion commands')
        guard = motion_dispatch_guard(self) if gcode.strip() == 'G28' else None
        return self.subscription.notify('printer.gcode.script', {'script': gcode}, guard=guard)

    def sendGCode(self, gcode, cleanup=None, report_error=True, dispatch_guard=None):
        if cleanup is None and self.jog_recovery_required:
            # Heater/fan shutdown and temperature control do not depend on modes.
            allowed = {'TURN_OFF_HEATERS', 'SET_HEATER_TEMPERATURE', 'M106', 'M107'}
            if any(line.strip().split()[0].upper() not in allowed
                   for line in gcode.splitlines() if line.strip()):
                raise ValueError('Restore jog state before sending motion commands')
        if dispatch_guard is None and gcode.strip() in ('G28', 'G28 X Y', 'G28 X Y Z', 'M84'):
            dispatch_guard = motion_dispatch_guard(self)
        if cleanup is not None:
            return self.postREST('/printer/gcode/script', json={'script': gcode},
                                 cleanup={'script': cleanup}, report_error=report_error, dispatch_guard=dispatch_guard)
        return self.postREST('/printer/gcode/script', json={'script': gcode},
                             report_error=report_error, dispatch_guard=dispatch_guard)

    def disable_all_heaters(self):
        if not self.capabilities.has_heaters:
            return None
        return self.sendGCode('TURN_OFF_HEATERS')

    def cooldown(self):
        commands = []
        if self.capabilities.has_heaters:
            commands.append('TURN_OFF_HEATERS')
        if self.capabilities.fan:
            commands.append(self._fan_command(0))
        if commands:
            return self.sendGCode('\n'.join(commands))

    def zero_fan_speeds(self):
        if self.HAS_FAN:
            return self.setFanSpeed(0)

    @staticmethod
    def _fan_command(percent):
        percent = float(percent)
        if not math.isfinite(percent) or not 0 <= percent <= 100:
            raise ValueError('Fan speed is out of range')
        return 'M106 S{:g}'.format(percent * 255 / 100)

    def setFanSpeed(self, percent):
        if not self.HAS_FAN:
            raise ValueError('Fan is unavailable')
        return self.sendGCode(self._fan_command(percent))

    def preheat(self, profile):
        preset = next((item for item in self.material_preset if item.name == profile), None)
        if preset is None:
            raise ValueError('Unknown preheat profile')
        return self.preHeat(preset.bed_temp, preset.hotend_temp)

    def preheat_preset(self, index):
        if not isinstance(index, int) or not 0 <= index < len(self.material_preset):
            raise ValueError('Unknown preheat preset')
        preset = self.material_preset[index]
        return self.preHeat(preset.bed_temp, preset.hotend_temp)

    def save_settings(self):
        if self.presets_from_mainsail:
            if self._settings_save is not None and not self._settings_save.done():
                return self._settings_save
            writes = []
            for preset in self.material_preset:
                if not preset.mainsail_id or not isinstance(preset.mainsail_raw, Mapping):
                    raise ValueError('Mainsail preset metadata is unavailable')
                raw = copy.deepcopy(preset.mainsail_raw)
                raw['name'] = preset.name
                values = raw.setdefault('values', {})
                for device, target in (('extruder', preset.hotend_temp), ('heater_bed', preset.bed_temp)):
                    if isinstance(values.get(device), Mapping):
                        values[device] = dict(values[device], value=target)
                writes.append({'namespace': 'mainsail', 'key': 'presets.presets.' + preset.mainsail_id, 'value': raw})
            def save():
                for payload in writes:
                    self.client.post('/server/database/item', payload).result(timeout=self.client.timeout + 1)
                return True
            self._settings_save = self._read_worker.submit(save)
            return self._settings_save
        try:
            self.preset_store.save([vars(preset).copy() for preset in self.material_preset])
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            self.settings_error = str(error)
            logging.error('Cannot save presets to %s: %s', self.preset_store.path, error)
            return False
        self.settings_error = None
        return True

    def setExtTemp(self, target, toolnum=None):
        heater = self.capabilities.active_hotend
        if toolnum is not None:
            name = 'extruder' + (str(toolnum) if toolnum else '')
            heater = next((item for item in self.capabilities.hotends if item.name == name), None)
        if heater is None:
            raise ValueError('Hotend is unavailable')
        value = heater.validate_target(target)
        return self.sendGCode('SET_HEATER_TEMPERATURE HEATER={} TARGET={:g}'.format(heater.name, value))

    def setBedTemp(self, target):
        heater = self.capabilities.bed
        if heater is None:
            raise ValueError('Heated bed is unavailable')
        value = heater.validate_target(target)
        return self.sendGCode('SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET={:g}'.format(value))

    def preHeat(self, bedtemp, exttemp, toolnum=None, fan_speed=None):
        # Validate the whole preset before sending any command.
        commands = []
        if self.capabilities.bed:
            value = self.capabilities.bed.validate_target(bedtemp)
            commands.append('SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET={:g}'.format(value))
        heater = self.capabilities.active_hotend
        if toolnum is not None:
            name = 'extruder' + (str(toolnum) if toolnum else '')
            heater = next((item for item in self.capabilities.hotends if item.name == name), None)
            if heater is None:
                raise ValueError('Hotend is unavailable')
        if heater:
            value = heater.validate_target(exttemp)
            commands.append('SET_HEATER_TEMPERATURE HEATER={} TARGET={:g}'.format(heater.name, value))
        if fan_speed is not None and self.capabilities.fan:
            commands.append(self._fan_command(fan_speed))
        if commands:
            return self.sendGCode('\n'.join(commands))

    def setZOffset(self, offset):
        offset = float(offset)
        if not math.isfinite(offset) or not self.Z_PROBE_OFFSET_RANGE_MIN <= offset <= self.Z_PROBE_OFFSET_RANGE_MAX:
            raise ValueError('Runtime Z offset is outside the supported range')
        return self.sendGCode('SET_GCODE_OFFSET Z=%s MOVE=1' % offset)