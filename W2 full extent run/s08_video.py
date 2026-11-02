"""The flood as a film: hazard H1 to H6 at each moment from the 5-minute frames, with a moving camera, on the GPU.

Each screen pixel takes several ground samples and shows the worst class among them, so a thin wadi stays visible when
zoomed out. A sample's depth is the cell's level less the 5 m ground; its speed is interpolated from wet cell corners, as
in s06_pixel_hazard.py. Frames are blended in time between the saved maps. Colours are those of Block_2_Hazard_200y, over
Google satellite hybrid drawn by s08b_background.py. Usage: s08_video.py preview | s08_video.py run
"""

from __future__ import annotations

import json
import sys
import time as clock
from pathlib import Path

import cupy as cp
import h5py
import imageio_ffmpeg
import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont

import s06_pixel_hazard as hz

HERE = Path(__file__).resolve().parent
RUN = HERE / "runs" / "full_30m_200yr_5min"
OUT = HERE / "Wadi2D_full_extent_flood_hazard.mp4"
W, H = 1920, 1080
FPS = 30
PIX = 5.0
DEPTH_MIN = hz.DEPTH_MIN
FILM_DEPTH_MIN = 0.10  # m; shallower sheet is left out of the picture
COLOURS = np.array([[0, 0, 0], [0, 0, 255], [0, 128, 255], [0, 255, 255], [0, 255, 0], [255, 255, 0], [255, 0, 0]], "float32")
ALPHA = np.array([0.0, 0.30, 0.45, 0.60, 0.80, 0.90, 0.95], "float32")  # by class: the low classes must not bury the high ones
LABELS = ("H1", "H2", "H3", "H4", "H5", "H6")
OVERVIEW = (505000.0, 2665000.0, 225000.0)  # x, y, view width in m
ZOOM_M = 9000.0
TRANSIT_M = 70000.0  # the camera rises to this width between targets, so it never crosses fine ground on coarse imagery
FINE_FROM_MPP = 25.0  # m per screen pixel; the fine windows fade in below this
FINE_FULL_MPP = 15.0
FEATHER_M = 600.0

# (film seconds, simulated hours): slow through the rise and the peak, quick in the recession
TIMELINE = [(0, 3.5), (10, 8.0), (20, 11.0), (66, 16.0), (80, 30.0)]


def waypoints() -> list:
    """(film s, x, y, width): overview, down the coast through each hot spot, back out."""
    spots = json.loads((HERE / "video_hotspots.json").read_text())
    x0, y0, w0 = OVERVIEW
    points = [(0.0, x0, y0, w0), (14.0, x0, y0, w0)]
    t = 20.0
    for k, s in enumerate(spots):
        points += [(t, s["x"], s["y"], ZOOM_M), (t + 6.0, s["x"], s["y"], ZOOM_M)]
        if k + 1 < len(spots):
            n = spots[k + 1]
            points.append((t + 9.0, 0.5 * (s["x"] + n["x"]), 0.5 * (s["y"] + n["y"]), TRANSIT_M))
        t += 12.0
    points += [(t + 0.0, x0, y0, w0), (80.0, x0, y0, w0)]
    return points


def camera(t: float, points: list) -> tuple:
    """Eased between waypoints; the width in log space, so a zoom has a steady feel."""
    times = [p[0] for p in points]
    i = min(int(np.searchsorted(times, t, side="right")) - 1, len(points) - 2)
    a, b = points[i], points[i + 1]
    f = np.clip((t - a[0]) / max(b[0] - a[0], 1e-6), 0.0, 1.0)
    f = f * f * (3.0 - 2.0 * f)
    width = float(np.exp(np.log(a[3]) + f * (np.log(b[3]) - np.log(a[3]))))
    # the centre leads the zoom out and trails the zoom in, so the target stays in frame
    g = f if b[3] >= a[3] else f
    return a[1] + g * (b[1] - a[1]), a[2] + g * (b[2] - a[2]), width


def sim_hours(t: float) -> float:
    return float(np.interp(t, [p[0] for p in TIMELINE], [p[1] for p in TIMELINE]))


