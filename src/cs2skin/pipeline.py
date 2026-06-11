"""Orchestrates prompt -> CS2-ready skin folder, in two stages so skins can be EDITED:

    generate_art()  — the slow AI step (SDXL/ControlNet). Produces the raw painted art. Cacheable.
    style_skin()    — instant, no GPU: colours / placement / brightness / detail / AO / PBR / export.

`create_skin()` just runs both (used by the CLI). The UI caches the GenArt so "Apply edits" can
restyle the same design instantly without regenerating.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance

from . import pbr
from .assets import Weapon, get_weapon
from .export import SkinMaps, export_skin
from .finishes import FinishStyle, get_style
from .generate import GenResult, Generator, NEGATIVE
from .rarity import get_rarity, DEFAULT_RARITY
from .skintype import SkinType, get_skin_type, DEFAULT_TYPE

# Design hint: two main colours, richly shaded, always highly detailed (never a flat fill).
DESIGN_HINT = "two main colours with many shades, highly detailed, never flat"


@dataclass
class GenArt:
    """The raw AI-generated art for a weapon — the cacheable 'design' that styling is applied to."""
    image: Image.Image
    weapon: Weapon
    skin_type: SkinType
    seed: int
    prompt: str
    gen: GenResult


@dataclass
class SkinResult:
    out_dir: Path
    gen: GenResult
    weapon: Weapon
    skin_type: SkinType
    style: FinishStyle
    maps: SkinMaps


def generate_art(*, prompt: str, weapon: str = "ak47", skin_type: str = DEFAULT_TYPE,
                 rarity: str | None = DEFAULT_RARITY, seed: int | None = None,
                 reference_image: Image.Image | None = None, reference_scale: float = 0.9,
                 generator: Generator | None = None, mock: bool | None = None) -> GenArt:
    """Run the AI generation only (the slow part). The result can be restyled many times cheaply."""
    wpn = get_weapon(weapon)
    st = get_skin_type(skin_type)
    rar = get_rarity(rarity)
    gen = generator or Generator(mock=mock)

    # Claude's prompt already describes the motif fully; keep the suffix short so SDXL's 77-token
    # text limit doesn't truncate it. Palette + tonal map handle colour/contrast (no DESIGN_HINT).
    user_prompt = f"{prompt}, {st.prompt}" if len(prompt) < 180 else prompt
    negative = f"{NEGATIVE}, {rar.negative_extra}"
    if reference_image is not None:        # always replicate the reference as closely as possible
        user_prompt = f"{user_prompt}, closely replicating the reference image as the skin design"

    result = gen.generate(user_prompt, wpn, seed=seed, negative=negative,
                          reference_image=reference_image, reference_scale=reference_scale,
                          controlnet_scale=rar.controlnet_scale, steps=rar.steps)
    return GenArt(image=result.image, weapon=wpn, skin_type=st, seed=result.seed,
                  prompt=prompt, gen=result)


def style_skin(art: GenArt, *, palette: list | None = None, style: str | None = None,
               colors: list[str] | None = None, main_colors: list | None = None,
               color_placement: str = "auto", brightness: float = 1.0, saturation: float = 1.0,
               detail: float = 1.0, flatten_strength: float = 1.0) -> SkinResult:
    """Apply styling to already-generated art and export. Fast (no GPU).

    palette: an ordered (dark->light) colour list — the art's tones are mapped onto it for a cohesive
    recolour (the primary path, set by the Claude art-director). If no palette, falls back to the
    older per-part flatten (main_colors / color_placement) for the CLI.
    """
    wpn, st = art.weapon, art.skin_type
    fin = get_style(style or st.finish_style)
    _clamp = lambda x, lo, hi: max(lo, min(hi, x))

    if palette:
        from .partition import gradient_map
        base = gradient_map(art.image, palette)     # deliberate, cohesive colours
    else:
        base = ImageEnhance.Color(art.image).enhance(st.saturation * saturation)
        if st.part_flatten and wpn.uv_path.exists():
            from .partition import flatten_by_parts
            fdetail = _clamp(max(st.flatten_detail, 0.55) * detail, 0.2, 1.1)
            base = flatten_by_parts(base, Image.open(wpn.uv_path), colors=main_colors or None,
                                    assign=color_placement, detail=fdetail, strength=flatten_strength)

    # Bake the weapon's ambient occlusion so physical detail (panel seams, mag ribs, screws) stays
    # visible. Lighter on the palette path so bright accents / glow aren't darkened away.
    ao_path = wpn.base_map("ao")
    if ao_path is not None:
        from .partition import bake_ao
        ao_amt = 0.45 if palette else _clamp(max(st.ao_amount, 0.8) * detail, 0, 1)
        ao_edge = 0.5 if palette else 0.55 * _clamp(detail, 0, 1.6)
        base = bake_ao(base, Image.open(ao_path), amount=ao_amt, edge=ao_edge)
    if brightness != 1.0:
        base = ImageEnhance.Brightness(base).enhance(float(brightness))

    derived = pbr.derive_all(base, metal_bias=st.metal_bias, roughness_base=st.roughness_base)
    maps = SkinMaps(
        pattern=base,
        normal=derived["normal"] if fin.needs_normal else None,
        roughness=derived["roughness"],
        metalness=derived["metalness"],
        ao=derived["ao"],
        mask=_default_mask(base) if fin.needs_mask else None,
    )

    out_dir = export_skin(weapon=wpn, style=fin, maps=maps, prompt=art.prompt,
                          seed=art.seed, colors=colors, params={k: "" for k in fin.params})
    try:
        from . import preview
        preview.render(wpn, maps, size=960).save(out_dir / "preview" / "render.png")
    except Exception:
        pass

    return SkinResult(out_dir=out_dir, gen=art.gen, weapon=wpn, skin_type=st, style=fin, maps=maps)


def create_skin(*, prompt: str, weapon: str = "ak47", skin_type: str = DEFAULT_TYPE,
                style: str | None = None, rarity: str | None = DEFAULT_RARITY,
                seed: int | None = None, colors: list[str] | None = None,
                main_colors: list | None = None, color_placement: str = "auto",
                brightness: float = 1.0, saturation: float = 1.0, detail: float = 1.0,
                reference_image: Image.Image | None = None, reference_scale: float = 0.9,
                flatten_strength: float = 1.0, generator: Generator | None = None,
                mock: bool | None = None) -> SkinResult:
    """Generate + style in one call (prompt -> CS2-ready skin folder)."""
    art = generate_art(prompt=prompt, weapon=weapon, skin_type=skin_type, rarity=rarity, seed=seed,
                       reference_image=reference_image, reference_scale=reference_scale,
                       generator=generator, mock=mock)
    return style_skin(art, style=style, colors=colors, main_colors=main_colors,
                      color_placement=color_placement, brightness=brightness, saturation=saturation,
                      detail=detail, flatten_strength=flatten_strength)


def _default_mask(base: Image.Image) -> Image.Image:
    """A neutral wear/paint mask (full coverage, no preset wear) the user can refine in Workbench."""
    import numpy as np
    size = base.size
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[..., 1] = 255    # G = patterned region (all); R=wear=0
    return Image.fromarray(arr, "RGB")
