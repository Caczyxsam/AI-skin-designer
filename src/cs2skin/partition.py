"""Flatten a generated albedo so each weapon part reads as a single colour.

CS2 UV template sheets outline each UV island (≈ a weapon part: trigger, barrel, magazine, stock…)
with GREEN lines (white lines are just internal mesh triangulation). We segment the sheet into
those green-bounded islands, then recolour each island with one dominant colour pulled from the
generated art. Result: clean, color-blocked parts instead of a busy pattern smeared across the gun.

Pipeline use: applied to the base albedo right after generation (strength-controlled).
"""

from __future__ import annotations

import numpy as np
from PIL import Image

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


def _green_lines(uv: np.ndarray) -> np.ndarray:
    """Mask of the green UV-island boundary lines."""
    r, g, b = uv[..., 0].astype(int), uv[..., 1].astype(int), uv[..., 2].astype(int)
    return ((g > 80) & (g - r > 25) & (g - b > 25)).astype(np.uint8)


def segment_islands(uv_img: Image.Image, size: tuple[int, int], *, dilate: int = 2,
                    min_area: int = 200):
    """Return (labels HxW int, [valid island labels]). None if cv2 unavailable."""
    if cv2 is None:
        return None
    uv = np.asarray(uv_img.convert("RGB").resize(size))
    green = _green_lines(uv)
    if dilate > 0:
        green = cv2.dilate(green, np.ones((dilate, dilate), np.uint8))
    non_barrier = (1 - green).astype(np.uint8)
    n, labels = cv2.connectedComponents(non_barrier, connectivity=4)
    bg = labels[0, 0]                      # exterior (corner) = background between shells
    valid = []
    for lab in range(n):
        if lab == bg:
            continue
        if int((labels == lab).sum()) >= min_area:
            valid.append(lab)
    return labels, valid


def flatten_by_parts(albedo: Image.Image, uv_img: Image.Image, *, palette: int = 10,
                     strength: float = 1.0, detail: float = 0.6, dilate: int = 2,
                     min_area: int = 90) -> Image.Image:
    """Give each UV island ONE colour while keeping its light/dark detail.

    Each island is tinted with its dominant colour, but every pixel is then modulated by the
    original art's local luminance — so painted detail (cracks, gradients, edges) survives as
    lighter/darker shades of that colour instead of a dead-flat fill. `detail` (0..1) controls how
    much of that variation is kept; `strength` blends the whole result with the original.
    """
    alb = albedo.convert("RGB")
    size = alb.size
    if cv2 is None:
        return alb
    arr = np.asarray(alb).astype(np.float32)
    lum = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    # Cohesive palette for the per-island tint (keeps the whole gun on a limited palette).
    quant = np.asarray(alb.quantize(colors=palette, method=Image.MEDIANCUT).convert("RGB"))
    seg = segment_islands(uv_img, size, dilate=dilate, min_area=min_area)
    if seg is None:
        return alb
    labels, valid = seg
    out = arr.copy()
    for lab in valid:
        m = labels == lab
        colors, counts = np.unique(quant[m].reshape(-1, 3), axis=0, return_counts=True)
        tint = colors[counts.argmax()].astype(np.float32)          # one colour for the part
        ratio = lum[m] / (lum[m].mean() + 1e-3)                    # local light/dark, ~1.0 mean
        ratio = np.clip(1.0 + detail * (ratio - 1.0), 0.35, 1.9)   # keep `detail` of the variation
        out[m] = np.clip(tint[None, :] * ratio[:, None], 0, 255)
    out = out.astype(np.uint8)
    # Fill the thin green seam lines from neighbouring islands so no green shows through.
    green = _green_lines(np.asarray(uv_img.convert("RGB").resize(size)))
    green = cv2.dilate(green, np.ones((dilate + 1, dilate + 1), np.uint8))
    out = cv2.inpaint(out, green.astype(np.uint8), 3, cv2.INPAINT_TELEA)
    flat = Image.fromarray(out)
    if strength >= 0.999:
        return flat
    return Image.blend(alb, flat, float(strength))


def bake_ao(albedo: Image.Image, ao_img: Image.Image, amount: float = 0.7) -> Image.Image:
    """Multiply the weapon's ambient-occlusion (crevices, panel lines, mag ribs) into the colour so
    physical surface detail stays visible even on a solid-coloured part. amount in [0,1]."""
    a = np.asarray(albedo.convert("RGB")).astype(np.float32)
    ao = np.asarray(ao_img.convert("L").resize(albedo.size)).astype(np.float32) / 255.0
    ao = 1.0 - amount * (1.0 - ao)                                 # lerp toward 1 by `amount`
    return Image.fromarray(np.clip(a * ao[..., None], 0, 255).astype(np.uint8), "RGB")
