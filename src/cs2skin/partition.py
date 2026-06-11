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


def _main_colors(arr: np.ndarray, k: int = 2) -> np.ndarray:
    """The k dominant colours of the image (k-means), brightest-first."""
    small = arr[::6, ::6].reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0)
    _, _, centers = cv2.kmeans(small, k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    centers = centers[np.argsort(-(centers @ np.array([0.299, 0.587, 0.114], np.float32)))]
    return centers


def flatten_by_parts(albedo: Image.Image, uv_img: Image.Image, *, main_colors: int = 2,
                     strength: float = 1.0, detail: float = 0.62, dilate: int = 2,
                     min_area: int = 90) -> Image.Image:
    """Recolour the gun with only `main_colors` (default 2) MAIN colours, each richly shaded.

    Two dominant colours are extracted from the generated art; every UV island is snapped to
    whichever main colour it's closest to, then each pixel is modulated by the original art's local
    luminance — so the skin reads as a cohesive ≤2-colour design but keeps full light/dark detail
    (shapes, gradients, edges) instead of a dead-flat fill. `detail` (0..1) sets how much variation
    is kept; `strength` blends with the original.
    """
    alb = albedo.convert("RGB")
    size = alb.size
    if cv2 is None:
        return alb
    arr = np.asarray(alb).astype(np.float32)
    lum = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    mains = _main_colors(arr, max(1, main_colors))
    seg = segment_islands(uv_img, size, dilate=dilate, min_area=min_area)
    if seg is None:
        return alb
    labels, valid = seg
    out = arr.copy()
    for lab in valid:
        m = labels == lab
        mean_c = arr[m].reshape(-1, 3).mean(axis=0)
        tint = mains[np.argmin(((mains - mean_c) ** 2).sum(axis=1))]   # nearest of the main colours
        ratio = lum[m] / (lum[m].mean() + 1e-3)                        # local light/dark, ~1.0 mean
        ratio = np.clip(1.0 + detail * (ratio - 1.0), 0.30, 2.0)       # keep `detail` of variation
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


def bake_ao(albedo: Image.Image, ao_img: Image.Image, amount: float = 0.8,
            edge: float = 0.55) -> Image.Image:
    """Bake the weapon's surface detail (panel lines, mag ribs, screws) into the colour so it stays
    visible on ANY colour — even plain black. Two effects:
      - cavity darkening: crevices get darker (`amount`),
      - edge highlighting: the rims around those crevices get lighter (`edge`),
    so every line reads as a dark groove + a bright edge and 'pops' regardless of base colour."""
    a = np.asarray(albedo.convert("RGB")).astype(np.float32)
    ao = np.asarray(ao_img.convert("L").resize(albedo.size)).astype(np.float32) / 255.0
    out = a * (1.0 - amount * (1.0 - ao))[..., None]              # darken cavities
    if edge > 0 and cv2 is not None:
        hp = ao - cv2.GaussianBlur(ao, (0, 0), 2.0)              # high-pass: +edges, -grooves
        out = out + (edge * 255.0) * hp[..., None]               # lift edges, deepen grooves
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
