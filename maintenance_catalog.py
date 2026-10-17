"""Static Maintenance test *definitions*, not discovered or runnable tests.

Discovery reports possible methods. Catalog entries describe required evidence
and the safety domain for a future registered adapter. No adapter is registered
here: no entry may be executed or considered PASSED by importing this module.
There is no I/O, G-code, status polling, or side effect at import time.
"""
from dataclasses import dataclass

from maintenance_discovery import (
    AUTOMATIC, USER, EXTERNAL, CALIBRATION, INFORMATION, NONE,
    ALWAYS_HIDDEN, FEATURE_COUNT, _index_for,
)


_METHOD_BITS = {
    'A': AUTOMATIC, 'U': USER, 'E': EXTERNAL,
    'K': CALIBRATION, 'I': INFORMATION, '-': NONE,
}
_SCOPES = frozenset(('global', 'device', 'mixed'))
_PROFILES = frozenset((
    'read_only', 'guided', 'fan', 'heater', 'motion', 'calibration',
    'actuator', 'extrusion', 'mmu', 'hidden',
))


@dataclass(frozen=True, slots=True)
class TestDefinition:
    feature_id: str
    title: str
    scope: str
    methods: int
    evidence_contract: str
    safety_profile: str
    adapter_id: str | None = None

    @property
    def implemented(self):
        """Adapter presence must be explicit, never inferred from discovery."""
        return self.adapter_id is not None


