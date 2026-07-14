"""Test: 前4行 1→2→3→4, 之后 2→3→2→3..."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.subtitle_service import burn_multi_text_effect

video_file = "E:/zidongjianji2/work/drawtext_exact.mp4"
output_file = "E:/zidongjianji2/work/result_pos_full_test.mp4"

text_lines = [
    "行1 上1",
    "行2 上2",
    "行3 下1",
    "行4 下2",
    "行5 上2",
    "行6 下1",
    "行7 上2",
    "行8 下1",
]

if __name__ == "__main__":
    if os.path.exists(output_file):
        os.remove(output_file)

    result = burn_multi_text_effect(
        video_file=video_file,
        text_blocks=[[line] for line in text_lines],
        duration=15.9,
        font_name="Microsoft YaHei",
        video_width=1080,
        video_height=1920
    )
    print(f"Result: {result}")

    if os.path.exists(result):
        import subprocess
        for t in [1, 3, 5, 7, 9, 11, 13, 15]:
            cmd = ['ffmpeg', '-i', result, '-vf', f'select=eq(n\\,{t*30})', '-vframes', '1',
                   '-y', f'E:/zidongjianji2/work/pos_full_{t}s.png']
            subprocess.run(cmd, capture_output=True)
        print("Frames extracted")
