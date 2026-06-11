"""CS2 weapon-finish style definitions.

A CS2 skin is a *weapon finish* with a chosen **style**. Each style consumes a different set of
texture maps, packs PBR data into specific channels, and is configured by a KeyValues block the
Workbench reads. This module encodes all of that so:
  - the exporter (`export.py`) writes a config the Workbench accepts (real `style` IDs + params),
  - the PBR stage (`pbr.py`) knows which maps to produce and how to pack them.

The numeric `style` IDs and default parameters below are taken verbatim from Valve's official
`FinishExamples/*.txt` (shipped in workbench_materials.zip). Style IDs:
  1 Solid Color · 2 Hydrographic · 3 Spray Paint · 4 Anodized · 5 Anodized Multicolored
  6 Anodized Airbrushed · 7 Custom Paint Job · 8 Patina · 9 Gunsmith
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class MapSpec:
    """One texture map a finish style consumes, and how its channels are packed."""

    name: str                      # logical name, e.g. "pattern"
    filename: str                  # exported file stem, with {stem} placeholder
    channels: dict[str, str]       # channel -> what it carries
    required: bool = True
    srgb: bool = True              # color maps sRGB; data maps (normal/rough) linear
    note: str = ""


@dataclass(frozen=True)
class FinishStyle:
    """A CS2 finish style and everything the pipeline needs to target it."""

    key: str                       # our stable id, e.g. "custom_paint"
    style_id: int                  # Valve numeric `style` value
    workbench_name: str            # label shown in the in-game Workbench dropdown
    description: str
    maps: list[MapSpec]
    params: dict[str, str]         # exposed finish parameters -> short description
    kv_defaults: dict[str, str]    # default KeyValues block (from Valve FinishExamples)
    user_colors: int               # how many user-pickable colors (color0..colorN-1)
    ai_suitability: int            # 1-5: how well free-form AI art maps onto this style
    ai_notes: str = ""

    def map(self, name: str) -> MapSpec | None:
        return next((m for m in self.maps if m.name == name), None)

    @property
    def needs_normal(self) -> bool:
        return self.map("normal") is not None

    @property
    def needs_mask(self) -> bool:
        return self.map("mask") is not None

    def keyvalues(self, *, pattern_name: str, colors: list[str] | None = None,
                  overrides: dict[str, str] | None = None) -> str:
        """Render the Workbench KeyValues config for this finish.

        `pattern_name` is the texture stem the Workbench will look up; `colors` overrides
        color0.. ; `overrides` replaces any default param (e.g. pattern_scale).
        """
        kv: dict[str, str] = {"style": str(self.style_id)}
        kv.update(self.kv_defaults)
        if self.map("pattern") is not None:
            kv["pattern"] = pattern_name
        for i, c in enumerate(colors or []):
            if i < 4:
                kv[f"color{i}"] = c
        if overrides:
            kv.update({k: str(v) for k, v in overrides.items()})
        lines = ['"workshop preview"', "{"]
        for k, v in kv.items():
            lines.append(f'\t"{k}"\t\t"{v}"')
        lines.append("}")
        return "\n".join(lines) + "\n"


# --- common map specs -------------------------------------------------------------------------

def _pattern(alpha: str = "") -> MapSpec:
    chans = {"RGB": "base color (the art)"}
    if alpha:
        chans["A"] = alpha
    return MapSpec("pattern", "{stem}_pattern", chans, srgb=True,
                   note="Painted onto the weapon UV layout at 2048 or 4096.")


def _normal() -> MapSpec:
    return MapSpec("normal", "{stem}_normal", {"RGB": "tangent-space normal"},
                   required=False, srgb=False, note="Source/OpenGL (Y+). Flat = (128,128,255).")


def _roughness() -> MapSpec:
    return MapSpec("roughness", "{stem}_rough", {"R": "roughness (0=mirror,255=matte)"},
                   required=False, srgb=False)


def _masks(desc: str) -> MapSpec:
    return MapSpec("mask", "{stem}_masks", {"R": "wear", "G/B": desc}, required=False, srgb=False,
                   note="Red = wear, Green/Blue = region selection (paint-by-number).")


# --- the finish styles ------------------------------------------------------------------------

STYLES: dict[str, FinishStyle] = {
    "custom_paint": FinishStyle(
        key="custom_paint", style_id=7, workbench_name="Custom Paint Job",
        description=("Fully custom art mapped directly to the weapon UV, with its own normal map "
                     "and paint/wear mask. The most freeform style and best target for AI art."),
        maps=[_pattern(alpha="paint mask (where paint sits)"), _normal(), _roughness(),
              _masks("where wear/grunge accumulates")],
        params={"pattern_scale": "Tiling/scale across the UV.",
                "phongexponent": "Specular tightness.", "phongintensity": "Specular strength.",
                "wear_remap_min/max": "Paint-wear range."},
        kv_defaults={"pattern_scale": "1.00", "phongexponent": "128", "phongintensity": "153",
                     "ignore_weapon_size_scale": "1", "pattern_offset_x_start": "0.00",
                     "pattern_offset_x_end": "0.00", "pattern_offset_y_start": "0.00",
                     "pattern_offset_y_end": "0.00", "pattern_rotate_start": "0.00",
                     "pattern_rotate_end": "0.00", "wear_remap_min": "0.02",
                     "wear_remap_max": "0.46", "dialog_config": "12,0,0,1"},
        user_colors=0, ai_suitability=5,
        ai_notes="Pattern is the literal painted texture — AI art lands 1:1. Default choice."),

    "anodized_multi": FinishStyle(
        key="anodized_multi", style_id=5, workbench_name="Anodized Multicolored",
        description=("Metallic anodized base with up to 4 colors plus a pattern. Roughness packs "
                     "into the pattern ALPHA; a paint-by-number mask (green/blue) selects patterned "
                     "vs. solid-color regions. Strong metallic sheen."),
        maps=[_pattern(alpha="roughness (per-pixel reflectivity)"),
              _masks("paint-by-number: G/B pick solid color regions (colors 3 & 4)")],
        params={"color0..color3": "Up to four user colors.", "pattern_scale": "Pattern scale.",
                "phongexponent": "Specular tightness.", "phongalbedoboost": "Metallic boost."},
        kv_defaults={"color0": "94 34 35", "color1": "94 34 35", "color2": "57 21 22",
                     "color3": "23 23 23", "pattern_scale": "2.50", "phongexponent": "4",
                     "phongalbedoboost": "100", "view_model_exponent_override_size": "1024",
                     "pattern_offset_x_start": "0.00", "pattern_offset_x_end": "1.00",
                     "pattern_offset_y_start": "0.00", "pattern_offset_y_end": "1.00",
                     "pattern_rotate_start": "0.00", "pattern_rotate_end": "0.00",
                     "wear_remap_min": "0.10", "wear_remap_max": "0.26", "dialog_config": "12,0,0,1"},
        user_colors=4, ai_suitability=3,
        ai_notes="AI generates the RGB pattern; we derive roughness into alpha. Looks metallic."),

    "anodized_airbrushed": FinishStyle(
        key="anodized_airbrushed", style_id=6, workbench_name="Anodized Airbrushed",
        description=("Anodized metal base with an airbrushed pattern; pattern alpha controls where "
                     "the color overlay applies over the metallic base."),
        maps=[_pattern(alpha="overlay opacity")],
        params={"color0..color3": "Anodized + overlay colors.", "pattern_scale": "Pattern scale."},
        kv_defaults={"color0": "80 10 1", "color1": "34 2 1", "color2": "16 16 16",
                     "color3": "90 60 4", "pattern_scale": "1.60", "phongexponent": "16",
                     "phongalbedoboost": "30", "ignore_weapon_size_scale": "1",
                     "pattern_offset_x_start": "-1.30", "pattern_offset_x_end": "-1.30",
                     "pattern_offset_y_start": "0.00", "pattern_offset_y_end": "1.00",
                     "pattern_rotate_start": "0.00", "pattern_rotate_end": "0.00",
                     "wear_remap_min": "0.00", "wear_remap_max": "0.08", "dialog_config": "12,0,0,1"},
        user_colors=4, ai_suitability=3,
        ai_notes="Good for glossy airbrushed designs over chrome/anodized metal."),

    "hydrographic": FinishStyle(
        key="hydrographic", style_id=2, workbench_name="Hydrographic",
        description=("Water-transfer print over base metal. Pattern provides color; a paint mask "
                     "controls coverage and wear. Semi-glossy."),
        maps=[_pattern(alpha="paint coverage"), _masks("coverage/wear")],
        params={"color0..color3": "Tints.", "pattern_scale": "Print scale.",
                "wear_remap_min/max": "Wear range."},
        kv_defaults={"color0": "191 191 191", "color1": "157 138 119", "color2": "96 67 51",
                     "color3": "19 19 19", "pattern_scale": "3.00", "phongexponent": "10",
                     "phongintensity": "10", "ignore_weapon_size_scale": "1",
                     "pattern_offset_x_start": "0.00", "pattern_offset_x_end": "1.00",
                     "pattern_offset_y_start": "0.00", "pattern_offset_y_end": "1.00",
                     "pattern_rotate_start": "0.00", "pattern_rotate_end": "360.00",
                     "wear_remap_min": "0.00", "wear_remap_max": "0.80", "dialog_config": "12,0,0,1"},
        user_colors=4, ai_suitability=4,
        ai_notes="Close to custom paint for AI art but with metallic show-through."),

    "spray_paint": FinishStyle(
        key="spray_paint", style_id=3, workbench_name="Spray Paint",
        description="Matte spray-painted coat. Like hydrographic but rough/non-reflective.",
        maps=[_pattern(alpha="paint coverage"), _masks("coverage/wear")],
        params={"color0..color3": "Tints.", "pattern_scale": "Pattern scale.",
                "wear_remap_min/max": "Wear range."},
        kv_defaults={"color0": "56 71 54", "color1": "158 149 114", "color2": "79 41 32",
                     "color3": "45 46 33", "pattern_scale": "0.90", "phongexponent": "32",
                     "phongintensity": "5", "ignore_weapon_size_scale": "0",
                     "pattern_offset_x_start": "0.00", "pattern_offset_x_end": "1.00",
                     "pattern_offset_y_start": "0.00", "pattern_offset_y_end": "1.00",
                     "pattern_rotate_start": "-10.00", "pattern_rotate_end": "7.00",
                     "wear_remap_min": "0.06", "wear_remap_max": "0.80", "dialog_config": "12,0,0,1"},
        user_colors=4, ai_suitability=4,
        ai_notes="Use for matte, stencil, graffiti looks."),

    "anodized": FinishStyle(
        key="anodized", style_id=4, workbench_name="Anodized",
        description="Single-color anodized metal. No pattern — color + specular only.",
        maps=[],
        params={"color0": "Anodized color.", "phongexponent": "Specular tightness."},
        kv_defaults={"color0": "48 3 1", "phongexponent": "16", "phongalbedoboost": "20",
                     "wear_remap_min": "0.00", "wear_remap_max": "0.08", "dialog_config": "12,0,0,1"},
        user_colors=1, ai_suitability=1,
        ai_notes="No art surface — not a meaningful AI target."),

    "patina": FinishStyle(
        key="patina", style_id=8, workbench_name="Patina",
        description=("Aged/oxidized metal. Pattern + masks drive where oxidation and polished "
                     "metal show. Strongly metallic, antique feel."),
        maps=[_pattern(), _masks("oxidation vs. polished metal")],
        params={"color0..color3": "Patina tints.", "pattern_scale": "Pattern scale."},
        kv_defaults={"color0": "90 62 50", "color1": "77 46 40", "color2": "68 72 70",
                     "color3": "121 142 135", "pattern_scale": "2.00", "phongexponent": "16",
                     "phongalbedoboost": "35", "pattern_offset_x_start": "0.00",
                     "pattern_offset_x_end": "1.00", "pattern_offset_y_start": "0.00",
                     "pattern_offset_y_end": "1.00", "pattern_rotate_start": "0.00",
                     "pattern_rotate_end": "360.00", "wear_remap_min": "0.00",
                     "wear_remap_max": "1.00", "dialog_config": "12,0,0,1"},
        user_colors=4, ai_suitability=2,
        ai_notes="Best for weathered/antique metal; AI controls the patina pattern."),

    "solid_color": FinishStyle(
        key="solid_color", style_id=1, workbench_name="Solid Color",
        description="Flat color blocks (up to 4). No pattern texture.",
        maps=[],
        params={"color0..color3": "The colors."},
        kv_defaults={"color0": "47 52 37", "color1": "65 78 61", "color2": "102 91 66",
                     "color3": "51 53 26", "phongexponent": "16", "phongintensity": "13",
                     "wear_remap_min": "0.06", "wear_remap_max": "0.80", "dialog_config": "12,0,0,1"},
        user_colors=4, ai_suitability=1,
        ai_notes="No art surface — not a meaningful AI target."),
}

DEFAULT_STYLE = "custom_paint"


def get_style(key: str) -> FinishStyle:
    try:
        return STYLES[key]
    except KeyError:
        raise KeyError(f"Unknown finish style {key!r}. Known: {', '.join(STYLES)}")


def list_styles() -> list[FinishStyle]:
    return list(STYLES.values())
