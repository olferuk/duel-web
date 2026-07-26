"""Cross-process GPU inference server for PVNet.

One process owns the RTX and fuses requests from all self-play workers into
single CUDA forward passes. Workers hold a PVClient that duck-types
`PVNet.infer(obs) -> (values, logits)`, so BatchPuctBot works unchanged and
worker processes never import torch (their cores stay free for the engine).

Usage (fork start method — queues are inherited):
    req_q, resp_qs, proc = start_pv_server("pv_gen6", n_clients=12)
    ... in worker wid: client = PVClient(req_q, resp_qs[wid], wid)
    ... shutdown: req_q.put(None); proc.join()
"""

import multiprocessing as mp
import queue as _queue

import numpy as np


def _server_loop(model_name: str, req_q, resp_qs, batch_max: int) -> None:
    import torch

    torch.set_num_threads(2)
    from duel.ai.puct import PVNet

    net = PVNet.load(model_name)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net.to(dev)
    net.eval()
    print(f"[gpu-server] {model_name} on {dev}", flush=True)
    while True:
        try:
            first = req_q.get(timeout=5.0)
        except _queue.Empty:
            continue
        if first is None:
            return
        reqs = [first]
        rows = len(first[2])
        while rows < batch_max:  # coalesce whatever is already waiting
            try:
                r = req_q.get_nowait()
            except _queue.Empty:
                break
            if r is None:
                return
            reqs.append(r)
            rows += len(r[2])
        obs = np.concatenate([r[2] for r in reqs]) if len(reqs) > 1 else reqs[0][2]
        with torch.no_grad():
            t = torch.from_numpy(obs).to(dev)
            v, lg = net(t)
            v = v.cpu().numpy()
            lg = lg.cpu().numpy()
        i = 0
        for wid, rid, o in reqs:
            n = len(o)
            resp_qs[wid].put((rid, v[i : i + n], lg[i : i + n]))
            i += n


def start_pv_server(model_name: str, n_clients: int, batch_max: int = 1024):
    ctx = mp.get_context("fork")
    req_q = ctx.Queue()
    resp_qs = [ctx.Queue() for _ in range(n_clients)]
    proc = ctx.Process(
        target=_server_loop, args=(model_name, req_q, resp_qs, batch_max), daemon=True
    )
    proc.start()
    return req_q, resp_qs, proc


class PVClient:
    """Worker-side handle; blocking infer() through the shared GPU server."""

    def __init__(self, req_q, resp_q, wid: int):
        self.req_q = req_q
        self.resp_q = resp_q
        self.wid = wid
        self._rid = 0

    def infer(self, obs: np.ndarray):
        self._rid += 1
        self.req_q.put((self.wid, self._rid, np.ascontiguousarray(obs, dtype=np.float32)))
        while True:
            rid, v, lg = self.resp_q.get()
            if rid == self._rid:
                return v, lg
            # stale response from a previous request cycle — drop it


def _value_server_loop(model_name: str, req_q, resp_qs, batch_max: int) -> None:
    import torch

    torch.set_num_threads(2)
    from duel.ai.value_net import ValueNet

    net = ValueNet.load(model_name)
    if torch.cuda.is_available():
        net.cuda()
    net.eval()
    print(f"[gpu-value-server] {model_name} ready", flush=True)
    while True:
        try:
            first = req_q.get(timeout=5.0)
        except _queue.Empty:
            continue
        if first is None:
            return
        reqs = [first]
        rows = len(first[2])
        while rows < batch_max:
            try:
                r = req_q.get_nowait()
            except _queue.Empty:
                break
            if r is None:
                return
            reqs.append(r)
            rows += len(r[2])
        obs = np.concatenate([r[2] for r in reqs]) if len(reqs) > 1 else reqs[0][2]
        with torch.no_grad():
            out = net.values(obs)  # handles prefix slicing + device
        i = 0
        for wid, rid, o in reqs:
            n = len(o)
            resp_qs[wid].put((rid, out[i : i + n]))
            i += n


def start_value_server(model_name: str, n_clients: int, batch_max: int = 2048):
    ctx = mp.get_context("fork")
    req_q = ctx.Queue()
    resp_qs = [ctx.Queue() for _ in range(n_clients)]
    proc = ctx.Process(
        target=_value_server_loop, args=(model_name, req_q, resp_qs, batch_max), daemon=True
    )
    proc.start()
    return req_q, resp_qs, proc


class VClient:
    """Worker-side handle duck-typing ValueNet.values() through the GPU server."""

    def __init__(self, req_q, resp_q, wid: int):
        self.req_q = req_q
        self.resp_q = resp_q
        self.wid = wid
        self._rid = 0

    def values(self, obs: np.ndarray) -> np.ndarray:
        self._rid += 1
        self.req_q.put((self.wid, self._rid, np.ascontiguousarray(obs, dtype=np.float32)))
        while True:
            rid, v = self.resp_q.get()
            if rid == self._rid:
                return v