# Ordered by the established 121-ID discovery contract. 'E' = EXTERNAL;
# 'I' = INFORMATION, which is a view and never a physical test PASS.
# Evidence names specify requirements, not an implemented evidence verifier.
_ROWS = """F01|Part fan rotation|device|AU|observed_rotation_or_tachometer_rpm|fan
F02|Part fan speed steps|device|AU|observed_speed_change_or_rpm|fan
F03|Fan RPM response|device|A|fresh_stable_rpm_samples|fan
F04|Generic fan rotation|device|AU|observed_rotation_or_tachometer_rpm|fan
F05|Generic fan speed steps|device|AU|observed_speed_change_or_rpm|fan
F06|Heater fan activation|device|AU|natural_heater_trigger_and_fan_feedback|heater
F07|Heater fan RPM|device|A|fresh_tachometer_rpm|heater
F08|Controller fan activation|device|AU|natural_trigger_and_fan_feedback|motion
F09|Temperature fan tracking|device|I|temperature_fan_status|read_only
F10|Temperature fan response|device|AU|safe_thermal_trigger_and_fan_feedback|heater
F11|Fan stall and RPM trend|device|AI|fresh_tachometer_series|fan
F12|Minimum usable fan PWM|device|AU|stable_rotation_at_pwm_or_rpm|fan
F13|Fan thermal comparison|device|A|repeatable_temperature_ab_series|heater
H01|Heater warmup|device|A|fresh_temperature_rise_after_command|heater
H02|Extruder PID calibration|device|K|klipper_pid_calibration_evidence|heater
H03|Bed PID calibration|device|K|klipper_pid_calibration_evidence|heater
H04|Generic heater PID calibration|device|K|klipper_pid_calibration_evidence|heater
H05|Heating rate|device|A|timestamped_temperature_series|heater
H06|Time to target|device|A|timestamped_target_and_temperature_series|heater
H07|Temperature overshoot|device|A|target_and_peak_temperature_series|heater
H08|Temperature stability|device|A|steady_state_temperature_series|heater
H09|Cooling rate|device|A|safe_cooling_temperature_series|heater
H10|Heater performance trend|device|AI|compatible_baseline_and_temperature_series|read_only
H11|Heater duty cycle|device|I|reported_heater_power_fraction|read_only
H12|Estimated heater energy|device|I|validated_nominal_power_and_duty_history|read_only
H13|Heater response warning|device|A|fresh_target_power_temperature_series|heater
H14|Temperature sensor reading|device|I|timestamped_sensor_value|read_only
H15|Paired sensor deviation|global|AI|verified_colocated_sensor_pair|read_only
H16|Environmental telemetry|device|I|reported_humidity_pressure_or_gas|read_only
H17|Temperature probe calibration|global|K|klipper_temperature_probe_result|calibration
H18|Fan assisted cooling comparison|device|A|repeatable_fan_heater_ab_series|heater
M01|Physical endstop response|mixed|AU|press_release_firmware_transitions|guided
M02|Virtual endstop manual press|global|-|unavailable|hidden
M03|Homing completion|global|K|klipper_homing_state|motion
M04|Stepper coarse motion|device|U|user_observed_stepper_motion|motion
M05|Axis coarse travel|device|U|user_observed_axis_travel|motion
M06|Measured axis travel|device|E|external_distance_measurement|motion
M07|TMC driver status|device|AI|fresh_driver_specific_status_registers|read_only
M08|TMC driver temperature|device|AI|fresh_driver_temperature_reading|read_only
M09|TMC configured current|device|I|reported_driver_current_setting|read_only
M10|Reserved unused ID|device|-|unavailable|hidden
M11|Stepper enable state|global|I|reported_stepper_enable_state|read_only
M12|Endstop phase calibration|mixed|IK|klipper_endstop_phase_evidence|calibration
M13|Angle sensor status|global|I|reported_angle_sensor_state|read_only
M14|Motion status|global|I|reported_commanded_motion_state|read_only
M15|Manual stepper motion|device|UE|allowlisted_motion_and_user_or_instrument|motion
M16|Multiple carriage status|global|I|reported_carriage_mode|read_only
M17|Raw force move or register writes|global|-|unavailable|hidden
P01|Probe trigger response|global|A|fresh_probe_trigger_state|guided
P02|Load cell tap response|global|AU|fresh_load_cell_tap_signal|guided
P03|Probe repeatability|global|A|klipper_probe_accuracy_samples|motion
P04|Single probe measurement|global|A|klipper_probe_measurement|motion
P05|Probe Z offset wizard|global|K|guided_probe_calibration|calibration
P06|Physical Z endstop calibration|global|KU|guided_endstop_calibration|calibration
P07|Automatic bed mesh|global|K|klipper_mesh_calibration_result|calibration
P08|Manual bed mesh|global|KU|guided_manual_mesh_result|calibration
P09|Bed mesh inspection|global|I|valid_mesh_matrix|read_only
P10|Bed mesh drift|global|AI|compatible_baseline_and_meshes|read_only
P11|Screws tilt adjustment|global|K|klipper_screws_tilt_result|calibration
P12|Manual bed screws|global|K|guided_bed_screws_result|calibration
P13|Z tilt adjustment|global|K|klipper_z_tilt_result|calibration
P14|Quad gantry leveling|global|K|klipper_quad_gantry_result|calibration
P15|Bed tilt calibration|global|K|klipper_bed_tilt_result|calibration
P16|Delta calibration|global|K|klipper_delta_calibration_result|calibration
P17|Axis twist calibration|global|K|klipper_axis_twist_result|calibration
P18|Eddy probe calibration|global|K|klipper_eddy_calibration_result|calibration
P19|BLTouch deploy and stow|global|U|user_observed_probe_deploy_stow|actuator
P20|Load cell force diagnostics|global|AI|fresh_validated_force_samples|read_only
P21|Dimensional skew measurement|global|EK|external_dimensional_reference|calibration
P22|Eddy temperature compensation|global|K|klipper_temperature_compensation_result|calibration
R01|Accelerometer reading|device|AI|fresh_accelerometer_samples|read_only
R02|Axis resonance measurement|mixed|A|validated_axis_acceleration_spectrum|motion
R03|Accelerometer noise floor|mixed|A|fresh_accelerometer_noise_samples|read_only
R04|Input shaper calibration|mixed|K|validated_shaper_calibration_result|calibration
R05|Resonance trend|global|AI|compatible_resonance_baseline|read_only
R06|Belt resonance comparison|global|AI|comparable_belt_spectra|motion
R07|Resonance without accelerometer|global|-|unavailable|hidden
R08|Open loop micro motion accuracy|global|-|unavailable|hidden
E01|Coarse filament extrusion|global|U|user_observed_filament_extrusion|extrusion
E02|Measured extrusion distance|global|E|external_filament_distance_measurement|extrusion
E03|Filament presence sensor|device|AU|fresh_insert_remove_sensor_transitions|guided
E04|Filament motion sensor|device|A|fresh_filament_motion_sensor_signal|extrusion
E05|Filament width sensor|device|AEI|fresh_width_reading_or_reference_measurement|read_only
E06|Filament diameter trend|device|AI|timestamped_diameter_samples|read_only
E07|Filament path motion|global|U|user_observed_filament_path|extrusion
E08|Load cell diagnostics|device|AI|fresh_load_cell_samples|read_only
E09|Load cell calibration|device|EK|traceable_reference_mass|calibration
E10|Unsupported automatic clog detection|global|-|unavailable|hidden
E11|MMU gate sensor diagnostics|global|AU|fresh_mmu_sensor_transitions|mmu
E12|MMU mechanical diagnostics|global|AU|allowlisted_mmu_motion_observation|mmu
E13|Abrasive material usage history|global|I|linked_spool_and_usage_records|read_only
E14|Filament drying calibration|global|K|declared_dryer_and_safe_profile|heater
E15|Chamber humidity|global|I|declared_chamber_humidity_sensor|read_only
S01|Host utilization|global|I|fresh_host_cpu_and_memory_stats|read_only
S02|Host CPU temperature|global|I|fresh_host_cpu_temperature|read_only
S03|Host throttling status|global|I|fresh_undervoltage_throttle_flags|read_only
S04|Storage information|global|I|fresh_disk_capacity_response|read_only
S05|Network throughput|global|I|fresh_host_network_counters|read_only
S06|MCU telemetry|global|I|fresh_mcu_statistics|read_only
S07|CAN bus diagnostics|device|AI|fresh_can_error_counters|read_only
S08|Klipper status and warnings|global|I|fresh_webhooks_status|read_only
S09|Recent G code events|global|I|recent_gcode_store_entries|read_only
S10|Recorded print history|global|I|bounded_moonraker_history|read_only
S11|Maintenance history|global|I|versioned_maintenance_records|read_only
S12|Heater and fan usage counters|global|I|persistent_usage_counters|read_only
S13|Axis travel counters|global|I|authoritative_travel_counter|read_only
S14|Petrel UART diagnostics|global|I|instrumented_uart_counters|read_only
S15|Petrel encoder diagnostics|global|IU|instrumented_encoder_events|read_only
S16|Petrel LCD diagnostics|global|IU|validated_display_asset_or_user_check|guided
S17|Backlight observation|global|U|user_observed_brightness_change|guided
S18|Audible output observation|device|U|user_observed_audible_tone|guided
S19|Software update information|global|I|reported_update_manager_status|read_only
S20|Diagnostic report export|global|I|versioned_sanitized_report|read_only
O01|Safe button response|device|AU|allowlisted_button_state_transitions|guided
O02|Safe servo movement|device|U|allowlisted_servo_observation|actuator
O03|Safe auxiliary output|device|U|allowlisted_output_observation|actuator
O04|LED output observation|device|U|user_observed_led_color|actuator
O05|Ambient monitor|global|I|declared_ambient_sensor_reading|read_only
O06|Guided servicing|global|U|user_confirmed_service_action|guided
O07|Missing MMU pseudo capability|global|-|unavailable|hidden
O08|Unknown macro pseudo capability|global|-|unavailable|hidden
"""


