"""Weapon registry + template-asset management.

Every CS2 skin is painted onto a specific weapon's **UV layout**. For each weapon we need:
  - `<key>.obj`         the weapon mesh (for the in-app 3D preview)
  - `<key>_uv.png`      the UV wireframe sheet (drives ControlNet so art lands on the right parts)
  - `<key>_base.png`    (optional) the default base color, useful as an img2img starting point

These come from Valve's official workshop resources (counter-strike.net/workshop/workshopresources)
or the community Valve Developer Union archive. We don't redistribute Valve assets; `ensure_weapon`
checks what's present and prints exactly where to drop missing files. `model_name` is the internal
econ name used in items_game / the Workbench.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import get_config


@dataclass(frozen=True)
class Weapon:
    key: str            # our stable id, e.g. "ak47"
    display: str        # "AK-47"
    category: str       # rifle / pistol / smg / shotgun / mg / sniper
    model_name: str     # internal econ name, e.g. "weapon_ak47"

    @property
    def dir(self) -> Path:
        return get_config().paths.weapons / self.key

    @property
    def obj_path(self) -> Path:
        return self.dir / f"{self.key}.obj"

    @property
    def uv_path(self) -> Path:
        return self.dir / f"{self.key}_uv.png"

    @property
    def base_path(self) -> Path:
        return self.dir / f"{self.key}_base.png"

    @property
    def base_dir(self) -> Path:
        return self.dir / "base"          # extracted game maps (ao/surface/masks)

    def base_map(self, kind: str) -> Path | None:
        """Find an extracted base map by kind ('ao', 'surface', 'masks'), or None."""
        if not self.base_dir.exists():
            return None
        hits = sorted(self.base_dir.rglob(f"*_{kind}_*.png"))
        return hits[0] if hits else None

    def status(self) -> dict[str, bool]:
        return {
            "mesh (.obj)": self.obj_path.exists(),
            "uv wireframe": self.uv_path.exists(),
            "base color": self.base_path.exists(),
        }

    def ready_for_generation(self) -> bool:
        # UV wireframe is the only hard requirement for generation; mesh only gates 3D preview.
        return self.uv_path.exists()


WEAPONS: dict[str, Weapon] = {w.key: w for w in [
    # Rifles
    Weapon("ak47", "AK-47", "rifle", "weapon_ak47"),
    Weapon("m4a4", "M4A4", "rifle", "weapon_m4a1"),
    Weapon("m4a1s", "M4A1-S", "rifle", "weapon_m4a1_silencer"),
    Weapon("aug", "AUG", "rifle", "weapon_aug"),
    Weapon("sg553", "SG 553", "rifle", "weapon_sg556"),
    Weapon("famas", "FAMAS", "rifle", "weapon_famas"),
    Weapon("galilar", "Galil AR", "rifle", "weapon_galilar"),
    # Snipers
    Weapon("awp", "AWP", "sniper", "weapon_awp"),
    Weapon("ssg08", "SSG 08", "sniper", "weapon_ssg08"),
    Weapon("scar20", "SCAR-20", "sniper", "weapon_scar20"),
    Weapon("g3sg1", "G3SG1", "sniper", "weapon_g3sg1"),
    # Pistols
    Weapon("deagle", "Desert Eagle", "pistol", "weapon_deagle"),
    Weapon("glock", "Glock-18", "pistol", "weapon_glock"),
    Weapon("usps", "USP-S", "pistol", "weapon_usp_silencer"),
    Weapon("p2000", "P2000", "pistol", "weapon_hkp2000"),
    Weapon("p250", "P250", "pistol", "weapon_p250"),
    Weapon("fiveseven", "Five-SeveN", "pistol", "weapon_fiveseven"),
    Weapon("tec9", "Tec-9", "pistol", "weapon_tec9"),
    Weapon("cz75a", "CZ75-Auto", "pistol", "weapon_cz75a"),
    Weapon("elite", "Dual Berettas", "pistol", "weapon_elite"),
    Weapon("revolver", "R8 Revolver", "pistol", "weapon_revolver"),
    # SMGs
    Weapon("mac10", "MAC-10", "smg", "weapon_mac10"),
    Weapon("mp9", "MP9", "smg", "weapon_mp9"),
    Weapon("mp7", "MP7", "smg", "weapon_mp7"),
    Weapon("mp5sd", "MP5-SD", "smg", "weapon_mp5sd"),
    Weapon("ump45", "UMP-45", "smg", "weapon_ump45"),
    Weapon("p90", "P90", "smg", "weapon_p90"),
    Weapon("bizon", "PP-Bizon", "smg", "weapon_bizon"),
    # Shotguns
    Weapon("nova", "Nova", "shotgun", "weapon_nova"),
    Weapon("xm1014", "XM1014", "shotgun", "weapon_xm1014"),
    Weapon("mag7", "MAG-7", "shotgun", "weapon_mag7"),
    Weapon("sawedoff", "Sawed-Off", "shotgun", "weapon_sawedoff"),
    # Machine guns
    Weapon("m249", "M249", "mg", "weapon_m249"),
    Weapon("negev", "Negev", "mg", "weapon_negev"),
]}

DEFAULT_WEAPON = "ak47"

ASSET_SOURCES = (
    "Official Valve workshop resources (OBJ meshes + UV sheets):\n"
    "    https://www.counter-strike.net/workshop/workshopresources\n"
    "Community archive (OBJs + 4096 UV TGA sheets, all weapons):\n"
    "    https://valvedev.info/tools/csgo-weapon-skin-templates/"
)


def get_weapon(key: str) -> Weapon:
    try:
        return WEAPONS[key]
    except KeyError:
        raise KeyError(f"Unknown weapon {key!r}. Known: {', '.join(WEAPONS)}")


def list_weapons() -> list[Weapon]:
    return list(WEAPONS.values())


def missing_assets_report(weapon: Weapon) -> str:
    """Human-readable note on what's missing and where to get it."""
    lines = [f"{weapon.display} ({weapon.key}) assets in {weapon.dir}:"]
    for label, present in weapon.status().items():
        lines.append(f"  [{'x' if present else ' '}] {label}")
    if not weapon.ready_for_generation():
        lines.append("\nMissing the UV wireframe (required). Get the template from:\n" + ASSET_SOURCES)
        lines.append(
            f"\nThen place files as:\n  {weapon.obj_path.name}, {weapon.uv_path.name}, "
            f"{weapon.base_path.name}\nin {weapon.dir}"
        )
    return "\n".join(lines)
