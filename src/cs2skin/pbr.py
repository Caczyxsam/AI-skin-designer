"""Derive PBR maps from a base-color image.

This is a procedural first pass (no ML): good enough to preview and to fill the Workbench maps,
and a clean seam to later swap in a dedicated material-estimation model. All functions operate on
RGB uint8 arrays / PIL images and return the same, so the pipeline never needs torch here.

Maps produced:
  normal    tangent-space, Source/OpenGL convention (Y+), flat = (128,128,255)
  roughness single channel; derived from local detail + a per-finish base level
  metalness single channel; heuristic, biased per finish style
  ao        ambient occlusion / cavity from the derived height field
"""

from __future__ import annotations

import numpy as np
from PIL import Image

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


def _to_array(img: Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(img, Image.Image):
        return np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    a = img.astype(np.float32)
    return a / 255.0 if a.max() > 1.0 else a


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _blur(a: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return a
    if cv2 is not None:
        k = max(1, int(sigma * 3) | 1)
        return cv2.GaussianBlur(a, (k, k), sigma)
    # numpy fallback: separable box blur approximation
    r = max(1, int(sigma))
    pad = np.pad(a, ((r, r), (r, r)), mode="reflect")
    out = np.zeros_like(a)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out += pad[r + dy:r + dy + a.shape[0], r + dx:r + dx + a.shape[1]]
    return out / ((2 * r + 1) ** 2)


def height_from_color(base: Image.Image | np.ndarray, detail: float = 1.0) -> np.ndarray:
    """Approximate a height field from perceived luminance (darker = lower)."""
    lum = _luminance(_to_array(base))
    # emphasise mid-frequency detail: height = lum minus a blurred version, recentred
    low = _blur(lum, sigma=8.0)
    h = lum + detail * (lum - low)
    h = np.clip(h, 0.0, 1.0)
    return h


def normal_from_height(height: np.ndarray, strength: float = 2.0) -> Image.Image:
    """Sobel-gradient tangent-space normal map (Source Y+ convention)."""
    h = height.astype(np.float32)
    if cv2 is not None:
        gx = cv2.Sobel(h, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(h, cv2.CV_32F, 0, 1, ksize=3)
    else:
        gx = np.gradient(h, axis=1)
        gy = np.gradient(h, axis=0)
    nx = -gx * strength
    ny = -gy * strength
    nz = np.ones_like(h)
    length = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-8
    nx, ny, nz = nx / length, ny / length, nz / length
    rgb = np.stack([nx, ny, nz], axis=-1)
    rgb = (rgb * 0.5 + 0.5) * 255.0
    return Image.fromarray(rgb.clip(0, 255).astype(np.uint8), mode="RGB")


def roughness_from_color(base: Image.Image | np.ndarray, base_level: float = 0.55,
                         detail_influence: float = 0.35) -> Image.Image:
    """Single-channel roughness: a base level modulated by local high-frequency detail.

    Detailed/edge regions read as slightly rougher; flat painted regions stay smoother.
    """
    rgb = _to_array(base)
    lum = _luminance(rgb)
    detail = np.abs(lum - _blur(lum, sigma=4.0))
    detail = detail / (detail.max() + 1e-6)
    rough = np.clip(base_level + detail_influence * (detail - 0.5), 0.02, 1.0)
    return Image.fromarray((rough * 255).astype(np.uint8), mode="L")


def metalness_from_color(base: Image.Image | np.ndarray, bias: float = 0.0) -> Image.Image:
    """Heuristic metalness in [0,1] biased per finish style.

    Desaturated, mid/bright pixels lean metallic; saturated colourful paint leans dielectric.
    `bias` shifts the whole map (e.g. +0.6 for anodized/patina metal styles).
    """
    rgb = _to_array(base)
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    sat = (mx - mn) / (mx + 1e-6)
    lum = _luminance(rgb)
    metal = (1.0 - sat) * lum
    metal = np.clip(metal * 0.8 + bias, 0.0, 1.0)
    return Image.fromarray((metal * 255).astype(np.uint8), mode="L")


def ao_from_height(height: np.ndarray, radius: float = 6.0, intensity: float = 0.6) -> Image.Image:
    """Cheap cavity-style AO: pixels below their local average are occluded."""
    low = _blur(height, sigma=radius)
    cavity = np.clip(height - low + 0.5, 0.0, 1.0)
    ao = 1.0 - intensity * (1.0 - cavity)
    return Image.fromarray((np.clip(ao, 0, 1) * 255).astype(np.uint8), mode="L")


def derive_all(base: Image.Image, *, metal_bias: float = 0.0, normal_strength: float = 2.0,
               roughness_base: float = 0.55) -> dict[str, Image.Image]:
    """Convenience: produce the full PBR set from a base-color image."""
    height = height_from_color(base)
    return {
        "normal": normal_from_height(height, strength=normal_strength),
        "roughness": roughness_from_color(base, base_level=roughness_base),
        "metalness": metalness_from_color(base, bias=metal_bias),
        "ao": ao_from_height(height),
    }
