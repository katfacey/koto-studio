"""Run inside a Torch worker environment after installation."""
import torch

print("PyTorch:", torch.__version__, "CUDA runtime:", torch.version.cuda)
if not torch.cuda.is_available():
    print("CUDA is unavailable on this machine. Workers can use CPU mode; check the NVIDIA driver before choosing CUDA.")
for i in range(torch.cuda.device_count()):
    name = torch.cuda.get_device_name(i)
    capability = torch.cuda.get_device_capability(i)
    print(name, "compute capability", capability, "VRAM", round(torch.cuda.get_device_properties(i).total_memory/1024**3), "GB")
    if capability == (12, 0) and "sm_120" not in torch.cuda.get_arch_list():
        raise SystemExit("This PyTorch wheel does not list sm_120 support for RTX 5090. Install a compatible CUDA 12.8+ build.")
    tensor = torch.ones((64,64),device=f"cuda:{i}")
    print("CUDA matrix check:", float((tensor @ tensor).mean().item()))
