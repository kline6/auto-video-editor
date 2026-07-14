import os
import platform
import random
import subprocess
from contextlib import contextmanager

from PIL import Image, ImageDraw, ImageFont

from utils import generate_temp_filename

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_DIR = os.path.join(BASE_DIR, "work")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

ASS_WIDTH_FACTOR = 1.35
MAX_BLOCK_TEXT_SCALE = 1.22
MIN_BLOCK_FONT_SIZE = 18
WRAP_MIN_FONT_RATIO = 0.7
BACKGROUND_PROBABILITY = 0.6
MAIN_EFFECT_MIN_MS = 800
MAIN_EFFECT_TARGET_MS = 900
MAIN_EFFECT_MAX_MS = 1000
BLOCK_LAYOUT_MARGIN_FACTOR = 0.65
BLOCK_LAYOUT_MIN_GAP_FACTOR = 0.3

# 模块级上下文变量：用于在 burn_multi_text_effect 中为每行传递正确的 y 坐标
_y_override_ctx = [None]

@contextmanager
def _set_y_override(cy):
    """临时设置 y 坐标覆盖，使 _y_pos 返回指定值"""
    _y_override_ctx[0] = cy
    try:
        yield
    finally:
        _y_override_ctx[0] = None

FONT_MAP = {
    "黑体": "simhei.ttf",
    "宋体": "simsun.ttc",
    "楷体": "simkai.ttf",
    "仿宋": "simfang.ttf",
    "华文楷体": "STKAITI.TTF",
    "华文中宋": "STSONG.TTF",
    "华文细黑": "STXIHEI.TTF",
    "华文宋体": "STZHONGS.TTF",
    "隶书": "SIMLI.TTF",
    "幼圆": "SIMYOU.TTF",
    "新宋体": "mingliub.ttc",
    "微软雅黑": "msyh.ttc",
    "微软雅黑粗体": "msyhbd.ttc",
    "微软雅黑细体": "msyhl.ttc",
    "Arial": "arial.ttf",
}

# ASS 字体名映射（必须用字体文件内部的真实名称）
ASS_FONT_NAME = {
    "simhei.ttf": "SimHei",
    "simsun.ttc": "SimSun",
    "simkai.ttf": "KaiTi",
    "simfang.ttf": "FangSong",
    "STKAITI.TTF": "STKaiti",
    "STSONG.TTF": "STSong",
    "STXIHEI.TTF": "STXihei",
    "STZHONGS.TTF": "STZhongsong",
    "SIMLI.TTF": "LiSu",
    "SIMYOU.TTF": "YouYuan",
    "mingliub.ttc": "MingLiU-ExtB",
    "msyh.ttc": "Microsoft YaHei",
    "msyhbd.ttc": "Microsoft YaHei",
    "msyhl.ttc": "Microsoft YaHei",
    "arial.ttf": "Arial",
}


def get_font_path(font_name):
    relative = FONT_MAP.get(font_name, "PingFang.ttc")
    project_path = os.path.join(FONTS_DIR, relative)
    if os.path.exists(project_path):
        return project_path
    return os.path.join(FONTS_DIR, "PingFang.ttc")


def hex_to_ass(hex_color):
    h = hex_color.lstrip('#')
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&"


def format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def format_srt_time(seconds):
    from datetime import timedelta
    time_str = str(timedelta(seconds=seconds))
    if '.' in time_str:
        time_str, ms = time_str.split('.')
        ms = int(ms) * 1000
    else:
        ms = 0
    return f"{time_str},000" if ms == 0 else f"{time_str},{ms:03d}"


# ============ SRT ============

def generate_srt_file(text, video_duration, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("1\n")
        f.write(f"{format_srt_time(0)} --> {format_srt_time(video_duration)}\n")
        f.write(f"{text}\n\n")
    return output_path


def burn_subtitles(video_file, srt_file, font_name='PingFang SC Regular',
                   font_size=12, primary_color='#FFFFFF', outline_color='#000000',
                   outline_width=0, position=2, margin_v=16, shadow=0, spacing=2):
    output_file = generate_temp_filename(video_file, new_directory=WORK_DIR)
    pc = hex_to_ass(primary_color)
    oc = hex_to_ass(outline_color)
    sub_file = srt_file
    fonts_dir = FONTS_DIR
    if platform.system() == "Windows":
        sub_file = sub_file.replace("\\", "/").replace(":", "\\:")
        fonts_dir = fonts_dir.replace("\\", "/").replace(":", "\\:")
    vf = (
        f"subtitles={sub_file}:fontsdir={fonts_dir}:"
        f"force_style='Fontname={font_name},Fontsize={font_size},"
        f"Alignment={position},MarginV={margin_v},MarginL=4,MarginR=4,"
        f"BorderStyle=1,Outline={outline_width},Shadow={shadow},"
        f"PrimaryColour={pc},OutlineColour={oc},Spacing={spacing}'"
    )
    cmd = ['ffmpeg', '-i', video_file, '-vf', vf, '-y', output_file]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_file


# ============ ASS 动画特效 ============

def _ass_header(font_name, font_size, primary_color, outline_color,
                outline_width, bold, video_width, video_height):
    pc = hex_to_ass(primary_color)
    oc = hex_to_ass(outline_color)
    bold_flag = "-1" if bold else "0"
    return f"""[Script Info]
Title: Auto Editor
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{pc},&H000000FF,{oc},&H80000000,{bold_flag},0,0,0,100,100,3,0,1,{outline_width},2,8,120,120,60,1
Style: BoxStyle,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,3,2,0,8,80,80,30,1

Style: BoxStyleWB,{font_name},{font_size},&H00000000,&H000000FF,&H00000000,&H00FFFFFF,-1,0,0,0,100,100,2,0,3,2,0,8,80,80,30,1

Style: BoxStyleYB,{font_name},{font_size},&H0000FFFF,&H000000FF,&H00000000,&H00FFFFFF,-1,0,0,0,100,100,2,0,3,2,0,8,80,80,30,1

Style: RedBoxStyle,{font_name},{font_size},&H000000FF,&H000000FF,&H00000000,&H00FFFFFF,-1,0,0,0,100,100,2,0,3,2,0,8,80,80,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _dial(text, start, end, tags="", an=8, y_override=None):
    s = format_ass_time(start)
    e = format_ass_time(end)
    has_pos = '\\pos(' in tags or '\\move(' in tags
    if not has_pos:
        y = y_override if y_override is not None else _y_pos(an, h=1920)
        tags += f"\\pos({540},{y})"
    return f"Dialogue: 0,{s},{e},Default,,0,0,0,,{{{tags}\\an{an}}}{text}\n"


def _dial_box(text, start, end, tags="", an=8, w=1080, h=1920, y_override=None):
    """使用背景框样式的字幕。如果 tags 中已包含 \\pos 或 \\move 则不再追加 \\pos"""
    s = format_ass_time(start)
    e = format_ass_time(end)
    has_pos = '\\pos(' in tags or '\\move(' in tags
    y = y_override if y_override is not None else _y_pos(an, h)
    pos_tag = "" if has_pos else f"\\pos({w // 2},{y})"
    return f"Dialogue: 0,{s},{e},BoxStyle,,0,0,0,,{{{tags}{pos_tag}\\an8}}{text}\n"


def _dial_red_box(text, start, end, tags="", an=8, w=1080, h=1920, y_override=None):
    """使用红色文字白色背景框样式的字幕。如果 tags 中已包含 \\pos 或 \\move 则不再追加 \\pos"""
    s = format_ass_time(start)
    e = format_ass_time(end)
    has_pos = '\\pos(' in tags or '\\move(' in tags
    y = y_override if y_override is not None else _y_pos(an, h)
    pos_tag = "" if has_pos else f"\\pos({w // 2},{y})"
    return f"Dialogue: 0,{s},{e},RedBoxStyle,,0,0,0,,{{{tags}{pos_tag}\\an8}}{text}\n"


# ============ 10 种专业特效 ============

POSITIONS = [8, 5, 2]  # 上、中、下 轮换


def eff_fade(text, s, e, an, w, h, fs):
    return _dial(text, s, e, f"\\fad(500,400)", an)


def eff_bounce_in(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\move({cx},{h},{cx},{cy},0,350)"
        f"\\fscx80\\fscy80"
        f"\\t(0,120,\\fscx110\\fscy90)"
        f"\\t(120,220,\\fscx95\\fscy105)"
        f"\\t(220,320,\\fscx103\\fscy97)"
        f"\\t(320,400,\\fscx100\\fscy100)"
        f"\\fad(50,300)", an)


def eff_zoom_bounce(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx0\\fscy0"
        f"\\t(0,150,\\fscx115\\fscy115)"
        f"\\t(150,260,\\fscx92\\fscy92)"
        f"\\t(260,350,\\fscx103\\fscy103)"
        f"\\t(350,420,\\fscx100\\fscy100)"
        f"\\fad(0,300)", an)


def eff_slide_left(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\move(-200,{cy},{cx},{cy},0,400)"
        f"\\fad(200,300)"
        f"\\fscx80\\fscy120"
        f"\\t(0,200,\\fscx105\\fscy95)"
        f"\\t(200,350,\\fscx100\\fscy100)", an)


def eff_slide_right(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\move({w + 200},{cy},{cx},{cy},0,400)"
        f"\\fad(200,300)"
        f"\\fscx80\\fscy120"
        f"\\t(0,200,\\fscx105\\fscy95)"
        f"\\t(200,350,\\fscx100\\fscy100)", an)


def eff_shake(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx0\\fscy0"
        f"\\t(0,40,\\fscx115\\fscy115)"
        f"\\t(40,80,\\fscx92\\fscy92\\frz3)"
        f"\\t(80,120,\\fscx110\\fscy110\\frz-2)"
        f"\\t(120,160,\\fscx95\\fscy95\\frz2)"
        f"\\t(160,200,\\fscx105\\fscy105\\frz-1)"
        f"\\t(200,260,\\fscx98\\fscy98\\frz0)"
        f"\\t(260,320,\\fscx100\\fscy100)"
        f"\\fad(0,200)", an)


def eff_neon_glow(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fad(400,300)"
        f"\\bord12\\shad0\\blur8"
        f"\\1c&H00FFFF&\\3c&H00FFFF&"
        f"\\t(0,400,\\bord2\\blur2)"
        f"\\t(0,400,\\1c&H00FFFFFF&)", an)


def eff_pop_color(text, s, e, an, w, h, fs):
    """抖音爆款: 弹入+颜色闪变"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx0\\fscy0"
        f"\\t(0,120,\\fscx115\\fscy115\\1c&H0000FF&)"
        f"\\t(120,250,\\fscx97\\fscy97\\1c&H00FFFF&)"
        f"\\t(250,350,\\fscx103\\fscy103\\1c&H00FFFFFF&)"
        f"\\t(350,420,\\fscx100\\fscy100)"
        f"\\fad(0,250)", an)


