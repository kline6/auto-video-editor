import re
import subprocess


def get_video_duration(video_file):
    command = ['ffprobe', '-i', video_file, '-show_entries', 'format=duration']
    result = subprocess.run(command, capture_output=True)
    output = result.stdout.decode('utf-8')
    duration_match = re.search(r'duration=(\d+\.\d+)', output)
    if duration_match:
        return float(duration_match.group(1))
    return None


def get_video_info(video_file):
    command = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_file
    ]
    result = subprocess.run(command, capture_output=True)
    output = result.stdout.decode('utf-8')
    width_height = output.split('\n')
    width = int(width_height[0])
    height = int(width_height[1])
    return width, height


def get_video_fps(video_file):
    command = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=r_frame_rate',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_file
    ]
    result = subprocess.run(command, capture_output=True)
    output = result.stdout.strip().decode('utf-8')
    if '/' in output:
        numerator, denominator = map(int, output.split('/'))
        return float(numerator) / float(denominator)
    return float(output)


def get_audio_duration(audio_file):
    cmd = ['ffmpeg', '-i', audio_file]
    result = subprocess.run(cmd, capture_output=True)
    duration_search = re.search(
        r'Duration: (?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+)\.(?P<milliseconds>\d+)',
        result.stderr.decode('utf-8'))
    if duration_search:
        hours = int(duration_search.group('hours'))
        minutes = int(duration_search.group('minutes'))
        seconds = int(duration_search.group('seconds'))
        return hours * 3600 + minutes * 60 + seconds
    return None
