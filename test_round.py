import os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

font_path = 'E:/zidongjianji2/fonts/simhei.ttf'
font_size = 84

# Measure text
text = '春天的花开了'
pil_font = ImageFont.truetype(font_path, font_size)
dummy = Image.new('RGBA', (1, 1))
bbox = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=pil_font)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
print(f'Text size: {tw}x{th}')

# Create rounded bg
pad_x, pad_y = 30, 12
bg_w = tw + pad_x * 2
bg_h = th + pad_y * 2
bg_img = Image.new('RGBA', (bg_w, bg_h), (0, 0, 0, 0))
ImageDraw.Draw(bg_img).rounded_rectangle([0, 0, bg_w - 1, bg_h - 1], radius=16, fill=(255, 255, 255, 240))
bg_path = os.path.join(os.path.dirname(__file__), 'work', 'test_bg.png')
bg_img.save(bg_path)
print(f'BG saved: {bg_path} ({bg_w}x{bg_h})')

# Test with ffmpeg
font_esc = font_path.replace("\\", "/").replace(":", "\\:")
ox = "(w-tw)/2-30"
oy = "192-12"

fc = (
    f"[0:v][1:v]overlay=x='{ox}':y='{oy}':enable='between(t\\,0.00\\,5.00)'[ov1];"
    f"[ov1]drawtext=text='春天的花开了':fontfile='{font_esc}':fontsize=84:fontcolor=white"
    f":x=(w-tw)/2:y=192"
    f":alpha='if(lt(t\\,0)\\,0\\,1)'"
    f":enable='between(t\\,0.00\\,5.00)'[dt1]"
)

cmd = [
    'ffmpeg', '-i', 'work/ext.mp4', '-i', bg_path,
    '-filter_complex', fc,
    '-map', '[dt1]', '-y', 'work/test_round.mp4'
]
print(f'\nFC:\n{fc}\n')
print(f'CMD: {" ".join(cmd[:8])}...')

result = subprocess.run(cmd, capture_output=True, text=True)
print(f'rc={result.returncode}')
if result.returncode != 0:
    print(f'stderr:\n{result.stderr[-500:]}')
else:
    print(f'OK size={os.path.getsize("work/test_round.mp4")}')
