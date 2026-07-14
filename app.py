import os
import streamlit as st
import shutil
import random
import subprocess

from utils import read_text_file, read_text_blocks, save_uploaded_file
from utils import generate_temp_filename, random_with_system_time

# 导入所需的子模块
from services.video_service import normalize_all_videos, concat_videos_with_transitions
from services.audio_service import trim_audio_to_duration, overlay_audio_on_video
from services.ffmpeg_utils import get_video_duration

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "work")
OUTPUT_DIR = os.path.join(BASE_DIR, "final")

def generate_single_video(video_pool, audio_pool, text_blocks, font_pool,
                          sfx_pool=None,  # 音效池
                          target_width=1080, target_height=1920, fps=30,
                          clip_count=3, target_duration=0,
                          enable_transitions=True, transition_duration=1.0,
                          enable_subtitles=True, text_effect="none",
                          font_name="PingFang SC Regular", font_size=78,
                          primary_color="#FFFFFF", outline_color="#000000",
                          outline_width=3, subtitle_position=8,
                          enable_box=False, box_color="black@0.6",
                          box_border=15, progress_callback=None):
    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    actual_clip_count = min(clip_count, len(video_pool))
    selected_videos = random.sample(video_pool, actual_clip_count)
    selected_audio = random.choice(audio_pool)

    # 随机选择字体
    font_name = random.choice(font_pool) if font_pool else "Microsoft YaHei"

    # 处理音效（按块数算）
    sfx_files = []
    if sfx_pool and text_blocks:
        n_sfx = min(3, len(sfx_pool), len(text_blocks))
        sfx_files = random.sample(sfx_pool, n_sfx) if n_sfx > 0 else []

    if progress_callback:
        progress_callback(f"正在归一化视频 (字体: {font_name})...")

    normalized = normalize_all_videos(selected_videos, target_width, target_height, fps)

    if progress_callback:
        progress_callback("正在拼接视频并添加转场...")

    if enable_transitions and len(normalized) > 1:
        merged = concat_videos_with_transitions(
            normalized, transition_duration=transition_duration,
            target_width=target_width, target_height=target_height
        )
    else:
        merged = normalized[0]

    # 调整视频时长 - 根据设定时长裁剪或循环
    if target_duration > 0:
        if progress_callback:
            progress_callback(f"正在调整视频时长到 {target_duration}秒...")
        # 考虑转场重叠：总时长 = 每个片段时长之和 - 转场重叠时长
        n_transitions = actual_clip_count - 1 if enable_transitions and actual_clip_count > 1 else 0
        total_overlap = n_transitions * transition_duration
        # 每个片段需要的时长 = (目标时长 + 转场重叠) / 片段数
        avg_duration = (target_duration + total_overlap) / actual_clip_count
        # 裁剪每个片段到平均时长
        trimmed_clips = []
        for clip in normalized:
            clip_dur = get_video_duration(clip)
            if clip_dur > avg_duration + 0.5:
                clip = trim_video_duration(clip, avg_duration)
            trimmed_clips.append(clip)
        normalized = trimmed_clips
        # 重新拼接
        if enable_transitions and len(normalized) > 1:
            merged = concat_videos_with_transitions(
                normalized, transition_duration=transition_duration,
                target_width=target_width, target_height=target_height
            )
        else:
            merged = normalized[0]
        total_duration = target_duration
    else:
        total_duration = get_video_duration(merged)

    concat_output = merged

    if progress_callback:
        progress_callback("正在处理音频...")

    trimmed_audio = trim_audio_to_duration(selected_audio, total_duration)
    video_with_audio = overlay_audio_on_video(merged, trimmed_audio)

    if concat_output != video_with_audio and os.path.exists(concat_output):
        os.remove(concat_output)

    final_video = video_with_audio

    # 叠加音效（文案出现时播放）
    if sfx_files and text_blocks:
        if progress_callback:
            progress_callback("正在叠加音效...")
        final_video = overlay_sfx_on_video(final_video, sfx_files, text_blocks, total_duration)

    if enable_subtitles and text_blocks:
        if progress_callback:
            progress_callback("正在添加字幕特效...")
        from services.subtitle_service import burn_multi_text_effect
        video_with_subs = burn_multi_text_effect(
            final_video, text_blocks, total_duration,
            font_name=font_name, font_size=font_size,
            font_color=primary_color, outline_color=outline_color,
            outline_width=outline_width,
            video_width=target_width, video_height=target_height
        )
        if os.path.exists(final_video) and final_video != video_with_audio:
            os.remove(final_video)
        final_video = video_with_subs

    final_name = f"final-{random_with_system_time()}.mp4"
    final_output = os.path.join(OUTPUT_DIR, final_name)
    if os.path.exists(final_video):
        if final_video != final_output:
            shutil.move(final_video, final_output)
        final_video = final_output

    cleanup_work_dir()
    return final_video


