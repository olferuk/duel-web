"""Torch-free value-net inference via onnxruntime (for tiny hosting tiers).

Duck-types ValueNet.values(); models exported by analysis/export assets live
next to the .pt checkpoints as <name>.onnx (w3 is 3 MB; runtime ~50 MB vs
~1.5 GB for CPU torch).
"""

from pathlib import Path

import numpy as np

MODELS = Path(__file__).resolve().parents[3] / "analysis" / "lab" / "models"


class OnnxValueNet:
    def __init__(self, name: str):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1  # tiny MLP: threading overhead only hurts
        self.sess = ort.InferenceSession(
            str(MODELS / f"{name}.onnx"), opts, providers=["CPUExecutionProvider"]
        )
        self.in_size = self.sess.get_inputs()[0].shape[1]

    def values(self, obs_batch: np.ndarray) -> np.ndarray:
        if obs_batch.shape[-1] > self.in_size:
            obs_batch = obs_batch[..., : self.in_size]
        return self.sess.run(None, {"obs": np.ascontiguousarray(obs_batch, dtype=np.float32)})[0]
