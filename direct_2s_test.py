"""Direct test: call burn_multi_text_effect and inspect result"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.subtitle_service import burn_multi_text_effect

video_file = "E:/zidongjianji2/work/drawtext_exact.mp4"
output_file = "E:/zidongjianji2/work/result_direct_test.mp4"

text_lines = [
    "这是一行中文文字",
    "第二行文字",
    "测试第三行",
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
    print(f"Exists: {os.path.exists(output_file)}")
