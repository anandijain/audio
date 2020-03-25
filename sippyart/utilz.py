import os
import glob
import torch
import numpy as np

import torchaudio
from torch.nn import functional as F

import sippyart

PROJ_DIR = sippyart.__path__[0] + "/"
PARENT_DIR = PROJ_DIR + "../"

# TODO sync_n sample rates 


def pct_crop(w: torch.tensor, start_pct: float, end_pct: float) -> torch.tensor:
    wave_len = len(w[0])
    
    start_idx = int(wave_len * start_pct)
    end_idx = int(wave_len * end_pct)
    cropped_channels = []

    for channel in w:
        cropped_channels.append(channel[start_idx:end_idx].view(1, -1))
        
    return torch.cat(cropped_channels, dim=0)


def gen_recon(model, bottleneck: int, device):
    with torch.no_grad():
        sample = torch.zeros(1, bottleneck).to(device)
        sample = model.decode(sample).cpu().view(2, -1)
    return sample


def gen_apply(model, sample, device):
    with torch.no_grad():
        recon_batch, mu, logvar = model(sample.to(device))
        recon_batch = recon_batch.view(2, -1)
    return recon_batch


def sync_sample_rates(fn: str, fn2: str):
    w, sr = torchaudio.load(fn)
    w2, sr2 = torchaudio.load(fn2)
    if sr == sr2:
        pass
    elif sr > sr2:
        resampler = torchaudio.transforms.Resample(sr, sr2)
        w = resampler.forward(w)
        sr = sr2
    else:
        resampler = torchaudio.transforms.Resample(sr2, sr)
        w2 = resampler.forward(w2)
        sr2 = sr
    return w, sr, w2, sr2


def get_n(fns:list, cat=True):
    tups = list(map(torchaudio.load, fns))
    waves, srs = list(zip(*tups))
    if cat:
        return torch.cat(waves, dim=1), srs
    return waves, srs


def get_n_fix(fns):
    waves = []
    srs = []
    for fn in fns:
        w, sr = torchaudio.load(fn)
        w = mono_fix(w)
        srs.append(sr)
        waves.append(w)
    return torch.cat(waves, dim=1), srs


def wave_cat(w: torch.tensor, idx: int, n: int, dim=0):
    l = w[0][idx*n:(idx + 1)*n].view(1, -1)
    r = w[1][idx*n:(idx + 1)*n].view(1, -1)
    x = torch.cat([l, r], dim=dim)
    return x


def data_windows(w: torch.tensor, n: int = 1000):
    # assuming stereo channels, w.shape == (2, n)
    windows = []
    length = len(w[0]) // n
    for i in range(length):
        l = w[0][i*n:(i+1)*n].view(1, -1)
        r = w[1][i*n:(i+1)*n].view(1, -1)
        elt = torch.cat([l, r])
        windows.append(elt)
    return windows


def mono_fix(w):
    if len(w) == 1:
        w = torch.cat([w, w])
        print(f'mono found, shape: {w.shape}')

    return w


def get_two(fn, fn2):
    w, sr, w2, sr2 = sync_sample_rates(fn, fn2)

    w_len = len(w[0])
    w2_len = len(w2[0])
    if w_len > w2_len:
        print('a')
        new = w[:][:w2_len]
    elif w_len < w2_len:
        print('b')
        new = w2[:][:w_len]
    return (w, sr), (w2, sr2)


def full_fn_to_name(fn: str):
    return fn.split('/')[-1].split('.')[0].replace(' ', '_')


def load_model(model, fn: str):
    try:
        model.load_state_dict(torch.load(fn))
        print(f'loaded: {fn}')
        return model
    except FileNotFoundError:
        print(f'model file {fn} not found')
    except RuntimeError:
        print(f'{fn} architecture most likely incompatible with model')
    return model


def make_folder(path):
    try:
        os.makedirs(path)
        print(f'made: {path}')
    except FileExistsError:
        print(f'writing to existing {path}')


def kl_loss(recon_x, x, mu, logvar):
    try:
        BCE = F.binary_cross_entropy(recon_x, x, reduction='sum')
    except RuntimeError:
        print(f'recon: {np.unique(recon_x.cpu().detach().numpy())}')
        print(f'x: {np.unique(x.cpu().detach().numpy())}')
        print('recon prob has nan')
        return

    KLD = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())
    return BCE + KLD
