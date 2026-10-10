"""Dispatch-time guards for motion captured against one printer snapshot."""
from printer_state import freeze


def motion_dispatch_guard(printer, owner='', manual_active=False, position=False, extrusion=None):
    initial = printer.subscription.snapshot()

    def signature(snapshot):
        status = snapshot['status']
        th, gm = status['toolhead'], status['gcode_move']
        return freeze((snapshot.get('settings', {}), th.get('homed_axes'),
                       th.get('axis_minimum'), th.get('axis_maximum'),
                       th.get('max_velocity'), th.get('extruder'),
                       gm.get('homing_origin'), gm.get('absolute_coordinates'),
                       gm.get('absolute_extrude'), gm.get('position') if position else None))

    expected = signature(initial)
    epoch = initial['epoch']

    def guard():
        try:
            current = printer.subscription.snapshot()
            status = current['status']
            if (current['state'] != 'ready' or current['epoch'] != epoch
                    or status['print_stats']['state'] not in ('standby', 'complete', 'cancelled', 'error')
                    or bool(status.get('manual_probe', {}).get('is_active')) != manual_active
                    or signature(current) != expected):
                return False
            if owner != 'jog' and printer.jog_recovery_required:
                return False
            if any(getattr(getattr(printer, name, None), 'pending', None)
                   for name in ('bed_mesh', 'screws_tilt', 'probe_wizard', 'mmu_session') if name != owner):
                return False
            mmu = status.get('mmu', {})
            if mmu and str(mmu.get('action', '')).lower() != 'idle':
                return False
            return extrusion is None or status.get(extrusion, {}).get('can_extrude') is True
        except (KeyError, TypeError, ValueError):
            return False

    if not guard():
        raise ValueError('Motion state changed; check printer')
    return guard


def config_save_guard(printer, config, owner, verify=None):
    """Bind SAVE_CONFIG to the exact pending values approved by the user."""
    expected = freeze((config.get('save_config_pending'), config.get('save_config_pending_items')))
    motion = motion_dispatch_guard(printer, owner=owner)

    def guard():
        try:
            status = printer.subscription.snapshot()['status']
            current = status['configfile']
            return (motion() and current.get('save_config_pending') is True
                    and freeze((current.get('save_config_pending'), current.get('save_config_pending_items'))) == expected
                    and (verify is None or verify(status)))
        except (KeyError, TypeError, ValueError):
            return False
    return guard
