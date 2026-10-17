"""Shared, consented XYZ preparation using the existing motion safety owner."""
from types import SimpleNamespace

def begin_homing(owner):
    # Lazy import also permits the motion controller to use this helper.
    from maintenance_motion_controller import MaintenanceMotionController
    child=MaintenanceMotionController(owner._printer,owner._worker,owner._client)
    row=owner._row
    child._row=SimpleNamespace(feature_id='M03',device=None,
        epoch=row.epoch,config_marker=row.config_marker)
    # Admission belongs to the originally selected capability, never a
    # synthetic discovery entry or a second independently admitted owner.
    child._current=owner._current
    owner._homing=child
    owner._home_attempted=True
    owner._phase='homing_preparation'
    accepted,reason=child._preflight()
    if not accepted:
        owner._homing=None
        raise ValueError(reason)

def poll_homing(owner):
    child=owner._homing
    result=child.poll()
    if result is not None:
        owner._homing=None
        return 'failed',result
    if child.phase=='await_observation':
        # Two fresh XYZ/mode readbacks already verified preparation.
        # This is not an invented physical observation or M03 acceptance.
        child._phase=None
        child._closed=True
        owner._homing=None
        owner._homing_verified=True
        return 'complete',None
    return 'pending',None
