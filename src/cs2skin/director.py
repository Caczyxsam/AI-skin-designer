"""Claude as the skin art-director.

Turns a short idea ("a cool dragon AK") into a deliberate, cohesive **design spec** — skin type,
an art-directed generation prompt, ≤2 main colours (+ accents), and colour placement — which feeds
straight into the existing generation controls. This is the "taste / sensible design" layer that
raw SDXL lacks. It calls the Anthropic API (Claude), so it needs ANTHROPIC_API_KEY; everything else
in the tool stays local. Optional — the tool works fully without it.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from .skintype import SKIN_TYPES, DEFAULT_TYPE

MODEL = os.environ.get("CS2SKIN_CLAUDE_MODEL", "claude-opus-4-8")

_TYPE_KEYS = ", ".join(SKIN_TYPES)

SYSTEM = f"""You are an expert art director for Counter-Strike 2 (CS2) weapon skins. Given a short
idea and a weapon, design a single cohesive, *cool and sensible* skin that could plausibly be
accepted into the game. You output a structured spec that downstream tools turn into the texture.

Design rules you MUST follow:
- Choose the best skin TYPE for the idea, exactly one of: {_TYPE_KEYS}.
  (painted = flat stylised graphics; metallic = tinted/anodized metal; hydrographic = wrapped
  camo/pattern; pattern = seamless all-over pattern; patina = aged/weathered metal;
  hybrid = layered paint+metal+decals.)
- Use at most TWO main colours (each can have many shades). You may add a few small ACCENT colours
  for fine details only. Pick a cohesive, tasteful palette using real colour theory — avoid muddy
  or clashing combinations. Colours are hex like "#1b2a4a".
- color_placement: "size" when the idea implies a clear base colour + accents (e.g. "white body,
  black details", "gold trim") — the largest parts take main colour 1, small parts colour 2.
  Use "auto" when the design should flow by composition rather than by part.
- Write `prompt`: a vivid but CONCISE (max ~35 words) generation prompt describing the motif,
  composition, where elements sit on the weapon, and the style language. No weapon name needed.
- Keep it elegant and intentional — a clear concept, not a random pile of effects.
- `rationale`: one short sentence on the design intent.

Be decisive and produce a strong, specific design."""


class DesignSpec(BaseModel):
    skin_type: str = Field(description=f"One of: {_TYPE_KEYS}")
    prompt: str = Field(description="Concise art-directed generation prompt (<=35 words)")
    main_colors: list[str] = Field(description="1-2 main colours as hex strings")
    accent_colors: list[str] = Field(default_factory=list, description="0-3 small accent colours (hex)")
    color_placement: str = Field(description='"auto" or "size"')
    rationale: str = Field(description="One sentence on the design intent")


def available() -> bool:
    """True if an Anthropic API key is configured (the feature is optional)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def design_skin(idea: str, weapon: str, skin_type: str | None = None) -> DesignSpec:
    """Ask Claude to art-direct a skin design from a short idea. Raises if no API key / on error."""
    if not available():
        raise RuntimeError(
            "Claude design needs an Anthropic API key. Set ANTHROPIC_API_KEY "
            "(get one at https://console.anthropic.com/settings/keys), then retry.")
    import anthropic

    client = anthropic.Anthropic()
    hint = f"\nThe user picked the '{skin_type}' type — prefer it unless clearly wrong." if skin_type else ""
    user = f"Weapon: {weapon}\nIdea: {idea}{hint}\n\nDesign the skin."

    resp = client.messages.parse(
        model=MODEL, max_tokens=4000,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=DesignSpec,
    )
    spec = resp.parsed_output

    # Sanitise into the ranges the pipeline expects.
    if spec.skin_type not in SKIN_TYPES:
        spec.skin_type = DEFAULT_TYPE
    spec.color_placement = "size" if spec.color_placement == "size" else "auto"
    spec.main_colors = [c for c in spec.main_colors if isinstance(c, str) and c.startswith("#")][:2]
    return spec
