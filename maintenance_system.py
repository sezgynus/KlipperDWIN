"""On-demand bounded system fields; no automatic health PASS."""
from collections.abc import Mapping
import json
from pathlib import Path
import re
from urllib.parse import quote
from maintenance_motion import number

FIELDS = {f:() for f in ('S04','S06','S07','S09','S11','S12','S13','S14','S15','S16','S19','S20')}
LOCAL = frozenset(('S11','S12','S14','S15','S16','S20'))


def travel_profile(state):
    try:
        path = Path.home()/'.config'/'Petrel'/'maintenance-travel-counter.json'
        if path.stat().st_size>2048:
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data,dict) or set(data)!={'version','object','authoritative'}
                or type(data['version']) is not int or data['version']!=1
                or data['authoritative'] is not True or data['object'] not in state.objects):
            return None
        return data['object']
    except (OSError,ValueError,TypeError):
        return None


def path_for(feature,device,state):
    if feature=='S04':
        return '/server/files/directory?path=gcodes&extended=false'
    if feature=='S09':
        return '/server/gcode_store?count=20'
    if feature=='S19':
        return '/machine/update/status?refresh=false'
    if feature=='S07':
        if not isinstance(device,str) or device not in state.objects or not device.startswith('canbus_stats '):
            raise ValueError('can_instance_unverified')
        return '/printer/objects/query?'+quote(device,safe='')+'=rx_error,tx_error,tx_retries,bus_state'
    if feature=='S06':
        names = [n for n in state.objects if n=='mcu' or n.startswith('mcu ')]
        if not 1 <= len(names) <= 8:
            raise ValueError('mcu_inventory_out_of_bound')
        return '/printer/objects/query?'+'&'.join(quote(n,safe='')+'=last_stats' for n in names)
    if feature=='S13':
        name = travel_profile(state)
        if not name:
            raise ValueError('authoritative_travel_counter_missing')
        return '/printer/objects/query?'+quote(name,safe='')+'=x_mm,y_mm,z_mm'
    raise ValueError('system_information_unsupported')


def read_fields(feature,reply,device=None):
    result = reply.get('result') if isinstance(reply,Mapping) else None
    if not isinstance(result,Mapping):
        return ()
    if feature=='S04':
        disk = result.get('disk_usage',{})
        if not isinstance(disk,Mapping):
            return ()
        fields = tuple((k+'_bytes',disk[k]) for k in ('total','used','free') if number(disk.get(k)) and disk[k]>=0)
        return fields if len(fields)==3 else ()
    if feature=='S09':
        events = result.get('gcode_store')
        if not isinstance(events,list) or len(events)>20:
            return ()
        errors = sum(1 for e in events if isinstance(e,Mapping) and
                     isinstance(e.get('message'),str) and e['message'].lstrip().startswith('!!'))
        codes = (('Shutdown due to webhooks request','webhook_shutdown'),
                 ('Timer too close','timer_too_close'),('Lost communication','communication_lost'),
                 ('Move out of range','move_out_of_range'),('not heating at expected rate','heater_response'),
                 ('ADC out of range','adc_range'),('Unknown command','unknown_command'))
        last = 'none_classified'
        for event in events:
            message = event.get('message','') if isinstance(event,Mapping) else ''
            if isinstance(message,str):
                last = next((code for marker,code in codes if marker in message),last)
        return (('buffered_events',len(events)),('error_events',errors),('last_error_code',last))
    if feature=='S19':
        versions = result.get('version_info')
        if not isinstance(versions,Mapping) or not versions:
            return ()
        fields = []
        for name,value in sorted(versions.items())[:8]:
            if not isinstance(value,Mapping):
                continue
            current,remote = value.get('version'),value.get('remote_version')
            if all(isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9.+_-]{1,48}',v) for v in (current,remote)):
                fields.append((str(name)[:24]+'.current',current))
                fields.append((str(name)[:24]+'.available',current!=remote))
        return tuple(fields)
    values = result.get('status')
    stamp = result.get('eventtime')
    if not isinstance(values,Mapping) or not number(stamp):
        return ()
    if feature=='S06':
        fields = []
        for name,value in sorted(values.items())[:8]:
            if name!='mcu' and not name.startswith('mcu '):
                continue
            stats = value.get('last_stats',{}) if isinstance(value,Mapping) else {}
            for key in ('mcu_awake','mcu_task_avg','mcu_task_stddev'):
                if number(stats.get(key)) and stats[key]>=0:
                    fields.append((name[:24]+'.'+key,stats[key]))
        return tuple(fields)
    if feature=='S07':
        source = values.get(device,{})
        fields = tuple((k,source[k]) for k in ('rx_error','tx_error','tx_retries')
                       if type(source.get(k)) is int and source[k]>=0)
        if isinstance(source.get('bus_state'),str) and source['bus_state'] in ('active','passive','off','error-active','error-passive','bus-off'):
            fields += (('bus_state',source['bus_state']),)
        return (('eventtime_s',stamp),)+fields if fields else ()
    if feature=='S13':
        if len(values)!=1:
            return ()
        source = next(iter(values.values()))
        if not isinstance(source,Mapping) or any(not number(source.get(k)) or source[k]<0 for k in ('x_mm','y_mm','z_mm')):
            return ()
        return tuple((k,source[k]) for k in ('x_mm','y_mm','z_mm'))+(('authoritative_source',True),)
    return ()