class Scene:
    def __init__(self) -> None:
        with rasterio.open(hz.DEM) as s:
            dem = s.read(1)
            self.left, self.top = s.transform.c, s.transform.f
        self.z = cp.asarray(dem)
        self.ny, self.nx = dem.shape
        del dem
        self.backgrounds = self._backgrounds()
        mean, tr = hz.read("max_mean_depth")
        depth_max, _ = hz.read("max_depth")
        level_max, _ = hz.read("max_level")
        self.tr = tr
        self.keep = cp.asarray(mean > DEPTH_MIN)
        self.zmin = cp.asarray(level_max - depth_max)
        self.file = h5py.File(RUN / "results.h5", "r")
        self.names = sorted(self.file["maps"].keys())
        self.times = np.array([float(self.file["maps"][n].attrs["t_s"]) for n in self.names]) / 3600.0
        self.cached: dict = {}

    @staticmethod
    def _backgrounds() -> dict:
        out = {}
        Image.MAX_IMAGE_PIXELS = None
        for path in sorted((HERE / "terrain" / "background").glob("*.png")):
            if path.stem == "test":
                continue
            meta = json.loads(path.with_suffix(".json").read_text())
            out[path.stem] = (cp.asarray(np.asarray(Image.open(path).convert("RGB"))), meta)
        return out

    @staticmethod
    def _bilinear(img: cp.ndarray, meta: dict, xs: cp.ndarray, ys: cp.ndarray) -> cp.ndarray:
        h, w = img.shape[:2]
        fy = cp.clip((meta["y1"] - ys) / (meta["y1"] - meta["y0"]) * h - 0.5, 0, h - 1.001)
        fx = cp.clip((xs - meta["x0"]) / (meta["x1"] - meta["x0"]) * w - 0.5, 0, w - 1.001)
        r, c = fy.astype(cp.int32), fx.astype(cp.int32)
        ty, tx = (fy - r)[:, None, None], (fx - c)[None, :, None]
        a = img[cp.ix_(r, c)].astype(cp.float32)
        b = img[cp.ix_(r, c + 1)].astype(cp.float32)
        d = img[cp.ix_(r + 1, c)].astype(cp.float32)
        e = img[cp.ix_(r + 1, c + 1)].astype(cp.float32)
        return (a * (1 - tx) + b * tx) * (1 - ty) + (d * (1 - tx) + e * tx) * ty

    def background(self, cx: float, cy: float, mpp: float) -> cp.ndarray:
        xs = cx + (cp.arange(W, dtype=cp.float32) + 0.5 - W / 2) * mpp
        ys = cy - (cp.arange(H, dtype=cp.float32) + 0.5 - H / 2) * mpp
        rgb = self._bilinear(*self.backgrounds["base"], xs, ys)
        strength = float(np.clip((FINE_FROM_MPP - mpp) / (FINE_FROM_MPP - FINE_FULL_MPP), 0.0, 1.0))
        if strength <= 0.0:
            return rgb
        for name, (img, meta) in self.backgrounds.items():
            if name == "base":
                continue
            if cx + W * mpp / 2 < meta["x0"] or cx - W * mpp / 2 > meta["x1"] or cy + H * mpp / 2 < meta["y0"] or cy - H * mpp / 2 > meta["y1"]:
                continue
            ex = cp.clip(cp.minimum(xs - meta["x0"], meta["x1"] - xs) / FEATHER_M, 0.0, 1.0)[None, :]
            ey = cp.clip(cp.minimum(ys - meta["y0"], meta["y1"] - ys) / FEATHER_M, 0.0, 1.0)[:, None]
            a = (ex * ey * strength)[..., None]
            rgb = rgb * (1 - a) + self._bilinear(img, meta, xs, ys) * a
        return rgb

    @staticmethod
    def _hillshade(dem: np.ndarray) -> cp.ndarray:
        """Hillshade, 8 bit, in strips so the gradients fit on the card."""
        out = np.empty(dem.shape, np.uint8)
        az, alt = np.radians(315.0), np.radians(45.0)
        for r in range(0, dem.shape[0], 8192):
            a = cp.asarray(dem[max(r - 1, 0) : r + 8193])
            gy, gx = cp.gradient(a * 1.5, PIX)
            off = r - max(r - 1, 0)
            gy, gx = gy[off : off + 8192], gx[off : off + 8192]
            slope = cp.pi / 2 - cp.arctan(cp.hypot(gx, gy))
            aspect = cp.arctan2(-gx, gy)
            s = cp.sin(alt) * cp.sin(slope) + cp.cos(alt) * cp.cos(slope) * cp.cos(az - cp.pi / 2 - aspect)
            out[r : r + 8192] = cp.asnumpy(cp.clip(150.0 + 95.0 * s, 0, 255).astype(cp.uint8))
        return cp.asarray(out)

    def frame_fields(self, i: int) -> tuple:
        if i not in self.cached:
            g = self.file["maps"][self.names[i]]
            d = cp.asarray(g["depth"][:]) * self.keep
            s = cp.asarray(g["speed"][:]) * self.keep * (d > DEPTH_MIN)
            if len(self.cached) >= 2:
                self.cached.pop(min(self.cached))
            self.cached[i] = (d, hz.corners(s))
        return self.cached[i]

    def render(self, hours: float, cx: float, cy: float, width: float) -> np.ndarray:
        mpp = width / W
        ss = int(np.clip(np.ceil(mpp / 12.0), 1, 4))
        xs = cx + (cp.arange(W * ss, dtype=cp.float32) + 0.5 - W * ss / 2) * mpp / ss
        ys = cy - (cp.arange(H * ss, dtype=cp.float32) + 0.5 - H * ss / 2) * mpp / ss
        pr = cp.clip(((self.top - ys) / PIX).astype(cp.int32), 0, self.ny - 1)
        pc = cp.clip(((xs - self.left) / PIX).astype(cp.int32), 0, self.nx - 1)
        i = int(np.clip(np.searchsorted(self.times, hours) - 1, 0, len(self.times) - 2))
        w = float(np.clip((hours - self.times[i]) / (self.times[i + 1] - self.times[i]), 0.0, 1.0))
        d0, c0 = self.frame_fields(i)
        d1, c1 = self.frame_fields(i + 1)
        tr = self.tr
        fy = (ys - tr.f) / tr.e
        fx = (xs - tr.c) / tr.a
        cr = cp.clip(fy.astype(cp.int32), 0, d0.shape[0] - 1)
        cc = cp.clip(fx.astype(cp.int32), 0, d0.shape[1] - 1)
        ty = (fy - cr)[:, None]
        tx = (fx - cc)[None, :]
        rr, ccg = cp.meshgrid(cr, cc, indexing="ij")
        pz = self.z[cp.ix_(pr, pc)]
        d = d0 * (1 - w) + d1 * w
        cell = d[rr, ccg]
        nw, ne, sw, se = hz.level_corners(self.zmin + d, (d > 0) & self.keep)

        def sample(c):
            return (c[rr, ccg] * (1 - ty) * (1 - tx) + c[rr, ccg + 1] * (1 - ty) * tx + c[rr + 1, ccg] * ty * (1 - tx) + c[rr + 1, ccg + 1] * ty * tx)

        surface = nw[rr, ccg] * (1 - ty) * (1 - tx) + ne[rr, ccg] * (1 - ty) * tx + sw[rr, ccg] * ty * (1 - tx) + se[rr, ccg] * ty * tx
        depth = cp.maximum(surface - pz, 0.0) * (cell > 0)
        speed = (sample(c0) * (1 - w) + sample(c1) * w) * (depth >= DEPTH_MIN)
        dv = depth * speed
        cls = cp.ones(depth.shape, cp.uint8)
        for k, (dv_lim, d_lim, v_lim) in enumerate(hz.LIMITS, start=1):
            above = (dv > dv_lim) | (depth > d_lim) | (speed > v_lim)
            cls = cp.where(above & (cls == k), k + 1, cls).astype(cp.uint8)
        cls = cls * (depth >= FILM_DEPTH_MIN)
        if ss > 1:
            cls = cls.reshape(H, ss, W, ss).max(axis=(1, 3))
        rgb = self.background(cx, cy, mpp)
        colours = cp.asarray(COLOURS)[cls.astype(cp.int32)]
        a = cp.asarray(ALPHA)[cls.astype(cp.int32)][..., None]
        return cp.asnumpy((rgb * (1 - a) + colours * a).astype(cp.uint8))


