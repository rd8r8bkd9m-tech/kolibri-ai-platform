#!/usr/bin/env python3
"""
Generate APNG animation frames for the Kolibri hummingbird mascot.
Uses PIL/Pillow to draw cartoon bird frames procedurally.
Outputs: kolibri-idle.apng, kolibri-thinking.apng, etc.
"""
import math
import os
from PIL import Image, ImageDraw

OUT_DIR = "/home/ladik/kolibri-projects/kimi_agent_kolibrifin/kolibri-v2/public/mascot"

W, H = 512, 512
CX, CY = 256, 270  # center of bird
FPS = 24
DURATION_MS = int(1000 / FPS)

# Colors (RGBA)
TEAL_DARK = (44, 168, 180)
TEAL_MID = (58, 186, 180)
TEAL_LIGHT = (92, 200, 196)
TEAL_PALE = (125, 216, 213)
BEAK_ORANGE = (232, 115, 74)
BEAK_DARK = (212, 96, 58)
BEAK_HAPPY = (245, 158, 11)
CHEEK_PINK = (249, 168, 212)
EYE_WHITE = (255, 255, 255)
PUPIL_BLACK = (26, 26, 46)
SHADOW_COLOR = (44, 168, 180, 38)
BG_COLOR = (0, 0, 0, 0)


