import os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

font_path = 'E:/zidongjianji2/fonts/simhei.ttf'
font_size = 84
text = '春天的花开了'

# Measure text
pil_font = ImageFont.truetype(font_path, font_size)
dummy = Image.new('RGBA', (1, 1))
bbox = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=pil_font)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

# Create rounded bg
pad_x, pad_y = 30, 12
bg_w, bg_h = tw + pad_x * 2, th + pad_y * 2
bg_img = Image.new('RGBA', (bg_w, bg_h), (0, 0, 0, 0))
ImageDraw.Draw(bg_img).rounded_rectangle([0, 0, bg_w - 1, bg_h - 1], radius=16, fill=(255, 255, 255, 240))
bg_path = os.path.join(os.path.dirname(__file__), 'work', 'test_bg.png')
bg_img.save(bg_path)

font_esc = font_path.replace("\\", "/").replace(":", "\\:")

# Filter complex with format conversion after overlay
fc = (
    "[0:v][1:v]overlay=x='(w-tw)/2-30':y='192-12':enable='between(t\\,0.00\\,5.00)'[ov1];"
    "[ov1]format=yuva420p[ov2];"
    f"[ov2]drawtext=text='春天的花开了':fontfile='{font_esc}':fontsize=84:fontcolor=white"
    ":x=(w-tw)/2:y=192"
    ":enable='between(t\\,0.00\\,5.00)'[dt1]"
)

cmd = [
    'ffmpeg', '-i', 'work/ext.mp4', '-i', bg_path,
    '-filter_complex', fc,
    '-map', '[dt1]', '-y', 'work/test_round2.mp4'
]
print(f'FC:\n{fc}\n')
result = subprocess.run(cmd, capture_output=True, text=True)
print(f'rc={result.returncode}')
if result.returncode != 0:
    print(f'stderr:\n{result.stderr[-500:]}')
else:
    print(f'OK size={os.path.getsize("work/test_round2.mp4")}')
