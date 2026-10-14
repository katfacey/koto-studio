"""Local-only Qwen reference cloning and voice-design adapter."""
import os
from pathlib import Path


def run(request,progress,batch):
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel
    settings=request.get('settings',{})
    design=request['adapter']=='qwen-design'
    from qwen_models import resolve_model
    directory=resolve_model(settings.get('model') or ('runtime/models/qwen/design' if design else 'runtime/models/qwen/base'))
    if not (directory/'config.json').is_file():
        raise ValueError('Install-Voice-Design.cmd is required' if design else 'Run Install-Qwen-Voices.cmd to download local weights')
    device=settings.get('device','cuda')
    if device not in ('cuda','cpu'):raise ValueError('Qwen device must be CUDA or CPU')
    if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA is unavailable; check the driver or select CPU')
    progress(.05,'Loading local Qwen VoiceDesign' if design else 'Loading local Qwen reference model')
    model=Qwen3TTSModel.from_pretrained(str(directory.resolve()),device_map='cuda:0' if device=='cuda' else 'cpu',torch_dtype=torch.bfloat16 if device=='cuda' else torch.float32,attn_implementation='sdpa',local_files_only=True)
    prompt=None
    if not design:
        reference=request.get('reference')
        if not reference or not Path(reference).is_file():raise ValueError('Qwen cloning needs a reference audio sample')
        text=request.get('reference_text') or ''
        progress(.12,'Preparing reference conditioning once for this voice group')
        prompt=model.create_voice_clone_prompt(ref_audio=reference,ref_text=text or None,x_vector_only_mode=not bool(text.strip()))
    def render(text,path,options=None):
        options=options or {}
        if options.get('seed') is not None:torch.manual_seed(options['seed'])
        if design:
            instruction=options.get('delivery') or request.get('delivery')
            if not instruction:raise ValueError('Describe the voice and delivery before generating a designed voice')
            wavs,rate=model.generate_voice_design(text=text,language='English',instruct=instruction,max_new_tokens=2048)
        else:
            wavs,rate=model.generate_voice_clone(text=text,language='English',voice_clone_prompt=prompt,max_new_tokens=2048)
        sf.write(str(path),wavs[0],rate)
    return batch(request,Path(request['output_dir']),render)