def font(size: int):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def overlay(img: np.ndarray, hours: float, width: float) -> np.ndarray:
    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil, "RGBA")
    draw.rectangle((0, 0, W, 64), fill=(0, 0, 0, 165))
    draw.text((24, 15), "Wadi2D rain-on-grid: AIDR hazard, Block 2 200-yr storm over the project boundary", font=font(28), fill=(255, 255, 255, 255))
    draw.rectangle((W - 250, 84, W - 20, 150), fill=(0, 0, 0, 165))
    draw.text((W - 235, 95), f"Hour {hours:5.1f}", font=font(38), fill=(255, 255, 255, 255))
    draw.text((W // 2 - 80, H - 30), "Imagery: Google", font=font(18), fill=(255, 255, 255, 230))
    x = 24
    draw.rectangle((12, H - 58, 12 + 6 * 96 + 8, H - 12), fill=(0, 0, 0, 165))
    for k, name in enumerate(LABELS, start=1):
        colour = tuple(int(v) for v in COLOURS[k])
        draw.rectangle((x, H - 47, x + 28, H - 23), fill=colour + (255,))
        draw.text((x + 34, H - 49), name, font=font(22), fill=(255, 255, 255, 255))
        x += 96
    span = 10 ** np.floor(np.log10(width / 5.0))
    span = next(v for v in (span, span * 2, span * 5, span * 10) if v * W / width >= 120)
    bar = span * W / width
    draw.rectangle((W - 40 - bar - 16, H - 58, W - 20, H - 12), fill=(0, 0, 0, 165))
    draw.rectangle((W - 36 - bar, H - 26, W - 36, H - 20), fill=(255, 255, 255, 255))
    draw.text((W - 36 - bar, H - 54), f"{span / 1000:g} km", font=font(20), fill=(255, 255, 255, 255))
    return np.asarray(pil)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "preview"
    t0 = clock.time()
    scene = Scene()
    points = waypoints()
    print("scene ready", round(clock.time() - t0), "s", points, flush=True)
    if mode == "preview":
        for film in (6.0, 17.0, 23.0, 29.0, 47.0, 72.0):
            t1 = clock.time()
            hours = sim_hours(film)
            cx, cy, width = camera(film, points)
            img = overlay(scene.render(hours, cx, cy, width), hours, width)
            Image.fromarray(img).save(HERE / "terrain" / f"preview_{int(film):02d}.jpg", quality=88)
            print(f"film {film} s, hour {hours:.1f}, width {width:.0f} m, {clock.time() - t1:.2f} s", flush=True)
        return
    total = int(TIMELINE[-1][0] * FPS)
    writer = imageio_ffmpeg.write_frames(str(OUT), (W, H), fps=FPS, codec="libx264", quality=None, bitrate=None, pix_fmt_out="yuv420p",
                                         macro_block_size=1, output_params=["-crf", "21", "-preset", "medium", "-movflags", "+faststart"])  # fmt: skip
    writer.send(None)
    t1 = clock.time()
    for n in range(total):
        film = n / FPS
        hours = sim_hours(film)
        cx, cy, width = camera(film, points)
        writer.send(overlay(scene.render(hours, cx, cy, width), hours, width).tobytes())
        if n % 150 == 0:
            print(f"frame {n} of {total}, hour {hours:.1f}, {(clock.time() - t1) / (n + 1):.2f} s each", flush=True)
    writer.close()
    print("done", OUT.stat().st_size / 1e6, "MB", flush=True)


if __name__ == "__main__":
    main()
