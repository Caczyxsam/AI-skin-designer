"""Export a generated skin into a CS2 Workbench-ready folder.

What the Workbench needs: the finish's texture maps as **TGA** files (it also accepts PNG), plus
a place to assign the finish style and parameters. We write:

  output/<weapon>_<slug>/
    textures/   <stem>_pattern.tga, _normal.tga, _rough.tga, _masks.tga, ...  (per finish style)
    preview/    flat map previews + (optional) 3D render
    finish.json the finish recipe (style, params, colors, channel-packing notes)
    IMPORT.md   exact click-by-click steps to load it in the in-game Workbench

We deliberately emit TGA (the format the Workbench imports) and a human recipe rather than trying
to forge engine-internal .vmat/compiled files — the supported authoring path is the in-game
Workbench, so we hand it clean inputs. Channel packing follows the chosen FinishStyle.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from .assets import Weapon
from .config import get_config
from .finishes import FinishStyle


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (s[:40] or "skin")


@dataclass
class SkinMaps:
    """The image maps available to export. Keys match FinishStyle MapSpec.name logical names."""

    pattern: Image.Image
    normal: Image.Image | None = None
    roughness: Image.Image | None = None
    metalness: Image.Image | None = None
    ao: Image.Image | None = None
    mask: Image.Image | None = None

    def get(self, name: str) -> Image.Image | None:
        return getattr(self, name, None)


def _pack_alpha(rgb: Image.Image, alpha: Image.Image | None) -> Image.Image:
    """Attach a single-channel alpha to an RGB image (for roughness-in-alpha style packing)."""
    rgb = rgb.convert("RGB")
    if alpha is None:
        return rgb
    a = alpha.convert("L").resize(rgb.size)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out


def _resize(img: Image.Image, size: int) -> Image.Image:
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    return img


@dataclass
class FinishRecipe:
    weapon: str
    weapon_display: str
    style: str
    style_workbench_name: str
    prompt: str
    seed: int
    colors: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)
    channel_packing: dict = field(default_factory=dict)


def export_skin(*, weapon: Weapon, style: FinishStyle, maps: SkinMaps, prompt: str,
                seed: int = -1, colors: list[str] | None = None,
                params: dict | None = None, out_root: Path | None = None) -> Path:
    """Write a complete Workbench-ready folder and return its path."""
    cfg = get_config()
    res = cfg.generation.texture_resolution
    slug = slugify(prompt)
    out_dir = (out_root or cfg.paths.output) / f"{weapon.key}_{slug}"
    tex_dir = out_dir / "textures"
    prev_dir = out_dir / "preview"
    tex_dir.mkdir(parents=True, exist_ok=True)
    prev_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{weapon.key}_{slug}"
    files: dict[str, str] = {}
    packing: dict[str, str] = {}

    # Write each map the finish style declares, honoring its channel-packing rules.
    for spec in style.maps:
        logical = spec.name
        img = maps.get(logical)
        if img is None:
            if spec.required:
                raise ValueError(
                    f"Finish '{style.key}' requires map '{logical}' but it was not generated."
                )
            continue
        img = _resize(img, res)

        # Roughness-in-alpha packing for styles that ask for it (e.g. anodized_multi, custom_paint).
        alpha_desc = spec.channels.get("A", "")
        if logical == "pattern" and alpha_desc:
            if "rough" in alpha_desc.lower() and maps.roughness is not None:
                img = _pack_alpha(img, _resize(maps.roughness, res))
                packing[f"{stem}_pattern"] = "RGB=base color, A=roughness"
            elif maps.mask is not None and ("mask" in alpha_desc.lower() or "coverage" in alpha_desc.lower() or "opacity" in alpha_desc.lower()):
                img = _pack_alpha(img, _resize(maps.mask, res))
                packing[f"{stem}_pattern"] = f"RGB=base color, A={alpha_desc}"

        fname = spec.filename.replace("{stem}", stem) + ".tga"
        path = tex_dir / fname
        # TGA: keep RGBA if we packed alpha, else RGB. PIL writes uncompressed TGA the Workbench reads.
        img.save(path)
        files[logical] = str(path.relative_to(out_dir))
        if fname.replace(".tga", "") not in packing:
            packing[fname.replace(".tga", "")] = ", ".join(f"{k}={v}" for k, v in spec.channels.items())

    # Flat previews (PNG, easy to eyeball) for every map we produced.
    for name in ("pattern", "normal", "roughness", "metalness", "ao", "mask"):
        img = maps.get(name)
        if img is not None:
            _resize(img.convert("RGB"), min(res, 1024)).save(prev_dir / f"{name}.png")

    recipe = FinishRecipe(
        weapon=weapon.key,
        weapon_display=weapon.display,
        style=style.key,
        style_workbench_name=style.workbench_name,
        prompt=prompt,
        seed=seed,
        colors=colors or [],
        params=params or {},
        files=files,
        channel_packing=packing,
    )
    (out_dir / "finish.json").write_text(json.dumps(asdict(recipe), indent=2), encoding="utf-8")

    # The real Workbench config: KeyValues with the style's numeric id + Valve default params.
    kv = style.keyvalues(pattern_name=f"{stem}_pattern", colors=colors or None)
    (out_dir / f"{stem}.txt").write_text(kv, encoding="utf-8")

    (out_dir / "IMPORT.md").write_text(_import_guide(weapon, style, stem, files), encoding="utf-8")
    return out_dir


def _import_guide(weapon: Weapon, style: FinishStyle, stem: str, files: dict[str, str]) -> str:
    tex = "\n".join(f"  - `{path.replace(chr(92), '/')}` → **{logical}** slot"
                    for logical, path in files.items())
    return f"""# Import into the CS2 Workshop Item Editor

Skin: **{weapon.display}** — finish style **{style.workbench_name}** (style id `{style.style_id}`)

## One-time setup
- Steam → Counter-Strike 2 → Properties → **DLC** → install **Counter-Strike 2 Workshop Tools**.
- Launch CS2 via **Play** → choose **Counter-Strike 2 Workshop Tools** from the dialog.

## Create the paint kit
1. In the tools launcher open the **Workshop Item Editor** (weapon finishes).
2. In the paint-kit list, right-click the **{style.workbench_name}** style folder → **New Paint Kit**.
   Name it with lowercase/no spaces, e.g. `{stem}`.
3. Set the **weapon** to **{weapon.display}** (`{weapon.model_name}`).

## Import these textures (from this folder's `textures/`)
{tex}

> Albedo/pattern color range matters for acceptance: keep metallic areas ~180-250 and
> non-metallic ~55-220 in 8-bit RGB, or the finish reads as too dark/bright in-game.

## Apply parameters
Use **`{stem}.txt`** — a ready-made KeyValues block in Valve's finish format (style id, colors,
pattern_scale, phong, wear_remap, offsets, from Valve's official defaults for this style). Match the
editor fields to these values, or drop it in as the `"workshop preview"` config.

## Preview & submit
Adjust pattern scale/offset until seams land cleanly, sweep the **wear** slider to check all wear
levels, then submit to the Steam Workshop when happy.

## Style notes
{style.description}
Channel packing is documented in `finish.json`.
"""
