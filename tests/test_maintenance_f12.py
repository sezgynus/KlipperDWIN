"""CI-only F12 adaptive five-step bracket regression."""
import unittest
from maintenance_f12 import F12Bracket

class F12BracketTests(unittest.TestCase):
    def test_first_moving_four_narrows_to_previous_step(self):
        q=F12Bracket(0,127)
        self.assertEqual(q.levels(),(25,50,76,101,127))
        q=q.next(4)
        self.assertEqual((q.low,q.high),(76,101))
        self.assertEqual(q.levels(),(81,86,91,96,101))

    def test_none_initial_low_half_moves_to_high_half(self):
        q=F12Bracket(0,127).next(0)
        self.assertEqual((q.low,q.high),(127,255))
        self.assertEqual(q.levels()[-1],255)

    def test_narrowed_search_preserves_observed_bound(self):
        q=F12Bracket(0,127).next(4)
        q=q.next(3)
        self.assertTrue(86<=q.low<q.high<=91)

    def test_invalid_and_contradictory_results_fail_closed(self):
        q=F12Bracket(0,127).next(4)
        for response in (-1,6,True,'3',0):
            with self.subTest(response=response),self.assertRaises(ValueError):
                q.next(response)

    def test_resolution_is_discrete_not_analog(self):
        q=F12Bracket(0,2,first_success=2)
        self.assertTrue(q.resolved)
        self.assertEqual(q.levels(),())

if __name__=='__main__':
    unittest.main()
