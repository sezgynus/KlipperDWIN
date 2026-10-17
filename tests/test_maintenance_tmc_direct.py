"""CI-only tests for homing-independent direct register diagnostics."""
import unittest
from maintenance_tmc_direct import direct_query, register_evidence, register_error


class DirectDriverRegisterTests(unittest.TestCase):
    def test_dynamic_valid_targets_not_printer_specific(self):
        self.assertEqual(direct_query('tmc2208 extruder'),
            'DUMP_TMC STEPPER=extruder REGISTER=DRV_STATUS')
        self.assertEqual(direct_query('tmc2209 stepper_z3'),
            'DUMP_TMC STEPPER=stepper_z3 REGISTER=DRV_STATUS')
        self.assertEqual(direct_query('tmc5160 stepper_x'),
            'DUMP_TMC STEPPER=stepper_x REGISTER=DRV_STATUS')
        for device in ('tmc2208 stepper_x\nG28', 'tmc2208 stepper_x OTHER=1',
                       'tmc9999 stepper_x', 'tmc2660 stepper_x',
                       'tmc2208 ', 'stepper_x', None):
            self.assertIsNone(direct_query(device))

    def test_2208_decodes_raw_bits_not_display_string_guesswork(self):
        values=register_evidence(('DRV_STATUS: c0120000 cs_actual=18 stealth=1 stst=1',),
                                 'tmc2208 stepper_x')
        self.assertIn(('fault_count',0),values)
        self.assertIn(('faults','none reported'),values)
        self.assertIn(('cs_actual',18),values)
        self.assertIn(('stealth',1),values)
        self.assertIn(('standstill',1),values)
        faults=register_evidence(('// DRV_STATUS: 00000007 otpw=1 ot=1 s2ga=1',),
                                 'tmc2208 extruder')
        self.assertIn(('fault_count',3),faults)
        self.assertIn(('faults','otpw,ot,s2ga'),faults)
        load=register_evidence(('DRV_STATUS: 00000040 ola=1',),
                               'tmc2208 stepper_y')
        self.assertIn(('open_load_flags','ola'),load)
        self.assertIn(('fault_count',0),load)

    def test_malformed_ambiguous_and_stale_messages_fail_closed(self):
        target='tmc2208 stepper_x'
        self.assertEqual(register_evidence((),target),())
        self.assertEqual(register_evidence(('DRV_STATUS: no reading',),target),())
        self.assertEqual(register_evidence(('DRV_STATUS: ffffffff',),target)[:2],
                         (('register','DRV_STATUS'),('register_hex','FFFFFFFF')))
        self.assertFalse(any(key=='fault_count' for key,value in
                         register_evidence(('DRV_STATUS: ffffffff',),target)))
        self.assertEqual(register_evidence(('DRV_STATUS: c0120000',
                                            'DRV_STATUS: c0000000'),target),())
        self.assertEqual(register_evidence(('DRV_STATUS: c0120000',),None),())
        self.assertTrue(register_error(('Unable to read tmc uart',)))
        self.assertFalse(register_error(('stst=1',)))

    def test_unknown_chip_faults_not_misinterpreted(self):
        fields=register_evidence(('DRV_STATUS: c0120000',),'tmc2209 stepper_x')
        self.assertEqual(fields[-1],('decode','chip-specific interpretation required'))
        self.assertFalse(any(name=='fault_count' for name,value in fields))


if __name__=='__main__':
    unittest.main()
