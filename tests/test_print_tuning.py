import unittest
from test_capabilities import snapshot, printer
from print_tuning import JOB_PINS, JOB_OBJECTS
from moonraker_subscription import OBJECTS

class PrintTuningTests(unittest.TestCase):
    def data(self):
        d=snapshot(probe=True)
        d['status']['toolhead'].update(square_corner_velocity=5, minimum_cruise_ratio=.5)
        d['status']['extruder'].update(pressure_advance=.04,smooth_time=.04)
        d['objects'].append('firmware_retraction');d['settings']['firmware_retraction']={}
        d['status']['firmware_retraction']=dict(retract_length=2,retract_speed=35,unretract_extra_length=0,unretract_speed=25)
        for name,_ in JOB_PINS:
            obj='output_pin '+name;d['objects'].append(obj);d['settings'][obj]={'pwm':False};d['status'][obj]={'value':1}
        return d
    def test_full_and_minimal_capabilities(self):
        p=printer(self.data());self.assertEqual(len(p.print_settings()),17)
        p=printer(snapshot(hotend=False,bed=False,fan=False));self.assertEqual([s.key for s in p.print_settings()],['speed','z'])
        self.assertTrue(set(JOB_OBJECTS).issubset(OBJECTS));self.assertIn('firmware_retraction',OBJECTS)
    def test_explicit_command_routes_and_percent_conversion(self):
        p=printer(self.data())
        for key,value,expected in [('flow',97,'M221 S97'),('cruise',40,'SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=0.4'),('pa@extruder',.035,'SET_PRESSURE_ADVANCE EXTRUDER=extruder ADVANCE=0.035'),('smooth@extruder',.05,'SET_PRESSURE_ADVANCE EXTRUDER=extruder SMOOTH_TIME=0.05'),('retract_length',2.5,'SET_RETRACTION RETRACT_LENGTH=2.5'),('pin@'+JOB_PINS[0][0],0,'SET_PIN PIN=Turn_OFF_Heaters_After_Job VALUE=0')]:
            p.set_print_setting(key,value);p.sendGCode.assert_called_with(expected)
    def test_invalid_and_unavailable_commands_do_not_send(self):
        p=printer(self.data())
        for key,value in [('cruise',100),('flow',float('nan')),('smooth@extruder',.3),('pin@'+JOB_PINS[0][0],.5),('pin@arbitrary',1)]:
            with self.assertRaises(ValueError):p.set_print_setting(key,value)
        p.sendGCode.assert_not_called()
    def test_switches_require_exact_names_digital_configuration_and_telemetry(self):
        d=self.data();d['settings'][JOB_OBJECTS[0]]['pwm']=True;d['status'][JOB_OBJECTS[1]]['value']=None
        keys=[s.key for s in printer(d).print_settings()]
        self.assertNotIn('pin@'+JOB_PINS[0][0],keys);self.assertNotIn('pin@'+JOB_PINS[1][0],keys)
    def test_layers_only_when_reported_and_valid(self):
        d=self.data();p=printer(d);self.assertIsNone(p.print_layers())
        d['status']['print_stats']['info']={'current_layer':85,'total_layer':200};p.update_variable();self.assertEqual(p.print_layers(),(85,200))
        d['status']['print_stats']['info']['current_layer']=201;p.update_variable();self.assertIsNone(p.print_layers())

    def test_quiet_requests_do_not_enter_global_error_queue(self):
        p=printer(self.data())
        p.set_print_setting('speed',110,report_error=False)
        p.sendGCode.assert_called_with('M220 S110',report_error=False)
        p.set_print_setting('cruise',40,report_error=False)
        p.sendGCode.assert_called_with('SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=0.4',report_error=False)
