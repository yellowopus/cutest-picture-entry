import math
import os
import struct
import zlib
from pathlib import Path

WIDTH = 512
HEIGHT = 512

# ---------------------------------------------------------------------------
# Colors (floats 0..1)
# ---------------------------------------------------------------------------
BG_TOP = (0.98, 0.90, 0.95)
BG_BOTTOM = (0.85, 0.92, 0.98)

PINK = (1.00, 0.69, 0.78)
PALE_PINK = (1.00, 0.81, 0.87)
LAVENDER = (0.88, 0.81, 0.96)
YELLOW = (1.00, 0.87, 0.53)
WHITE = (1.00, 1.00, 0.98)

EAR_HEAD = (1.00, 0.965, 0.918)
INNER_EAR = (1.00, 0.71, 0.79)
OUTLINE = (0.79, 0.64, 0.55)
EYE = (0.24, 0.19, 0.22)
NOSE = (0.98, 0.62, 0.71)
MOUTH = (0.55, 0.40, 0.35)
BLUSH = (1.00, 0.67, 0.76)
WHISKER = (0.76, 0.63, 0.55)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def inside_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xint:
                inside = not inside
        j = i
    return inside


def bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def heart_poly(cx, cy, s, n=40):
    pts = []
    for i in range(n):
        t = 2.0 * math.pi * i / n
        hx = 16.0 * math.sin(t) ** 3
        hy = 13.0 * math.cos(t) - 5.0 * math.cos(2.0 * t) - 2.0 * math.cos(3.0 * t) - math.cos(4.0 * t)
        pts.append((cx + hx * s, cy - hy * s))
    return pts


def star_poly(cx, cy, radius, ratio=0.45, points=5):
    pts = []
    for i in range(points * 2):
        ang = -math.pi / 2.0 + i * math.pi / points
        rad = radius if i % 2 == 0 else radius * ratio
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def ellipse_inside(x, y, cx, cy, rx, ry):
    return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0


