import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from koto.timing import estimate_seconds,playback_rate,adaptation_signature

class TimingTests(unittest.TestCase):
    def test_estimates_and_reversible_speed_rules(self):
        self.assertEqual(estimate_seconds('Wait here.'),.95)
        self.assertEqual(estimate_seconds(''),0)
        self.assertLess(estimate_seconds('Wait here.',200),estimate_seconds('Wait here.',100))
        p={'settings':{'fit_duration':True}};l={'start':1,'end':3,'translation':'Wait here.'}
        self.assertAlmostEqual(playback_rate(p,l,2.2),1.1)
        self.assertEqual(playback_rate(p,l,4),1)
        l.update(auto_fit=False,playback_rate=.9)
        self.assertEqual(playback_rate(p,l,2.2),.9)
        key=adaptation_signature(l);l['gain']=.5
        self.assertEqual(adaptation_signature(l),key)
        l['translation']='Stay here.';self.assertNotEqual(adaptation_signature(l),key)
