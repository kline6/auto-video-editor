import os
import random
import subprocess
import time


def generate_temp_filename(original_filepath, new_ext="", new_directory=None):
    directory, filename_with_ext = os.path.split(original_filepath)
    filename, ext = os.path.splitext(filename_with_ext)
    if new_ext:
        new_filename = filename + '.temp' + new_ext
    else:
        new_filename = filename + '.temp' + ext
    if new_directory:
        new_filepath = os.path.join(new_directory, new_filename)
    else:
        new_filepath = os.path.join(directory, new_filename)
    return new_filepath


def random_with_system_time():
    system_time = int(time.time() * 1000)
    return system_time + random.randint(0, 10000)


def run_ffmpeg_command(command):
    result = subprocess.run(command, capture_output=True, check=True, text=True)
    return result


def read_text_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def read_text_blocks(filepath):
    """按 --- 分隔符读取文案块。每个块是多行文字，块内行同时显示在同一位置。
    返回 [[块1行1, 块1行2,...], [块2行1,...], ...]
    无 --- 分隔的文件视为单块(每行一条, 兼容旧格式)。"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if '---' not in content:
        # 兼容旧格式: 每行一块
        return [[line.strip()] for line in content.splitlines() if line.strip()]
    blocks = []
    for chunk in content.split('---'):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if lines:
            blocks.append(lines)
    return blocks


def save_uploaded_file(uploaded_file, save_path):
    with open(save_path, 'wb') as f:
        f.write(uploaded_file.read())
