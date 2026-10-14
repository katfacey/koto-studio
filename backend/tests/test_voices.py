import copy
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from koto.store import Store
from koto.registry import Registry
from koto.voices import VoiceLibrary,resolve_voice,signature,validate_voice


class VoiceTests(unittest.TestCase):
    def test_profile_versions_copy_samples_pin_projects_and_reject_conflicting_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp));library=VoiceLibrary(store,Registry())
            sample=Path(temp)/'example.wav';sample.write_bytes(b'explicit file-copy fixture')
            config={'adapter':'xtts','settings':{'device':'cpu'},'reference_text':'Example.'}
            first=library.save('Character','First',config,sample)
            p=store.create('Project A');binding=library.bind(p['id'],first['id'])
            second=library.save('Character','Revised',{**config,'seed':12},sample,first['id'],1)
            self.assertEqual((first['version'],second['version'],binding['version']),(1,2,1))
            self.assertEqual(library.get(first['id'],1),first)
            sample.unlink();library.asset(first['id'],1,first['reference']).unlink()
            self.assertTrue(store.asset(p['id'],binding['reference']).is_file())
            self.assertEqual(library.get(first['id'])['version'],2)
            with self.assertRaisesRegex(ValueError,'changed'):
                library.save('Character','Conflict',config,None,first['id'],1)
            with self.assertRaises(ValueError):library.asset(first['id'],2,'../../other')

    def test_clip_profile_overrides_speaker_and_overrides_have_independent_fingerprints(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Store(Path(temp)).create(demo=True);line=p['dialogue'][0];other=p['dialogue'][2]
            sp=p['speakers'][0]
            sp['voice_profile']={'id':'saved','version':1,'config':{'adapter':'xtts','settings':{'device':'cpu'}}}
            sp['reference']='voice.wav';line['voice']={'seed':7}
            self.assertEqual(resolve_voice(p,line)['seed'],7)
            before=signature(p,other);changed=signature(p,line)
            line['voice']['seed']=8
            self.assertNotEqual(signature(p,line),changed);self.assertEqual(signature(p,other),before)
            sp['voice']={'adapter':'piper','settings':{'speaker_id':2}}
            line['voice_profile']={'id':'clip','version':3,'reference':'clip.wav','config':{'adapter':'xtts','settings':{'device':'cpu'}}}
            resolved=resolve_voice(p,line)
            self.assertEqual(resolved['adapter'],'xtts');self.assertEqual(resolved['reference'],'clip.wav')
            self.assertNotIn('speaker_id',resolved['settings'])
            frozen=copy.deepcopy(line['voice_profile']);sp['voice_profile']['config']['settings']['device']='cuda'
            self.assertEqual(line['voice_profile'],frozen)
            with self.assertRaises(ValueError):validate_voice({'seed':True},Registry())