def eff_char_reveal(text, s, e, an, w, h, fs):
    """逐字弹出"""
    cx, cy = w // 2, _y_pos(an, h)
    chars = list(text)
    n = len(chars)
    dur = (e - s) * 1000  # ms
    char_time = min(80, dur / max(1, n) * 0.6)
    tags = []
    for i, ch in enumerate(chars):
        t0 = int(i * char_time)
        t1 = t0 + int(char_time)
        tags.append(f"\\t({t0},{t1},\\fscx115\\fscy115)")
        tags.append(f"\\t({t1},{t1 + 60},\\fscx100\\fscy100)")
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx0\\fscy0"
        + "".join(tags[:40])
        + f"\\fad(0,200)", an)


def eff_rotation_in(text, s, e, an, w, h, fs):
    """旋转飞入 (角度 360→90 避免旋转过程文字角冲出视频边界被裁)"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\move({cx},{h + 100},{cx},{cy},0,450)"
        f"\\frz90\\fscx0\\fscy0"
        f"\\t(0,200,\\frz0\\fscx110\\fscy110)"
        f"\\t(200,330,\\fscx95\\fscy95)"
        f"\\t(330,420,\\fscx100\\fscy100)"
        f"\\fad(50,300)", an)


def eff_slide_up(text, s, e, an, w, h, fs):
    """上滑入"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\move({cx},{h},{cx},{cy},0,400)"
        f"\\fad(200,300)"
        f"\\t(0,200,\\fscx110\\fscy90)"
        f"\\t(200,350,\\fscx100\\fscy100)", an)


def eff_slide_down(text, s, e, an, w, h, fs):
    """下滑入"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\move({cx},0,{cx},{cy},0,400)"
        f"\\fad(200,300)"
        f"\\t(0,200,\\fscx110\\fscy90)"
        f"\\t(200,350,\\fscx100\\fscy100)", an)


def eff_scale_up(text, s, e, an, w, h, fs):
    """从小变大"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx10\\fscy10"
        f"\\t(0,400,\\fscx100\\fscy100)"
        f"\\fad(0,300)", an)


def eff_scale_down(text, s, e, an, w, h, fs):
    """从大变小 (起始 1.3 倍而非 2 倍, 避文字角冲出视频边界)"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx130\\fscy130"
        f"\\t(0,400,\\fscx100\\fscy100)"
        f"\\fad(0,300)", an)


def eff_flip_h(text, s, e, an, w, h, fs):
    """水平翻转入"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx0\\fscy100"
        f"\\t(0,200,\\fscx110\\fscy100)"
        f"\\t(200,350,\\fscx95\\fscy100)"
        f"\\t(350,420,\\fscx100\\fscy100)"
        f"\\fad(0,250)", an)


def eff_flip_v(text, s, e, an, w, h, fs):
    """垂直翻转入"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx100\\fscy0"
        f"\\t(0,200,\\fscx100\\fscy110)"
        f"\\t(200,350,\\fscx100\\fscy95)"
        f"\\t(350,420,\\fscx100\\fscy100)"
        f"\\fad(0,250)", an)


def eff_spin_in(text, s, e, an, w, h, fs):
    """旋入(小角度)"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\frz90\\fscx0\\fscy0"
        f"\\t(0,250,\\frz0\\fscx115\\fscy115)"
        f"\\t(250,380,\\fscx95\\fscy95)"
        f"\\t(380,450,\\fscx100\\fscy100)"
        f"\\fad(0,300)", an)


def eff_blur_in(text, s, e, an, w, h, fs):
    """模糊渐清"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\blur10"
        f"\\t(0,500,\\blur0)"
        f"\\fad(500,300)", an)


def eff_bounce_down(text, s, e, an, w, h, fs):
    """从上弹下"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\move({cx},-100,{cx},{cy},0,400)"
        f"\\fscx80\\fscy80"
        f"\\t(0,150,\\fscx105\\fscy110)"
        f"\\t(150,280,\\fscx97\\fscy95)"
        f"\\t(280,380,\\fscx100\\fscy100)"
        f"\\fad(50,300)", an)


def eff_pop(text, s, e, an, w, h, fs):
    """弹出"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx0\\fscy0"
        f"\\t(0,100,\\fscx115\\fscy115)"
        f"\\t(100,200,\\fscx95\\fscy95)"
        f"\\t(200,280,\\fscx103\\fscy103)"
        f"\\t(280,340,\\fscx100\\fscy100)"
        f"\\fad(0,200)", an)


def eff_flip_rotate(text, s, e, an, w, h, fs):
    """翻转旋转"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\frx90\\fscx0\\fscy0"
        f"\\t(0,300,\\frx0\\fscx100\\fscy100)"
        f"\\fad(0,300)", an)


def eff_wipe_left(text, s, e, an, w, h, fs):
    """从右擦除到左"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\clip({w},{cy - 80},{w},{cy + 80})"
        f"\\t(0,500,[\\clip(0,{cy - 80},{w},{cy + 80})])"
        f"\\fad(0,200)", an)


def eff_wipe_right(text, s, e, an, w, h, fs):
    """从左擦除到右"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\clip(0,{cy - 80},0,{cy + 80})"
        f"\\t(0,500,[\\clip(0,{cy - 80},{w},{cy + 80})])"
        f"\\fad(0,200)", an)


def eff_wipe_down(text, s, e, an, w, h, fs):
    """从上擦除到下 (x 用全屏宽, 仅 y 做擦除动画, 避免左右被裁)"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\clip(0,0,{w},0)"
        f"\\t(0,500,[\\clip(0,0,{w},{h})])"
        f"\\fad(0,200)", an)


def eff_wipe_up(text, s, e, an, w, h, fs):
    """从下擦除到上 (x 用全屏宽, 仅 y 做擦除动画, 避免左右被裁)"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\clip(0,{h},{w},{h})"
        f"\\t(0,500,[\\clip(0,0,{w},{h})])"
        f"\\fad(0,200)", an)


def eff_grow_left(text, s, e, an, w, h, fs):
    """从中心向左展开"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\clip({cx},{cy - 80},{cx},{cy + 80})"
        f"\\t(0,400,[\\clip(0,{cy - 80},{w},{cy + 80})])"
        f"\\fad(0,200)", an)


def eff_grow_center(text, s, e, an, w, h, fs):
    """从中心向两边展开"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\clip({cx},{cy - 80},{cx},{cy + 80})"
        f"\\t(0,400,[\\clip(0,{cy - 80},{w},{cy + 80})])"
        f"\\fad(0,200)", an)


def eff_squeeze_h(text, s, e, an, w, h, fs):
    """水平挤压 (起始 1.3 倍而非 3 倍, 避横向冲出视频边界被裁)"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx130\\fscy85"
        f"\\t(0,200,\\fscx95\\fscy105)"
        f"\\t(200,320,\\fscx103\\fscy97)"
        f"\\t(320,400,\\fscx100\\fscy100)"
        f"\\fad(0,250)", an)


def eff_squeeze_v(text, s, e, an, w, h, fs):
    """垂直挤压 (起始 1.3 倍而非 3 倍, 避纵向冲出视频边界被裁)"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx85\\fscy130"
        f"\\t(0,200,\\fscx105\\fscy95)"
        f"\\t(200,320,\\fscx97\\fscy103)"
        f"\\t(320,400,\\fscx100\\fscy100)"
        f"\\fad(0,250)", an)


def eff_glow_pulse(text, s, e, an, w, h, fs):
    """发光脉冲"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\bord8\\blur4"
        f"\\t(0,500,\\bord2\\blur1)"
        f"\\t(500,1000,\\bord8\\blur4)"
        f"\\t(1000,1500,\\bord2\\blur1)"
        f"\\t(1500,2000,\\bord8\\blur4)"
        f"\\fad(300,300)", an)


def eff_color_flash(text, s, e, an, w, h, fs):
    """颜色闪烁"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\1c&H0000FF&"
        f"\\t(0,200,\\1c&H00FFFF&)"
        f"\\t(200,400,\\1c&H0000FF&)"
        f"\\t(400,600,\\1c&H00FFFF&)"
        f"\\t(600,800,\\1c&H00FFFFFF&)"
        f"\\fad(200,300)", an)


