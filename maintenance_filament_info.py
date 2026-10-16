"""Read-only filament application evidence; no hardware PASS."""
from collections.abc import Mapping
from urllib.parse import quote
from maintenance_filament import profile
from maintenance_motion import number

FIELDS = {'E13':(), 'E15':()}


def path_for(feature,device,state):
    if feature=='E13':
        return '/server/spoolman/spool_id'
    if feature=='E15':
        name = profile().get('chamber_sensor')
        if not isinstance(name,str) or name not in state.objects:
            raise ValueError('chamber_sensor_role_missing')
        return '/printer/objects/query?'+quote(name,safe='')+'=humidity'
    raise ValueError('filament_information_unsupported')


def read_fields(feature,reply,device=None):
    result = reply.get('result') if isinstance(reply,Mapping) else None
    if not isinstance(result,Mapping):
        return ()
    data = profile()
    if feature=='E15':
        values = result.get('status',{}).get(data.get('chamber_sensor'),{})
        humidity = values.get('humidity')
        stamp = result.get('eventtime')
        if number(humidity) and 0 <= humidity <= 100 and number(stamp):
            return (('humidity_pct',humidity),('klipper_eventtime_s',stamp))
        return ()
    if 'spool_id' not in result:
        return ()
    active = result.get('spool_id')
    if active is not None and (type(active) is not int or active<=0):
        return ()
    records = data.get('material_history')
    if not isinstance(records,list) or not 1 <= len(records) <= 16:
        return ()
    if any(not isinstance(r,dict) or type(r.get('spool_id')) is not int
           or r['spool_id']<=0 or not number(r.get('used_mm')) or r['used_mm']<0
           or not isinstance(r.get('material'),str) or len(r['material'])>32
           or not isinstance(r.get('source'),str) or len(r['source'])>48 for r in records):
        return ()
    selected = [r for r in records if active is None or r['spool_id']==active]
    if not selected:
        return ()
    return (('linked_spools',len({r['spool_id'] for r in selected})),
            ('declared_used_mm',sum(r['used_mm'] for r in selected)),
            ('wear_measured',False))
