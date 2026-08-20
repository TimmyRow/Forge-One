"""Drop-in CPU fallback for TripoSR's optional torchmcubes extension.

TripoSR performs neural inference and density sampling on CUDA. Only the final
marching-cubes conversion is handled here on CPU, avoiding a local CUDA/C++
compiler requirement on Windows.
"""

from __future__ import annotations

import numpy as np
import torch
from skimage import measure


def marching_cubes(volume: torch.Tensor, isovalue: float):
    source_device = volume.device
    values = volume.detach().float().cpu().numpy()
    vertices, faces, _normals, _values = measure.marching_cubes(
        values, level=float(isovalue), allow_degenerate=False
    )
    return (
        torch.from_numpy(np.ascontiguousarray(vertices)).to(source_device),
        torch.from_numpy(np.ascontiguousarray(faces.astype(np.int64))).to(source_device),
    )

