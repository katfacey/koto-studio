import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from koto import separation
from koto.registry import interpreter


class ProvisionTests(unittest.TestCase):
    def test_missing_separator_environment_never_falls_back_to_editor_python(self):
        with tempfile.TemporaryDirectory() as temp, patch('koto.registry.ROOT',Path(temp)), patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'Install-Separation.cmd'):
                interpreter({'environment':'separator'})

    def test_verified_download_cache_corruption_cancellation_and_unknown_model(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            data=b'explicit test fixture, not a model'
            spec={'id':'fixture','label':'Fixture','filename':'fixture.onnx','size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'url':'https://github.com/example/model'}
            catalog=directory/'catalog.json'
            catalog.write_text(json.dumps({'models':[spec]}))
            with patch.object(separation,'CATALOG_PATH',catalog), patch('urllib.request.urlopen',return_value=io.BytesIO(data)) as request:
                separation.download('fixture',directory=directory)
                self.assertTrue(separation.installed(spec,directory,verify=True))
                separation.download('fixture',directory=directory)
                self.assertEqual(request.call_count,1)
                separation.model_path(spec,directory).write_bytes(b'x'*len(data))
                self.assertFalse(separation.installed(spec,directory,verify=True))
                with patch('urllib.request.urlopen',return_value=io.BytesIO(b'x'*len(data))):
                    with self.assertRaisesRegex(ValueError,'checksum'):
                        separation.download('fixture',directory=directory)
                self.assertFalse(list(directory.glob('*.partial')))
                with patch('urllib.request.urlopen',return_value=io.BytesIO(data)):
                    with self.assertRaisesRegex(RuntimeError,'cancelled'):
                        separation.download('fixture',directory=directory,check=lambda:(_ for _ in ()).throw(RuntimeError('cancelled')))
                self.assertFalse(list(directory.glob('*.partial')))
                with self.assertRaisesRegex(ValueError,'supported'):
                    separation.model_spec('../../evil')

    def test_settings_reject_invalid_numbers_and_only_forward_architecture_controls(self):
        settings=separation.validated_settings({'model':'vr-hp-karaoke','device':'cpu','aggression':6,'denoise':True})
        self.assertNotIn('denoise',settings)
        self.assertEqual(settings['batch_size'],1)
        for values in ({'batch_size':float('nan')},{'batch_size':.5},{'batch_size':True},{'device':'magic'},{'denoise':'yes'}):
            with self.assertRaises(ValueError):
                separation.validated_settings({'model':'mdx-inst-hq3',**values})

    def test_activating_full_stems_invalidates_only_original_reference_generated_takes(self):
        p={'assets':{'original_audio':'source.wav','export':'old.mkv'},'speakers':[{'id':'original','use_source_reference':True,'source_reference':{'asset':'ref.wav'}},{'id':'sample','use_source_reference':False}], 'dialogue':[{'id':'a','speaker':'original','audio':{'kind':'generated'}},{'id':'b','speaker':'original','audio':{'kind':'imported'}},{'id':'c','speaker':'sample','audio':{'kind':'generated'}}]}
        result={'id':'full','preview':False,'source_asset':'source.wav','assets':{'vocals':'vocals.wav','background':'background.wav'}}
        separation.activate(p,result)
        self.assertNotIn('export',p['assets'])
        self.assertIsNone(p['dialogue'][0]['audio'])
        self.assertEqual(p['dialogue'][1]['audio']['kind'],'imported')
        self.assertEqual(p['dialogue'][2]['audio']['kind'],'generated')
        self.assertNotIn('source_reference',p['speakers'][0])
        p['dialogue'][0]['audio']={'kind':'generated'}
        p['assets']['export']='new.mkv'
        separation.activate(p,result)
        self.assertEqual(p['dialogue'][0]['audio']['kind'],'generated')
        self.assertEqual(p['assets']['export'],'new.mkv')
