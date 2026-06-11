"""Gradio web UI — describe a CS2 skin, Claude designs it, it generates.

Launch:  python -m cs2skin.app   (or  python -m cs2skin.cli ui)

Deliberately minimal: you describe the skin and pick the weapon. Claude (the art-director) chooses
the skin type, a cohesive colour palette, and the composition; the local model paints it. Needs
ANTHROPIC_API_KEY for the Claude design step.
"""

from __future__ import annotations

import gradio as gr

from .assets import list_weapons
from .skintype import get_skin_type
from .generate import Generator
from .pipeline import generate_art, style_skin
from .preview import render
from . import director

_WEAPONS = {w.display: w.key for w in list_weapons()}

_CSS = """
#title-row h1 { margin-bottom: 0; }
.card { border: 1px solid var(--border-color-primary); border-radius: 12px; padding: 16px; }
.generate-btn { font-size: 1.15rem !important; padding: 14px !important; }
footer { display: none !important; }
"""

_GEN: Generator | None = None


def _gen() -> Generator:
    global _GEN
    if _GEN is None:
        _GEN = Generator()
    return _GEN


def _run(description, weapon_label, progress=gr.Progress()):
    if not description or not description.strip():
        raise gr.Error("Describe the skin you want.")
    if not director.available():
        raise gr.Error("This needs an Anthropic API key for the Claude design step. "
                       "Set ANTHROPIC_API_KEY (console.anthropic.com) and restart.")
    weapon = _WEAPONS[weapon_label]
    progress(0.15, desc="Claude is designing the skin…")
    spec = director.design_skin(description.strip(), weapon)
    progress(0.45, desc="Painting it…")
    art = generate_art(prompt=spec.prompt, weapon=weapon, skin_type=spec.skin_type, generator=_gen())
    progress(0.9, desc="Finishing…")
    res = style_skin(art, palette=spec.palette)
    preview = render(res.weapon, res.maps, size=820)
    swatches = " ".join(f"`{c}`" for c in spec.palette)
    info = (f"### ✅ {res.weapon.display} — {get_skin_type(spec.skin_type).label}\n"
            f"_{spec.rationale}_\n\n"
            f"**Palette:** {swatches}\n\n"
            f"📁 Saved to `{res.out_dir}` — open **IMPORT.md** there for the CS2 Workbench steps.")
    return preview, info


def build() -> gr.Blocks:
    with gr.Blocks(title="CS2 Skin AI") as demo:
        with gr.Row(elem_id="title-row"):
            gr.Markdown("# 🔫 CS2 Skin AI\nDescribe a skin and pick a weapon — Claude designs it, the AI paints it.")
        with gr.Row():
            with gr.Column(scale=4, elem_classes="card"):
                description = gr.Textbox(
                    label="Describe your skin", lines=4, autofocus=True,
                    placeholder="e.g. a sleek dragon coiling around the body, deep teal and gold, "
                                "glowing scales\nor: weathered desert camo, sand and olive")
                weapon = gr.Dropdown(list(_WEAPONS), value="AK-47", label="Weapon")
                go = gr.Button("✨ Create Skin", variant="primary", elem_classes="generate-btn")
                if not director.available():
                    gr.Markdown("⚠️ _Set `ANTHROPIC_API_KEY` and restart to enable design._")
            with gr.Column(scale=6):
                preview = gr.Image(label="Your skin", height=480)
                info = gr.Markdown("_Describe a skin and click Create._")
        go.click(_run, [description, weapon], [preview, info])
    return demo


def launch(**kwargs):
    demo = build()
    demo.queue()
    kwargs.setdefault("theme", gr.themes.Soft(primary_hue="orange", secondary_hue="slate"))
    kwargs.setdefault("css", _CSS)
    demo.launch(**kwargs)


if __name__ == "__main__":
    launch(inbrowser=True)
