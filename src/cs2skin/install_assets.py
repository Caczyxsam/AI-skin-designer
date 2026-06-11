"""Install weapon template assets from Valve's official zips into our per-weapon layout.

Reads `assets/raw/workbench_materials.zip` (matched OBJ + UV-sheet pairs that share UVs) and writes:
    assets/weapons/<key>/<key>.obj      the mesh (UVs match the sheet)
    assets/weapons/<key>/<key>_uv.png   the UV sheet (converted from TGA)

Run:  python -m cs2skin.install_assets
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image

from .config import get_config
from .assets import WEAPONS

# Valve workbench filename stem -> our weapon key. (OBJs/ and UVSheets/ share these stems.)
WORKBENCH_NAME_TO_KEY = {
    "ak-47": "ak47", "aug": "aug", "awp": "awp", "bizon": "bizon", "cz_75": "cz75a",
    "desert_eagle": "deagle", "dual_berettas": "elite", "famas": "famas", "five-seven": "fiveseven",
    "g3sg1": "g3sg1", "galil_ar": "galilar", "glock-18": "glock", "m249": "m249", "m4a1_s": "m4a1s",
    "m4a4": "m4a4", "mac-10": "mac10", "mag-7": "mag7", "mp5sd": "mp5sd", "mp7": "mp7", "mp9": "mp9",
    "negev": "negev", "nova": "nova", "p2000": "p2000", "p250": "p250", "p90": "p90",
    "revolver": "revolver", "sawed-off": "sawedoff", "scar-20": "scar20", "sg_553": "sg553",
    "ssg_08": "ssg08", "tec-9": "tec9", "ump-45": "ump45", "usp-s": "usps", "xm1014": "xm1014",
}


def install(zip_path: Path | None = None) -> dict[str, list[str]]:
    cfg = get_config()
    zip_path = zip_path or (cfg.paths.assets / "raw" / "workbench_materials.zip")
    if not zip_path.exists():
        raise FileNotFoundError(f"Missing {zip_path}. Download workbench_materials.zip first.")

    installed: dict[str, list[str]] = {}
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        for wb_name, key in WORKBENCH_NAME_TO_KEY.items():
            if key not in WEAPONS:
                continue
            wpn = WEAPONS[key]
            wpn.dir.mkdir(parents=True, exist_ok=True)
            done: list[str] = []

            obj_entry = f"OBJs/{wb_name}.obj"
            if obj_entry in names:
                wpn.obj_path.write_bytes(zf.read(obj_entry))
                done.append("obj")

            uv_entry = f"UVSheets/{wb_name}.tga"
            if uv_entry in names:
                img = Image.open(io.BytesIO(zf.read(uv_entry))).convert("RGB")
                img.save(wpn.uv_path)        # -> <key>_uv.png
                done.append(f"uv {img.size[0]}px")

            installed[key] = done
    return installed


if __name__ == "__main__":
    result = install()
    ok = sum(1 for v in result.values() if "obj" in v)
    print(f"Installed assets for {ok}/{len(result)} weapons.")
    for key, done in sorted(result.items()):
        print(f"  {key:10s} {', '.join(done) or 'MISSING'}")