def overlay_sfx_on_video(video_file, sfx_files, text_blocks, duration):
    """叠加音效到视频，文案块出现时播放音效"""
    if not sfx_files or not text_blocks:
        return video_file

    n = len(text_blocks)
    seg_dur = duration / n

    # 构建 FFmpeg 音频混合滤镜
    audio_inputs = []
    filter_parts = []

    for i, sfx in enumerate(sfx_files[:3]):  # 最多3个音效
        start_time = i * seg_dur  # 每个音效在对应文案出现时播放
        audio_inputs.extend(['-i', sfx])
        filter_parts.append(f"[{i+1}:a]adelay={int(start_time*1000)}|{int(start_time*1000)}[sfx{i}]")

    if not audio_inputs:
        return video_file

    # 混合所有音频
    mix_inputs = "[0:a]" + "".join(f"[sfx{i}]" for i in range(len(sfx_files[:3])))
    filter_parts.append(f"{mix_inputs}amix=inputs={len(sfx_files[:3])+1}:duration=first[out]")

    filter_complex = ";".join(filter_parts)
    output_file = generate_temp_filename(video_file, new_directory=WORK_DIR)

    cmd = [
        'ffmpeg', '-i', video_file,
    ] + audio_inputs + [
        '-filter_complex', filter_complex,
        '-map', '0:v', '-map', '[out]',
        '-y', output_file
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    if os.path.exists(video_file) and video_file != output_file:
        os.remove(video_file)

    return output_file


def extend_video_duration(video_file, target_duration, width, height):
    current_duration = get_video_duration(video_file)
    if current_duration >= target_duration:
        return video_file
    loop_count = int(target_duration / current_duration) + 1
    output_file = generate_temp_filename(video_file, new_directory=WORK_DIR)
    cmd = [
        'ffmpeg', '-stream_loop', str(loop_count),
        '-i', video_file,
        '-t', str(target_duration),
        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=1,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
        '-an', '-y', output_file
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_file


def trim_video_duration(video_file, target_duration):
    output_file = generate_temp_filename(video_file, new_directory=WORK_DIR)
    cmd = ['ffmpeg', '-i', video_file, '-t', str(target_duration), '-c', 'copy', '-y', output_file]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_file


def cleanup_work_dir():
    if os.path.exists(WORK_DIR):
        for f in os.listdir(WORK_DIR):
            file_path = os.path.join(WORK_DIR, f)
            if os.path.isfile(file_path) and ('.temp' in f or f.endswith('.srt')):
                os.remove(file_path)


def generate_batch(video_pool, audio_pool, text_pool, sfx_pool, count, settings, progress_callback=None):
    results = []
    for i in range(count):
        def batch_callback(msg):
            if progress_callback:
                progress_callback(i + 1, count, msg)
        if text_pool:
            selected_txt = random.choice(text_pool)
            text_blocks = read_text_blocks(selected_txt)
        else:
            text_blocks = []
        try:
            path = generate_single_video(
                video_pool=video_pool, audio_pool=audio_pool,
                text_blocks=text_blocks, sfx_pool=sfx_pool,
                **settings, progress_callback=batch_callback
            )
            results.append(path)
        except Exception as e:
            if progress_callback:
                progress_callback(i + 1, count, f"第 {i+1} 个生成失败: {e}")
    return results


LIBRARY_DIR = os.path.join(BASE_DIR, "library")
LIBRARY_VIDEO_DIR = os.path.join(LIBRARY_DIR, "videos")
LIBRARY_AUDIO_DIR = os.path.join(LIBRARY_DIR, "audios")
LIBRARY_SFX_DIR = os.path.join(LIBRARY_DIR, "sfx")  # 音效目录
LIBRARY_TEXT_DIR = os.path.join(LIBRARY_DIR, "texts")

VIDEO_EXTENSIONS = ["mp4", "mov", "avi", "mkv", "webm"]
AUDIO_EXTENSIONS = ["mp3", "wav", "aac", "flac", "ogg"]
SFX_EXTENSIONS = ["mp3", "wav", "aac", "ogg"]  # 音效格式

FADE_OPTIONS = [
    'fade', 'dissolve', 'smoothleft', 'smoothright',
    'zoomin', 'circlecrop', 'wipetl', 'wipetr',
    'coverleft', 'coverright', 'revealleft', 'revealright',
    'smoothup', 'smoothdown', 'circleclose', 'circleopen',
    'horzclose', 'horzopen', 'vertclose', 'vertopen',
    'diagbl', 'diagbr', 'diagtl', 'diagtr',
    'pixelize', 'radial', 'hblur',
    'wipebl', 'wipebr', 'revealup', 'revealdown', 'rectcrop',
]

FADE_LABELS = {
    'fade': '淡入淡出', 'smoothleft': '平滑左移', 'smoothright': '平滑右移',
    'smoothup': '平滑上移', 'smoothdown': '平滑下移',
    'circlecrop': '圆形裁剪', 'rectcrop': '矩形裁剪',
    'circleclose': '圆形关闭', 'circleopen': '圆形打开',
    'horzclose': '水平关闭', 'horzopen': '水平打开',
    'vertclose': '垂直关闭', 'vertopen': '垂直打开',
    'diagbl': '对角线左下', 'diagbr': '对角线右下',
    'diagtl': '对角线左上', 'diagtr': '对角线右上',
    'dissolve': '溶解', 'pixelize': '像素化', 'radial': '径向', 'hblur': '高斯模糊',
    'wipetl': '擦除左上', 'wipetr': '擦除右上',
    'wipebl': '擦除左下', 'wipebr': '擦除右下',
    'zoomin': '缩放进入',
    'coverleft': '覆盖左入', 'coverright': '覆盖右入',
    'revealleft': '揭示左入', 'revealright': '揭示右入',
    'revealup': '揭示上入', 'revealdown': '揭示下入'
}

FONT_OPTIONS = [
    "黑体", "宋体", "楷体", "仿宋", "华文楷体",
    "华文中宋", "华文细黑", "华文宋体",
    "隶书", "幼圆", "新宋体",
    "微软雅黑", "微软雅黑粗体", "微软雅黑细体", "Arial"
]

VIDEO_SIZES = {
    "竖屏 (9:16)": ["1080x1920", "720x1280", "480x960"],
    "横屏 (16:9)": ["1920x1080", "1280x720", "960x540"],
    "方形 (1:1)": ["1080x1080", "720x720", "480x480"]
}


def init_dirs():
    for d in [WORK_DIR, LIBRARY_VIDEO_DIR, LIBRARY_AUDIO_DIR, LIBRARY_SFX_DIR, LIBRARY_TEXT_DIR, OUTPUT_DIR]:
        os.makedirs(d, exist_ok=True)


def get_library_files(directory, extensions):
    files = []
    if os.path.exists(directory):
        for f in sorted(os.listdir(directory)):
            ext = os.path.splitext(f)[1].lower().lstrip('.')
            if ext in extensions:
                files.append(os.path.join(directory, f))
    return files


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


st.set_page_config(page_title="自动剪辑工具", layout="wide")

# 隐藏 Deploy 按钮和右上角菜单
st.markdown("""
    <style>
    #MainMenu {display: none !important;}
    header {display: none !important;}
    .stDeployButton {display: none !important;}
    </style>
    """, unsafe_allow_html=True)

st.markdown("<h1 style='text-align:center;'>自动剪辑工具</h1>", unsafe_allow_html=True)

init_dirs()

# ========== 素材库 ==========
with st.container(border=True):
    st.subheader("素材库")

    tab_video, tab_audio, tab_sfx, tab_text = st.tabs(["视频素材", "背景音乐", "音效", "文案素材"])

    # --- 视频素材库 ---
    with tab_video:
        col_upload, col_list = st.columns([1, 2])

        with col_upload:
            st.markdown("**上传新视频**")
            video_uploads = st.file_uploader(
                "选择视频文件",
                type=VIDEO_EXTENSIONS,
                accept_multiple_files=True,
                key="video_upload",
                label_visibility="collapsed"
            )
            if video_uploads:
                count = 0
                for f in video_uploads:
                    save_path = os.path.join(LIBRARY_VIDEO_DIR, f.name)
                    if not os.path.exists(save_path):
                        save_uploaded_file(f, save_path)
                        count += 1
                if count > 0:
                    st.success(f"已添加 {count} 个视频")
                    st.rerun()

        with col_list:
            library_videos = get_library_files(LIBRARY_VIDEO_DIR, VIDEO_EXTENSIONS)
            if library_videos:
                st.markdown(f"**已有 {len(library_videos)} 个视频**")
                # 分列显示
                cols_per_row = 3
                for row_start in range(0, len(library_videos), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for idx, col in enumerate(cols):
                        file_idx = row_start + idx
                        if file_idx < len(library_videos):
                            filepath = library_videos[file_idx]
                            filename = os.path.basename(filepath)
                            size = format_size(os.path.getsize(filepath))
                            with col:
                                st.caption(f"{filename}\n{size}")
                                if st.button("删除", key=f"del_v_{file_idx}", type="secondary"):
                                    os.remove(filepath)
                                    st.rerun()
            else:
                st.info("暂无视频素材，请上传")

    # --- 音频素材库 ---
    with tab_audio:
        col_upload, col_list = st.columns([1, 2])

        with col_upload:
            st.markdown("**上传新音频**")
            audio_uploads = st.file_uploader(
                "选择音频文件",
                type=AUDIO_EXTENSIONS,
                accept_multiple_files=True,
                key="audio_upload",
                label_visibility="collapsed"
            )
            if audio_uploads:
                count = 0
                for f in audio_uploads:
                    save_path = os.path.join(LIBRARY_AUDIO_DIR, f.name)
                    if not os.path.exists(save_path):
                        save_uploaded_file(f, save_path)
                        count += 1
                if count > 0:
                    st.success(f"已添加 {count} 个音频")
                    st.rerun()

        with col_list:
            library_audios = get_library_files(LIBRARY_AUDIO_DIR, AUDIO_EXTENSIONS)
            if library_audios:
                st.markdown(f"**已有 {len(library_audios)} 个音频**")
                cols_per_row = 3
                for row_start in range(0, len(library_audios), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for idx, col in enumerate(cols):
                        file_idx = row_start + idx
                        if file_idx < len(library_audios):
                            filepath = library_audios[file_idx]
                            filename = os.path.basename(filepath)
                            size = format_size(os.path.getsize(filepath))
                            with col:
                                st.caption(f"{filename}\n{size}")
                                if st.button("删除", key=f"del_a_{file_idx}", type="secondary"):
                                    os.remove(filepath)
                                    st.rerun()
            else:
                st.info("暂无音频素材，请上传")

    # --- 音效素材库 ---
    with tab_sfx:
        col_upload, col_list = st.columns([1, 2])

        with col_upload:
            st.markdown("**上传新音效**")
            sfx_uploads = st.file_uploader(
                "选择音效文件",
                type=SFX_EXTENSIONS,
                accept_multiple_files=True,
                key="sfx_upload",
                label_visibility="collapsed"
            )
            if sfx_uploads:
                count = 0
                for f in sfx_uploads:
                    save_path = os.path.join(LIBRARY_SFX_DIR, f.name)
                    if not os.path.exists(save_path):
                        save_uploaded_file(f, save_path)
                        count += 1
                if count > 0:
                    st.success(f"已添加 {count} 个音效")
                    st.rerun()

        with col_list:
            library_sfx = get_library_files(LIBRARY_SFX_DIR, SFX_EXTENSIONS)
            if library_sfx:
                st.markdown(f"**已有 {len(library_sfx)} 个音效**")
                cols_per_row = 3
                for row_start in range(0, len(library_sfx), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for idx, col in enumerate(cols):
                        file_idx = row_start + idx
                        if file_idx < len(library_sfx):
                            filepath = library_sfx[file_idx]
                            filename = os.path.basename(filepath)
                            size = format_size(os.path.getsize(filepath))
                            with col:
                                st.caption(f"{filename}\n{size}")
                                if st.button("删除", key=f"del_s_{file_idx}", type="secondary"):
                                    os.remove(filepath)
                                    st.rerun()
            else:
                st.info("暂无音效素材，请上传")

    # --- 文案素材库 ---
    with tab_text:
        col_upload, col_list = st.columns([1, 2])

        with col_upload:
            st.markdown("**上传新文案**")
            text_uploads = st.file_uploader(
                "选择txt文件（每行一条文案）",
                type=["txt"],
                accept_multiple_files=True,
                key="text_upload",
                label_visibility="collapsed"
            )
            if text_uploads:
                count = 0
                for f in text_uploads:
                    save_path = os.path.join(LIBRARY_TEXT_DIR, f.name)
                    if not os.path.exists(save_path):
                        save_uploaded_file(f, save_path)
                        count += 1
                if count > 0:
                    st.success(f"已添加 {count} 个文案文件")
                    st.rerun()

        with col_list:
            library_texts = get_library_files(LIBRARY_TEXT_DIR, ["txt"])
            if library_texts:
                st.markdown(f"**已有 {len(library_texts)} 个文案文件**")
                for file_idx, filepath in enumerate(library_texts):
                    filename = os.path.basename(filepath)
                    lines = read_text_file(filepath)
                    with st.expander(f"{filename} ({len(lines)} 条文案)"):
                        for line in lines[:5]:
                            st.text(line)
                        if len(lines) > 5:
                            st.caption(f"... 还有 {len(lines) - 5} 条")
                        if st.button("删除", key=f"del_t_{file_idx}"):
                            os.remove(filepath)
                            st.rerun()
            else:
                st.info("暂无文案素材，请上传")

    # 汇总信息
    library_videos = get_library_files(LIBRARY_VIDEO_DIR, VIDEO_EXTENSIONS)
    library_audios = get_library_files(LIBRARY_AUDIO_DIR, AUDIO_EXTENSIONS)
    library_sfx = get_library_files(LIBRARY_SFX_DIR, SFX_EXTENSIONS)
    library_texts = get_library_files(LIBRARY_TEXT_DIR, ["txt"])

    st.markdown("---")
    info_parts = []
    info_parts.append(f"**{len(library_videos)}** 个视频")
    info_parts.append(f"**{len(library_audios)}** 个背景音乐")
    info_parts.append(f"**{len(library_sfx)}** 个音效")
    info_parts.append(f"**{len(library_texts)}** 个文案文件")
    st.info("素材库汇总:  " + " | ".join(info_parts))

# ========== 参数设置 ==========
with st.container(border=True):
    st.subheader("参数设置")

    row1_col1, row1_col2, row1_col3 = st.columns(3)
    with row1_col1:
        layout = st.selectbox("画面方向", list(VIDEO_SIZES.keys()), key="layout")
    with row1_col2:
        video_size = st.selectbox("视频尺寸", VIDEO_SIZES[layout], key="video_size")
    with row1_col3:
        fps = st.selectbox("帧率 (FPS)", [24, 25, 30], index=2, key="fps")

    row2_col1, row2_col2, row2_col3 = st.columns(3)
    with row2_col1:
        clip_count = st.slider("每个视频使用的片段数", 2, 10, 3, key="clip_count")
    with row2_col2:
        target_duration = st.number_input("目标视频时长 (秒)", min_value=5, max_value=300, value=10, step=5, key="target_duration",
                                          help="设置为0表示自动计算时长")
    with row2_col3:
        st.caption("设置为0则自动按时长")

    st.markdown("---")
    row3_col1, row3_col2, row3_col3 = st.columns(3)
    with row3_col1:
        enable_transitions = st.checkbox("启用转场效果", value=True, key="enable_transitions")
    with row3_col2:
        transition_duration = st.selectbox("转场时长 (秒)", [0.5, 1.0, 1.5, 2.0], index=1, key="transition_duration")
    with row3_col3:
        st.empty()

    # 转场效果展示
    with st.container():
        st.markdown(f"**视频转场** ({len(FADE_OPTIONS)}种，自动随机)")
        tags_html = " ".join([
            f'<span style="background:#e8e8e8;padding:2px 8px;border-radius:4px;margin:2px;font-size:13px;display:inline-block">{FADE_LABELS.get(o, o)}</span>'
            for o in FADE_OPTIONS
        ])
        st.markdown(tags_html, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**字幕设置**")
    row4_col1, row4_col2, row4_col3 = st.columns(3)
    with row4_col1:
        enable_subtitles = st.checkbox("启用字幕", value=True, key="enable_subtitles")
    with row4_col2:
        font_size = st.selectbox("字体大小", [72, 78, 84, 90, 96, 102], index=2, key="font_size")
    with row4_col3:
        st.caption("每个视频随机选一种字体")

    row5_col1, row5_col2, row5_col3, row5_col4 = st.columns(4)
    with row5_col1:
        primary_color = st.color_picker("文字颜色", "#FFFFFF", key="primary_color")
    with row5_col2:
        outline_color = st.color_picker("描边颜色", "#000000", key="outline_color")
    with row5_col3:
        outline_width = st.slider("描边宽度", 0, 8, 4, key="outline_width")
    with row5_col4:
        st.empty()

    # 字幕样式说明（与 burn_multi_text_effect 实际行为一致）
    with st.container():
        st.markdown("**字幕样式**（每段文案自动随机）")
        SUBTITLE_FEATURES = [
            "27种安全长时段特效", "0.8-1秒入场", "60%圆角背景", "40%纯文字",
            "弹跳缩放", "近距离滑入", "呼吸脉冲",
            "模糊进入", "发光描边", "四位置轮换 (上1/上2/下1/下2)"
        ]
        tags_html = " ".join([
            f'<span style="background:#fff3cd;padding:2px 8px;border-radius:4px;margin:2px;font-size:13px;display:inline-block">{n}</span>'
            for n in SUBTITLE_FEATURES
        ])
        st.markdown(tags_html, unsafe_allow_html=True)

    row6_col1 = st.columns(1)[0]
    with row6_col1:
        enable_box = st.checkbox("文字背景框", value=False, key="enable_box")
    box_color = "black@0.6"
    box_border = 15

# ========== 生成 ==========
with st.container(border=True):
    st.subheader("生成视频")

    gen_count = st.slider("生成数量", 1, 20, 1, key="gen_count")

    if st.button("开始生成", type="primary", key="generate_btn"):
        if not library_videos:
            st.toast("素材库中没有视频素材，请先上传", icon="warning")
            st.stop()
        if not library_audios:
            st.toast("素材库中没有音频素材，请先上传", icon="warning")
            st.stop()

        settings = {
            "font_pool": FONT_OPTIONS,
            "target_width": int(video_size.split('x')[0]),
            "target_height": int(video_size.split('x')[1]),
            "fps": fps,
            "clip_count": clip_count,
            "target_duration": target_duration,
            "enable_transitions": enable_transitions,
            "transition_duration": float(transition_duration),
            "enable_subtitles": enable_subtitles,
            "font_size": font_size,
            "primary_color": primary_color,
            "outline_color": outline_color,
            "outline_width": outline_width,
            "enable_box": enable_box,
            "box_color": box_color if enable_box else "black@0.6",
            "box_border": box_border if enable_box else 15,
        }

        with st.status("正在生成视频...", expanded=True) as status:
            def progress_fn(current, total, msg):
                st.write(f"[{current}/{total}] {msg}")

            results = generate_batch(
                video_pool=library_videos,
                audio_pool=library_audios,
                text_pool=library_texts,
                sfx_pool=library_sfx,
                count=gen_count,
                settings=settings,
                progress_callback=progress_fn
            )
            status.update(label=f"已生成 {len(results)} 个视频！", state="complete", expanded=False)

        st.session_state["results"] = results

# ========== 结果 ==========
if "results" in st.session_state and st.session_state["results"]:
    with st.container(border=True):
        st.subheader("生成结果")
        for i, video_path in enumerate(st.session_state["results"]):
            if os.path.exists(video_path):
                col_video, col_download = st.columns([3, 1])
                with col_video:
                    st.video(video_path)
                with col_download:
                    with open(video_path, 'rb') as f:
                        st.download_button(
                            label=f"下载 #{i+1}",
                            data=f.read(),
                            file_name=os.path.basename(video_path),
                            mime="video/mp4",
                            key=f"download_{i}"
                        )