def seg_dist2(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        px, py = x - ax, y - ay
        return px * px + py * py
    t = ((x - ax) * dx + (y - ay) * dy) / l2
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    px = ax + t * dx - x
    py = ay + t * dy - y
    return px * px + py * py


# ---------------------------------------------------------------------------
# Scene definition
# ---------------------------------------------------------------------------
def build_scene():
    shapes = []

    def add_poly(poly, color, alpha=1.0):
        mnx, mny, mxx, mxy = bbox(poly)
        shapes.append((poly, mnx, mny, mxx, mxy, color[0], color[1], color[2], alpha))

    # Pastel background confetti
    add_poly(heart_poly(64, 86, 1.15), PINK)
    add_poly(heart_poly(452, 70, 1.05), PALE_PINK)
    add_poly(heart_poly(58, 382, 1.25), PALE_PINK)
    add_poly(heart_poly(448, 398, 1.05), PINK)
    add_poly(heart_poly(32, 232, 0.95), LAVENDER)
    add_poly(heart_poly(482, 218, 0.85), PINK)
    add_poly(heart_poly(190, 46, 0.95), PALE_PINK)
    add_poly(heart_poly(330, 42, 0.80), PINK)
    add_poly(heart_poly(258, 478, 1.15), PINK)
    add_poly(heart_poly(120, 486, 0.85), PALE_PINK)

    add_poly(star_poly(112, 168, 13), YELLOW)
    add_poly(star_poly(404, 144, 11), YELLOW)
    add_poly(star_poly(78, 326, 14), WHITE)
    add_poly(star_poly(458, 330, 10), YELLOW)
    add_poly(star_poly(170, 92, 9), WHITE)
    add_poly(star_poly(354, 84, 8), YELLOW)
    add_poly(star_poly(300, 478, 12), WHITE)
    add_poly(star_poly(200, 488, 9), YELLOW)
    add_poly(star_poly(52, 168, 8), YELLOW)
    add_poly(star_poly(462, 258, 8), WHITE)

    # Cat ears (drawn first, head covers their bases)
    ear_shapes = []
    earL = [(126, 48), (184, 132), (238, 116)]
    earR = [(386, 48), (274, 116), (328, 132)]
    innerL = [(152, 82), (166, 100), (190, 104)]
    innerR = [(360, 82), (346, 100), (322, 104)]
    for poly, color in ((earL, EAR_HEAD), (earR, EAR_HEAD), (innerL, INNER_EAR), (innerR, INNER_EAR)):
        mnx, mny, mxx, mxy = bbox(poly)
        ear_shapes.append((poly, mnx, mny, mxx, mxy, color[0], color[1], color[2]))

    face = {
        'cx': 256.0, 'cy': 260.0, 'outline_r': 149.0, 'fill_r': 145.0,
        'outline': OUTLINE, 'head': EAR_HEAD,
    }

    blushes = [(152.0, 302.0), (360.0, 302.0)]
    eyes = [(196.0, 250.0), (316.0, 250.0)]
    highlights = [(188.0, 232.0, 9.0), (206.0, 264.0, 4.0),
                  (324.0, 232.0, 9.0), (306.0, 264.0, 4.0)]

    nose_poly = [(248.0, 292.0), (264.0, 292.0), (256.0, 302.0)]

    mouth_segs = [
        (232.0, 306.0, 244.0, 314.0, 3.0),
        (244.0, 314.0, 256.0, 306.0, 3.0),
        (256.0, 306.0, 268.0, 314.0, 3.0),
        (268.0, 314.0, 280.0, 306.0, 3.0),
    ]

    whiskers = [
        (88.0, 262.0, 148.0, 270.0, 1.8),
        (92.0, 288.0, 150.0, 290.0, 1.8),
        (364.0, 270.0, 424.0, 262.0, 1.8),
        (362.0, 290.0, 420.0, 288.0, 1.8),
    ]

    return shapes, ear_shapes, face, blushes, eyes, highlights, nose_poly, mouth_segs, whiskers


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------
def render_image():
    shapes, ear_shapes, face, blushes, eyes, highlights, nose_poly, mouth_segs, whiskers = build_scene()

    nose_bbox = bbox(nose_poly)
    mouth_bboxes = [(min(ax, bx) - t, min(ay, by) - t, max(ax, bx) + t, max(ay, by) + t)
                    for ax, ay, bx, by, t in mouth_segs]
    whisker_bboxes = [(min(ax, bx) - t, min(ay, by) - t, max(ax, bx) + t, max(ay, by) + t)
                      for ax, ay, bx, by, t in whiskers]

    hcx, hcy = face['cx'], face['cy']
    outline_r2 = face['outline_r'] ** 2
    fill_r2 = face['fill_r'] ** 2

    eye_rx, eye_ry = 29.0, 36.0
    blush_rx, blush_ry = 25.0, 13.0

    gt0, gt1, gt2 = BG_TOP
    gb0, gb1, gb2 = BG_BOTTOM
    gd0, gd1, gd2 = gb0 - gt0, gb1 - gt1, gb2 - gt2
    inv_h = 1.0 / (HEIGHT - 1)

    offsets = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))
    pixels = bytearray(WIDTH * HEIGHT * 4)
    idx = 0

    for y in range(HEIGHT):
        for x in range(WIDTH):
            r_acc = g_acc = b_acc = 0.0

            for ox, oy in offsets:
                sx = x + ox
                sy = y + oy

                t = sy * inv_h
                cr = gt0 + gd0 * t
                cg = gt1 + gd1 * t
                cb = gt2 + gd2 * t

                # Background confetti
                for poly, mnx, mny, mxx, mxy, sr, sg, sb, sa in shapes:
                    if sx < mnx or sx > mxx or sy < mny or sy > mxy:
                        continue
                    if inside_poly(sx, sy, poly):
                        if sa >= 1.0:
                            cr, cg, cb = sr, sg, sb
                        else:
                            cr += (sr - cr) * sa
                            cg += (sg - cg) * sa
                            cb += (sb - cb) * sa

                # Ears (outer + inner), behind the head
                for poly, mnx, mny, mxx, mxy, sr, sg, sb in ear_shapes:
                    if sx < mnx or sx > mxx or sy < mny or sy > mxy:
                        continue
                    if inside_poly(sx, sy, poly):
                        cr, cg, cb = sr, sg, sb

                # Head outline then fill
                dx = sx - hcx
                dy = sy - hcy
                d2 = dx * dx + dy * dy
                if d2 <= outline_r2:
                    cr, cg, cb = face['outline']
                if d2 <= fill_r2:
                    cr, cg, cb = face['head']

                # Blush
                for bx, by in blushes:
                    if ellipse_inside(sx, sy, bx, by, blush_rx, blush_ry):
                        cr += (BLUSH[0] - cr) * 0.90
                        cg += (BLUSH[1] - cg) * 0.90
                        cb += (BLUSH[2] - cb) * 0.90

                # Whiskers
                for i, (ax, ay, bx, by, th) in enumerate(whiskers):
                    mnx, mny, mxx, mxy = whisker_bboxes[i]
                    if sx < mnx or sx > mxx or sy < mny or sy > mxy:
                        continue
                    if seg_dist2(sx, sy, ax, ay, bx, by) <= th * th:
                        cr += (WHISKER[0] - cr) * 0.90
                        cg += (WHISKER[1] - cg) * 0.90
                        cb += (WHISKER[2] - cb) * 0.90

                # Eyes
                for ex, ey in eyes:
                    if ellipse_inside(sx, sy, ex, ey, eye_rx, eye_ry):
                        cr, cg, cb = EYE

                # Sparkles
                for hx, hy, hr in highlights:
                    hdx = sx - hx
                    hdy = sy - hy
                    if hdx * hdx + hdy * hdy <= hr * hr:
                        cr, cg, cb = 1.0, 1.0, 1.0

                # Nose
                mnx, mny, mxx, mxy = nose_bbox
                if not (sx < mnx or sx > mxx or sy < mny or sy > mxy):
                    if inside_poly(sx, sy, nose_poly):
                        cr, cg, cb = NOSE

                # Tiny "w" smile
                for i, (ax, ay, bx, by, th) in enumerate(mouth_segs):
                    mnx, mny, mxx, mxy = mouth_bboxes[i]
                    if sx < mnx or sx > mxx or sy < mny or sy > mxy:
                        continue
                    if seg_dist2(sx, sy, ax, ay, bx, by) <= th * th:
                        cr, cg, cb = MOUTH

                r_acc += cr
                g_acc += cg
                b_acc += cb

            pixels[idx] = int(r_acc * 63.75 + 0.5)      # /4 * 255
            pixels[idx + 1] = int(g_acc * 63.75 + 0.5)
            pixels[idx + 2] = int(b_acc * 63.75 + 0.5)
            pixels[idx + 3] = 255
            idx += 4

    return pixels


# ---------------------------------------------------------------------------
# PNG writer (zlib + struct, no external deps)
# ---------------------------------------------------------------------------
def write_png(path, width, height, pixels):
    def chunk(tag, data):
        block = struct.pack('>I', len(data)) + tag + data
        block += struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
        return block

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type: None
        start = y * stride
        raw.extend(pixels[start:start + stride])

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', ihdr)
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    path.write_bytes(png)


def main():
    output_dir = Path(os.environ.get('MAKEFUN_OUTPUT_DIR', '/output'))
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / 'entry.png'
    write_png(out_path, WIDTH, HEIGHT, render_image())
    print(out_path)


if __name__ == '__main__':
    main()
