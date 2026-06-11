"""Orchestrates prompt -> CS2-ready skin folder.

    generate (SDXL/ControlNet) -> type-driven treatment (flatten / AO / PBR) -> export

Single entry point used by both the CLI and the Gradio UI.
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
from .rarity import Rarity, get_rarity, DEFAULT_RARITY
from .skintype import SkinType, get_skin_type, DEFAULT_TYPE

# Design hint: two main colours, richly shaded, always highly detailed (never a flat fill).
DESIGN_HINT = "two main colours with many shades, highly detailed, never flat"


@dataclass
class SkinResult:
    out_dir: Path
    gen: GenResult
    weapon: Weapon
    skin_type: SkinType
    style: FinishStyle
    rarity: Rarity
    maps: SkinMaps


def create_skin(*, prompt: str, weapon: str = "ak47", skin_type: str = DEFAULT_TYPE,
                style: str | None = None, rarity: str | None = DEFAULT_RARITY,
                seed: int | None = None, colors: list[str] | None = None,
                main_colors: list | None = None, color_placement: str = "auto",
                brightness: float = 1.0, saturation: float = 1.0, detail: float = 1.0,
                reference_image: Image.Image | None = None, reference_scale: float = 0.9,
                flatten_strength: float = 1.0, generator: Generator | None = None,
                mock: bool | None = None) -> SkinResult:
    """Prompt + skin TYPE (+ optional reference image) -> CS2-ready skin folder.

    The type drives the finish style, material prompt, PBR (metalness/roughness), and whether the
    art is flattened to its main colours or left as a continuous pattern. Optional controls:
    main_colors (explicit list, else auto-extracted), color_placement ('auto' or 'size' = base/
    details by part size), and brightness/saturation/detail multipliers. A reference image (if
    given) is replicated as closely as possible. AO is always baked in for physical surface detail.
    """
    wpn = get_weapon(weapon)
    st = get_skin_type(skin_type)
    rar = get_rarity(rarity)
    fin = get_style(style or st.finish_style)
    gen = generator or Generator(mock=mock)

    user_prompt = f"{prompt}, {st.prompt}, {DESIGN_HINT}"
    negative = f"{NEGATIVE}, {rar.negative_extra}"
    if reference_image is not None:        # always replicate the reference as closely as possible
        user_prompt = f"{user_prompt}, closely replicating the reference image as the skin design"

    result = gen.generate(user_prompt, wpn, seed=seed, negative=negative,
                          reference_image=reference_image, reference_scale=reference_scale,
                          controlnet_scale=rar.controlnet_scale, steps=rar.steps)
    base = ImageEnhance.Color(result.image).enhance(st.saturation * saturation)

    _clamp = lambda x, lo, hi: max(lo, min(hi, x))
    # Type-driven post-processing: collapse to the main colours (explicit or auto), keeping shading.
    if st.part_flatten and wpn.uv_path.exists():
        from .partition import flatten_by_parts
        fdetail = _clamp(max(st.flatten_detail, 0.55) * detail, 0.2, 1.1)
        base = flatten_by_parts(base, Image.open(wpn.uv_path), colors=main_colors or None,
                                assign=color_placement, detail=fdetail, strength=flatten_strength)
    # ...then ALWAYS bake the weapon's ambient occlusion strongly, so physical detail (panel seams,
    # magazine ribs, screws) stays visible and even a plain/black skin never looks flat.
    ao_path = wpn.base_map("ao")
    if ao_path is not None:
        from .partition import bake_ao
        base = bake_ao(base, Image.open(ao_path), amount=_clamp(max(st.ao_amount, 0.8) * detail, 0, 1),
                       edge=0.55 * _clamp(detail, 0, 1.6))
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

    out_dir = export_skin(weapon=wpn, style=fin, maps=maps, prompt=prompt,
                          seed=result.seed, colors=colors, params={k: "" for k in fin.params})

    try:
        from . import preview
        preview.render(wpn, maps, size=960).save(out_dir / "preview" / "render.png")
    except Exception:
        pass

    return SkinResult(out_dir=out_dir, gen=result, weapon=wpn, skin_type=st, style=fin,
                      rarity=rar, maps=maps)


def _default_mask(base: Image.Image) -> Image.Image:
    """A neutral wear/paint mask (full coverage, no preset wear) the user can refine in Workbench."""
    import numpy as np
    size = base.size
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[..., 1] = 255    # G = patterned region (all); R=wear=0
    return Image.fromarray(arr, "RGB")
