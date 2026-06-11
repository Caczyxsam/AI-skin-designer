"""Skin TYPE — the primary creative choice (the material/look family).

Each type maps to a CS2 finish style for export AND drives how the skin is generated and treated:
prompt modifiers (material look), PBR (metalness/roughness), and post-processing (per-part colour
flatten vs. continuous pattern, AO strength, saturation). This is what makes a "metallic" skin
look like tinted steel and a "patina" skin look like aged rusted metal.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkinType:
    key: str
    label: str
    blurb: str                 # short UI description
    finish_style: str          # CS2 finish style key (for export config)
    prompt: str                # material/look modifiers added to the prompt
    metal_bias: float          # PBR metalness bias (0 dielectric .. 1 metal)
    roughness_base: float      # PBR base roughness (low = glossy/reflective)
    part_flatten: bool         # True = one colour per part; False = continuous pattern
    flatten_detail: float      # how much surface detail to keep when flattening (0..1)
    saturation: float          # colour boost
    ao_amount: float           # how strongly to bake in surface occlusion (lines/wear)


SKIN_TYPES: dict[str, SkinType] = {
    "painted": SkinType(
        key="painted", label="Painted / Coated",
        blurb="Flat paint layer, bold stylized graphics — clearly ‘art on the gun’. Arcade / esports / fantasy.",
        finish_style="custom_paint",
        prompt="flat painted coating, bold stylized graphic design, vivid art printed on the weapon, "
               "clean colour blocking, matte paint finish",
        metal_bias=0.0, roughness_base=0.62, part_flatten=True, flatten_detail=0.5,
        saturation=1.5, ao_amount=0.7),

    "metallic": SkinType(
        key="metallic", label="Metallic / Anodized",
        blurb="Shiny tinted metal, brushed or polished steel, reflective. Industrial / high-end.",
        finish_style="anodized_multi",
        prompt="polished anodized metal, brushed metallic steel, colour-tinted chrome, glossy "
               "reflective sheen, premium high-end metal finish",
        metal_bias=0.78, roughness_base=0.26, part_flatten=True, flatten_detail=0.85,
        saturation=1.3, ao_amount=0.6),

    "hydrographic": SkinType(
        key="hydrographic", label="Hydrographic (water-transfer)",
        blurb="Pattern wrapped over the metal like a film — camo / tactical, conforms to edges.",
        finish_style="hydrographic",
        prompt="hydrographic water-transfer film wrapped over metal, tactical camouflage pattern, "
               "thin semi-gloss film conforming to the surface, utilitarian",
        metal_bias=0.3, roughness_base=0.45, part_flatten=False, flatten_detail=1.0,
        saturation=1.3, ao_amount=0.65),

    "pattern": SkinType(
        key="pattern", label="Pattern-based",
        blurb="Seamless all-over pattern; placement varies per copy (collectible ‘god patterns’).",
        finish_style="custom_paint",
        prompt="seamless repeating procedural pattern, intricate all-over pattern design, "
               "collectible varied pattern placement, cohesive motif",
        metal_bias=0.12, roughness_base=0.5, part_flatten=False, flatten_detail=1.0,
        saturation=1.45, ao_amount=0.6),

    "patina": SkinType(
        key="patina", label="Patina / Weathered",
        blurb="Rust, oxidation, scratches and aging — a real-world used weapon look.",
        finish_style="patina",
        prompt="aged weathered metal, rust and oxidation stains, corrosion, scratched worn surface, "
               "darkened antique patina, real-world used weapon",
        metal_bias=0.5, roughness_base=0.7, part_flatten=False, flatten_detail=1.0,
        saturation=1.05, ao_amount=0.9),

    "hybrid": SkinType(
        key="hybrid", label="Hybrid / Composite",
        blurb="Mix of paint + metal + decals + effects — detailed, futuristic, light-reactive.",
        finish_style="custom_paint",
        prompt="complex multi-layer composite finish, mix of paint metal and decals, futuristic "
               "high-detail design, dynamic light-reactive materials, intricate layered shapes",
        metal_bias=0.35, roughness_base=0.4, part_flatten=True, flatten_detail=0.78,
        saturation=1.45, ao_amount=0.7),
}

DEFAULT_TYPE = "painted"


def get_skin_type(key: str | None) -> SkinType:
    if key is None:
        return SKIN_TYPES[DEFAULT_TYPE]
    try:
        return SKIN_TYPES[key]
    except KeyError:
        raise KeyError(f"Unknown skin type {key!r}. Known: {', '.join(SKIN_TYPES)}")


def list_skin_types() -> list[SkinType]:
    return list(SKIN_TYPES.values())
