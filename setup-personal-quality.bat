@echo off
setlocal
cd /d "%~dp0"

echo Creating the isolated personal Hunyuan3D environment...
py -3.11 -m venv .venv-hunyuan
call .venv-hunyuan\Scripts\activate.bat
python -m pip install --upgrade pip

echo Installing the CUDA runtime and shape-generation dependencies...
python -m pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 --index-url https://download.pytorch.org/whl/cu121
python -m pip install ninja pybind11 diffusers einops opencv-python numpy "transformers>=4.48" omegaconf tqdm trimesh pymeshlab pygltflib xatlas accelerate rembg onnxruntime safetensors
python -m pip install -e third_party\Hunyuan3D-2 --no-deps

echo.
echo Personal Hunyuan3D setup complete.
echo Its model weights download automatically on the first personal-quality generation.
endlocal
