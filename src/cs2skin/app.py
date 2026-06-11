"""Gradio web UI — a simple input window for designing CS2 skins.

Launch:  python -m cs2skin.app   (or  python -m cs2skin.cli ui)

Left panel = the input form (type, prompt, weapon, optional reference image).
Right panel = the result (3D preview, PBR maps, where it saved).
"""

from __future__ import annotations

import gradio as gr

from .assets import list_weapons
from .skintype import list_skin_types, get_skin_type, DEFAULT_TYPE
from .generate import Generator
from .pipeline import create_skin
from .preview import render

_WEAPONS = {w.display: w.key for w in list_weapons()}
_TYPES = {t.label: t.key for t in list_skin_types()}
_DEFAULT_TYPE_LABEL = next(lbl for lbl, k in _TYPES.items() if k == DEFAULT_TYPE)

_CSS = """
#title-row h1 { margin-bottom: 0; }
.card { border: 1px solid var(--border-color-primary); border-radius: 12px; padding: 14px; }
.generate-btn { font-size: 1.1rem !important; padding: 14px !important; }
footer { display: none !important; }
"""

_GEN: Generator | None = None


def _gen() -> Generator:
    global _GEN
    if _GEN is None:
        _GEN = Generator()
    return _GEN


def _type_help(type_label: str) -> str:
    t = get_skin_type(_TYPES[type_label])
    return f"**{t.label}** — {t.blurb}"


def _run(prompt, type_label, weapon_label, reference, progress=gr.Progress()):
    if not prompt or not prompt.strip():
        raise gr.Error("Please enter a prompt describing the skin you want.")
    progress(0.2, desc="Loading model…")
    gen = _gen()
    progress(0.4, desc="Generating…")
    res = create_skin(
        prompt=prompt, weapon=_WEAPONS[weapon_label], skin_type=_TYPES[type_label],
        reference_image=reference, generator=gen,
    )
    progress(0.9, desc="Rendering preview…")
    preview = render(res.weapon, res.maps, size=768)
    maps = res.maps
    gallery = [(m.convert("RGB"), nm) for nm, m in
               [("pattern", maps.pattern), ("normal", maps.normal), ("roughness", maps.roughness),
                ("metalness", maps.metalness), ("ao", maps.ao), ("mask", maps.mask)] if m is not None]
    info = (f"### ✅ Skin created\n"
            f"**{res.weapon.display}** · {res.skin_type.label} · {res.style.workbench_name} · "
            f"seed `{res.gen.seed}`{' · (mock)' if res.gen.mock else ''}\n\n"
            f"📁 Saved to:\n`{res.out_dir}`\n\n"
            f"Open **IMPORT.md** in that folder for the CS2 Workbench steps.")
    return preview, gallery, info


def build() -> gr.Blocks:
    with gr.Blocks(title="CS2 Skin AI") as demo:
        with gr.Row(elem_id="title-row"):
            gr.Markdown("# 🔫 CS2 Skin AI\nDescribe a skin → get a Workbench-ready finish for any CS2 weapon.")
        with gr.Row():
            # ---------- INPUT PANEL ----------
            with gr.Column(scale=5, elem_classes="card"):
                gr.Markdown("### Design your skin")
                skintype = gr.Dropdown(list(_TYPES), value=_DEFAULT_TYPE_LABEL, label="① Type")
                type_help = gr.Markdown(_type_help(_DEFAULT_TYPE_LABEL))
                prompt = gr.Textbox(
                    label="② Prompt", lines=3, autofocus=True,
                    placeholder="Describe the look — theme, colors, motifs.\ne.g. emerald green with brushed bronze accents")
                weapon = gr.Dropdown(list(_WEAPONS), value="AK-47", label="③ Weapon")
                with gr.Accordion("④ Reference image (optional — the skin will copy it)", open=False):
                    reference = gr.Image(label="Reference image", type="pil", height=180)
                go = gr.Button("✨ Generate Skin", variant="primary", elem_classes="generate-btn")

            # ---------- RESULT PANEL ----------
            with gr.Column(scale=6):
                preview = gr.Image(label="Preview", height=440)
                gallery = gr.Gallery(label="PBR texture maps", columns=3, height=300)
                info = gr.Markdown("_Your generated skin and its details will appear here._")

        skintype.change(_type_help, skintype, type_help)
        go.click(_run, [prompt, skintype, weapon, reference], [preview, gallery, info])
    return demo


def launch(**kwargs):
    demo = build()
    demo.queue()                       # serialize long GPU jobs, show progress
    kwargs.setdefault("theme", gr.themes.Soft(primary_hue="orange", secondary_hue="slate"))
    kwargs.setdefault("css", _CSS)
    demo.launch(**kwargs)


if __name__ == "__main__":
    launch(inbrowser=True)
