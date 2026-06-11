"""Configuration and canonical paths for the project.

Everything is resolved relative to the repo root so the tool works regardless of CWD. Values can
be overridden by a `config.yaml` at the repo root (loaded lazily) or by environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml optional until deps installed
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Paths:
    root: Path = REPO_ROOT
    assets: Path = REPO_ROOT / "assets"
    weapons: Path = REPO_ROOT / "assets" / "weapons"
    models: Path = REPO_ROOT / "assets" / "models"     # SD checkpoints / LoRAs cache
    loras: Path = REPO_ROOT / "assets" / "loras"
    output: Path = REPO_ROOT / "output"                # generated skins land here
    cache: Path = REPO_ROOT / ".cache"

    def ensure(self) -> "Paths":
        for p in (self.assets, self.weapons, self.models, self.loras, self.output, self.cache):
            p.mkdir(parents=True, exist_ok=True)
        return self


@dataclass
class GenerationConfig:
    base_model: str = "stabilityai/stable-diffusion-xl-base-1.0"
    controlnet_model: str = "diffusers/controlnet-canny-sdxl-1.0"
    resolution: int = 1024              # SD generation tile size; upscaled to texture_resolution
    texture_resolution: int = 2048      # final exported map size (2048 or 4096)
    steps: int = 30
    guidance_scale: float = 6.5
    controlnet_scale: float = 0.55      # how strongly the UV wireframe constrains layout
    seed: int = -1                      # -1 = random
    dtype: str = "float16"


@dataclass
class Config:
    paths: Paths = field(default_factory=Paths)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    device: str = "cuda"

    @staticmethod
    def load() -> "Config":
        cfg = Config()
        cfg.paths.ensure()
        yaml_path = REPO_ROOT / "config.yaml"
        if yaml and yaml_path.exists():
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            gen = data.get("generation", {})
            for k, v in gen.items():
                if hasattr(cfg.generation, k):
                    setattr(cfg.generation, k, v)
            if "device" in data:
                cfg.device = data["device"]
        # env overrides
        cfg.device = os.environ.get("CS2SKIN_DEVICE", cfg.device)
        return cfg


@lru_cache
def get_config() -> Config:
    return Config.load()
