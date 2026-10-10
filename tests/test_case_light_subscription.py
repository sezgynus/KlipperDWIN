import unittest
from unittest.mock import Mock
from concurrent.futures import Future
from moonraker_subscription import MoonrakerSubscription

class CaseLightSubscriptionTests(unittest.TestCase):
    def make(self):
        sub = MoonrakerSubscription('http://localhost:7125', autostart=False)
        self.addCleanup(sub.close)
        sub._objects = ['webhooks', 'toolhead', 'output_pin case_light']
        sub._base_subscription = {'webhooks': None, 'toolhead': None, 'configfile': ['save_config_pending']}
        sub._state = 'ready'; sub._eventtime = 10
        sub._status = {'toolhead': {'position': [1, 2, 3]}}
        sub.request = Mock(return_value=Future())
        return sub

    def test_enable_seeds_value_and_disable_preserves_baseline(self):
        sub = self.make(); callback = Mock()
        future = sub.set_case_light_tracking(True, callback)
        objects = sub.request.call_args.args[1]['objects']
        self.assertEqual(objects['output_pin case_light'], ['value'])
        self.assertEqual(objects['configfile'], ['save_config_pending'])
        self.assertIn('toolhead', objects)
        future.set_result({'status': {'output_pin case_light': {'value': 0.6}}, 'eventtime': 11})
        self.assertEqual(sub.snapshot()['status']['output_pin case_light']['value'], 0.6)
        callback.assert_called_once()
        sub.set_case_light_tracking(False)
        self.assertNotIn('output_pin case_light', sub.request.call_args.args[1]['objects'])
        self.assertIn('toolhead', sub.snapshot()['status'])
        sub._merge({'output_pin case_light': {'value': 1}}, 12)
        self.assertNotIn('output_pin case_light', sub.snapshot()['status'])
        callback.assert_called_once()

    def test_stale_initial_reply_after_exit_is_ignored(self):
        sub = self.make(); callback = Mock()
        future = sub.set_case_light_tracking(True, callback)
        sub.request.return_value = Future(); sub.set_case_light_tracking(False)
        future.set_result({'status': {'output_pin case_light': {'value': 0.5}}, 'eventtime': 11})
        callback.assert_not_called()
        self.assertNotIn('output_pin case_light', sub.snapshot()['status'])

    def test_older_initial_reply_can_seed_pin_without_replacing_newer_state(self):
        sub = self.make(); callback = Mock()
        future = sub.set_case_light_tracking(True, callback)
        sub._merge({'toolhead': {'position': [4, 5, 6]}}, 12)
        future.set_result({'status': {'output_pin case_light': {'value': 0.4},
                                    'toolhead': {'position': [0, 0, 0]}}, 'eventtime': 11})
        self.assertEqual(sub.snapshot()['status']['toolhead']['position'], [4, 5, 6])
        self.assertEqual(sub.snapshot()['status']['output_pin case_light']['value'], 0.4)
        callback.assert_called_once()

    def test_external_changes_notify_once_and_never_replace_newer_pin(self):
        sub = self.make(); callback = Mock()
        future = sub.set_case_light_tracking(True, callback)
        sub._merge({'output_pin case_light': {'value': 0.9}}, 12)
        future.set_result({'status': {'output_pin case_light': {'value': 0.4}}, 'eventtime': 11})
        self.assertEqual(sub.snapshot()['status']['output_pin case_light']['value'], 0.9)
        callback.assert_called_once()
