"""In-app 3D preview: render the weapon mesh with the generated PBR maps.

Lets you iterate in seconds without launching CS2. Uses trimesh + pyrender (offscreen) when a mesh
and the libraries are available; otherwise falls back to a flat 2D contact sheet of the maps so the
pipeline still produces a visual. Returns a PIL image.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .assets import Weapon
from .export import SkinMaps


def render(weapon: Weapon, maps: SkinMaps, *, size: int = 1024) -> Image.Image:
    img = _render_3d(weapon, maps, size)
    if img is not None:
        return img
    return contact_sheet(maps, size)


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    """OpenGL-style camera pose (camera looks down -Z toward target)."""
    forward = target - eye
    forward = forward / (np.linalg.norm(forward) + 1e-9)
    right = np.cross(forward, up)
    right = right / (np.linalg.norm(right) + 1e-9)
    true_up = np.cross(right, forward)
    pose = np.eye(4)
    pose[:3, 0] = right
    pose[:3, 1] = true_up
    pose[:3, 2] = -forward
    pose[:3, 3] = eye
    return pose


def _render_3d(weapon: Weapon, maps: SkinMaps, size: int) -> Image.Image | None:
    if not weapon.obj_path.exists():
        return None
    try:
        import os
        import sys
        # egl is for headless Linux; on Windows/desktop let pyrender use the native context.
        if sys.platform.startswith("linux"):
            os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
        import trimesh
        import pyrender
    except Exception:
        return None
    try:
        mesh = trimesh.load(str(weapon.obj_path), force="mesh")
        uv = getattr(mesh.visual, "uv", None)
        if uv is None:
            return None
        mesh.visual = trimesh.visual.TextureVisuals(uv=uv)

        material = _pbr_material(maps, pyrender)
        prim = pyrender.Mesh.from_trimesh(mesh, material=material, smooth=False)

        # bg kept very dark so it stays dark after the display tone-map lift below.
        scene = pyrender.Scene(bg_color=[0.02, 0.02, 0.025, 1.0], ambient_light=[0.9, 0.9, 0.95])
        scene.add(prim)

        # Auto-frame: long axis = weapon length (horizontal); view the broad side at 3/4.
        bounds = mesh.bounds
        center = bounds.mean(axis=0)
        extents = bounds[1] - bounds[0]
        long_axis = int(np.argmax(extents))
        thin_axis = int(np.argmin(extents))
        up_axis = ({0, 1, 2} - {long_axis, thin_axis}).pop()

        yfov = np.pi / 4.0
        aspect = 16 / 9
        radius = float(np.linalg.norm(extents)) * 0.5
        dist = (max(extents) * 0.5) / (np.tan(yfov / 2.0) * aspect) + radius
        dist *= 1.25

        up = np.zeros(3); up[up_axis] = 1.0
        view_dir = np.zeros(3); view_dir[thin_axis] = 1.0
        eye = center + view_dir * dist + up * dist * 0.35
        pose = _look_at(eye, center, up)

        cam = pyrender.PerspectiveCamera(yfov=yfov, aspectRatio=aspect)
        scene.add(cam, pose=pose)

        # Multi-light rig (key + side fills + rim) so metallic/low-roughness surfaces catch
        # moving specular highlights instead of looking flat.
        right = np.cross(view_dir, up); right /= (np.linalg.norm(right) + 1e-9)
        rig = [
            (view_dir * 1.0 + up * 0.4, 11.0),                   # key, front-top
            (-right * 0.9 + up * 0.3 + view_dir * 0.5, 6.0),     # left fill
            (right * 0.9 + up * 0.3 + view_dir * 0.5, 6.0),      # right fill
            (-view_dir * 0.6 + up * 0.9, 4.5),                   # rim, back-top
        ]
        for direction, intensity in rig:
            eye2 = center + direction * dist
            scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=intensity),
                      pose=_look_at(eye2, center, up))

        w = size; h = int(size * 9 / 16)
        r = pyrender.OffscreenRenderer(w, h)
        color, _ = r.render(scene)
        r.delete()
        # Display tone-map: lift shadows so dark albedos read clearly, keep specular highlights.
        c = color.astype(np.float32) / 255.0
        c = np.clip(c ** 0.55 * 1.25, 0.0, 1.0)
        return Image.fromarray((c * 255).astype(np.uint8))
    except Exception:
        return None


def _pbr_material(maps: SkinMaps, pyrender):
    """Build a glTF MetallicRoughness material from the generated maps.

    glTF packs occlusion=R, roughness=G, metalness=B in one texture; baseColor + normal separate.
    """
    size = maps.pattern.size
    base = np.asarray(maps.pattern.convert("RGB"))

    def _chan(img, default):
        if img is None:
            return np.full((size[1], size[0]), default, np.uint8)
        return np.asarray(img.convert("L").resize(size))

    rough = _chan(maps.roughness, 140)
    # Cap metalness for the preview: pyrender has no environment map, so true metals would render
    # black. We treat it as a gloss hint — low roughness already gives the shiny highlights.
    metal = (_chan(maps.metalness, 0).astype(np.float32) * 0.35).astype(np.uint8)
    # glTF metallicRoughness packs roughness=G, metalness=B (R unused). AO is already baked into
    # the albedo, so no occlusion texture here (would double-darken). Normal map omitted too — the
    # baked AO already shows surface lines, and a tangent-space normal on this low-poly mesh just
    # darkens the diffuse.
    mr = np.stack([np.zeros_like(rough), rough, metal], axis=-1).astype(np.uint8)
    T = pyrender.Texture
    return pyrender.MetallicRoughnessMaterial(
        baseColorFactor=[1, 1, 1, 1], metallicFactor=1.0, roughnessFactor=1.0,
        baseColorTexture=T(source=base, source_channels="RGB"),
        metallicRoughnessTexture=T(source=mr, source_channels="RGB"))


def contact_sheet(maps: SkinMaps, size: int = 1024) -> Image.Image:
    """2D fallback: a labelled grid of all generated maps."""
    names = [("pattern", maps.pattern), ("normal", maps.normal), ("roughness", maps.roughness),
             ("metalness", maps.metalness), ("ao", maps.ao), ("mask", maps.mask)]
    present = [(n, m) for n, m in names if m is not None]
    cols = 3
    rows = (len(present) + cols - 1) // cols
    cell = size // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (20, 20, 24))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(sheet)
    for i, (name, m) in enumerate(present):
        thumb = m.convert("RGB").resize((cell, cell))
        x, y = (i % cols) * cell, (i // cols) * cell
        sheet.paste(thumb, (x, y))
        draw.rectangle([x, y, x + cell - 1, y + cell - 1], outline=(80, 80, 90))
        draw.text((x + 6, y + 6), name, fill=(255, 255, 255))
    return sheet
