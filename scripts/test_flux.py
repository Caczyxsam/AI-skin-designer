import time, gc
import torch
from PIL import Image, ImageDraw
from cs2skin.config import get_config
from cs2skin.generate import Generator
from cs2skin.assets import get_weapon

w = get_weapon("ak47")
P = "molten lava over black obsidian, glowing orange cracks, intricate detailed weapon skin design"
imgs = []
for backend in ["sdxl", "flux"]:
    cfg = get_config(); cfg.generation.backend = backend
    gen = Generator(cfg.generation, mock=False)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time(); r = gen.generate(P, w, seed=1); dt = time.time() - t0
    peak = torch.cuda.max_memory_allocated() / 1e9
    print(f"{backend}: {dt:.1f}s, peak VRAM {peak:.1f} GB", flush=True)
    imgs.append((f"{backend.upper()}  {dt:.0f}s / {peak:.1f}GB", r.image.resize((512, 512))))
    del gen, r; gc.collect(); torch.cuda.empty_cache()
W = 512; c = Image.new("RGB", (2 * W + 20, W + 30), (18, 18, 18)); d = ImageDraw.Draw(c); x = 0
for t, im in imgs:
    d.text((x + 8, 4), t, fill=(255, 200, 120)); c.paste(im, (x, 24)); x += W + 20
c.save("output/_sdxl_vs_flux.png"); print("SAVED")
