#!/usr/bin/env python3
"""Offline GIF of production Print/Tune, quiet edits and MMU recovery views."""
from pathlib import Path
from concurrent.futures import Future
from unittest.mock import Mock, patch
import argparse
import logging
import time

from render_docs_screenshots import canvas, sample, cube_thumbnail, finish
from thumbnail_cache import ThumbnailCache
from print_tuning import JOB_PINS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frame',action='store_true')
    args=parser.parse_args()
    logging.getLogger().setLevel(logging.ERROR)
    data=sample(mmu=True)
    data['status']['print_stats'].update(state='printing',filename='calibration_cube.gcode',print_duration=4800,info={'current_layer':85,'total_layer':200})
    data['status']['virtual_sdcard'].update(progress=.42,is_active=True)
    data['status']['gcode_move'].update(speed_factor=1,extrude_factor=1)
    data['status']['extruder'].update(temperature=215,target=215,pressure_advance=.04,smooth_time=.04)
    data['status']['heater_bed'].update(temperature=60,target=60)
    data['status']['fan']['speed']=.5
    data['status']['mmu'].update(tool=2,gate=2,print_state='printing',action='Idle',gate_material=['PETG','PLA','ABS','PLA'])
    data['objects'].append('firmware_retraction');data['settings']['firmware_retraction']={}
    data['status']['firmware_retraction']=dict(retract_length=2,retract_speed=35,unretract_extra_length=0,unretract_speed=25)
    for name,_ in JOB_PINS:
        obj='output_pin '+name;data['objects'].append(obj);data['settings'][obj]={'pwm':False};data['status'][obj]={'value':not name.startswith('Power')}
    frames=[];durations=[]
    with patch.object(time,'strftime',return_value='12:34'),patch.object(time,'monotonic',return_value=0):
        v=canvas(data)
        # All drawing still uses the production driver and SRAM JPEG command.
        v._sync_thumbnail_cache();key=v._print_thumbnail_key;payload=cube_thumbnail(size=88)
        v.lcd.write_sram(0,payload);v._thumbnail_cache.entries[key]=(0,len(payload))
        def capture(duration=1500):
            frames.append(finish(v,dashboard=v.checkkey not in (v.PowerConfirm,v.MMUMenu,v.Tune,v.TuneEdit,v.PrintErrorDetails)));durations.append(duration)
        def enter(handler):
            v.get_encoder_state.return_value=v.ENCODER_DIFF_ENTER;handler()
        v.Goto_PrintProcess();capture()
        v.select_print.set(1);v._focus_print_tick();capture(700)
        v.pd.pause_job=Mock(return_value=Future());enter(v.HMI_Printing);capture()
        data['status']['print_stats']['state']='paused';v.pd.update_variable();v._focus_print_tick();capture(700)
        v.pd.resume_job=Mock(return_value=Future());enter(v.HMI_Printing)
        data['status']['print_stats']['state']='printing';v.pd.update_variable();v._focus_print_tick()
        v.select_print.set(0);enter(v.HMI_Printing);capture()
        v.select_tune.set(2);v._focus_tune_tick();capture(700)
        enter(v.HMI_Tune);v._tune_target=97;v._focus_edit_value();capture()
        accepted=Future();accepted.set_result(None);v.pd.set_print_setting=Mock(return_value=accepted)
        enter(v._focus_edit_input);capture()
        data['status']['gcode_move']['extrude_factor']=.97;v.pd.update_variable();v._focus_tune_tick()
        v.select_tune.set(17);v._focus_tune_tick();enter(v.HMI_Tune);capture()
        data['status']['output_pin Power_OFF_Printer_After_Job']['value']=1;v.pd.update_variable();v._focus_tick_quiet()
        v.Goto_PrintProcess()
        data['status']['mmu'].update(action='Unloading',last_tool=2,next_tool=3)
        v.pd.update_variable();v._focus_print_tick();capture()
        data['status']['mmu'].update(print_state='pause_locked',reason_for_pause='Unload failed: toolhead sensor still active after filament retraction. Check filament path and recover MMU state before resuming.')
        data['status']['print_stats']['state']='paused';v.pd.update_variable();v._focus_print_tick();capture()
        v.select_print.set(1);enter(v.HMI_Printing);capture()
        enter(v._focus_error_input);capture()
        v._mmu_back();v.select_print.set(2);enter(v.HMI_Printing);capture()
        enter(v.HMI_PauseOrStop);v._open_power_hold_popup();capture()
    target=Path(__file__).resolve().parents[1]/'docs/assets/print-controls-demo.gif'
    if args.frame:
        from dwin_emulator.presentation import with_frame
        frames=[with_frame(frame) for frame in frames]
        target=target.parent/'framed'/target.name;target.parent.mkdir(exist_ok=True)
    frames[0].save(target,save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2)
    print(target)


if __name__=='__main__':main()
