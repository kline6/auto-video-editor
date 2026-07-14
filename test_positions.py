"""Test 2-position cycle: 上2, 下1, 上2"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.subtitle_service import burn_multi_text_effect

video_file = "E:/zidongjianji2/work/drawtext_exact.mp4"
output_file = "E:/zidongjianji2/work/result_pos_test.mp4"

text_lines = [
    "第一行文字（上2）",
    "第二行文字（下1）",
    "第三行文字（上2）",
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
        # Extract frames at 2s, 5s, 8s to check positions
        import subprocess
        for t in [2, 5, 8]:
            cmd = ['ffmpeg', '-i', result, '-vf', f'select=eq(n\\,{t*30})', '-vframes', '1',
                   '-y', f'E:/zidongjianji2/work/pos_test_{t}s.png']
            subprocess.run(cmd, capture_output=True)
        print("Frames extracted: pos_test_2s.png, pos_test_5s.png, pos_test_8s.png")
