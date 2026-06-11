"""Text-to-pattern generation.

Produces the **base-color pattern** painted onto a weapon's UV layout. Uses SDXL with a ControlNet
conditioned on the weapon's UV wireframe so generated art lands on the correct gun parts instead of
floating in UV space. Falls back to a procedural placeholder when torch/diffusers aren't available
(or `mock=True`), so the rest of the pipeline — PBR, packing, export, preview — is fully runnable
before the model is downloaded.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .assets import Weapon
from .config import GenerationConfig, get_config

# Prompt scaffolding. Generation uses base SDXL for clean, vivid output. Keep this short to leave
# token budget (CLIP's 77 limit) for the user prompt + quality modifiers.
STYLE_PREAMBLE = "weapon skin texture design, flat uv texture layout, crisp high detail, vivid"
NEGATIVE = (
    "photo of a real gun, 3d render, hands, person, blurry, low-res, jpeg artifacts, watermark, "
    "text, signature, seams, stretched, distorted, washed out"
)


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


@dataclass
class GenResult:
    image: Image.Image     # base color on the UV layout
    seed: int
    prompt: str
    mock: bool


class Generator:
    """Lazy-loading SDXL + ControlNet generator with a procedural fallback."""

    def __init__(self, cfg: GenerationConfig | None = None, *, mock: bool | None = None):
        self.cfg = cfg or get_config().generation
        # Auto-mock if torch can't be imported; explicit mock arg overrides.
        self.mock = (not _torch_available()) if mock is None else mock
        self._pipe = None
        self._ip_loaded = False

    # -- public API ---------------------------------------------------------------------------

    def generate(self, prompt: str, weapon: Weapon, *, seed: int | None = None,
                 negative: str = NEGATIVE, reference_image: Image.Image | None = None,
                 reference_scale: float = 0.6, controlnet_scale: float | None = None,
                 steps: int | None = None) -> GenResult:
        """Generate the base-color pattern.

        reference_image -> IP-Adapter style/colour conditioning. controlnet_scale/steps override
        config for this call (used by the rarity/complexity dial).
        """
        seed = self.cfg.seed if seed is None else seed
        if seed is None or seed < 0:
            seed = self._seed_from(prompt + weapon.key)
        full_prompt = f"{STYLE_PREAMBLE}, {prompt}"
        if self.mock:
            img = self._procedural(full_prompt, weapon, seed, reference_image)
            return GenResult(img, seed, full_prompt, mock=True)
        img = self._diffuse(full_prompt, negative, weapon, seed,
                            reference_image=reference_image, reference_scale=reference_scale,
                            controlnet_scale=controlnet_scale, steps=steps)
        return GenResult(img, seed, full_prompt, mock=False)

    # -- real SDXL path -----------------------------------------------------------------------

    def _load(self):
        if self._pipe is not None:
            return self._pipe
        import torch
        from diffusers import (
            StableDiffusionXLControlNetPipeline,
            ControlNetModel,
            AutoencoderKL,
        )

        dtype = torch.float16 if self.cfg.dtype == "float16" else torch.float32
        controlnet = ControlNetModel.from_pretrained(self.cfg.controlnet_model, torch_dtype=dtype)
        vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=dtype)
        pipe = StableDiffusionXLControlNetPipeline.from_pretrained(
            self.cfg.base_model, controlnet=controlnet, vae=vae, torch_dtype=dtype,
            variant="fp16" if dtype == torch.float16 else None,
        )
        pipe.enable_model_cpu_offload()        # fits comfortably in 16GB
        pipe.enable_vae_tiling()
        self._pipe = pipe
        return pipe

    def _control_image(self, weapon: Weapon, size: int) -> Image.Image:
        """Canny edges of the UV wireframe → ControlNet conditioning."""
        import cv2
        if weapon.uv_path.exists():
            uv = Image.open(weapon.uv_path).convert("L").resize((size, size))
            arr = np.asarray(uv)
            edges = cv2.Canny(arr, 80, 160)
        else:
            edges = np.zeros((size, size), dtype=np.uint8)
        return Image.fromarray(np.stack([edges] * 3, axis=-1))

    def _ensure_ip_adapter(self):
        """Lazy-load the SDXL IP-Adapter (used when a reference image is supplied)."""
        if self._ip_loaded:
            return
        import torch
        pipe = self._load()
        pipe.load_ip_adapter("h94/IP-Adapter", subfolder="sdxl_models",
                             weight_name="ip-adapter_sdxl.bin")
        # With model_cpu_offload, the image encoder loads on CPU (fp16) while latents are on GPU,
        # causing a device/dtype mismatch. Pin it to the GPU in fp16.
        if getattr(pipe, "image_encoder", None) is not None:
            pipe.image_encoder.to(device="cuda", dtype=torch.float16)
        self._ip_loaded = True

    def _diffuse(self, prompt: str, negative: str, weapon: Weapon, seed: int, *,
                 reference_image: Image.Image | None = None, reference_scale: float = 0.6,
                 controlnet_scale: float | None = None, steps: int | None = None) -> Image.Image:
        import torch
        pipe = self._load()
        size = self.cfg.resolution
        control = self._control_image(weapon, size)
        gen = torch.Generator(device="cpu").manual_seed(seed)
        cn = controlnet_scale if controlnet_scale is not None else self.cfg.controlnet_scale
        kwargs = dict(
            prompt=prompt, negative_prompt=negative, image=control,
            num_inference_steps=steps or self.cfg.steps,
            guidance_scale=self.cfg.guidance_scale,
            controlnet_conditioning_scale=cn,
            generator=gen, width=size, height=size,
        )
        if reference_image is not None:
            self._ensure_ip_adapter()
            pipe.set_ip_adapter_scale(reference_scale)
            kwargs["ip_adapter_image"] = reference_image.convert("RGB")
        elif self._ip_loaded:
            pipe.set_ip_adapter_scale(0.0)   # disable when no reference this call
        out = pipe(**kwargs)
        img = out.images[0]
        tex = self.cfg.texture_resolution
        return img.resize((tex, tex), Image.LANCZOS)

    # -- procedural fallback ------------------------------------------------------------------

    @staticmethod
    def _seed_from(text: str) -> int:
        return int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**31)

    def _procedural(self, prompt: str, weapon: Weapon, seed: int,
                    reference: Image.Image | None = None) -> Image.Image:
        """Deterministic placeholder art: derives a palette from the prompt and lays down a
        layered pattern over the UV wireframe. Lets us validate export/PBR/preview end-to-end."""
        size = self.cfg.texture_resolution
        rng = np.random.default_rng(seed)
        # palette from prompt hash -> a few hues
        h = hashlib.sha256(prompt.encode()).digest()
        base = np.array([h[0], h[1], h[2]], dtype=np.float32)
        accent = np.array([h[3], h[4], h[5]], dtype=np.float32)
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size
        # layered waves + noise for a finish-like field
        field = (np.sin(xx * 18 + yy * 7 + h[6]) + np.cos(yy * 14 - xx * 5 + h[7])) * 0.5
        noise = rng.standard_normal((size // 8, size // 8))
        noise = np.asarray(Image.fromarray(((noise - noise.min()) /
                  (np.ptp(noise) + 1e-6) * 255).astype(np.uint8)).resize((size, size))) / 255.0
        mix = np.clip(0.5 + 0.4 * field + 0.3 * (noise - 0.5), 0, 1)[..., None]
        rgb = (base[None, None] * mix + accent[None, None] * (1 - mix)).clip(0, 255)
        img = Image.fromarray(rgb.astype(np.uint8), "RGB")
        # If a reference image is supplied, blend its colours in (mock of IP-Adapter behaviour).
        if reference is not None:
            ref = np.asarray(reference.convert("RGB").resize((size, size))).astype(np.float32)
            img = Image.fromarray((np.asarray(img).astype(np.float32) * 0.5 + ref * 0.5)
                                  .clip(0, 255).astype(np.uint8), "RGB")
        # overlay the UV wireframe so it visibly aligns to the weapon parts
        if weapon.uv_path.exists():
            uv = Image.open(weapon.uv_path).convert("L").resize((size, size))
            uv_arr = np.asarray(uv)[..., None] / 255.0
            base_arr = np.asarray(img).astype(np.float32)
            img = Image.fromarray((base_arr * (0.35 + 0.65 * uv_arr)).clip(0, 255).astype(np.uint8))
        return img
