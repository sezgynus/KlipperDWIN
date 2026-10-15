"""Static resource sampling helper tests; CI does not access a printer."""
import unittest
from tools.measure_petrel_resources import parse_smaps, cpu_ticks, compare
from unittest.mock import patch


class ResourceProbeTests(unittest.TestCase):
    def test_smaps_returns_uss_not_virtual_size(self):
        sample = ("Rss: 3000 kB\nPss: 2400 kB\n"
                  "Private_Clean: 150 kB\nPrivate_Dirty: 800 kB\n")
        self.assertEqual(parse_smaps(sample), {'Rss': 3000, 'Pss': 2400, 'USS': 950})
        with self.assertRaises(ValueError):
            parse_smaps("Rss: 3000 kB\n")

    def test_stat_with_spaces_and_parentheses(self):
        stat = "1201 (Petrel python (display)) S " + " ".join(
            ['0'] * 10 + ['120', '90', '0'])
        self.assertEqual(cpu_ticks(stat), 210)

    def test_report_uses_median_uss_and_detects_budget_violation(self):
        def report(uss):
            return {'cpu_percent_single_core': 1.0, 'memory_kib': {
                key: {'median': uss} for key in ('Rss', 'Pss', 'USS')}}
        with patch('builtins.print'):
            self.assertEqual(compare(report(1000), report(1800), 1024), 0)
            self.assertEqual(compare(report(1000), report(2400), 1024), 1)
            base = report(1000)
            cand = report(1000)
            cand['memory_kib']['Rss']['median'] = 2400
            self.assertEqual(compare(base, cand, 1024), 1)


if __name__ == '__main__':
    unittest.main()
