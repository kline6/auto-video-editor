import itertools
import os
import random
import subprocess

from services.ffmpeg_utils import get_video_duration, get_video_info
from utils import generate_temp_filename, random_with_system_time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_DIR = os.path.join(BASE_DIR, "work")
OUTPUT_DIR = os.path.join(BASE_DIR, "final")

# 全部可用的 xfade 转场样式
XFADE_TRANSITIONS = [
    'fade', 'dissolve', 'smoothleft', 'smoothright',
    'zoomin', 'circlecrop', 'wipetl', 'wipetr',
    'coverleft', 'coverright', 'revealleft', 'revealright',
    'smoothup', 'smoothdown', 'circleclose', 'circleopen',
    'horzclose', 'horzopen', 'vertclose', 'vertopen',
    'diagbl', 'diagbr', 'diagtl', 'diagtr',
    'pixelize', 'radial', 'hblur',
    'wipebl', 'wipebr', 'revealup', 'revealdown', 'rectcrop',
]


def normalize_video(video_file, target_width, target_height, fps):
    video_duration = get_video_duration(video_file)
    video_width, video_height = get_video_info(video_file)
    output_name = generate_temp_filename(video_file, new_directory=WORK_DIR)

    if video_width / video_height > target_width / target_height:
        vf = f"scale=-1:{target_height}:force_original_aspect_ratio=1,crop={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2"
    else:
        vf = f"scale={target_width}:-1:force_original_aspect_ratio=1,crop={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2"

    command = [
        'ffmpeg', '-i', video_file,
        '-r', str(fps),
        '-an',
        '-vf', vf,
        '-y', output_name
    ]
    subprocess.run(command, capture_output=True, check=True)
    return output_name


def normalize_all_videos(video_files, target_width, target_height, fps):
    return [normalize_video(v, target_width, target_height, fps) for v in video_files]


def gen_xfade_filter(segments, transition_type, transition_value, transition_duration):
    """构建 xfade filter。transition_value 可以是单个字符串或列表(每对片段不同转场)"""
    video_fades = ""
    last_fade_output = "0v"
    video_length = 0

    for i in range(len(segments) - 1):
        video_length += float(segments[i])
        next_fade_output = "v%d%d" % (i, i + 1)
        offset = video_length - float(transition_duration) * (i + 1)
        connector = '[' + next_fade_output + '];' if i < len(segments) - 2 else ""
        end_label = "" if i < len(segments) - 2 else ",format=yuv420p[video];"
        # 支持每对片段使用不同的转场
        tv = transition_value[i] if isinstance(transition_value, list) else transition_value
        video_fades += "[%s][%dv]%s=transition=%s:duration=%f:offset=%f%s%s" % (
            last_fade_output, i + 1, transition_type, tv,
            float(transition_duration), offset, connector, end_label
        )
        last_fade_output = next_fade_output

    return video_fades


def concat_videos_with_transitions(video_files, transition_type=None, transition_value=None,
                                   transition_duration=1.0, target_width=1080, target_height=1920):
    if len(video_files) <= 1:
        return video_files[0] if video_files else None

    durations = [get_video_duration(f) for f in video_files]

    # 自动生成随机转场列表 (每对片段不同)
    n_transitions = len(video_files) - 1
    if transition_value is None:
        transition_value = [random.choice(XFADE_TRANSITIONS) for _ in range(n_transitions)]
    if transition_type is None:
        transition_type = 'xfade'

    settb = ""
    for i in range(len(video_files)):
        settb += "[%d:v]settb=AVTB,scale=w=%d:h=%d:force_original_aspect_ratio=1,pad=%d:%d:(ow-iw)/2:(oh-ih)/2[%dv];" % (
            i, target_width, target_height, target_width, target_height, i
        )

    video_fades = gen_xfade_filter(durations, transition_type, transition_value, transition_duration)
    filter_complex = settb + video_fades

    random_name = str(random_with_system_time())
    output_file = os.path.join(OUTPUT_DIR, "final-" + random_name + ".mp4")

    files_input = []
    for f in video_files:
        files_input.extend(['-i', f])

    ffmpeg_cmd = ['ffmpeg'] + files_input + [
        '-filter_complex', filter_complex,
        '-map', '[video]',
        '-y', output_file
    ]
    subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
    return output_file
