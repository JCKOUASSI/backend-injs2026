"""
Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur
d'import/reprise — sorties print() de console volontaires ;
exclu du garde-fou check_repo_hygiene.
Génère l'icône de l'app mobile QR Badge (1024x1024 PNG).
Usage: source venv/bin/activate && python scripts/generate_app_icon.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
OUT = os.path.join(os.path.dirname(__file__), '..', 'qr_badge_mobile', 'assets', 'app_icon.png')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Background: rounded green gradient feel
# Solid green background
bg_color = (56, 142, 60)  # #1A68AC
draw.rounded_rectangle([(0, 0), (SIZE - 1, SIZE - 1)], radius=200, fill=bg_color)

# White QR code pattern (simplified)
margin = 180
qr_area = SIZE - 2 * margin
cell = qr_area // 7

# Draw finder patterns (3 corners of QR code)
def draw_finder(x, y):
    """Draw a QR finder pattern (3 nested squares)."""
    s = cell * 3
    # Outer white square
    draw.rectangle([x, y, x + s, y + s], fill='white')
    # Inner green square
    inset = cell // 2
    draw.rectangle([x + inset, y + inset, x + s - inset, y + s - inset], fill=bg_color)
    # Center white square
    inset2 = cell
    draw.rectangle([x + inset2, y + inset2, x + s - inset2, y + s - inset2], fill='white')

# Top-left finder
draw_finder(margin, margin)
# Top-right finder
draw_finder(SIZE - margin - cell * 3, margin)
# Bottom-left finder
draw_finder(margin, SIZE - margin - cell * 3)

# Center checkmark circle (orange accent)
cx, cy = SIZE // 2, SIZE // 2 + 30
r = 160
# Orange circle
orange = (245, 124, 0)  # #F5B100
draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=orange)

# White checkmark in the circle
check_pts = [
    (cx - 70, cy + 5),
    (cx - 20, cy + 60),
    (cx + 80, cy - 50),
]
draw.line(check_pts, fill='white', width=36, joint='curve')

# Some decorative QR dots
import random
random.seed(42)
for row in range(7):
    for col in range(7):
        # Skip finder pattern areas and center
        if row < 3 and col < 3:
            continue
        if row < 3 and col > 3:
            continue
        if row > 3 and col < 3:
            continue
        # Skip center area (checkmark)
        if 2 <= row <= 4 and 2 <= col <= 4:
            continue

        if random.random() > 0.45:
            x = margin + col * cell + cell // 4
            y = margin + row * cell + cell // 4
            s = cell // 2
            draw.rounded_rectangle([x, y, x + s, y + s], radius=8, fill='white', outline=None)

img.save(OUT, 'PNG')
print(f'Icon saved: {OUT}')