def eff_shadow_move(text, s, e, an, w, h, fs):
    """带阴影移动"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\shad20"
        f"\\t(0,400,\\shad2)"
        f"\\fad(300,300)", an)


def eff_rubber_band(text, s, e, an, w, h, fs):
    """橡皮筋效果"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx0\\fscy0"
        f"\\t(0,80,\\fscx160\\fscy60)"
        f"\\t(80,160,\\fscx80\\fscy130)"
        f"\\t(160,240,\\fscx115\\fscy90)"
        f"\\t(240,320,\\fscx95\\fscy105)"
        f"\\t(320,400,\\fscx100\\fscy100)"
        f"\\fad(0,200)", an)


def eff_zoom_rotate(text, s, e, an, w, h, fs):
    """缩放+旋转"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx0\\fscy0\\frz180"
        f"\\t(0,250,\\fscx110\\fscy110\\frz0)"
        f"\\t(250,350,\\fscx95\\fscy95)"
        f"\\t(350,420,\\fscx100\\fscy100)"
        f"\\fad(0,300)", an)


def eff_bounce_rotate(text, s, e, an, w, h, fs):
    """弹跳+旋转"""
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\move({cx},{h},{cx},{cy},0,400)"
        f"\\frz-30\\fscx80\\fscy80"
        f"\\t(0,200,\\frz10\\fscx110\\fscy90)"
        f"\\t(200,320,\\frz-5\\fscx95\\fscy105)"
        f"\\t(320,400,\\frz0\\fscx100\\fscy100)"
        f"\\fad(50,300)", an)


# ============ 背景框特效 (抖音风格) ============
# 注意: 不在 tags 中添加 \pos 标签，由 _dial_box/_dial_red_box 根据 an 自动定位

def eff_box_fade(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e, f"\\fad(300,300)", an, w, h)

def eff_red_box_fade(text, s, e, an, w, h, fs):
    return _dial_red_box(text, s, e, f"\\fad(300,300)", an, w, h)

def eff_box_pop(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx0\\fscy0"
        f"\\t(0,150,\\fscx110\\fscy110)"
        f"\\t(150,250,\\fscx95\\fscy95)"
        f"\\t(250,320,\\fscx100\\fscy100)"
        f"\\fad(0,200)", an, w, h)

def eff_red_box_pop(text, s, e, an, w, h, fs):
    return _dial_red_box(text, s, e,
        f"\\fscx0\\fscy0"
        f"\\t(0,150,\\fscx110\\fscy110)"
        f"\\t(150,250,\\fscx95\\fscy95)"
        f"\\t(250,320,\\fscx100\\fscy100)"
        f"\\fad(0,200)", an, w, h)

def eff_box_slide_up(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_box(text, s, e,
        f"\\move({w // 2},{h},{w // 2},{cy},0,400)\\fad(100,300)", an, w, h)

def eff_red_box_slide_up(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_red_box(text, s, e,
        f"\\move({w // 2},{h},{w // 2},{cy},0,400)\\fad(100,300)", an, w, h)

def eff_box_slide_left(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_box(text, s, e,
        f"\\move(-200,{cy},{w // 2},{cy},0,400)\\fad(100,300)", an, w, h)

def eff_red_box_slide_left(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_red_box(text, s, e,
        f"\\move(-200,{cy},{w // 2},{cy},0,400)\\fad(100,300)", an, w, h)

def eff_box_scale(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx50\\fscy50\\t(0,300,\\fscx100\\fscy100)\\fad(0,200)", an, w, h)

def eff_box_bounce(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_box(text, s, e,
        f"\\move({w // 2},{h},{w // 2},{cy},0,350)"
        f"\\fscx80\\fscy80"
        f"\\t(0,120,\\fscx110\\fscy90)\\t(120,220,\\fscx95\\fscy105)\\t(220,320,\\fscx100\\fscy100)"
        f"\\fad(50,300)", an, w, h)

def eff_box_rotate(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\frz90\\fscx0\\fscy0"
        f"\\t(0,250,\\frz0\\fscx110\\fscy110)\\t(250,380,\\fscx95\\fscy95)\\t(380,450,\\fscx100\\fscy100)"
        f"\\fad(0,300)", an, w, h)

def eff_box_shake(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx0\\fscy0"
        f"\\t(0,40,\\fscx130\\fscy130)\\t(40,80,\\fscx85\\fscy85\\frz5)"
        f"\\t(80,120,\\fscx120\\fscy120\\frz-4)\\t(120,160,\\fscx90\\fscy90\\frz3)"
        f"\\t(160,260,\\fscx100\\fscy100\\frz0)\\fad(0,200)", an, w, h)

def eff_box_slide_down(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_box(text, s, e,
        f"\\move({w // 2},0,{w // 2},{cy},0,400)\\fad(100,300)", an, w, h)

def eff_box_slide_right(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_box(text, s, e,
        f"\\move({w + 200},{cy},{w // 2},{cy},0,400)\\fad(100,300)", an, w, h)

def eff_box_zoom(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx0\\fscy0"
        f"\\t(0,400,\\fscx125\\fscy125)\\t(400,500,\\fscx100\\fscy100)"
        f"\\fad(0,300)", an, w, h)

def eff_box_char_reveal(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e, f"\\fad(0,200)", an, w, h)

def eff_box_flip_h(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx0\\fscy100"
        f"\\t(0,200,\\fscx110\\fscy100)\\t(200,350,\\fscx100\\fscy100)"
        f"\\fad(0,250)", an, w, h)

def eff_box_flip_v(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx100\\fscy0"
        f"\\t(0,200,\\fscx100\\fscy110)\\t(200,350,\\fscx100\\fscy100)"
        f"\\fad(0,250)", an, w, h)

def eff_box_wipe_left(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_box(text, s, e,
        f"\\clip({w},{cy - 80},{w},{cy + 80})"
        f"\\t(0,500,[\\clip(0,{cy - 80},{w},{cy + 80})])\\fad(0,200)", an, w, h)

def eff_box_wipe_right(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_box(text, s, e,
        f"\\clip(0,{cy - 80},0,{cy + 80})"
        f"\\t(0,500,[\\clip(0,{cy - 80},{w},{cy + 80})])\\fad(0,200)", an, w, h)

def eff_box_pop_color(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx0\\fscy0"
        f"\\t(0,120,\\fscx120\\fscy120)\\t(120,250,\\fscx95\\fscy95)"
        f"\\t(250,350,\\fscx105\\fscy105)\\t(350,420,\\fscx100\\fscy100)"
        f"\\fad(0,250)", an, w, h)

def eff_box_blur(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\blur10\\t(0,500,\\blur0)\\fad(500,300)", an, w, h)

def eff_box_color_flash(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e, f"\\fad(200,300)", an, w, h)

def eff_box_shadow(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\shad20\\t(0,400,\\shad2)\\fad(300,300)", an, w, h)

def eff_box_rubber(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx0\\fscy0"
        f"\\t(0,80,\\fscx160\\fscy60)\\t(80,160,\\fscx80\\fscy130)"
        f"\\t(160,240,\\fscx115\\fscy90)\\t(240,320,\\fscx95\\fscy105)"
        f"\\t(320,400,\\fscx100\\fscy100)\\fad(0,200)", an, w, h)

def eff_box_squeeze_h(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx300\\fscy60"
        f"\\t(0,200,\\fscx90\\fscy110)\\t(200,320,\\fscx105\\fscy97)"
        f"\\t(320,400,\\fscx100\\fscy100)\\fad(0,250)", an, w, h)

def eff_box_squeeze_v(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\fscx60\\fscy300"
        f"\\t(0,200,\\fscx110\\fscy90)\\t(200,320,\\fscx97\\fscy105)"
        f"\\t(320,400,\\fscx100\\fscy100)\\fad(0,250)", an, w, h)

def eff_box_grow(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    cx = w // 2
    return _dial_box(text, s, e,
        f"\\clip({cx},{cy - 80},{cx},{cy + 80})"
        f"\\t(0,400,[\\clip(0,{cy - 80},{w},{cy + 80})])\\fad(0,200)", an, w, h)

def eff_box_spin(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\frz90\\fscx0\\fscy0"
        f"\\t(0,250,\\frz0\\fscx115\\fscy115)\\t(250,380,\\fscx95\\fscy95)"
        f"\\t(380,450,\\fscx100\\fscy100)\\fad(0,300)", an, w, h)

def eff_box_glow(text, s, e, an, w, h, fs):
    return _dial_box(text, s, e,
        f"\\bord8\\blur4"
        f"\\t(0,500,\\bord2\\blur1)\\t(500,1000,\\bord8\\blur4)"
        f"\\fad(300,300)", an, w, h)

def eff_box_wipe_up(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    cx = w // 2
    return _dial_box(text, s, e,
        f"\\clip(0,{h},{w},{h})"
        f"\\t(0,500,[\\clip(0,0,{w},{h})])\\fad(0,200)", an, w, h)

def eff_box_wipe_down(text, s, e, an, w, h, fs):
    cx = w // 2
    return _dial_box(text, s, e,
        f"\\clip(0,0,{w},0)"
        f"\\t(0,500,[\\clip(0,0,{w},{h})])\\fad(0,200)", an, w, h)

def eff_box_bounce_rotate(text, s, e, an, w, h, fs):
    cy = _y_pos(an, h)
    return _dial_box(text, s, e,
        f"\\move({w // 2},{h},{w // 2},{cy},0,400)"
        f"\\frz-30\\fscx80\\fscy80"
        f"\\t(0,200,\\frz10\\fscx110\\fscy90)\\t(200,320,\\frz-5\\fscx95\\fscy105)"
        f"\\t(320,400,\\frz0\\fscx100\\fscy100)\\fad(50,300)", an, w, h)


ALL_EFFECTS = [
    eff_fade, eff_bounce_in, eff_zoom_bounce,
    eff_slide_left, eff_slide_right, eff_slide_up, eff_slide_down,
    eff_shake, eff_neon_glow, eff_pop_color,
    eff_char_reveal,  # eff_rotation_in(\frz90) 已移除: 旋转90°纵向冲出\pos点0.5倍字宽→上下裁
    eff_scale_up, eff_scale_down,
    eff_flip_h, eff_flip_v, eff_blur_in,  # eff_spin_in(\frz90) 已移除: 旋转90°纵向冲出\pos点0.5倍字宽→上下裁
    eff_bounce_down, eff_pop,  # eff_flip_rotate(\frx90) 已移除: 绕X轴翻转90°纵向冲出0.5倍字宽
    # 含 \clip 的擦除/grow 特效 (eff_wipe_*/eff_grow_*) 已移除:
    # \t(...,\clip(...)) 嵌套括号在 libass 下 \t 会吃掉内层 \clip 的闭合 ),
    # 方括号 [\clip(...)] 嵌套语法 libass 亦不可靠, 终点矩形残缺 → 文字左右被裁。
    eff_squeeze_h, eff_squeeze_v,
    eff_glow_pulse, eff_color_flash, eff_shadow_move,
    eff_rubber_band,  # eff_zoom_rotate(\frz180)/eff_bounce_rotate(\frz-30+飞入) 已移除: 大旋转纵向冲出
    # 背景框特效 (约50%, 含 \clip 的 eff_box_wipe_*/eff_box_grow + 大旋转 eff_box_rotate/eff_box_spin/eff_box_bounce_rotate 已移除)
    eff_box_fade, eff_box_pop, eff_box_slide_up, eff_box_slide_left, eff_box_scale,
    eff_box_bounce, eff_box_shake, eff_box_slide_down, eff_box_slide_right,
    eff_box_zoom, eff_box_char_reveal, eff_box_flip_h, eff_box_flip_v,
    eff_box_pop_color,
    eff_box_blur, eff_box_color_flash, eff_box_shadow, eff_box_rubber,
    eff_box_squeeze_h, eff_box_squeeze_v,
    eff_box_glow,
    # 红色文字背景框特效
    eff_red_box_fade, eff_red_box_pop, eff_red_box_slide_up, eff_red_box_slide_left,
]

EFFECT_NAMES = {
    "eff_fade": "淡入淡出", "eff_bounce_in": "弹入",
    "eff_zoom_bounce": "缩放弹入", "eff_slide_left": "左滑入",
    "eff_slide_right": "右滑入", "eff_shake": "抖动出现",
    "eff_neon_glow": "霓虹发光", "eff_pop_color": "彩色弹入",
    "eff_char_reveal": "逐字弹出", "eff_rotation_in": "旋转飞入",
}


def _y_pos(an, h):
    """根据对齐方式返回 y 坐标。优先使用上下文覆盖值"""
    if _y_override_ctx[0] is not None:
        return _y_override_ctx[0]
    if an in (7, 8, 9):
        return int(h * 0.12)  # 顶部 12%
    elif an in (4, 5, 6):
        return int(h * 0.45)  # 中部 45%
    else:
        return int(h * 0.82)  # 底部 82%


def _measure_text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _scaled_padding(base_padding, base_font_size, eff_font_size, min_padding):
    if base_font_size <= 0:
        return max(min_padding, base_padding)
    return max(min_padding, int(base_padding * eff_font_size / base_font_size))


def _split_line_evenly(line, max_lines):
    chars = list(line)
    chunk_size = max(1, (len(chars) + max_lines - 1) // max_lines)
    return [
        "".join(chars[i:i + chunk_size]).strip()
        for i in range(0, len(chars), chunk_size)
        if "".join(chars[i:i + chunk_size]).strip()
    ]


def _wrap_line_to_width(line, draw, font, max_pil_width, max_lines=3):
    line = line.strip()
    if not line:
        return []
    if _measure_text_width(draw, line, font) <= max_pil_width:
        return [line]

    wrapped = []
    current = ""
    for ch in line:
        trial = current + ch
        if current and _measure_text_width(draw, trial, font) > max_pil_width:
            wrapped.append(current.rstrip())
            current = ch.lstrip()
        else:
            current = trial
    if current.strip():
        wrapped.append(current.strip())
    if len(wrapped) > max_lines:
        return _split_line_evenly(line, max_lines)
    return wrapped


def _wrap_block_lines_for_box(block_lines, font_path, font_size, max_w, pad_x):
    """把超长行拆成视觉行，保证每行能放进块级背景框。"""
    font = ImageFont.truetype(font_path, font_size)
    draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    max_pil_width = max(
        1,
        (max_w - pad_x * 2)
        / ASS_WIDTH_FACTOR
        / MAX_BLOCK_TEXT_SCALE
        / WRAP_MIN_FONT_RATIO
    )

    visual_lines = []
    for line in block_lines:
        visual_lines.extend(_wrap_line_to_width(line, draw, font, max_pil_width))
    return visual_lines


def eff_block_fade(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\alpha&H28&\\fscx94\\fscy94"
        f"\\t(0,180,\\alpha&H00&\\fscx106\\fscy106)"
        f"\\t(180,320,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_soft_pop(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx96\\fscy96"
        f"\\t(0,120,\\fscx108\\fscy108)"
        f"\\t(120,240,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_pulse(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\t(0,180,\\fscx106\\fscy106)"
        f"\\t(180,360,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_shadow(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\shad4"
        f"\\t(0,180,\\shad2)"
        f"\\fad(0,120)", an)


def eff_block_slide_left(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_x = max(0, cx - int(fs * 1.65))
    return _dial(text, s, e,
        f"\\move({start_x},{cy},{cx},{cy},0,220)"
        f"\\fscx96\\fscy104"
        f"\\t(0,220,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_slide_right(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_x = min(w, cx + int(fs * 1.65))
    return _dial(text, s, e,
        f"\\move({start_x},{cy},{cx},{cy},0,220)"
        f"\\fscx96\\fscy104"
        f"\\t(0,220,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_slide_up(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_y = min(h, cy + int(fs * 1.25))
    return _dial(text, s, e,
        f"\\move({cx},{start_y},{cx},{cy},0,220)"
        f"\\fscx104\\fscy96"
        f"\\t(0,220,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_slide_down(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_y = max(0, cy - int(fs * 1.25))
    return _dial(text, s, e,
        f"\\move({cx},{start_y},{cx},{cy},0,220)"
        f"\\fscx104\\fscy96"
        f"\\t(0,220,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_bounce(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx88\\fscy88"
        f"\\t(0,120,\\fscx112\\fscy112)"
        f"\\t(120,220,\\fscx96\\fscy96)"
        f"\\t(220,320,\\fscx104\\fscy104)"
        f"\\t(320,420,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_shake(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    dx = max(4, int(fs * 0.08))
    return _dial(text, s, e,
        f"\\move({cx - dx},{cy},{cx},{cy},0,180)"
        f"\\t(0,60,\\fscx108\\fscy108)"
        f"\\t(60,120,\\fscx96\\fscy96)"
        f"\\t(120,220,\\fscx104\\fscy104)"
        f"\\t(220,320,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_blur_in(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\blur6"
        f"\\fscx104\\fscy104"
        f"\\t(0,260,\\blur0\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_squeeze(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx120\\fscy88"
        f"\\t(0,140,\\fscx92\\fscy108)"
        f"\\t(140,280,\\fscx106\\fscy96)"
        f"\\t(280,380,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_shadow_sweep(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\shad8"
        f"\\t(0,220,\\shad2\\fscx106\\fscy106)"
        f"\\t(220,360,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_zoom_in(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx72\\fscy72"
        f"\\t(0,180,\\fscx116\\fscy116)"
        f"\\t(180,340,\\fscx98\\fscy98)"
        f"\\t(340,480,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_zoom_out(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx118\\fscy118"
        f"\\t(0,260,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_breath_slow(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\t(0,500,\\fscx107\\fscy107)"
        f"\\t(500,1000,\\fscx100\\fscy100)"
        f"\\t(1000,1500,\\fscx105\\fscy105)"
        f"\\t(1500,2000,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_breath_wide(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\t(0,450,\\fscx112\\fscy96)"
        f"\\t(450,900,\\fscx100\\fscy100)"
        f"\\t(900,1350,\\fscx96\\fscy110)"
        f"\\t(1350,1800,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_glow_in(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\bord8\\blur4"
        f"\\t(0,360,\\bord3\\blur0)"
        f"\\t(900,1300,\\bord6\\blur2)"
        f"\\t(1300,1700,\\bord3\\blur0)"
        f"\\fad(0,120)", an)


def eff_block_glow_pulse(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\bord4\\blur1"
        f"\\t(0,350,\\bord7\\blur3)"
        f"\\t(350,700,\\bord3\\blur0)"
        f"\\t(1000,1400,\\bord6\\blur2)"
        f"\\t(1400,1800,\\bord3\\blur0)"
        f"\\fad(0,120)", an)


def eff_block_float_up(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_y = min(h, cy + int(fs * 1.25))
    return _dial(text, s, e,
        f"\\move({cx},{start_y},{cx},{cy},0,360)"
        f"\\t(800,1300,\\fscx105\\fscy105)"
        f"\\t(1300,1800,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_float_down(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_y = max(0, cy - int(fs * 1.25))
    return _dial(text, s, e,
        f"\\move({cx},{start_y},{cx},{cy},0,360)"
        f"\\t(800,1300,\\fscx105\\fscy105)"
        f"\\t(1300,1800,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_shadow_dance(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\shad10"
        f"\\t(0,300,\\shad2)"
        f"\\t(800,1200,\\shad8\\fscx105\\fscy105)"
        f"\\t(1200,1600,\\shad2\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_soft_blink(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\alpha&H20&"
        f"\\t(0,220,\\alpha&H00&\\fscx108\\fscy108)"
        f"\\t(220,420,\\fscx100\\fscy100)"
        f"\\t(900,1150,\\alpha&H18&)"
        f"\\t(1150,1400,\\alpha&H00&)"
        f"\\fad(0,120)", an)


def eff_block_rubber_safe(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx118\\fscy88"
        f"\\t(0,120,\\fscx92\\fscy112)"
        f"\\t(120,240,\\fscx110\\fscy94)"
        f"\\t(240,360,\\fscx98\\fscy104)"
        f"\\t(360,480,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_blur_pulse(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\blur5"
        f"\\t(0,260,\\blur0)"
        f"\\t(900,1200,\\blur2\\fscx105\\fscy105)"
        f"\\t(1200,1500,\\blur0\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_pop_twice(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx90\\fscy90"
        f"\\t(0,120,\\fscx116\\fscy116)"
        f"\\t(120,260,\\fscx100\\fscy100)"
        f"\\t(850,1000,\\fscx110\\fscy110)"
        f"\\t(1000,1180,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_spark_safe(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\bord6\\blur2\\shad4"
        f"\\t(0,220,\\bord3\\blur0\\shad2)"
        f"\\t(900,1150,\\bord7\\blur3\\shad6)"
        f"\\t(1150,1450,\\bord3\\blur0\\shad2)"
        f"\\fad(0,120)", an)


def eff_block_color_pop(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx82\\fscy82\\1c&H0000FF&"
        f"\\t(0,240,\\fscx118\\fscy118\\1c&H00FFFF&)"
        f"\\t(240,540,\\fscx96\\fscy96\\1c&H00FF00&)"
        f"\\t(540,900,\\fscx100\\fscy100\\1c&H00FFFFFF&)"
        f"\\fad(0,120)", an)


def eff_block_color_flash_safe(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\1c&H0000FF&\\bord5"
        f"\\t(0,220,\\1c&H00FFFF&\\bord8)"
        f"\\t(220,460,\\1c&H00FF00&\\bord4)"
        f"\\t(460,700,\\1c&H00FFFFFF&\\bord6)"
        f"\\t(700,900,\\bord3)"
        f"\\fad(0,120)", an)


def eff_block_flip_h_safe(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx42\\fscy100"
        f"\\t(0,320,\\fscx122\\fscy100)"
        f"\\t(320,620,\\fscx92\\fscy100)"
        f"\\t(620,900,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_flip_v_safe(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\fscx100\\fscy42"
        f"\\t(0,320,\\fscx100\\fscy122)"
        f"\\t(320,620,\\fscx100\\fscy92)"
        f"\\t(620,900,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_letter_spread(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\alpha&H38&\\fsp14\\fscx92\\fscy92"
        f"\\t(0,420,\\alpha&H00&\\fsp2\\fscx108\\fscy108)"
        f"\\t(420,900,\\fsp0\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_focus_spread(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    return _dial(text, s, e,
        f"\\pos({cx},{cy})"
        f"\\blur8\\fsp10"
        f"\\t(0,520,\\blur1\\fsp1\\fscx108\\fscy108)"
        f"\\t(520,900,\\blur0\\fsp0\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_slam_left_safe(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_x = max(0, cx - int(fs * 2.2))
    return _dial(text, s, e,
        f"\\move({start_x},{cy},{cx},{cy},0,360)"
        f"\\fscx70\\fscy125"
        f"\\t(0,360,\\fscx116\\fscy92)"
        f"\\t(360,650,\\fscx96\\fscy106)"
        f"\\t(650,900,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_slam_right_safe(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_x = min(w, cx + int(fs * 2.2))
    return _dial(text, s, e,
        f"\\move({start_x},{cy},{cx},{cy},0,360)"
        f"\\fscx70\\fscy125"
        f"\\t(0,360,\\fscx116\\fscy92)"
        f"\\t(360,650,\\fscx96\\fscy106)"
        f"\\t(650,900,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_drop_big_safe(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_y = max(0, cy - int(fs * 1.8))
    return _dial(text, s, e,
        f"\\move({cx},{start_y},{cx},{cy},0,420)"
        f"\\fscx88\\fscy120"
        f"\\t(0,420,\\fscx108\\fscy92)"
        f"\\t(420,900,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


def eff_block_rise_big_safe(text, s, e, an, w, h, fs):
    cx, cy = w // 2, _y_pos(an, h)
    start_y = min(h, cy + int(fs * 1.8))
    return _dial(text, s, e,
        f"\\move({cx},{start_y},{cx},{cy},0,420)"
        f"\\fscx88\\fscy120"
        f"\\t(0,420,\\fscx108\\fscy92)"
        f"\\t(420,900,\\fscx100\\fscy100)"
        f"\\fad(0,120)", an)


BLOCK_TEXT_EFFECTS = [
    eff_block_fade,
    eff_block_soft_pop,
    eff_block_pulse,
    eff_block_shadow,
    eff_block_slide_left,
    eff_block_slide_right,
    eff_block_slide_up,
    eff_block_slide_down,
    eff_block_bounce,
    eff_block_shake,
    eff_block_blur_in,
    eff_block_squeeze,
    eff_block_shadow_sweep,
    eff_block_zoom_in,
    eff_block_zoom_out,
    eff_block_breath_slow,
    eff_block_breath_wide,
    eff_block_glow_in,
    eff_block_glow_pulse,
    eff_block_float_up,
    eff_block_float_down,
    eff_block_shadow_dance,
    eff_block_soft_blink,
    eff_block_rubber_safe,
    eff_block_blur_pulse,
    eff_block_pop_twice,
    eff_block_spark_safe,
    eff_block_color_pop,
    eff_block_color_flash_safe,
    eff_block_flip_h_safe,
    eff_block_flip_v_safe,
    eff_block_letter_spread,
    eff_block_focus_spread,
    eff_block_slam_left_safe,
    eff_block_slam_right_safe,
    eff_block_drop_big_safe,
    eff_block_rise_big_safe,
]


BLOCK_TEXT_EFFECT_GROUPS = [
    ("motion", [
        eff_block_slide_left,
        eff_block_slide_right,
        eff_block_slide_up,
        eff_block_slide_down,
        eff_block_float_up,
        eff_block_float_down,
        eff_block_shake,
        eff_block_slam_left_safe,
        eff_block_slam_right_safe,
        eff_block_drop_big_safe,
        eff_block_rise_big_safe,
    ]),
    ("scale", [
        eff_block_soft_pop,
        eff_block_pulse,
        eff_block_bounce,
        eff_block_squeeze,
        eff_block_zoom_in,
        eff_block_zoom_out,
        eff_block_breath_slow,
        eff_block_breath_wide,
        eff_block_rubber_safe,
        eff_block_pop_twice,
    ]),
    ("glow_blur", [
        eff_block_blur_in,
        eff_block_glow_in,
        eff_block_glow_pulse,
        eff_block_blur_pulse,
        eff_block_spark_safe,
    ]),
    ("shadow", [
        eff_block_shadow,
        eff_block_shadow_sweep,
        eff_block_shadow_dance,
    ]),
    ("alpha", [
        eff_block_fade,
        eff_block_soft_blink,
    ]),
    ("color", [
        eff_block_color_pop,
        eff_block_color_flash_safe,
    ]),
    ("flip", [
        eff_block_flip_h_safe,
        eff_block_flip_v_safe,
    ]),
    ("reveal", [
        eff_block_letter_spread,
        eff_block_focus_spread,
    ]),
]


def _block_effect_category(effect_fn):
    for category, effects in BLOCK_TEXT_EFFECT_GROUPS:
        if effect_fn in effects:
            return category
    return "other"


def _build_single_block_effect_cycle():
    groups = []
    for category, effects in BLOCK_TEXT_EFFECT_GROUPS:
        pool = [effect for effect in effects if effect in BLOCK_TEXT_EFFECTS]
        if not pool:
            continue
        random.shuffle(pool)
        groups.append([category, pool])

    category_order = list(range(len(groups)))
    random.shuffle(category_order)
    cycle = []
    last_category = None

    while any(pool for _, pool in groups):
        progressed = False
        for group_idx in category_order:
            category, pool = groups[group_idx]
            if not pool or category == last_category:
                continue
            cycle.append(pool.pop())
            last_category = category
            progressed = True
        if progressed:
            continue

        for category, pool in groups:
            if not pool:
                continue
            cycle.append(pool.pop())
            last_category = category
            break

    return cycle


def _make_block_effect_sequence(count):
    sequence = []
    while len(sequence) < count:
        cycle = _build_single_block_effect_cycle()
        if not cycle:
            break
        sequence.extend(cycle)
    return sequence[:count]


def _should_use_block_background():
    return random.random() < BACKGROUND_PROBABILITY


def _effect_tail_tags(block_duration):
    dur_ms = max(800, int(block_duration * 1000))
    if dur_ms <= MAIN_EFFECT_MAX_MS + 300:
        return ""

    t0 = min(dur_ms - 500, max(MAIN_EFFECT_MAX_MS + 200, int(dur_ms * 0.35)))
    t1 = min(dur_ms - 250, max(t0 + 360, int(dur_ms * 0.55)))
    t2 = min(dur_ms - 80, max(t1 + 360, int(dur_ms * 0.82)))
    if t2 <= t1:
        t2 = t1 + 120
    return (
        f"\\t({t0},{t1},\\fscx106\\fscy106)"
        f"\\t({t1},{t2},\\fscx100\\fscy100)"
    )


def _transition_ranges(dialogue):
    import re
    ranges = [
        (int(m.group(1)), int(m.group(2)))
        for m in re.finditer(r"\\t\((\d+),(\d+),", dialogue)
    ]
    for match in re.finditer(r"\\move\(([^)]+)\)", dialogue):
        parts = match.group(1).split(",")
        if len(parts) >= 6:
            try:
                ranges.append((int(float(parts[4])), int(float(parts[5]))))
            except ValueError:
                pass
    return ranges


def _main_effect_end_ms(dialogue):
    ranges = sorted(_transition_ranges(dialogue))
    if not ranges:
        return 0

    cluster_end = 0
    for start, end in ranges:
        if cluster_end == 0:
            if start > 80:
                continue
            cluster_end = end
            continue
        if cluster_end >= MAIN_EFFECT_MIN_MS:
            break
        if start <= cluster_end + 80 and start <= MAIN_EFFECT_TARGET_MS:
            cluster_end = max(cluster_end, end)
            continue
        break
    return cluster_end


def _stretch_block_effect_timing(dialogue):
    import re

    main_end = _main_effect_end_ms(dialogue)
    if main_end == 0 or MAIN_EFFECT_MIN_MS <= main_end <= MAIN_EFFECT_MAX_MS:
        return dialogue

    target = MAIN_EFFECT_TARGET_MS
    scale = target / main_end

    def scale_time(value):
        return str(int(round(int(value) * scale)))

    def replace_transition(match):
        start, end = int(match.group(1)), int(match.group(2))
        if start <= main_end and end <= main_end:
            return f"\\t({scale_time(start)},{scale_time(end)},"
        return match.group(0)

    dialogue = re.sub(r"\\t\((\d+),(\d+),", replace_transition, dialogue)

    def replace_move(match):
        parts = match.group(1).split(",")
        if len(parts) >= 6:
            try:
                t1 = int(float(parts[4]))
                t2 = int(float(parts[5]))
            except ValueError:
                return match.group(0)
            if t1 <= main_end and t2 <= main_end:
                parts[4] = scale_time(t1)
                parts[5] = scale_time(t2)
        return "\\move(" + ",".join(parts) + ")"

    return re.sub(r"\\move\(([^)]+)\)", replace_move, dialogue)


def _extend_block_effect_duration(dialogue, block_duration):
    dialogue = _stretch_block_effect_timing(dialogue)
    tail = _effect_tail_tags(block_duration)
    return dialogue.replace("\\an8", f"{tail}\\an8", 1)


def _apply_block_text_style(dialogue, eff_font_size, text_color_ass):
    return dialogue.replace("{", f"{{\\fs{eff_font_size}\\1c{text_color_ass}", 1)


def _normalize_text_blocks(text_blocks):
    if isinstance(text_blocks, str):
        return [[text_blocks]]

    normalized = []
    for block in text_blocks:
        if isinstance(block, str):
            normalized.append([block])
        else:
            normalized.append(list(block))
    return normalized


def _time_ranges_overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def _block_bounds(cy, bg_h):
    half_h = bg_h / 2
    return cy - half_h, cy + half_h


def _clamp_block_center_y(cy, bg_h, video_height, margin):
    half_h = bg_h / 2
    min_cy = margin + half_h
    max_cy = video_height - margin - half_h
    if min_cy > max_cy:
        return video_height / 2
    return max(min_cy, min(cy, max_cy))


def _background_overlap_amount(cy, bg_h, layout, min_gap):
    top, bottom = _block_bounds(cy, bg_h)
    other_top, other_bottom = _block_bounds(layout["cy"], layout["bg_h"])
    if bottom + min_gap <= other_top or other_bottom + min_gap <= top:
        return 0
    return min(bottom + min_gap, other_bottom + min_gap) - max(top, other_top)


def _resolve_single_block_center(layout, placed_layouts, video_height, margin, min_gap):
    bg_h = layout["bg_h"]
    preferred = layout["preferred_cy"]
    active = [
        other for other in placed_layouts
        if _time_ranges_overlap(layout["start"], layout["end"], other["start"], other["end"])
    ]
    if not active or bg_h <= 0:
        return _clamp_block_center_y(preferred, bg_h, video_height, margin)

    half_h = bg_h / 2
    candidates = [
        preferred,
        margin + half_h,
        video_height - margin - half_h,
    ]
    for other in active:
        other_top, other_bottom = _block_bounds(other["cy"], other["bg_h"])
        candidates.append(other_top - min_gap - half_h)
        candidates.append(other_bottom + min_gap + half_h)

    normalized = []
    for candidate in candidates:
        cy = _clamp_block_center_y(candidate, bg_h, video_height, margin)
        if cy not in normalized:
            normalized.append(cy)

    def score(cy):
        overlap = sum(_background_overlap_amount(cy, bg_h, other, min_gap) for other in active)
        return overlap, abs(cy - preferred)

    return min(normalized, key=score)


def _resolve_block_background_layouts(layouts, video_height, font_size):
    margin = int(font_size * BLOCK_LAYOUT_MARGIN_FACTOR)
    min_gap = int(font_size * BLOCK_LAYOUT_MIN_GAP_FACTOR)
    resolved = [None] * len(layouts)
    placed = []

    indexed_layouts = [(idx, dict(layout)) for idx, layout in enumerate(layouts)]
    indexed_layouts.sort(
        key=lambda item: (
            item[1].get("start", 0),
            item[1].get("pos_idx", 0),
            item[1].get("block_idx", item[0]),
        )
    )

    for original_idx, layout in indexed_layouts:
        cy = _resolve_single_block_center(layout, placed, video_height, margin, min_gap)
        layout["cy"] = int(round(cy))
        layout["top"], layout["bottom"] = _block_bounds(layout["cy"], layout["bg_h"])
        placed.append(layout)
        resolved[original_idx] = layout

    return [layout for layout in resolved if layout is not None]


def _make_block_bg(block_lines, font_path, font_size, line_height, bg_color, pad_x=80, pad_y=32, radius=24, max_w=None):
    """为一块多行文字生成大圆角背景 PNG。返回 (png_path, bg_w, bg_h, eff_font_size)。
    长文字时自动缩字号 eff_font_size 让 ASS 渲染文字宽适配框内可用宽 (max_w - pad_x*2),
    避免文字横向溢出背景框 + 超出视频宽被 ffmpeg 裁左右。
    pad_x/pad_y 加大余量(PIL测量中文字宽比ASS渲染窄 ~30%, 需更大余量避免文字露出框外)。
    max_w: 背景框最大宽度上限(默认视频宽度的98%), 超长文字不溢出屏幕。"""
    dummy = Image.new('RGBA', (1, 1))
    draw = ImageDraw.Draw(dummy)
    clean_lines = [line.strip() for line in block_lines if line.strip()]
    if not clean_lines:
        return None, 0, 0, font_size
    if max_w is None:
        max_w = int(1080 * 0.98)

    min_font_size = min(font_size, max(MIN_BLOCK_FONT_SIZE, int(font_size * 0.28)))
    eff_font_size = min_font_size
    eff_pad_x = _scaled_padding(pad_x, font_size, eff_font_size, 24)

    for candidate_size in range(font_size, min_font_size - 1, -1):
        candidate_font = ImageFont.truetype(font_path, candidate_size)
        candidate_pad_x = _scaled_padding(pad_x, font_size, candidate_size, 24)
        avail_w = max_w - candidate_pad_x * 2
        if avail_w <= 0:
            continue
        max_w_text = max(_measure_text_width(draw, line, candidate_font) for line in clean_lines)
        ass_w_est = int(max_w_text * ASS_WIDTH_FACTOR * MAX_BLOCK_TEXT_SCALE)
        if ass_w_est <= avail_w:
            eff_font_size = candidate_size
            eff_pad_x = candidate_pad_x
            break

    eff_pad_y = _scaled_padding(pad_y, font_size, eff_font_size, 18)
    pil_font_eff = ImageFont.truetype(font_path, eff_font_size)
    max_w_text_eff = max(_measure_text_width(draw, line, pil_font_eff) for line in clean_lines)
    bg_w = int(max_w_text_eff * ASS_WIDTH_FACTOR * MAX_BLOCK_TEXT_SCALE) + eff_pad_x * 2
    line_ratio = line_height / font_size if font_size else 1.0
    eff_line_height = max(int(eff_font_size * line_ratio), eff_font_size)
    bg_h = len(clean_lines) * eff_line_height + eff_pad_y * 2
    if bg_w > max_w:
        bg_w = max_w
    img = Image.new('RGBA', (bg_w, bg_h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, bg_w - 1, bg_h - 1], radius=radius, fill=bg_color
    )
    path = os.path.join(WORK_DIR, f"blockbg_{random.randint(100000, 999999)}.png")
    img.save(path)
    return path, bg_w, bg_h, eff_font_size


def burn_multi_text_effect(video_file, text_blocks, duration,
                           font_name='PingFang SC Regular', font_size=78,
                           font_color='#FFFFFF', outline_color='#000000',
                           outline_width=3, video_width=1080, video_height=1920):
    """
    多块文案烧录: 每块对应一个位置, 块内多行同时显示(中心对称堆叠)。
    块1→位置1(上1), 块2→位置2(上2), 块3→位置3(下1), 块4→位置4(下2),
    块5起在位置2/3间轮换(替换旧块内容)。位置1/4固定不换。
    每块 60% 概率使用大圆角背景框(Pillow PNG + overlay), 40% 概率纯文字。
    块内各行随机安全文字特效(ASS), 并注入长尾动画避免特效过快消失。
    text_blocks: [[块1行1,块1行2,...], [块2行1,...], ...]
    """
    if not text_blocks:
        return video_file
    text_blocks = _normalize_text_blocks(text_blocks)

    # 准备字体: 中文键→文件名→ASS内部名
    font_file_name = FONT_MAP.get(font_name, "simhei.ttf")
    font_path = os.path.join(FONTS_DIR, font_file_name)
    if not os.path.exists(font_path):
        font_path = os.path.join(FONTS_DIR, "simhei.ttf")
        font_file_name = "simhei.ttf"
    ass_font_name = ASS_FONT_NAME.get(font_file_name, "SimHei")

    # 4个位置槽位 y 坐标
    POSITIONS_Y = [
        int(video_height * 0.15),   # 上1: 15%
        int(video_height * 0.35),   # 上2: 35%
        int(video_height * 0.65),   # 下1: 65%
        int(video_height * 0.85),   # 下2: 85%
    ]

    # 块→位置映射
    def block_pos(b_idx):
        if b_idx < 4:
            return b_idx
        return 1 + (b_idx - 4) % 2  # 5→位置1(上2), 6→位置2(下1), 7→位置1, 8→位置2...

    n_blocks = len(text_blocks)
    # 每块占一个时间槽, 依次出现。时间槽数 = 块数
    slot_dur = duration / max(n_blocks, 1)
    # 行间距用 1.0 倍字号 (而非 1.2), 收紧堆叠跨度避免多行时行0 冲出视频顶/行N 冲底
    line_height = int(font_size * 1.0)

    # 预计算每个位置的块序列: pos_blocks[pos_idx] = [块号列表]
    pos_blocks = {}
    for b_idx in range(n_blocks):
        p = block_pos(b_idx)
        pos_blocks.setdefault(p, []).append(b_idx)

    # 有背景时使用绑定配色: 黑字白底 / 红字白底 / 白字黑底。
    BG_COLOR_COMBOS = [
        ("&H00202020&", (255, 255, 255, 235)),   # 黑字白底
        ("&H000000FF&", (255, 255, 255, 235)),   # 红字白底 (FF0000 BGR->&H000000FF&)
        ("&H00FFFFFF&", (20, 20, 20, 220)),      # 白字黑底
    ]
    PURE_TEXT_COLORS = [
        "&H00FFFFFF&",  # 白字黑描边
        "&H000000FF&",  # 红字黑描边
        "&H0000FFFF&",  # 黄字黑描边
    ]

    events = ""
    bg_overlays = []  # [(png_path, x, y, start, end), ...]
    bg_pngs = []  # 待清理
    placed_layouts = []
    effect_sequence = _make_block_effect_sequence(len(BLOCK_TEXT_EFFECTS))
    effect_idx = 0

    for b_idx, block in enumerate(text_blocks):
        raw_lines = [l.strip() for l in block if l.strip()]
        max_bg_w = int(video_width * 0.98)
        bg_pad_x = int(font_size * 1.4)
        bg_pad_y = int(font_size * 0.75)
        clean_lines = _wrap_block_lines_for_box(raw_lines, font_path, font_size, max_bg_w, bg_pad_x)
        if not clean_lines:
            continue
        pos_idx = block_pos(b_idx)
        cy = POSITIONS_Y[pos_idx]

        # 时间窗口: 每块从自己的时间槽开始
        start = b_idx * slot_dur
        # 结束时间 = 下一个进同一位置的块的开始时间; 没有后续则到视频结束
        blocks_at_pos = pos_blocks[pos_idx]
        my_pos_order = blocks_at_pos.index(b_idx)
        if my_pos_order < len(blocks_at_pos) - 1:
            end = blocks_at_pos[my_pos_order + 1] * slot_dur
        else:
            end = duration

        use_background = _should_use_block_background()
        if use_background:
            text_color_ass, bg_color = random.choice(BG_COLOR_COMBOS)
        else:
            text_color_ass = random.choice(PURE_TEXT_COLORS)
            bg_color = (0, 0, 0, 0)

        # 生成块级布局。60% 概率贴圆角背景，40% 只保留文字特效。
        bg_path, bg_w, bg_h, eff_font_size = _make_block_bg(
            clean_lines, font_path, font_size, line_height, bg_color,
            pad_x=bg_pad_x, pad_y=bg_pad_y,
            max_w=max_bg_w
        )
        if bg_path:
            bg_pngs.append(bg_path)
            layout = {
                "block_idx": b_idx,
                "pos_idx": pos_idx,
                "preferred_cy": cy,
                "bg_h": bg_h,
                "start": start,
                "end": end,
            }
            margin = int(font_size * BLOCK_LAYOUT_MARGIN_FACTOR)
            min_gap = int(font_size * BLOCK_LAYOUT_MIN_GAP_FACTOR)
            safe_cy = _resolve_single_block_center(
                layout, placed_layouts, video_height, margin, min_gap
            )
            layout["cy"] = int(round(safe_cy))
            layout["top"], layout["bottom"] = _block_bounds(layout["cy"], bg_h)
            placed_layouts.append(layout)
            bg_x = (video_width - bg_w) // 2
            bg_y = int(safe_cy - bg_h // 2)
            if use_background:
                bg_overlays.append((bg_path, bg_x, bg_y, start, end))
        else:
            safe_cy = cy
            eff_font_size = font_size

        # 块内多行文字 (无框特效, 中心对称堆叠, 用 safe_cy 避免超界)
        # 用缩后的字号 eff_font_size 渲染文字 + 算行堆叠, 长文字不超框
        eff_line_height = int(eff_font_size * 1.0)
        n_lines = len(clean_lines)
        for li, text in enumerate(clean_lines):
            line_center_y = safe_cy + (li - (n_lines - 1) / 2) * eff_line_height
            line_y = int(line_center_y - eff_font_size / 2)
            # 二次钳制: 留整字高边距, 预留缩放 scx115 动画溢出
            # 缩放中心在 \pos 点, 缩放后文字角会冲出 \pos 上下整字高, 不留够边距会被 ffmpeg 裁
            line_y = max(int(eff_font_size), min(line_y, video_height - int(eff_font_size * 1.5)))
            if effect_idx >= len(effect_sequence):
                effect_sequence = _make_block_effect_sequence(len(BLOCK_TEXT_EFFECTS))
                effect_idx = 0
            eff_fn = effect_sequence[effect_idx] if effect_sequence else random.choice(BLOCK_TEXT_EFFECTS)
            effect_idx += 1
            # 用 y 上下文让特效内部 cy=_y_pos(...) 直接拿到 line_y,
            with _set_y_override(line_y):
                dialogue = eff_fn(text, start, end, 8, video_width, video_height, eff_font_size)
            dialogue = _extend_block_effect_duration(dialogue, end - start)
            dialogue = _inject_y(dialogue, line_y)  # 兜底: 改 \pos/\move 的 y
            # 块时长短时特效飞入淡出动画 (普遍 400-500ms) 占满整个块时长, 文字稳定显示时间几乎为零 → 不显示
            # 块时长 < 2s 时把原 ad(x,y) 改成 ad(100,100) 短淡入淡出, 文字稳定显示时间至少留 0.5s
            block_dur = end - start
            if block_dur < 2.0:
                import re as _re
                dialogue = _re.sub(r'\\fad\([^)]+\)', r'\\fad(0,100)', dialogue)
            # 基础色和字号放在前面，后续颜色/发光动画仍可覆盖它。
            dialogue = _apply_block_text_style(dialogue, eff_font_size, text_color_ass)
            events += dialogue

    if not events.strip():
        return video_file

    # 生成 ASS 文件
    header = _ass_header(ass_font_name, font_size, font_color, outline_color,
                         outline_width, False, video_width, video_height)
    ass_content = header + events
    ass_path = os.path.join(WORK_DIR, f"subs_{random.randint(100000, 999999)}.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    output_file = generate_temp_filename(video_file, new_directory=WORK_DIR)
    cwd = os.getcwd()
    ass_rel = os.path.relpath(ass_path, cwd).replace("\\", "/")
    fonts_rel = os.path.relpath(FONTS_DIR, cwd).replace("\\", "/")

    # 构建 filter_complex: 先 overlay 所有块背景, 再 ass 烧字幕
    inputs = ['-i', video_file]
    for bg_path, _, _, _, _ in bg_overlays:
        inputs.extend(['-i', bg_path])

    fc_parts = []
    prev_label = "[0:v]"
    for idx, (bg_path, x, y, start, end) in enumerate(bg_overlays):
        in_idx = idx + 1
        out_label = f"[bg{idx}]"
        # overlay 用 enable 控制时间段显示
        enable = f"between(t\\,{start:.2f}\\,{end:.2f})"
        fc_parts.append(
            f"{prev_label}[{in_idx}:v]overlay={x}:{y}:enable='{enable}'{out_label}"
        )
        prev_label = out_label

    # 末尾接 ass 字幕滤镜
    ass_filter = f"ass={ass_rel}:fontsdir={fonts_rel}"
    fc_parts.append(f"{prev_label}{ass_filter}[vout]")

    filter_complex = ";".join(fc_parts)
    cmd = ['ffmpeg', '-y'] + inputs + [
        '-filter_complex', filter_complex,
        '-map', '[vout]', '-t', str(duration), output_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[WARN] overlay+ass failed: {result.stderr[-400:]}")
        # 回退1: 纯 ass 无背景框
        vf2 = f"ass={ass_rel}:fontsdir={fonts_rel}"
        cmd2 = ['ffmpeg', '-y', '-i', video_file, '-vf', vf2, '-t', str(duration), output_file]
        r2 = subprocess.run(cmd2, capture_output=True, text=True)
        if r2.returncode != 0:
            print(f"[WARN] ass-only fallback failed: {r2.stderr[-300:]}")
            # 回退2: 复制无字幕
            cmd3 = ['ffmpeg', '-y', '-i', video_file, '-t', str(duration), '-c', 'copy', output_file]
            subprocess.run(cmd3, capture_output=True, check=True)

    # 清理临时文件必须放在 fallback 之后，否则 ass-only fallback 会找不到 ASS 文件。
    for p in bg_pngs + [ass_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    return output_file


def _inject_y(dialogue, target_y):
    """把 ASS Dialogue 行里 \\pos / \\move / \\clip 的 y 坐标替换为 target_y。
    \\pos: 直接用 target_y (静态定位)。
    \\move: 只改终点 y2, 起点 y1 保持相对偏移 (保留从屏幕外飞入的动画方向和距离)。
    \\clip: 矩形 (x1,y1,x2,y2) 的 y1/y2 都按相对终点的偏移平移 (保留擦除动画方向)。
    x 坐标保持不变(slide 类动画需要 x 变化)。
    否则含 \\clip 的特效 (eff_wipe_*/eff_grow_*) 的剪裁矩形会停在生成时的默认 y,
    多行场景每行 line_y 不同但 clip 矩形全停在一处 → 文字被裁出可见区外 → 文字不出现。"""
    import re

    def replace_pos(m):
        coords = m.group(1).split(',')
        if len(coords) >= 2:
            coords[1] = str(target_y)
        return '\\pos(' + ','.join(coords) + ')'

    def replace_move(m):
        coords = m.group(1).split(',')
        # \move(x1,y1,x2,y2[,t1,t2]) y1在2位, y2在4位
        if len(coords) >= 4:
            try:
                y1_orig = float(coords[1])
                y2_orig = float(coords[3])
                # 保持起点相对终点的偏移: y1 = target_y + (y1_orig - y2_orig)
                coords[1] = str(int(target_y + (y1_orig - y2_orig)))
                coords[3] = str(target_y)
            except ValueError:
                coords[3] = str(target_y)
        return '\\move(' + ','.join(coords) + ')'

    def replace_clip(m):
        # 已停用: 含 \clip 的特效在生成时通过 _set_y_override 上下文拿到对的 y,
        # 此处再用相对偏移平移会 double-shift 导致剪裁矩形错位、文字被裁出可见区。
        # 函数定义保留以备后用, 但 _inject_y 不再调用此 re.sub。
        return '\\clip(' + m.group(1) + ')'

    dialogue = re.sub(r'\\pos\(([^)]+)\)', replace_pos, dialogue)
    dialogue = re.sub(r'\\move\(([^)]+)\)', replace_move, dialogue)
    # 注意: 不在此改 \clip。含 \clip 的特效已在生成时通过 _set_y_override 上下文拿到对的 y,
    # 若此处再用相对偏移平移会 double-shift 导致剪裁矩形错位、文字被裁出可见区。
    return dialogue


def _make_rounded_rect_bg(video_width, video_height, rects, radius=20):
    """
    生成一张透明背景图，上面画多个圆角矩形。
    rects: [(x, y, w, h, color_rgba), ...]
    """
    img = Image.new('RGBA', (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for (x, y, w, h, color) in rects:
        draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=color)
    path = os.path.join(WORK_DIR, f"rounded_bg_{random.randint(100000, 999999)}.png")
    img.save(path)
    return path


def _make_text_bg_image(text, font_path, font_size, bg_color, padding_x=30, padding_y=12, radius=16):
    """为单行文字生成带圆角背景的透明 PNG。返回 (png_path, width, height)。"""
    pil_font = ImageFont.truetype(font_path, font_size)
    dummy = Image.new('RGBA', (1, 1))
    bbox = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=pil_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    img_w = tw + padding_x * 2
    img_h = th + padding_y * 2
    img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, img_w - 1, img_h - 1], radius=radius, fill=bg_color)
    draw.text((padding_x, padding_y), text, font=pil_font, fill=(0, 0, 0, 255))
    path = os.path.join(WORK_DIR, f"txtbg_{random.randint(100000, 999999)}.png")
    img.save(path)
    return path, img_w, img_h


def _burn_with_drawtext(video_file, text_lines, duration, font_path,
                        font_size, video_width, video_height):
    """drawtext 方案：每行文字带白色背景框"""
    output_file = generate_temp_filename(video_file, new_directory=WORK_DIR)
    font_path_esc = font_path.replace("\\", "/").replace(":", chr(92)+":")

    n = len([l for l in text_lines if l.strip()])

    POSITIONS_Y = [
        int(video_height * 0.10),
        int(video_height * 0.37),
        int(video_height * 0.63),
        int(video_height * 0.90),
    ]

    filter_parts = []
    for i, line in enumerate(text_lines):
        if not line.strip():
            continue
        text = line.strip()
        safe = text.replace("'", "'\\''").replace(":", "\\:")

        # 位置
        if i < 4:
            pos_idx = i
        else:
            pos_idx = 1 + ((i - 4) % 2)
        cy = POSITIONS_Y[pos_idx]

        # 时间
        start = i * (duration / max(n, 1))
        end = duration
        if i < 4 and pos_idx in (1, 2):
            for j in range(4, n):
                if 1 + ((j - 4) % 2) == pos_idx:
                    end = j * (duration / max(n, 1))
                    break
        elif i >= 4:
            end = start + (duration / max(n, 1))

        # 颜色：随机 白字黑底 / 红字白底
        if random.random() < 0.5:
            text_color = "white"
            box_color = "black@0.9"
        else:
            text_color = "red"
            box_color = "white@0.95"

        # 字号
        if i == 0:
            line_fs = font_size + random.randint(0, 10)
        elif i < 4:
            line_fs = font_size + random.randint(-5, 5)
        else:
            line_fs = font_size + random.randint(-8, 0)

        filter_parts.append(
            f"drawtext=text='{safe}':fontfile='{font_path_esc}':"
            f"fontsize={line_fs}:fontcolor={text_color}:"
            f"box=1:boxcolor={box_color}:boxborderw=15:"
            f"x=(w-tw)/2:y={cy - line_fs // 2}:"
            f"enable='between(t,{start:.2f},{end:.2f})'"
        )

    if filter_parts:
        vf = ",".join(filter_parts)
        cmd = ['ffmpeg', '-i', video_file, '-vf', vf, '-y', output_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[WARN] drawtext failed: {result.stderr[-300:]}")
            # 最简回退
            simple = []
            for i, line in enumerate(text_lines):
                if not line.strip():
                    continue
                safe = line.strip().replace("'", "'\\''").replace(":", "\\:")
                simple.append(
                    f"drawtext=text='{safe}':fontfile='{font_path_esc}':"
                    f"fontsize={font_size}:fontcolor=black:"
                    f"box=1:boxcolor=white:boxborderw=10:"
                    f"x=(w-tw)/2:y={video_height * (0.2 + i * 0.2)}:"
                    f"enable='between(t,{i * duration / max(n,1):.2f},{duration:.2f})'"
                )
            if simple:
                cmd2 = ['ffmpeg', '-i', video_file, '-vf', ','.join(simple), '-y', output_file]
                subprocess.run(cmd2, capture_output=True, check=True)
    else:
        cmd = ['ffmpeg', '-i', video_file, '-c', 'copy', '-y', output_file]
        subprocess.run(cmd, capture_output=True, check=True)

    return output_file


# ============ 单行特效 (兼容旧接口) ============

def burn_text_effect(video_file, text, effect_type, duration,
                     font_name='PingFang SC Regular', font_size=80,
                     font_color='#FFFFFF', outline_color='#000000',
                     outline_width=3, position=8, margin_v=16,
                     enable_box=False, box_color='black@0.6', box_border=15,
                     video_width=1080, video_height=1920):
    return burn_multi_text_effect(
        video_file, [text], duration,
        font_name=font_name, font_size=font_size,
        font_color=font_color, outline_color=outline_color,
        outline_width=outline_width, video_width=video_width,
        video_height=video_height
    )