def draw_bird(draw, cx, cy, wing_angle=0, body_scale=1.0, head_tilt=0,
              eye_open=True, pupil_offset=(0, 0), beak_happy=False,
              cheek_alpha=0.3, sleeping=False, wing_fold=0.0):
    """Draw the Kolibri bird at given position with animation parameters."""
    
    # Body dimensions
    bw = int(32 * body_scale)
    bh = int(36 * body_scale)
    
    # Shadow
    shadow_w = int(28 * body_scale)
    shadow_h = int(6 * body_scale)
    draw.ellipse([cx - shadow_w, cy + bh//2 + 8, cx + shadow_w, cy + bh//2 + 22],
                 fill=SHADOW_COLOR)
    
    # Tail feathers
    tail_x = cx - int(10 * body_scale)
    tail_y = cy + int(10 * body_scale)
    tail_len = int(28 * body_scale)
    for i, (dx, dy, w) in enumerate([
        (-18, 12, 8), (-14, 18, 7), (-10, 24, 6),
    ]):
        alpha = [180, 200, 170][i]
        color = TEAL_DARK + (alpha,)
        pts = [
            (tail_x, tail_y),
            (tail_x + int(dx * body_scale), tail_y + int(dy * body_scale)),
            (tail_x + int(dx * body_scale * 0.8), tail_y + int((dy + 8) * body_scale)),
        ]
        draw.polygon(pts, fill=color)
    
    # Wings
    wing_len = int(26 * body_scale)
    wing_y = cy - int(5 * body_scale)
    
    # Left wing
    if wing_fold < 0.5:
        la = wing_angle
        lx1 = cx - bw//2
        ly1 = wing_y
        lx2 = lx1 - wing_len * math.cos(math.radians(la))
        ly2 = ly1 - wing_len * math.sin(math.radians(la))
        wing_pts = [
            (lx1, ly1),
            (lx2, ly2 - 8),
            (lx2 + 10, ly2 + 5),
            (lx1 - 5, ly1 + 6),
            (lx1 + 5, ly1 + 3),
        ]
        draw.polygon(wing_pts, fill=TEAL_MID + (217,))
        # Wing highlight
        inner_pts = [
            (lx1, ly1),
            (lx2 + 5, ly2 - 3),
            (lx2 + 12, ly2 + 2),
            (lx1 - 2, ly1 + 3),
        ]
        draw.polygon(inner_pts, fill=TEAL_DARK + (153,))
    else:
        # Folded wing
        fold_pts = [
            (cx - bw//2, wing_y),
            (cx - bw//2 - 5, wing_y + 15),
            (cx - bw//2 + 5, wing_y + 18),
            (cx - bw//2 + 8, wing_y + 5),
        ]
        draw.polygon(fold_pts, fill=TEAL_MID + (217,))
    
    # Right wing
    if wing_fold < 0.5:
        ra = -wing_angle
        rx1 = cx + bw//2
        ry1 = wing_y
        rx2 = rx1 + wing_len * math.cos(math.radians(ra))
        ry2 = ry1 - wing_len * math.sin(math.radians(-ra))
        wing_pts = [
            (rx1, ry1),
            (rx2, ry2 - 8),
            (rx2 - 10, ry2 + 5),
            (rx1 + 5, ry1 + 6),
            (rx1 - 5, ry1 + 3),
        ]
        draw.polygon(wing_pts, fill=TEAL_MID + (217,))
        inner_pts = [
            (rx1, ry1),
            (rx2 - 5, ry2 - 3),
            (rx2 - 12, ry2 + 2),
            (rx1 + 2, ry1 + 3),
        ]
        draw.polygon(inner_pts, fill=TEAL_DARK + (153,))
    else:
        fold_pts = [
            (cx + bw//2, wing_y),
            (cx + bw//2 + 5, wing_y + 15),
            (cx + bw//2 - 5, wing_y + 18),
            (cx + bw//2 - 8, wing_y + 5),
        ]
        draw.polygon(fold_pts, fill=TEAL_MID + (217,))
    
    # Body
    draw.ellipse([cx - bw, cy - bh, cx + bw, cy + bh], fill=TEAL_MID)
    # Belly
    belly_w, belly_h = int(bw * 0.65), int(bh * 0.65)
    draw.ellipse([cx - belly_w, cy - belly_h + 8, cx + belly_w, cy + belly_h + 8],
                 fill=TEAL_LIGHT + (153,))
    # Belly spot
    spot_w, spot_h = int(bw * 0.45), int(bh * 0.5)
    draw.ellipse([cx - spot_w, cy - spot_h + 12, cx + spot_w, cy + spot_h + 12],
                 fill=TEAL_PALE + (102,))
    
    # Head
    hr = int(24 * body_scale)
    head_cx = cx + int(head_tilt * 2)
    head_cy = cy - bh - hr + 5
    draw.ellipse([head_cx - hr, head_cy - hr, head_cx + hr, head_cy + hr], fill=TEAL_MID)
    # Head highlight
    draw.ellipse([head_cx - hr + 4, head_cy - hr + 2, head_cx + hr - 6, head_cy + hr - 6],
                 fill=TEAL_LIGHT + (102,))
    
    # Crown feathers
    crown_pts = [
        (head_cx - 3, head_cy - hr),
        (head_cx - 2, head_cy - hr - 14),
        (head_cx + 1, head_cy - hr - 14),
        (head_cx, head_cy - hr),
    ]
    draw.polygon(crown_pts, fill=TEAL_DARK)
    crown2_pts = [
        (head_cx + 1, head_cy - hr - 1),
        (head_cx + 1, head_cy - hr - 12),
        (head_cx + 4, head_cy - hr - 12),
        (head_cx + 3, head_cy - hr - 1),
    ]
    draw.polygon(crown2_pts, fill=TEAL_MID + (204,))
    
    # Eye
    eye_cx = head_cx + int(12 * body_scale)
    eye_cy = head_cy - int(2 * body_scale)
    eye_rx, eye_ry = int(5 * body_scale), int(5.5 * body_scale)
    
    if sleeping:
        # Sleeping: curved line
        draw.arc([eye_cx - eye_rx, eye_cy - 2, eye_cx + eye_rx, eye_cy + 4],
                 0, 180, fill=TEAL_DARK, width=2)
    elif eye_open:
        # Open eye
        draw.ellipse([eye_cx - eye_rx, eye_cy - eye_ry, eye_cx + eye_rx, eye_cy + eye_ry],
                     fill=EYE_WHITE)
        # Pupil
        px = eye_cx + int(pupil_offset[0])
        py = eye_cy + int(pupil_offset[1])
        pr = int(3 * body_scale)
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=PUPIL_BLACK)
        # Eye shine
        sr = int(1.2 * body_scale)
        draw.ellipse([px + sr - 1, py - sr - 1, px + sr + sr, py - sr + sr],
                     fill=EYE_WHITE + (204,))
    else:
        # Blinking: eyelid covers eye
        draw.ellipse([eye_cx - eye_rx, eye_cy - eye_ry, eye_cx + eye_rx, eye_cy + eye_ry],
                     fill=EYE_WHITE)
        lid_h = int(eye_ry * 2 * min(1.0, (1.0 - pupil_offset[1] if pupil_offset[1] > 0 else 1.0)))
        draw.rectangle([eye_cx - eye_rx - 1, eye_cy - eye_ry - 1,
                        eye_cx + eye_rx + 1, eye_cy - eye_ry + lid_h],
                       fill=TEAL_MID)
    
    # Beak
    beak_cx = eye_cx + int(7 * body_scale)
    beak_cy = eye_cy + int(5 * body_scale)
    beak_len = int(16 * body_scale)
    beak_h = int(3 * body_scale)
    beak_color = BEAK_HAPPY if beak_happy else BEAK_ORANGE
    beak_pts = [
        (beak_cx, beak_cy - beak_h),
        (beak_cx + beak_len, beak_cy),
        (beak_cx, beak_cy + beak_h),
    ]
    draw.polygon(beak_pts, fill=beak_color)
    # Beak top half
    beak_top = [
        (beak_cx, beak_cy - beak_h),
        (beak_cx + beak_len, beak_cy),
        (beak_cx, beak_cy),
    ]
    draw.polygon(beak_top, fill=BEAK_DARK if not beak_happy else (217, 119, 6))
    
    # Cheek blush
    cheek_x = head_cx - int(8 * body_scale)
    cheek_y = head_cy + int(4 * body_scale)
    cheek_r = int(4 * body_scale)
    cheek_alpha_int = int(cheek_alpha * 255)
    draw.ellipse([cheek_x - cheek_r, cheek_y - cheek_r, cheek_x + cheek_r, cheek_y + cheek_r],
                 fill=CHEEK_PINK + (cheek_alpha_int,))


def draw_sparkles(draw, frame_idx, cx, cy, count=5, seed=42):
    """Draw sparkle/star decorations around the bird."""
    import random
    rng = random.Random(seed)
    for i in range(count):
        sx = cx + rng.randint(-80, 80)
        sy = cy + rng.randint(-100, -20)
        phase = rng.random() * math.pi * 2
        t = frame_idx / FPS
        sparkle_alpha = max(0, min(255, int(255 * abs(math.sin(t * 3 + phase)))))
        size = rng.randint(4, 10)
        
        # Star shape
        points = []
        for j in range(8):
            angle = math.pi * 2 * j / 8 - math.pi / 2
            r = size if j % 2 == 0 else size // 2
            points.append((sx + r * math.cos(angle), sy + r * math.sin(angle)))
        draw.polygon(points, fill=(245, 158, 11, sparkle_alpha))


def draw_zzz(draw, frame_idx, cx, cy):
    """Draw floating Z's for sleeping animation."""
    t = frame_idx / FPS
    for i, (dx, dy, sz) in enumerate([(30, -50, 14), (50, -70, 12), (65, -88, 10)]):
        phase = (t * 0.5 + i * 0.3) % 1.0
        alpha = int(180 * (1 - phase))
        x = cx + dx + phase * 10
        y = cy + dy - phase * 30
        # Draw "z"
        draw.text((x, y), "z", fill=TEAL_MID + (alpha,))
        # Draw line below z
        draw.line([(x, y + sz), (x + sz - 2, y + sz)], fill=TEAL_MID + (alpha,), width=2)


def draw_alert_mark(draw, cx, cy, color=(245, 158, 11)):
    """Draw alert exclamation mark."""
    x, y = cx + 60, cy - 65
    draw.text((x, y), "!", fill=color + (220,))


# ─── State generators ──────────────────────────────────────────────────

def gen_idle_frame(n, total):
    """Idle: gentle breathing, slow wing flutter, periodic blink."""
    t = n / total
    phase = t * math.pi * 2
    
    body_y_offset = 3 * math.sin(phase)
    wing_angle = 12 * math.sin(phase * 0.8)
    body_scale = 1.0 + 0.015 * math.sin(phase * 0.5)
    
    # Blink at ~20% through cycle
    blink = 0.08 < (t % 1.0) < 0.12
    
    return {
        'cy': CY + body_y_offset,
        'wing_angle': wing_angle,
        'body_scale': body_scale,
        'eye_open': not blink,
        'pupil_offset': (0, 0),
        'beak_happy': False,
        'cheek_alpha': 0.3,
        'sleeping': False,
        'wing_fold': 0,
    }


def gen_thinking_frame(n, total):
    """Thinking: fast wing flutter, slight head tilt, pupil wandering."""
    t = n / total
    phase = t * math.pi * 2
    
    body_y_offset = 2 * math.sin(phase * 1.2)
    wing_angle = 35 * math.sin(phase * 3)
    body_scale = 1.0 + 0.01 * math.sin(phase)
    head_tilt = -3 * math.sin(phase * 0.4)
    pupil_x = 1.5 * math.sin(phase * 0.6)
    pupil_y = 1.0 * math.cos(phase * 0.6)
    
    blink = (t % 1.0) in [0.3, 0.31, 0.32]
    
    return {
        'cy': CY + body_y_offset,
        'wing_angle': wing_angle,
        'body_scale': body_scale,
        'eye_open': not blink,
        'pupil_offset': (pupil_x, pupil_y),
        'head_tilt': head_tilt,
        'beak_happy': False,
        'cheek_alpha': 0.3,
        'sleeping': False,
        'wing_fold': 0,
    }


def gen_ready_frame(n, total):
    """Ready: attentive hover, slightly faster wing than idle."""
    t = n / total
    phase = t * math.pi * 2
    
    body_y_offset = 4 * math.sin(phase * 0.8)
    wing_angle = 18 * math.sin(phase * 1.1)
    body_scale = 1.0 + 0.02 * math.sin(phase * 0.7)
    
    blink = (t % 1.0) in [0.25, 0.26, 0.27]
    
    return {
        'cy': CY + body_y_offset,
        'wing_angle': wing_angle,
        'body_scale': body_scale,
        'eye_open': not blink,
        'pupil_offset': (0, 0),
        'beak_happy': False,
        'cheek_alpha': 0.3,
        'sleeping': False,
        'wing_fold': 0,
    }


def gen_success_frame(n, total):
    """Success: jump, happy wings, sparkle."""
    t = n / total
    phase = t * math.pi * 2
    
    # Jump arc
    jump_t = t % 1.0
    if jump_t < 0.3:
        jump_y = -60 * math.sin(jump_t / 0.3 * math.pi)
    elif jump_t < 0.6:
        jump_y = -60 * math.sin((jump_t - 0.3) / 0.3 * math.pi)
    else:
        jump_y = 0
    
    wing_angle = 40 * math.sin(phase * 4)
    body_scale = 1.0 + 0.05 * abs(math.sin(phase * 2))
    head_tilt = 5 * math.sin(phase * 3)
    
    return {
        'cy': CY + jump_y,
        'wing_angle': wing_angle,
        'body_scale': body_scale,
        'eye_open': True,
        'pupil_offset': (0, -0.5),
        'head_tilt': head_tilt,
        'beak_happy': True,
        'cheek_alpha': 0.6,
        'sleeping': False,
        'wing_fold': 0,
        'sparkle': True,
    }


def gen_alert_frame(n, total):
    """Alert: startled shake, wide eyes, fast wings."""
    t = n / total
    phase = t * math.pi * 2
    
    shake_x = 4 * math.sin(phase * 6)
    wing_angle = 30 * math.sin(phase * 4)
    body_scale = 1.05 + 0.03 * math.sin(phase * 5)
    pupil_x = 1.5 * math.sin(phase * 3)
    pupil_y = 1.0 * math.cos(phase * 3)
    
    blink = (t % 1.0) in [0.2, 0.21, 0.22]
    
    return {
        'cy': CY,
        'cx_offset': shake_x,
        'wing_angle': wing_angle,
        'body_scale': body_scale,
        'eye_open': not blink,
        'pupil_offset': (pupil_x, pupil_y),
        'beak_happy': False,
        'cheek_alpha': 0.5,
        'sleeping': False,
        'wing_fold': 0,
        'alert': True,
    }


def gen_sleeping_frame(n, total):
    """Sleeping: slow breathing, closed eyes, Zzz floating."""
    t = n / total
    phase = t * math.pi * 2
    
    body_y_offset = 2 * math.sin(phase * 0.3)
    body_scale = 1.0 + 0.01 * math.sin(phase * 0.3)
    head_tilt = 4 * math.sin(phase * 0.2)
    
    return {
        'cy': CY + body_y_offset,
        'wing_angle': 0,
        'body_scale': body_scale,
        'eye_open': False,
        'pupil_offset': (0, 0),
        'head_tilt': head_tilt,
        'beak_happy': False,
        'cheek_alpha': 0.3,
        'sleeping': True,
        'wing_fold': 1.0,
    }


STATE_GENERATORS = {
    'idle': gen_idle_frame,
    'thinking': gen_thinking_frame,
    'ready': gen_ready_frame,
    'success': gen_success_frame,
    'alert': gen_alert_frame,
    'sleeping': gen_sleeping_frame,
}


def generate_state_apng(state_name, frame_count=72):
    """Generate APNG for a specific animation state."""
    gen = STATE_GENERATORS[state_name]
    frames = []
    
    for n in range(frame_count):
        params = gen(n, frame_count)
        cx = CX + params.get('cx_offset', 0)
        cy = params['cy']
        
        img = Image.new('RGBA', (W, H), BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        draw_bird(
            draw, cx, cy,
            wing_angle=params.get('wing_angle', 0),
            body_scale=params.get('body_scale', 1.0),
            head_tilt=params.get('head_tilt', 0),
            eye_open=params.get('eye_open', True),
            pupil_offset=params.get('pupil_offset', (0, 0)),
            beak_happy=params.get('beak_happy', False),
            cheek_alpha=params.get('cheek_alpha', 0.3),
            sleeping=params.get('sleeping', False),
            wing_fold=params.get('wing_fold', 0),
        )
        
        if params.get('sparkle'):
            draw_sparkles(draw, n, cx, cy)
        
        if params.get('sleeping'):
            draw_zzz(draw, n, cx, cy)
        
        if params.get('alert'):
            draw_alert_mark(draw, cx, cy)
        
        frames.append(img)
    
    # Save as APNG
    out_path = os.path.join(OUT_DIR, f"kolibri-{state_name}.png")
    frames[0].save(
        out_path,
        'PNG',
        save_all=True,
        append_images=frames[1:],
        duration=DURATION_MS,
        loop=0,
        disposal=2,
    )
    
    file_size = os.path.getsize(out_path)
    print(f"  {state_name}: {frame_count} frames, {out_path} ({file_size:,} bytes)")
    return out_path


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    
    print("Generating Kolibri mascot APNG animations...")
    print(f"  Canvas: {W}x{H}, FPS: {FPS}, Duration: {DURATION_MS}ms/frame")
    
    for state_name in STATE_GENERATORS:
        generate_state_apng(state_name)
    
    print("\nDone! All states generated.")
    
    # Summary
    total_size = 0
    for f in os.listdir(OUT_DIR):
        if f.startswith('kolibri-') and f.endswith('.png') and 'previous' not in f and 'CiBawowe' not in f:
            size = os.path.getsize(os.path.join(OUT_DIR, f))
            total_size += size
            print(f"  {f}: {size:,} bytes")
    print(f"  Total: {total_size:,} bytes")


if __name__ == '__main__':
    main()
