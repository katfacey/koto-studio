import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from koto.runtime import executable, ollama_url, runtime_environment
from release_files import refresh_source_manifest
import runtime_services


class RuntimeIsolationTests(unittest.TestCase):
    def test_windows_media_tools_resolve_without_path_and_prefer_managed_files(self):
        with tempfile.TemporaryDirectory(prefix="KOTO with spaces ") as tmp:
            root = Path(tmp).resolve()
            bin_dir = root / "runtime" / "ffmpeg" / "bin"
            bin_dir.mkdir(parents=True)
            for name in ("ffmpeg", "ffprobe"):
                (bin_dir / f"{name}.exe").write_bytes(b"fixture")
                with patch("koto.runtime.shutil.which", side_effect=AssertionError("PATH must not be searched")):
                    self.assertEqual(executable(name, root=root, env={"PATH":""}, windows=True), str(bin_dir / f"{name}.exe"))

    def test_missing_managed_windows_binary_does_not_use_system_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("koto.runtime.shutil.which", return_value="C:/external/ffmpeg.exe") as which:
                with self.assertRaisesRegex(RuntimeError,"Run Install.cmd"):
                    executable("ffmpeg", root=tmp, env={"PATH":"C:/external"}, windows=True)
                which.assert_not_called()
            with self.assertRaisesRegex(RuntimeError,"absolute executable"):
                executable("ffmpeg",root=tmp,env={"KOTO_FFMPEG":"ffmpeg"},windows=True)

    def test_worker_caches_and_dll_directories_are_owned_by_app(self):
        with tempfile.TemporaryDirectory(prefix="KOTO app ") as tmp:
            root = Path(tmp).resolve()
            dlls = root / ".workers" / "whisper" / "Lib" / "site-packages" / "torch" / "lib"
            dlls.mkdir(parents=True)
            (root/"runtime"/"ffmpeg"/"bin").mkdir(parents=True)
            base={"PATH":"external-system-path","SystemRoot":str(root/"Windows"),"HF_HUB_CACHE":"external-model-cache"}
            worker=root/".workers"/"whisper"/"Scripts"/"python.exe"
            env=runtime_environment(root=root,base=base,python=worker,windows=True)
            self.assertEqual(base["PATH"],"external-system-path")
            self.assertIn(str(dlls),env["PATH"].split(";"))
            self.assertEqual(env["PATH"].split(";")[0],str(root/"runtime"/"ffmpeg"/"bin"))
            for name in ("HF_HOME","HF_HUB_CACHE","HUGGINGFACE_HUB_CACHE","HF_DATASETS_CACHE","TRANSFORMERS_CACHE","TORCH_HOME","UV_CACHE_DIR","UV_PYTHON_INSTALL_DIR","OLLAMA_MODELS"):
                self.assertTrue(Path(env[name]).is_relative_to(root/"runtime"))

    def test_driver_and_cancellation_binaries_use_windows_system_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            windows=Path(tmp)/"Windows"
            system=windows/"System32"
            system.mkdir(parents=True)
            for name in ("nvidia-smi","taskkill"):
                path=system/(name+".exe")
                path.write_bytes(b"fixture")
                self.assertEqual(executable(name,env={"SystemRoot":str(windows),"PATH":""},windows=True),str(path))

    def test_translation_endpoint_requires_local_loopback(self):
        self.assertEqual(ollama_url({}),"http://127.0.0.1:11435")
        self.assertEqual(ollama_url({"KOTO_OLLAMA_URL":"http://localhost:11435/"}),"http://localhost:11435")
        for value in ("https://example.com","http://example.com","http://user:secret@localhost:11435","http://localhost:11435/proxy"):
            with self.assertRaises(ValueError):ollama_url({"KOTO_OLLAMA_URL":value})

    def test_standalone_source_manifest_excludes_installed_tools_and_project_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            (root/"scripts").mkdir()
            for name in ("Install.cmd","Start.cmd","runtime/uv/uv.exe","data/projects/private/video.mkv",".venv/Scripts/python.exe",".workers/audio/model.pth"):
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b"fixture")
            refresh_source_manifest(root)
            files=json.loads((root/"scripts"/"source-files.json").read_text())
            self.assertIn("Install.cmd",files)
            self.assertIn("Start.cmd",files)
            self.assertIn("scripts/source-files.json",files)
            self.assertNotIn("runtime/uv/uv.exe",files)
            self.assertNotIn("data/projects/private/video.mkv",files)
            self.assertNotIn(".venv/Scripts/python.exe",files)
            self.assertNotIn(".workers/audio/model.pth",files)


class ManagedServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.binary=self.root/"runtime"/"ollama"/("ollama.exe" if os.name=="nt" else "ollama")
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"fixture")

    def tearDown(self):self.temp.cleanup()

    def test_session_starts_and_stops_its_own_translation_server(self):
        proc=MagicMock()
        proc.poll.return_value=None
        with patch.object(runtime_services,"service_ready",side_effect=[False,False,True]), patch.object(runtime_services.subprocess,"Popen",return_value=proc) as start, patch.object(runtime_services,"stop_owned_process") as stop, patch.object(runtime_services.time,"sleep"):
            with runtime_services.managed_ollama(root=self.root) as actual:
                self.assertIs(actual,proc)
                args=start.call_args.args[0]
                self.assertEqual(args,[str(self.binary),"serve"])
                self.assertTrue(Path(start.call_args.kwargs["env"]["OLLAMA_MODELS"]).is_relative_to(self.root))
                self.assertEqual(start.call_args.kwargs["env"]["OLLAMA_HOST"],"127.0.0.1:11435")
            stop.assert_called_once_with(proc)

    def test_existing_translation_service_is_not_terminated(self):
        with patch.object(runtime_services,"service_ready",return_value=True), patch.object(runtime_services.subprocess,"Popen") as start, patch.object(runtime_services,"stop_owned_process") as stop:
            with runtime_services.managed_ollama(root=self.root) as actual:self.assertIsNone(actual)
            start.assert_not_called()
            stop.assert_not_called()

    def test_missing_optional_service_allows_core_editor_to_start(self):
        self.binary.unlink()
        with runtime_services.managed_ollama(root=self.root) as actual:self.assertIsNone(actual)
        with self.assertRaisesRegex(RuntimeError,"Install-Translation"):
            with runtime_services.managed_ollama(root=self.root,required=True):pass

    def test_failed_translation_start_cleans_up_owned_process(self):
        proc=MagicMock()
        proc.poll.return_value=None
        with patch.object(runtime_services,"service_ready",return_value=False), patch.object(runtime_services.subprocess,"Popen",return_value=proc), patch.object(runtime_services,"stop_owned_process") as stop:
            with self.assertRaisesRegex(RuntimeError,"did not start"):
                with runtime_services.managed_ollama(root=self.root,timeout=0):pass
            stop.assert_called_once_with(proc)


if __name__=="__main__":unittest.main()
