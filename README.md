# AI Skin Designer

Generate **CS2 Workbench-ready weapon finishes** from a text prompt, locally on your own GPU.
Pick a skin *type*, describe the look, choose a weapon — and get a full PBR texture set plus the
finish config that drops straight into CS2's in-game Workshop Item Editor.

> No software can inject a skin directly into CS2 — Valve's in-game **Workshop Item Editor** is the
> mandatory final step. This tool builds everything *up to* that import: correctly-formatted TGA
> maps + a finish config, so the import is a couple of clicks.

## Pipeline

```
prompt + type (+ optional quality / reference)
   → SDXL + UV-ControlNet            (art generated onto the weapon's UV layout)
   → per-part colour flatten         (each weapon part reads as one colour, detail preserved)
   → bake weapon AO                  (panel lines, magazine ribs stay visible)
   → derive PBR maps                 (normal / roughness / metalness / AO)
   → export                          (Workbench-ready TGAs + KeyValues config + IMPORT.md)
```

Generation uses **base SDXL** (no fine-tuned model) for clean, vivid output. A 3D PBR preview lets
you judge the result without launching the game.

## Inputs

| Input | What it does |
|-------|--------------|
| **Type** | Painted, Metallic/Anodized, Hydrographic, Pattern-based, Patina, or Hybrid — drives the finish style, material look, PBR and post-processing. |
| **Prompt** | Free-text description of the design. |
| **Weapon** | Any of 33 CS2 weapons (UV layout + mesh). |
| **Quality** *(optional)* | CS2 rarity tier as a complexity dial (Mil-Spec → Covert). |
| **Reference image** *(optional)* | **Model** mode replicates the skin in the image; **Theme** mode borrows its colours/style (via IP-Adapter). |

## Requirements

- Windows + an NVIDIA GPU. Blackwell (RTX 50-series) needs the **CUDA 12.8** build of PyTorch.
- Python **3.12** (the AI stack has no 3.14 wheels yet).
- The CS2 weapon templates + base maps, fetched from your local CS2 install (see Setup).

## Setup

```powershell
./scripts/setup_env.ps1          # creates .venv (Python 3.12) + installs torch cu128 + deps
```

Fetch the weapon templates (one-time; reads Valve's official workshop zips / your CS2 install):

```powershell
.\.venv\Scripts\python.exe -m cs2skin.install_assets       # OBJ meshes + UV sheets
.\.venv\Scripts\python.exe -m cs2skin.extract_base_maps    # per-weapon AO/surface (needs ValveResourceFormat in tools/vrf)
```

## Use

```powershell
# Web UI (recommended)
.\.venv\Scripts\python.exe -m cs2skin.app                  # http://127.0.0.1:7860

# CLI
.\.venv\Scripts\python.exe -m cs2skin.cli generate -t metallic -w ak47 -p "royal blue with silver accents"
.\.venv\Scripts\python.exe -m cs2skin.cli types            # list skin types
.\.venv\Scripts\python.exe -m cs2skin.cli weapons          # list weapons
```

Each run writes `output/<weapon>_<slug>/` with the TGA maps, the `.txt` finish config, a 3D
`render.png`, and `IMPORT.md` — click-by-click steps to load it in the CS2 Workshop Item Editor.

## Project layout

```
src/cs2skin/
  app.py          Gradio web UI                 generate.py    SDXL + ControlNet + IP-Adapter
  cli.py          command-line interface        pipeline.py    orchestration
  skintype.py     the 6 skin types              rarity.py      quality/complexity tiers
  finishes.py     CS2 finish styles + config    partition.py   per-part flatten + AO bake
  pbr.py          PBR map derivation            preview.py     3D PBR preview
  export.py       Workbench-ready export        assets.py      weapon registry
  install_assets.py / extract_base_maps.py      asset fetchers
```

## Notes

- The in-app preview is a real-time PBR approximation (no environment map), so metallic reflections
  and patina sheen show *fully* only in-game under CS2's lighting.
- Weapon templates and extracted game maps are Valve assets — they're fetched locally and are **not**
  redistributed in this repo.
