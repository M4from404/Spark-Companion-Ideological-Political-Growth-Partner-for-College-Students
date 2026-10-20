# -*- coding: utf-8 -*-
"""Extract transparent character sprites from the red-background expression sheet."""
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

SHEET = "assets/sheet.png"
# cells: col 0/2 are red-bg columns, rows 0/1
CELLS = {
    "stand":  (0, 0),
    "wave":   (2, 0),
    "think":  (0, 1),
    "talk":   (2, 1),
}
CW, CH = 276, 369


def extract(cell_img):
    a = np.array(cell_img.convert("RGB")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    # saturated red background candidate (bright + dark shadow reds)
    red_x = r - np.maximum(g, b)
    cand = ((r > 85) & (red_x > 45)) | ((r > 30) & (red_x > 20) & (g < 60) & (b < 95))
    # keep only the component connected to the border
    lbl, n = ndimage.label(cand)
    border = np.unique(np.concatenate([lbl[0, :], lbl[-1, :], lbl[:, 0], lbl[:, -1]]))
    border = border[border != 0]
    bg = np.isin(lbl, border)
    # shadowed red trapped inside hair/arm gaps is not border-connected: kill it globally
    bg |= (red_x >= 16) & (g < 55) & (b < 95) & (r > 28) & (r < 115)
    bg = ndimage.binary_closing(bg, np.ones((3, 3)))
    # don't swallow lips: bg must not be tiny enclosed specks - handled above
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    # feather edge 1.2px
    am = Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(0.9))
    alpha = np.array(am)
    out = np.array(cell_img.convert("RGB")).astype(np.float32)
    # color decontamination: pull edge colours from the solid interior so red spill disappears
    solid = ~bg
    interior = ndimage.binary_erosion(solid, np.ones((7, 7)))
    if interior.sum() > 100:
        dist, (iy, ix) = ndimage.distance_transform_edt(~interior, return_indices=True)
        edge = solid & (dist <= 4)
        src = out[iy, ix]
        w = np.clip(1.0 - dist / 4.0, 0, 1)[..., None] * 0.9
        out = np.where(edge[..., None], out * (1 - w) + src * w, out)
    # final despill pass
    red_x = out[..., 0] - np.maximum(out[..., 1], out[..., 2])
    out[..., 0] = np.where(red_x > 8, out[..., 0] - (red_x - 8) * 0.9, out[..., 0])
    out = np.clip(out, 0, 255).astype(np.uint8)
    rgba = np.dstack([out, alpha])
    im = Image.fromarray(rgba, "RGBA")
    bbox = im.getbbox()
    # trim 2px margin to drop any residual key-colour line at the cell border
    bbox = (bbox[0] + 2, bbox[1] + 2, bbox[2] - 2, bbox[3] - 2)
    im = im.crop(bbox)
    # clean red-tinted glow that survives on the hair fringe
    arr = np.array(im).astype(np.float32)
    al = arr[..., 3]
    redx = arr[..., 0] - np.maximum(arr[..., 1], arr[..., 2])
    solid_ok = (al > 235) & (redx < 12)
    dist, (iy, ix) = ndimage.distance_transform_edt(~solid_ok, return_indices=True)
    fringe = (redx > 14) & (al > 3)
    src = arr[iy, ix][..., :3]
    arr[..., :3] = np.where(fringe[..., None], src, arr[..., :3])
    al = np.where(fringe & (al < 200), 0, al)
    arr[..., 3] = al
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    # clear residual key-colour artifacts on the outermost ring
    arr = np.array(im)
    arr[[0, -1], :, 3] = 0
    arr[:, [0, -1], 3] = 0
    im = Image.fromarray(arr, "RGBA")
    # pad bottom slightly so the feet don't touch the frame
    canvas = Image.new("RGBA", (im.width, im.height + 6), (0, 0, 0, 0))
    canvas.paste(im, (0, 0))
    return canvas


def main():
    sheet = Image.open(SHEET)
    for name, (cx, cy) in CELLS.items():
        cell = sheet.crop((cx * CW, cy * CH, cx * CW + CW, cy * CH + CH))
        sprite = extract(cell)
        # upscale 2x for 720p compositing
        sprite = sprite.resize((sprite.width * 2, sprite.height * 2), Image.LANCZOS)
        sprite.save(f"assets/sprites/{name}.png")
        print(name, sprite.size)


if __name__ == "__main__":
    main()
