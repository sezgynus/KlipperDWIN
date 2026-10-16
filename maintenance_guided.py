"""Stage 8: explicit guided hardware-test candidates and consent gate.

This layer deliberately CANNOT actuate hardware, send G-code, or award a
physical PASS. It defines the bounded targets and requires the existing
MaintenanceSafetyCoordinator's positive live/queue admission before even
arming an observed test. A later command adapter must implement dispatch-time
guards, bounded stimulation, verified cleanup, and observation handling.
"""
from dataclasses import dataclass
from time import monotonic
import math

from maintenance_catalog import definition_for
from maintenance_discovery import MaintenanceSnapshot, USER
from maintenance_planner import AdapterRegistration, PlannedTest, build_plan
from maintenance_safety import MaintenanceSafetyCoordinator


# Only these well-defined contracts can become stage-8 guided candidates.
# S18/O03 require declared physical roles on real Klipper objects.
# Never infer an actuator's function from its name.
# A PWM fan without tachometer is USER-observed, never automatic RPM PASS.
_KINDS = {
    'F01': 'part_fan_observation',
    'F02': 'part_fan_speed_steps_observation',
    'F12': 'part_fan_minimum_usable_pwm_observation',
    'F04': 'generic_fan_observation',
    'O03': 'case_light_observation',
    'O04': 'led_observation',
    'S18': 'buzzer_observation',
}
_DEVICE_PREFIXES = ('led ', 'neopixel ', 'dotstar ', 'pca9632 ')


def guided_adapters():
    """Production-valid USER registrations, not authorization to actuate."""
    return tuple(AdapterRegistration(
        key, USER, 'maintenance.guided.' + key,
        definition_for(key).evidence_contract,
        definition_for(key).safety_profile)
        for key in _KINDS)


def _trusted_target(row, snapshot):
    if not isinstance(row, PlannedTest) or not isinstance(snapshot, MaintenanceSnapshot):
        return False
    if (row.feature_id not in _KINDS or row.method != USER
            or row.category != 'guided'
            or row.adapter_id != 'maintenance.guided.' + row.feature_id):
        return False
    if row.feature_id in ('F01', 'F02', 'F12'):
        return row.device == 'fan'
    if row.feature_id == 'F04':
        return (isinstance(row.device, str)
                and row.device.startswith('fan_generic ')
                and 'maintenance.safe_fan:' + row.device in snapshot.service_key)
    if row.feature_id == 'O03':
        return (isinstance(row.device, str)
                and row.device.startswith('output_pin ')
                and 'maintenance.visual:' + row.device in snapshot.service_key)
    if row.feature_id == 'O04':
        return (isinstance(row.device, str)
                and row.device.startswith(_DEVICE_PREFIXES)
                and 'maintenance.safe_led:' + row.device in snapshot.service_key)
    return (row.feature_id == 'S18' and isinstance(row.device, str)
            and row.device.startswith('pwm_cycle_time ')
            and 'maintenance.audible:' + row.device in snapshot.service_key)


def guided_plan(snapshot):
    """Return real target rows only; never read hardware or manufacture IDs."""
    if not isinstance(snapshot, MaintenanceSnapshot):
        return ()
    return tuple(row for row in build_plan(snapshot, guided_adapters())
                 if _trusted_target(row, snapshot))


@dataclass(frozen=True, slots=True)
class GuidedArmResult:
    feature_id: str
    device: str | None
    status: str  # CONSENTED != EXECUTED; no PASS state exists here.
    reason: str


class GuidedConsentGate:
    """One short consent reservation; no command is implemented or scheduled."""

    __slots__ = ('_safety', '_session', '_row', '_expires', '_token', '_generation')

    def __init__(self, safety=None):
        self._safety = safety if safety is not None else MaintenanceSafetyCoordinator()
        self._session = None
        self._row = None
        self._expires = 0.0
        self._token = None
        self._generation = 0

    @property
    def active(self):
        return self._session is not None

    def _release(self):
        if self._session is not None:
            self._safety.end(self._session)
        self._session = None
        self._row = None
        self._expires = 0.0
        self._token = None

    def arm(self, row, snapshot, context, *, timeout=15.0):
        """Require a current, exact planned target and live, verified safety.

        The opaque positive token is a consent-session identity, NOT an
        actuator authorization. Only explicit UI user action can grant it.
        """
        if self.active:
            return None, 'guided_busy'
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            return None, 'invalid_timeout'
        if (not _trusted_target(row, snapshot)
                or row not in guided_plan(snapshot)):
            return None, 'unregistered_or_stale_target'
        decision, session = self._safety.begin(snapshot, context)
        if not decision.allowed:
            return None, decision.reason
        self._generation += 1
        self._session = session
        self._row = row
        self._expires = monotonic() + timeout
        self._token = self._generation
        return self._token, 'awaiting_user_consent'

    def approve(self, token, snapshot, context):
        """Record operator intent only; NEVER starts a fan/buzzer/light."""
        if (type(token) is not int or not self.active or self._token != token):
            return None, 'invalid_consent_session'
        if monotonic() >= self._expires:
            self._release()
            return None, 'consent_expired'
        if (self._row not in guided_plan(snapshot)
                or not self._safety.guard(self._session, snapshot, context).allowed):
            self._release()
            return None, 'unsafe_or_stale_consent'
        result = GuidedArmResult(
            self._row.feature_id, self._row.device,
            'CONSENTED', 'no_hardware_command_dispatched')
        self._release()
        return result, 'consented_without_actuation'

    def cancel(self):
        self._release()

    def close(self):
        self.cancel()
        self._safety.clear()
