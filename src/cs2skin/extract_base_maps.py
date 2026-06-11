"""Extract each weapon's base AO/surface maps from the CS2 VPK into assets/weapons/<key>/base/.

These give the pipeline the weapon's real surface detail (panel lines, magazine ribs, screws) so
the AO can be baked into the flat-coloured albedo and the detail stays visible.

Requires tools/vrf/Source2Viewer-CLI.exe and the game VPK. Run: python -m cs2skin.extract_base_maps
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .assets import WEAPONS
from .config import get_config

# our weapon key -> CS2 customization folder name (materials/.../customization/<folder>/)
CUSTOMIZATION = {
    "ak47": "rif_ak47", "m4a4": "rif_m4a1", "m4a1s": "rif_m4a1_s", "aug": "rif_aug",
    "sg553": "rif_sg556", "famas": "rif_famas", "galilar": "rif_galilar",
    "awp": "snip_awp", "ssg08": "snip_ssg08", "scar20": "snip_scar20", "g3sg1": "snip_g3sg1",
    "deagle": "pist_deagle", "glock": "pist_glock18", "usps": "pist_usp_silencer",
    "p2000": "pist_hkp2000", "p250": "pist_p250", "fiveseven": "pist_fiveseven",
    "tec9": "pist_tec9", "cz75a": "pist_cz_75", "elite": "pist_elite", "revolver": "pist_revolver",
    "mac10": "smg_mac10", "mp9": "smg_mp9", "mp7": "smg_mp7", "mp5sd": "smg_mp5sd",
    "ump45": "smg_ump45", "p90": "smg_p90", "bizon": "smg_bizon",
    "nova": "shot_nova", "xm1014": "shot_xm1014", "mag7": "shot_mag7", "sawedoff": "shot_sawedoff",
    "m249": "mach_m249para", "negev": "mach_negev",
}

VPK = (r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive"
       r"\game\csgo\pak01_dir.vpk")
CLI = Path(__file__).resolve().parents[2] / "tools" / "vrf" / "Source2Viewer-CLI.exe"


def extract(key: str) -> bool:
    folder = CUSTOMIZATION.get(key)
    if not folder or not Path(VPK).exists() or not CLI.exists():
        return False
    out = WEAPONS[key].base_dir
    out.mkdir(parents=True, exist_ok=True)
    path = f"materials/models/weapons/customization/{folder}/"
    subprocess.run([str(CLI), "-i", VPK, "-o", str(out), "-d", "-f", path, "-e", "vtex_c"],
                   capture_output=True, text=True)
    return WEAPONS[key].base_map("ao") is not None


def main():
    get_config().paths.ensure()
    ok = 0
    for key in WEAPONS:
        got = extract(key)
        ok += got
        print(f"  {key:10s} {'ao ✓' if got else '—'}")
    print(f"base maps extracted for {ok}/{len(WEAPONS)} weapons")


if __name__ == "__main__":
    main()
