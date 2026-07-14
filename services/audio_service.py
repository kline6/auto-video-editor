import os
import subprocess

from services.ffmpeg_utils import get_audio_duration, get_video_duration
from utils import generate_temp_filename

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_DIR = os.path.join(BASE_DIR, "work")


def get_total_video_duration(video_files, transition_duration):
    total = sum(get_video_duration(f) for f in video_files)
    if len(video_files) > 1:
        total -= transition_duration * (len(video_files) - 1)
    return total


def trim_audio_to_duration(audio_file, target_duration):
    output_file = generate_temp_filename(audio_file, new_directory=WORK_DIR)
    audio_duration = get_audio_duration(audio_file)

    if audio_duration and audio_duration < target_duration:
        pad_dur = int(target_duration - audio_duration) + 2
        command = [
            'ffmpeg', '-i', audio_file,
            '-af', f'apad=pad_dur={pad_dur}',
            '-t', str(target_duration),
            '-y', output_file
        ]
    else:
        command = [
            'ffmpeg', '-i', audio_file,
            '-t', str(target_duration),
            '-y', output_file
        ]

    subprocess.run(command, capture_output=True, check=True)
    return output_file


def overlay_audio_on_video(video_file, audio_file):
    output_file = generate_temp_filename(video_file, new_directory=WORK_DIR)
    command = [
        'ffmpeg',
        '-i', video_file,
        '-i', audio_file,
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-strict', 'experimental',
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-shortest',
        '-y', output_file
    ]
    subprocess.run(command, capture_output=True, check=True)
    return output_file
