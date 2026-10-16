"""Declared ambient-temperature information, never heater accuracy."""
from collections.abc import Mapping
from urllib.parse import quote
from maintenance_auxiliary import profile
from maintenance_motion import number

FIELDS = {'O05':()}

def path_for(feature,device,state):
    name = profile().get('ambient_sensor')
    if feature!='O05' or not isinstance(name,str) or name not in state.objects or not name.startswith('temperature_sensor '):
        raise ValueError('ambient_role_unverified')
    return '/printer/objects/query?'+quote(name,safe='')+'=temperature'

def read_fields(feature,reply,device=None):
    result = reply.get('result') if isinstance(reply,Mapping) else None
    if not isinstance(result,Mapping):
        return ()
    status = result.get('status')
    name = profile().get('ambient_sensor')
    values = status.get(name) if isinstance(status,Mapping) else None
    stamp = result.get('eventtime')
    temperature = values.get('temperature') if isinstance(values,Mapping) else None
    if number(stamp) and stamp>=0 and number(temperature):
        return (('ambient_c',temperature),('klipper_eventtime_s',stamp))
    return ()
