"""Validate model provisioning without credentials or simulated model inference."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from koto.diarization import pipeline_path, require_pipeline
from diarization_setup import local_config, provision, REPOSITORIES


class DiarizationSetupTests(unittest.TestCase):
    def test_blank_paths_use_managed_pipeline_and_missing_weights_have_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            managed = root / "runtime/models/pyannote/pipeline.yaml"
            self.assertEqual(pipeline_path({"model": ""}, root), managed.resolve())
            with self.assertRaisesRegex(ValueError, "Install-Diarization.cmd"):
                require_pipeline({"model": ""}, root)
            managed.parent.mkdir(parents=True)
            managed.write_text("fixture")
            self.assertEqual(require_pipeline({"model": ""}, root), managed.resolve())

    def test_downloads_pin_revisions_and_local_config_contains_no_remote_model_or_token(self):
        with tempfile.TemporaryDirectory(prefix="KOTO speakers 日本語 ") as tmp:
            destination = Path(tmp).resolve()
            secret = "fixture-read-token-not-a-real-credential"
            calls = []
            template = {"version": "3.1.0", "pipeline": {"name": "pyannote.audio.pipelines.SpeakerDiarization", "params": {"segmentation": "pyannote/segmentation-3.0", "embedding": "pyannote/wespeaker-voxceleb-resnet34-LM", "use_auth_token": secret}}, "params": {"clustering": {"threshold": .7}}}
            class API:
                def model_info(self, repo, token):
                    self_test.assertEqual(token, secret)
                    return SimpleNamespace(sha="a" * 40)
            self_test = self
            def download(**args):
                calls.append(args)
                path = Path(args["local_dir"]) / args["filename"]
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix == ".yaml":
                    path.write_text(yaml.safe_dump(template), encoding="utf-8")
                else:
                    path.write_bytes(b"test checkpoint, not inference weights")
                return path
            pipeline = provision(secret, API(), download, destination)
            payload = pipeline.read_text(encoding="ascii")
            config = yaml.safe_load(payload)
            for name in ("segmentation", "embedding"):
                path = Path(config["pipeline"]["params"][name])
                self.assertTrue(path.is_absolute() and path.is_file())
                self.assertTrue(path.is_relative_to(destination))
            self.assertNotIn(secret, payload)
            self.assertNotIn(secret, (destination / "source.json").read_text())
            self.assertEqual(len(calls), len(REPOSITORIES))
            self.assertTrue(all(c["revision"] == "a" * 40 and c["token"] == secret for c in calls))
            self.assertEqual(config["params"], template["params"])
            self.assertEqual(len(json.loads((destination / "source.json").read_text())["revisions"]), 3)

    def test_unexpected_configs_or_missing_checkpoints_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unexpected pipeline"):
            local_config({"pipeline": {"name": "other.Pipeline"}}, {})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "Missing local segmentation"):
                local_config({"pipeline": {"name": "pyannote.audio.pipelines.SpeakerDiarization"}}, {"segmentation": Path(tmp)/"missing.bin"})
