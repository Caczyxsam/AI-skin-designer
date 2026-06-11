"""Command-line interface.  Run as:  python -m cs2skin.cli <command>"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows consoles default to cp1252; force UTF-8 so rich glyphs (stars, arrows) render.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

import typer
from rich.console import Console
from rich.table import Table

from .assets import get_weapon, list_weapons, missing_assets_report
from .finishes import list_styles, get_style
from .generate import Generator
from .pipeline import create_skin

app = typer.Typer(add_completion=False, help="Generate CS2 Workbench-ready weapon skins from a prompt.")
console = Console()


@app.command("weapons")
def weapons_cmd():
    """List supported weapons and which assets are present."""
    table = Table(title="Weapons")
    table.add_column("key"); table.add_column("weapon"); table.add_column("category")
    table.add_column("UV ready", justify="center")
    for w in list_weapons():
        table.add_row(w.key, w.display, w.category, "✓" if w.ready_for_generation() else "—")
    console.print(table)


@app.command("styles")
def styles_cmd():
    """List CS2 finish styles and how suited they are to AI art."""
    table = Table(title="Finish styles")
    table.add_column("key"); table.add_column("Workbench name"); table.add_column("AI fit", justify="center")
    table.add_column("maps")
    for s in list_styles():
        table.add_row(s.key, s.workbench_name, "★" * s.ai_suitability,
                      ", ".join(m.name for m in s.maps) or "—")
    console.print(table)


@app.command("assets")
def assets_cmd(weapon: str):
    """Show asset status for a weapon and where to get missing templates."""
    console.print(missing_assets_report(get_weapon(weapon)))


@app.command("types")
def types_cmd():
    """List skin types (the primary material/look choice)."""
    from .skintype import list_skin_types
    table = Table(title="Skin types")
    table.add_column("key"); table.add_column("type"); table.add_column("look")
    for t in list_skin_types():
        table.add_row(t.key, t.label, t.blurb)
    console.print(table)


@app.command("generate")
def generate_cmd(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Describe the skin."),
    skin_type: str = typer.Option("painted", "--type", "-t",
                                  help="painted|metallic|hydrographic|pattern|patina|hybrid."),
    weapon: str = typer.Option("ak47", "--weapon", "-w"),
    style: str = typer.Option("", "--style", "-s", help="Finish style; blank = auto from type."),
    reference: str = typer.Option("", "--reference", "-r",
                                  help="Path to a reference image to replicate (optional)."),
    seed: int = typer.Option(-1, "--seed"),
    mock: bool = typer.Option(False, "--mock", help="Use the procedural fallback (no SD model)."),
):
    """Generate a skin and export a Workbench-ready folder."""
    ref_img = None
    if reference:
        from PIL import Image
        ref_img = Image.open(reference)
    console.print(f"[cyan]Generating[/] [{skin_type}] '{prompt}' for "
                  f"[bold]{get_weapon(weapon).display}[/]"
                  f"{' +ref' if ref_img else ''}{' (mock)' if mock else ''}…")
    res = create_skin(prompt=prompt, weapon=weapon, skin_type=skin_type,
                      style=style or None, reference_image=ref_img,
                      seed=None if seed < 0 else seed, mock=mock)
    console.print(f"[green]✓ Exported[/] → {res.out_dir}")
    console.print(f"  type={res.skin_type.label}  finish={res.style.workbench_name}  "
                  f"seed={res.gen.seed}")
    console.print(f"  Open [bold]{res.out_dir / 'IMPORT.md'}[/] for Workbench steps.")


@app.command("ui")
def ui_cmd():
    """Launch the Gradio web UI."""
    from .app import launch
    launch()


if __name__ == "__main__":
    app()
