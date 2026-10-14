"""UVR-style inference. Loaded only by the dedicated separator Python worker."""
import logging
import os
from pathlib import Path
from separation import CATALOG_PATH, MODEL_DIR, metadata, require_model, validated_settings


def run(request, progress):
    settings = validated_settings(request.get('settings', {}))
    spec, path = require_model(settings)
    device = settings.get('device', 'cuda')
    import torch
    import onnxruntime as ort
    from audio_separator.separator import Separator

    if device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA is unavailable. Check the NVIDIA driver, or select CPU explicitly.')
    if device == 'cuda' and spec['architecture'] == 'MDX' and 'CUDAExecutionProvider' not in ort.get_available_providers():
        raise ValueError('ONNX CUDA is unavailable. Rerun Install-Separation.cmd or select CPU.')
    # Trusted local checkpoints predate Torch's weights-only default.
    os.environ['TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD'] = '1'
    os.environ['AUDIO_SEPARATOR_MODEL_DIR'] = str(MODEL_DIR)

    class LocalSeparator(Separator):
        def download_model_files(self, filename):
            if filename != spec['filename']:
                raise ValueError('Unexpected separation model')
            self.model_is_uvr_vip = False
            config = str(CATALOG_PATH.parent / spec['config']) if spec.get('config') else None
            return filename, spec['architecture'], spec['label'], str(path), config

        def load_model_data_using_hash(self, filename):
            return metadata(spec, filename)

        def download_file_if_not_exists(self, *args, **kwargs):
            raise RuntimeError('Inference cannot download files. Use the explicit model download job.')

        def setup_torch_device(self, system_info):
            self.torch_device_cpu = torch.device('cpu')
            self.torch_device = torch.device(device)
            self.onnx_execution_provider = ['CUDAExecutionProvider' if device == 'cuda' else 'CPUExecutionProvider']

    # Upstream warns and falls back when CUDA DLL loading fails. Enforce the
    # requested provider for every session created while this model is loaded.
    original_session = ort.InferenceSession
    def session(*args, **kwargs):
        instance = original_session(*args, **kwargs)
        required = 'CUDAExecutionProvider' if device == 'cuda' else 'CPUExecutionProvider'
        if required not in instance.get_providers():
            raise RuntimeError(f'ONNX could not activate {required}. Check the driver and rerun Install-Separation.cmd.')
        instance.disable_fallback()
        return instance
    ort.InferenceSession = session
    try:
        out = Path(request['output_dir'])
        progress(.1, 'Loading ' + spec['label'] + ' on ' + device.upper())
        separator = LocalSeparator(
            log_level=logging.INFO, model_file_dir=str(MODEL_DIR), output_dir=str(out),
            output_format='WAV', sample_rate=44100, use_soundfile=True,
            normalization_threshold=1., amplification_threshold=0., chunk_duration=60,
            mdx_params={'hop_length': 1024, 'segment_size': 256, 'overlap': settings.get('overlap', .25), 'batch_size': settings['batch_size'], 'enable_denoise': settings.get('denoise', False)},
            vr_params={'batch_size': settings['batch_size'], 'window_size': 512, 'aggression': settings.get('aggression', 5), 'enable_tta': settings.get('tta', False), 'enable_post_process': False, 'post_process_threshold': .2, 'high_end_process': False},
            mdxc_params={'segment_size': 256, 'override_model_segment_size': False, 'batch_size': settings['batch_size'], 'overlap': settings.get('overlap', 4), 'pitch_shift': 0},
        )
        # ONNX models must use their trained window size; otherwise upstream
        # converts them to Torch and bypasses the requested ONNX provider.
        if spec['architecture'] == 'MDX':
            separator.arch_specific_params['MDX']['segment_size'] = 2 ** metadata(spec, path)['mdx_dim_t_set']
        separator.load_model(spec['filename'])
        progress(.2, 'Separating dialogue and background · ' + spec['label'])
        separator.separate(request['audio'], custom_output_names={'Vocals': 'vocals', 'Instrumental': 'background'})
        stems = {key: str(out / (key + '.wav')) for key in ('vocals', 'background')}
        if not all(Path(p).is_file() for p in stems.values()):
            raise RuntimeError('Model did not produce both expected vocal/background stems')
        return {**stems, 'device': device, 'model': spec['id']}
    finally:
        ort.InferenceSession = original_session
