"""Gradio web UI — design and EDIT CS2 skins.

Launch:  python -m cs2skin.app   (or  python -m cs2skin.cli ui)

Workflow: ✨ Generate makes a new design (slow, AI). 🎨 Apply edits restyles the SAME design
instantly (colours / placement / brightness / detail — no regeneration), so you can refine a skin
you like instead of gambling on a new one. Lock the seed to keep a design while changing the prompt.
"""

from __future__ import annotations

import random

import gradio as gr

from .assets import list_weapons
from .skintype import list_skin_types, get_skin_type, DEFAULT_TYPE
from .generate import Generator
from .pipeline import generate_art, style_skin
from .preview import render

_WEAPONS = {w.display: w.key for w in list_weapons()}
_TYPES = {t.label: t.key for t in list_skin_types()}
_TYPE_LABEL = {k: lbl for lbl, k in _TYPES.items()}
_DEFAULT_TYPE_LABEL = next(lbl for lbl, k in _TYPES.items() if k == DEFAULT_TYPE)
_PLACEMENT = {"By design (auto)": "auto", "Base vs details (by part size)": "size"}
_PLACEMENT_LABEL = {v: k for k, v in _PLACEMENT.items()}

_CSS = """
#title-row h1 { margin-bottom: 0; }
.card { border: 1px solid var(--border-color-primary); border-radius: 12px; padding: 14px; }
.generate-btn { font-size: 1.05rem !important; padding: 12px !important; }
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


def _design(idea, type_label, weapon_label, progress=gr.Progress()):
    """Let Claude art-direct the design from a short idea; fills in the form fields."""
    from . import director
    if not idea or not idea.strip():
        raise gr.Error("Type a short idea first (e.g. 'a cool dragon AK'), then Design with Claude.")
    if not director.available():
        raise gr.Error("Set the ANTHROPIC_API_KEY environment variable to use Claude design "
                       "(get a key at console.anthropic.com). The rest of the tool works without it.")
    progress(0.3, desc="Claude is designing…")
    try:
        spec = director.design_skin(idea.strip(), _WEAPONS[weapon_label], skin_type=_TYPES[type_label])
    except Exception as e:
        raise gr.Error(f"Claude design failed: {e}")
    base = spec.main_colors[0] if spec.main_colors else "#ffffff"
    second = (spec.main_colors[1] if len(spec.main_colors) > 1
              else (spec.accent_colors[0] if spec.accent_colors else "#111111"))
    note = (f"### 🎨 Claude designed it\n**{get_skin_type(spec.skin_type).label}** · "
            f"placement: {spec.color_placement} · colors: {', '.join(spec.main_colors) or 'auto'}\n\n"
            f"_{spec.rationale}_\n\nReview the fields, then hit **Generate**.")
    return (gr.update(value=_TYPE_LABEL.get(spec.skin_type, _DEFAULT_TYPE_LABEL)),
            gr.update(value=spec.prompt),
            gr.update(value=bool(spec.main_colors)),
            gr.update(value=base), gr.update(value=second),
            gr.update(value=_PLACEMENT_LABEL.get(spec.color_placement, "By design (auto)")),
            note)


def _style_kwargs(use_colors, c1, c2, placement_label, brightness, saturation, detail):
    return dict(main_colors=([c1, c2] if use_colors else None),
                color_placement=_PLACEMENT[placement_label],
                brightness=float(brightness), saturation=float(saturation), detail=float(detail))


def _outputs(res):
    preview = render(res.weapon, res.maps, size=768)
    m = res.maps
    gallery = [(im.convert("RGB"), nm) for nm, im in
               [("pattern", m.pattern), ("normal", m.normal), ("roughness", m.roughness),
                ("metalness", m.metalness), ("ao", m.ao), ("mask", m.mask)] if im is not None]
    info = (f"### ✅ Skin ready\n"
            f"**{res.weapon.display}** · {res.skin_type.label} · {res.style.workbench_name} · "
            f"seed `{res.gen.seed}`\n\n"
            f"🎨 Tweak the colours / appearance below and hit **Apply edits** to restyle this same "
            f"design instantly.\n\n"
            f"📁 Saved to `{res.out_dir}` — open **IMPORT.md** there for the CS2 Workbench steps.")
    return preview, gallery, info


def _generate(prompt, type_label, weapon_label, reference, seed, lock,
              use_colors, c1, c2, placement_label, brightness, saturation, detail,
              progress=gr.Progress()):
    if not prompt or not prompt.strip():
        raise gr.Error("Please enter a prompt describing the skin you want.")
    progress(0.2, desc="Loading model…")
    gen = _gen()
    use_seed = int(seed) if (lock and seed is not None and int(seed) >= 0) else random.randint(0, 2**31 - 1)
    progress(0.4, desc="Generating new design…")
    art = generate_art(prompt=prompt, weapon=_WEAPONS[weapon_label], skin_type=_TYPES[type_label],
                       seed=use_seed, reference_image=reference, generator=gen)
    progress(0.9, desc="Styling…")
    res = style_skin(art, **_style_kwargs(use_colors, c1, c2, placement_label, brightness, saturation, detail))
    preview, gallery, info = _outputs(res)
    return preview, gallery, info, art, art.seed


def _apply(art, use_colors, c1, c2, placement_label, brightness, saturation, detail):
    if art is None:
        raise gr.Error("Generate a skin first, then use Apply edits to restyle it.")
    res = style_skin(art, **_style_kwargs(use_colors, c1, c2, placement_label, brightness, saturation, detail))
    return _outputs(res)


def build() -> gr.Blocks:
    with gr.Blocks(title="CS2 Skin AI") as demo:
        art_state = gr.State(None)            # cached generated art, for instant restyling
        with gr.Row(elem_id="title-row"):
            gr.Markdown("# 🔫 CS2 Skin AI\nDescribe a skin, then edit it live — for any CS2 weapon.")
        with gr.Row():
            # ---------- INPUT PANEL ----------
            with gr.Column(scale=5, elem_classes="card"):
                gr.Markdown("### Design your skin")
                skintype = gr.Dropdown(list(_TYPES), value=_DEFAULT_TYPE_LABEL, label="① Type")
                type_help = gr.Markdown(_type_help(_DEFAULT_TYPE_LABEL))
                prompt = gr.Textbox(
                    label="② Prompt", lines=3, autofocus=True,
                    placeholder="Describe the look — theme, colors, motifs.\ne.g. emerald green with brushed bronze accents")
                design_btn = gr.Button("✨ Design with Claude (turn a short idea into a full design)",
                                       size="sm")
                weapon = gr.Dropdown(list(_WEAPONS), value="AK-47", label="③ Weapon")
                with gr.Accordion("④ Reference image (optional — the skin will copy it)", open=False):
                    reference = gr.Image(label="Reference image", type="pil", height=180)
                with gr.Accordion("🎨 Colors (optional)", open=False):
                    use_colors = gr.Checkbox(value=False, label="Choose the main colors manually")
                    with gr.Row():
                        color_base = gr.ColorPicker(value="#ffffff", label="Base / main color")
                        color_details = gr.ColorPicker(value="#111111", label="Second / details color")
                    placement = gr.Radio(list(_PLACEMENT), value="By design (auto)",
                                         label="Color placement",
                                         info="‘Base vs details’ = biggest parts get the base color, "
                                              "smaller parts the second (e.g. base white, rest black)")
                with gr.Accordion("⚙️ Appearance (optional)", open=False):
                    brightness = gr.Slider(0.5, 1.8, value=1.0, step=0.05, label="Brightness")
                    saturation = gr.Slider(0.3, 1.8, value=1.0, step=0.05, label="Saturation")
                    detail = gr.Slider(0.3, 1.6, value=1.0, step=0.05, label="Detail / texture strength")
                with gr.Row():
                    seed = gr.Number(value=-1, label="Seed (-1 = random)", precision=0, scale=2)
                    lock = gr.Checkbox(value=False, label="🔒 Lock seed", scale=1)
                with gr.Row():
                    go = gr.Button("✨ Generate new", variant="primary", elem_classes="generate-btn")
                    edit = gr.Button("🎨 Apply edits", variant="secondary", elem_classes="generate-btn")
                gr.Markdown("_Apply edits restyles the current design instantly (no regeneration)._")

            # ---------- RESULT PANEL ----------
            with gr.Column(scale=6):
                preview = gr.Image(label="Preview", height=440)
                gallery = gr.Gallery(label="PBR texture maps", columns=3, height=300)
                info = gr.Markdown("_Generate a skin to begin, then edit it below._")

        edit_inputs = [art_state, use_colors, color_base, color_details, placement,
                       brightness, saturation, detail]
        skintype.change(_type_help, skintype, type_help)
        design_btn.click(_design, [prompt, skintype, weapon],
                         [skintype, prompt, use_colors, color_base, color_details, placement, info])
        go.click(_generate,
                 [prompt, skintype, weapon, reference, seed, lock,
                  use_colors, color_base, color_details, placement, brightness, saturation, detail],
                 [preview, gallery, info, art_state, seed])
        edit.click(_apply, edit_inputs, [preview, gallery, info])
    return demo


def launch(**kwargs):
    demo = build()
    demo.queue()                       # serialize long GPU jobs, show progress
    kwargs.setdefault("theme", gr.themes.Soft(primary_hue="orange", secondary_hue="slate"))
    kwargs.setdefault("css", _CSS)
    demo.launch(**kwargs)


if __name__ == "__main__":
    launch(inbrowser=True)
