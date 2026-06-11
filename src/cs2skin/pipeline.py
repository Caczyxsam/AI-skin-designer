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

# A small (untrained) hint that keeps compositions clean.
DESIGN_HINT = "integrated with weapon shape, cohesive natural palette"


@dataclass
class SkinResult:
    out_dir: Path
    gen: GenResult
    weapon: Weapon
    skin_type: SkinType
    style: FinishStyle
    rarity: Rarity
    maps: SkinMaps


# Reference-image use modes. "model" = replicate the skin in the image closely; "theme" = borrow
# its style/colours. Each maps to an IP-Adapter strength + a prompt nudge.
REFERENCE_MODES = {
    "model": (0.9, "closely replicating the reference skin design"),
    "theme": (0.55, "themed after the reference image's colours and style"),
}
DEFAULT_REFERENCE_MODE = "theme"


def create_skin(*, prompt: str, weapon: str = "ak47", skin_type: str = DEFAULT_TYPE,
                style: str | None = None, rarity: str | None = DEFAULT_RARITY,
                seed: int | None = None, colors: list[str] | None = None,
                reference_image: Image.Image | None = None,
                reference_mode: str = DEFAULT_REFERENCE_MODE, reference_scale: float | None = None,
                flatten_strength: float = 1.0, generator: Generator | None = None,
                mock: bool | None = None) -> SkinResult:
    """Prompt + skin TYPE (+ optional quality + reference) -> CS2-ready skin folder.

    The type drives the finish style, material prompt, PBR (metalness/roughness), and whether the
    art is flattened per part or left as a continuous pattern. Quality adds complexity. A reference
    image is used either as a 'model' (replicate the skin) or a 'theme' (style/colours only). AO is
    baked in for physical surface detail (panel lines, magazine ribs).
    """
    wpn = get_weapon(weapon)
    st = get_skin_type(skin_type)
    rar = get_rarity(rarity)
    fin = get_style(style or st.finish_style)
    gen = generator or Generator(mock=mock)

    user_prompt = f"{prompt}, {st.prompt}, {rar.prompt_modifiers}, {DESIGN_HINT}"
    negative = f"{NEGATIVE}, {rar.negative_extra}"

    ip_scale, ref_hint = REFERENCE_MODES.get(reference_mode, REFERENCE_MODES[DEFAULT_REFERENCE_MODE])
    if reference_scale is not None:        # explicit override of the mode's default strength
        ip_scale = reference_scale
    if reference_image is not None:
        user_prompt = f"{user_prompt}, {ref_hint}"

    result = gen.generate(user_prompt, wpn, seed=seed, negative=negative,
                          reference_image=reference_image, reference_scale=ip_scale,
                          controlnet_scale=rar.controlnet_scale, steps=rar.steps)
    base = ImageEnhance.Color(result.image).enhance(st.saturation)

    # Type-driven post-processing.
    if st.part_flatten and wpn.uv_path.exists():
        from .partition import flatten_by_parts
        base = flatten_by_parts(base, Image.open(wpn.uv_path), strength=flatten_strength,
                                detail=st.flatten_detail)
    # Bake the weapon's ambient occlusion so physical lines (panel seams, mag ribs) stay visible.
    ao_path = wpn.base_map("ao")
    if ao_path is not None:
        from .partition import bake_ao
        base = bake_ao(base, Image.open(ao_path), amount=st.ao_amount)

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