def _build_catalog():
    definitions = []
    seen = set()
    for line in _ROWS.splitlines():
        feature, title, scope, keys, evidence, profile = line.split('|')
        index = _index_for(feature)
        if feature in seen or index != len(definitions):
            raise ValueError('Duplicate or misordered Maintenance feature: ' + feature)
        seen.add(feature)
        if scope not in _SCOPES or profile not in _PROFILES:
            raise ValueError('Unknown Maintenance catalog scope/profile')
        if len(keys) != len(set(keys)) or any(key not in _METHOD_BITS for key in keys):
            raise ValueError('Invalid Maintenance catalog method')
        methods = NONE
        for key in keys:
            methods |= _METHOD_BITS[key]
        if (feature in ALWAYS_HIDDEN) != (methods == NONE and profile == 'hidden'):
            raise ValueError('Hidden Maintenance feature contract mismatch')
        definitions.append(TestDefinition(
            feature, title, scope, methods, evidence, profile))
    if len(definitions) != FEATURE_COUNT:
        raise ValueError('Maintenance catalog must cover every discovery ID')
    return tuple(definitions)


CATALOG = _build_catalog()


def definition_for(feature_id):
    """Retrieve one immutable definition; malformed/unknown IDs fail closed."""
    index = _index_for(feature_id)
    entry = CATALOG[index]
    if entry.feature_id != feature_id:
        raise ValueError('Noncanonical Maintenance feature ID')
    return entry


def candidate_methods(feature_id, discovered_mask):
    """Potential overlap only; never an execution permission or PASS."""
    entry = definition_for(feature_id)
    if not isinstance(discovered_mask, int) or isinstance(discovered_mask, bool):
        raise ValueError('Invalid discovered method mask')
    if discovered_mask < 0 or discovered_mask & ~31:
        raise ValueError('Invalid discovered method mask')
    return entry.methods & discovered_mask
