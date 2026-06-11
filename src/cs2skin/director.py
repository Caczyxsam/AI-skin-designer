"""Claude as the skin art-director — the only design path.

You describe a skin; Claude designs it: the skin type, an art-directed generation prompt, and a
deliberate, cohesive COLOUR PALETTE (ordered dark -> light). The palette is applied as a tonal map
so colours land intentionally instead of being a random mess. Needs ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from .skintype import SKIN_TYPES, DEFAULT_TYPE

MODEL = os.environ.get("CS2SKIN_CLAUDE_MODEL", "claude-opus-4-8")
_TYPE_KEYS = ", ".join(SKIN_TYPES)

SYSTEM = f"""You are an expert art director for Counter-Strike 2 (CS2) weapon skins. Given a short
description and a weapon, design ONE cohesive, visually impressive skin that looks like the
description and could plausibly ship in the game. You output a structured spec; downstream tools
turn it into the texture.

How the colour system works (important): the generated artwork is recoloured by mapping its TONES
onto your `palette` — the darkest parts of the design take palette[0], the brightest take the last
colour, with smooth blends between. So you are choosing a deliberate, limited colour scheme, and the
ordering (dark -> light) controls how it reads. A tight, well-chosen palette is what makes a skin
look intentional instead of a muddy mess.

Rules:
- `skin_type`: exactly one of: {_TYPE_KEYS}. (painted = flat stylised graphics; metallic = tinted
  anodized metal; hydrographic = wrapped camo/pattern; pattern = seamless all-over pattern;
  patina = aged/weathered metal; hybrid = layered paint+metal+decals.)
- `palette`: 2 to 4 hex colours ordered DARKEST FIRST -> LIGHTEST LAST. Use real colour theory —
  a cohesive, tasteful scheme (e.g. analogous or a strong two-colour contrast with a tonal bridge).
  Avoid muddy or clashing combinations. Think about how a darkest->lightest ramp will read on a gun.
- `prompt`: a vivid but CONCISE (max ~35 words) prompt describing the MOTIF, composition, and where
  elements sit on the weapon. Describe it in terms of shapes and TONES/contrast (light vs dark),
  not specific colours (the palette handles colour). No weapon name needed.
- `rationale`: one short sentence on the design intent.

Be decisive and produce a strong, specific, elegant design."""


class DesignSpec(BaseModel):
    skin_type: str = Field(description=f"One of: {_TYPE_KEYS}")
    prompt: str = Field(description="Concise art-directed prompt describing motif + tones (<=35 words)")
    palette: list[str] = Field(description="2-4 hex colours, ordered darkest first -> lightest last")
    rationale: str = Field(description="One sentence on the design intent")


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def design_skin(description: str, weapon: str) -> DesignSpec:
    """Ask Claude to art-direct a skin from a description. Raises if no API key / on error."""
    if not available():
        raise RuntimeError(
            "Claude design needs an Anthropic API key. Set ANTHROPIC_API_KEY "
            "(get one at https://console.anthropic.com/settings/keys), then restart.")
    import anthropic

    client = anthropic.Anthropic()
    user = f"Weapon: {weapon}\nDescription: {description}\n\nDesign the skin."
    resp = client.messages.parse(
        model=MODEL, max_tokens=4000,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=DesignSpec,
    )
    spec = resp.parsed_output
    if spec.skin_type not in SKIN_TYPES:
        spec.skin_type = DEFAULT_TYPE
    spec.palette = [c for c in spec.palette if isinstance(c, str) and c.startswith("#")][:4]
    if len(spec.palette) < 2:
        spec.palette = ["#202028", "#c8c8d0"]      # safe fallback ramp
    return spec
