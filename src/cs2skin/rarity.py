"""CS2 rarity tiers used as a skin-complexity dial.

The user picks a rarity color; that maps to how elaborate the generated skin should be, by
injecting prompt modifiers, tuning generation params, and suggesting a finish style. Mirrors the
in-game grades (Mil-Spec → Covert). Knife/glove gold tier is intentionally omitted for now.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rarity:
    key: str
    label: str
    complexity: int               # 1 (simple) .. 4 (elaborate)
    prompt_modifiers: str         # appended to the user prompt
    negative_extra: str           # added to the negative prompt
    controlnet_scale: float       # lower = bolder/looser art
    steps: int
    saturation: float             # post-gen color boost
    suggested_style: str          # default finish style for this tier


RARITIES: dict[str, Rarity] = {
    "blue": Rarity(
        key="blue", label="Mil-Spec (Blue)", complexity=1,
        prompt_modifiers="clean minimal design, simple flat color blocks, subtle understated finish, "
                         "few elements, restrained palette",
        negative_extra="busy, cluttered, overly detailed, chaotic",
        controlnet_scale=0.62, steps=28, saturation=1.25, suggested_style="hydrographic"),
    "purple": Rarity(
        key="purple", label="Restricted (Purple)", complexity=2,
        prompt_modifiers="clear bold graphic pattern, two or three color palette, balanced confident "
                         "design, clean shapes",
        negative_extra="muddy, noisy",
        controlnet_scale=0.52, steps=30, saturation=1.4, suggested_style="custom_paint"),
    "pink": Rarity(
        key="pink", label="Classified (Pink)", complexity=3,
        prompt_modifiers="detailed intricate design, rich multi-color palette, elaborate ornate "
                         "patterns, layered composition, vibrant",
        negative_extra="plain, flat, boring, washed out",
        controlnet_scale=0.46, steps=34, saturation=1.5, suggested_style="custom_paint"),
    "red": Rarity(
        key="red", label="Covert (Red)", complexity=4,
        prompt_modifiers="highly detailed elaborate masterpiece weapon skin, intricate dramatic "
                         "design, vivid saturated colors, complex cohesive composition, ornate "
                         "details, premium AAA covert finish, award winning",
        negative_extra="plain, flat, simple, boring, low detail, washed out",
        controlnet_scale=0.40, steps=38, saturation=1.6, suggested_style="custom_paint"),
}

# Neutral tier used when the user leaves quality unspecified (it's optional).
NEUTRAL = Rarity(
    key="none", label="Any / Unspecified", complexity=2,
    prompt_modifiers="bold clean design, cohesive palette",
    negative_extra="", controlnet_scale=0.50, steps=32, saturation=1.4,
    suggested_style="custom_paint")

DEFAULT_RARITY = "none"          # quality selection is optional


def get_rarity(key: str | None) -> Rarity:
    if key is None or key in ("none", "", "any"):
        return NEUTRAL
    try:
        return RARITIES[key]
    except KeyError:
        raise KeyError(f"Unknown rarity {key!r}. Known: none, {', '.join(RARITIES)}")


def list_rarities() -> list[Rarity]:
    return list(RARITIES.values())
