import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from koto.references import reference_signature, reference_segments
from koto.registry import interpreter
from koto.jobs import signature
from xtts_setup import provision, FILES


class ReferenceTests(unittest.TestCase):
    def fixture(self):
        return {'assets':{'vocals':'vocals.wav'},'models':{'synthesis':{'id':'xtts'}},'speakers':[{'id':'a','use_source_reference':True,'voice':{}}],'dialogue':[{'id':'one','speaker':'a','start':0,'end':5},{'id':'two','speaker':'b','start':1,'end':2},{'id':'three','speaker':'a','start':5,'end':9}]}

    def test_reference_excludes_overlapping_other_voices_and_preserves_original_bounds(self):
        p=self.fixture()
        self.assertEqual(reference_segments(p,'a'),[(0,1),(2,9)])
        original=reference_signature(p,'a')
        p['dialogue'][0].update(source_start=0,source_end=5,start=10,end=15)
        self.assertEqual(reference_signature(p,'a'),original)
        self.assertEqual(reference_segments(p,'a'),[(0,1),(2,9)])
        p['dialogue'][1]['speaker']='a'
        self.assertNotEqual(reference_signature(p,'a'),original)
        self.assertEqual(reference_segments(p,'a'),[(0,9)])
        p['dialogue']=[{'id':'short','speaker':'a','start':0,'end':2}]
        with self.assertRaisesRegex(ValueError,'3 seconds'): reference_segments(p,'a')

    def test_mutes_reordering_and_unrelated_dialogue_do_not_invalidate_takes(self):
        p=self.fixture();before=signature(p,p['dialogue'][0]);p['speakers'][0]['muted']=True
        p['speakers'].insert(0,{'id':'unrelated'})
        p['dialogue'].append({'id':'later','speaker':'b','start':30,'end':40})
        self.assertEqual(signature(p,p['dialogue'][0]),before)
        p['dialogue'][1]['speaker']='a'
        self.assertNotEqual(signature(p,p['dialogue'][0]),before)

    def test_moved_windows_worker_has_specific_repair_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);venv=root/'.workers/piper';(venv/'Scripts').mkdir(parents=True)
            (venv/'Scripts/python.exe').touch();cfg=venv/'pyvenv.cfg';cfg.write_text('home = F:/old/runtime/python/cpython')
            with patch('koto.registry.ROOT',root),patch('koto.registry.os',SimpleNamespace(name='nt',environ={})):
                with self.assertRaisesRegex(RuntimeError,'Install-Piper.cmd'):interpreter({'environment':'piper'})
                cfg.write_text('home = '+str(root/'runtime/python/cpython').replace('/','\\'))
                self.assertEqual(interpreter({'environment':'piper'}),str(venv/'Scripts/python.exe'))

    def test_xtts_provision_pins_revision_and_keeps_files_in_app_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def download(**kw):
                calls.append(kw);path=Path(kw['local_dir'])/kw['filename'];path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('{}' if path.suffix=='.json' else 'checkpoint-fixture');return str(path)
            provision(SimpleNamespace(model_info=lambda *a,**k:SimpleNamespace(sha='a'*40)),download,tmp)
            self.assertEqual({c['filename'] for c in calls},set(FILES))
            self.assertTrue(all(c['revision']=='a'*40 and c['token'] is False for c in calls))
            self.assertNotIn('token', (Path(tmp)/'source.json').read_text())
