import os
import requests
from moviepy.editor import VideoFileClip, AudioFileClip
import edge_tts
import asyncio

# 创建文件夹存放临时文件和成品
TEMP_DIR = "temp_files"
OUTPUT_DIR = "output_videos"
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 语言对应的配音员 (Edge-TTS)
VOICE_MAP = {
    "中文": "zh-CN-XiaoxiaoNeural", # 知性女声
    "英语": "en-US-JennyNeural",    # 美式女声
    "日语": "ja-JP-NanamiNeural"    # 日语女声
}

async def generate_tts_audio(text, language, output_path):
    """使用 Edge-TTS 生成配音文件"""
    voice = VOICE_MAP.get(language, "en-US-JennyNeural")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def download_file(url, save_path):
    """下载文件到本地"""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def create_final_video(video_url, tts_text, language, task_id):
    """主函数：下载视频 -> 生成音频 -> 合成视频"""
    
    # 1. 定义路径
    video_path = os.path.join(TEMP_DIR, f"{task_id}_video.mp4")
    audio_path = os.path.join(TEMP_DIR, f"{task_id}_audio.mp3")
    final_output_path = os.path.join(OUTPUT_DIR, f"FINAL_{task_id}.mp4")
    
    print(f"开始处理任务 {task_id}...")

    # 2. 下载 Sora 视频
    print("正在下载 Sora 原片...")
    download_file(video_url, video_path)
    
    # 3. 生成 TTS 配音
    print(f"正在生成配音 ({language})...")
    #由于 edge-tts 是异步的，这里需要用 asyncio.run 来运行
    asyncio.run(generate_tts_audio(tts_text, language, audio_path))
    
    # 4. 合成视频与音频 (使用 MoviePy)
    print("正在合成最终视频...")
    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_path)
    
    # 设置视频长度与音频一致 (或保持原视频长度，配音循环/截断)
    # 这里采用简单策略：视频长度保持不变，配音如果短就播一次，长了就截断
    final_audio = audio_clip.set_duration(min(video_clip.duration, audio_clip.duration))
    final_video = video_clip.set_audio(final_audio)
    
    # 导出最终文件
    # preset='ultrafast' 加快合成速度，crf=23 保持较高画质
    final_video.write_videofile(final_output_path, codec='libx264', audio_codec='aac', preset='ultrafast', crf=23, logger=None)
    
    # 5. 清理临时文件 (可选)
    video_clip.close()
    audio_clip.close()
    os.remove(video_path)
    os.remove(audio_path)
    
    print(f"合成完成！输出路径: {final_output_path}")
    return final_output_path