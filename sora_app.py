import streamlit as st
import requests
import time
import json
import os
import base64
import asyncio
import io
import math
from PIL import Image # 图片处理核心库
from datetime import datetime
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip

# ================= 配置区域 =================
# API_KEY = "sk-xxx"  <-- 这一行删掉或注释掉
API_KEY = st.secrets["API_KEY"]  # <-- 改成这一行！从后台读取密码
HOST = "https://grsai.dakka.com.cn"

# 智谱 AI 配置 (用于写脚本)
LLM_API_KEY = "f87cd651378147b58a12828ad95465ee.9yUBYWw6o3DIGWKW" 
LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"     
LLM_MODEL = "glm-4-flash"                                 
# ===============================================

st.set_page_config(page_title="Sora 视频工坊 v8.6", layout="wide", page_icon="🎬")

# === 🗣️ 语音库 ===
VOICE_MAP = {
    "English (英语)": "en-US-ChristopherNeural",
    "Chinese (中文)": "zh-CN-YunxiNeural",
    "Malay (马来语)": "ms-MY-OsmanNeural",
    "Indonesian (印尼语)": "id-ID-ArdiNeural",
    "Vietnamese (越南语)": "vi-VN-NamMinhNeural",
    "Thai (泰语)": "th-TH-NiwatNeural",
    "Filipino (菲律宾语)": "fil-PH-AngeloNeural"
}

# === 🛠️ 核心功能 ===

# 1. 🔥🔥🔥 智能拼图引擎 (自动处理 1-9 张图)
def stitch_images_to_base64(uploaded_files):
    if not uploaded_files: return None, None
    try:
        images = [Image.open(f) for f in uploaded_files]
        count = len(images)
        
        # 单张图直接返回
        if count == 1:
            buffered = io.BytesIO()
            images[0].save(buffered, format="PNG")
            return images[0], f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"

        # 多张图：计算网格 (例如 6张 -> 3列x2行)
        cols = math.ceil(math.sqrt(count))
        rows = math.ceil(count / cols)
        
        # 统一把所有图片缩放到 512x512 以便拼接 (保持比例居中)
        cell_size = 512
        grid_w = cols * cell_size
        grid_h = rows * cell_size
        
        # 创建白底大画布
        new_image = Image.new('RGB', (grid_w, grid_h), (255, 255, 255))
        
        for idx, img in enumerate(images):
            # 计算当前格子的位置
            r = idx // cols
            c = idx % cols
            x = c * cell_size
            y = r * cell_size
            
            # 缩放图片适应格子
            img.thumbnail((cell_size, cell_size))
            # 居中粘贴
            paste_x = x + (cell_size - img.width) // 2
            paste_y = y + (cell_size - img.height) // 2
            new_image.paste(img, (paste_x, paste_y))
            
        # 转 Base64
        buffered = io.BytesIO()
        new_image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        return new_image, f"data:image/png;base64,{img_str}"
        
    except Exception as e:
        st.error(f"拼图出错: {e}")
        return None, None

# 2. LLM 写脚本
def generate_timed_script(product_name, target_lang):
    if "xxxx" in LLM_API_KEY:
        return None, "❌ 请配置智谱 API Key"
        
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    system_prompt = (
        "You are a professional video scriptwriter. "
        "Write a concise product narration script strictly for a **15-second video**. "
        "Structure: Hook -> Benefit -> CTA. "
        f"Output must be in {target_lang} ONLY."
    )
    user_prompt = f"Product: {product_name}. Write a 15s sales script in {target_lang}."
    
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.7
    }
    try:
        res = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content'].strip(), None
        else:
            return None, f"API Error: {res.text}"
    except Exception as e:
        return None, str(e)

# 3. TTS 生成
async def generate_tts_audio(text, voice, output_filename):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_filename)

# 4. 音画合成
def merge_video_audio(video_path, audio_path, output_path):
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(audio_path)
        final_audio = audio_clip
        if audio_clip.duration > video_clip.duration:
            final_audio = audio_clip.subclip(0, video_clip.duration)
        final_clip = video_clip.set_audio(final_audio)
        final_clip.write_videofile(output_path, codec='libx264', audio_codec='aac', logger=None)
        video_clip.close()
        audio_clip.close()
        return True
    except: return False

# 5. API 提交
def check_result(task_id):
    url = f"{HOST}/v1/draw/result"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        return requests.post(url, headers=headers, json={"task_id": task_id}, timeout=30).json()
    except Exception as e:
        return {"error": str(e)}

def submit_video_task(prompt, model, aspect_ratio, duration, size, img_data=None):
    url = f"{HOST}/v1/video/sora-video"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt, "model": model, "aspect_ratio": aspect_ratio, "duration": duration, "size": size, "expand_prompt": True
    }
    if img_data: payload["url"] = img_data
    try:
        return requests.post(url, headers=headers, json=payload, timeout=60).json()
    except Exception as e:
        return {"error": str(e), "data": None}

# === 侧边栏 ===
with st.sidebar:
    st.markdown("### 📜 历史记录")
    st.info("💡 **v8.6 新特性**：支持多图自动拼贴，一次性让 AI 看清产品 6 个角度！")

# === 主界面 ===
st.markdown("## 🏭 Sora 视频工坊 <span style='font-size:0.8rem; color:red'>v8.6 (终极融合版)</span>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 1.5])

# --- 左侧：设置 ---
with col1:
    st.subheader("1. 基础设置")
    target_lang_label = st.selectbox("目标语言", list(VOICE_MAP.keys()))
    voice_code = VOICE_MAP[target_lang_label]
    lang_name = target_lang_label.split("(")[0].strip()
    
    product_name = st.text_input("产品名称", placeholder="例如：美白牙膏")

    st.markdown("---")
    st.subheader("2. 视觉与听觉")
    
    # 视觉指令
    visual_script = st.text_area(
        "🎥 视觉脚本 (Visual)", 
        placeholder="例如：赛博朋克风格，特写镜头展示产品细节...",
        height=100
    )

    # 口播文案
    c_gen, c_txt = st.columns([1, 3])
    with c_gen:
        if st.button("✨ 自动写稿", use_container_width=True):
            if not product_name:
                st.error("缺产品名")
            else:
                with st.spinner("生成中..."):
                    script, err = generate_timed_script(product_name, lang_name)
                    if script:
                        st.session_state['gen_script_15s'] = script
                        st.success("已生成")
                    else:
                        st.error(err)
    with c_txt:
        voice_text = st.text_area("🗣️ 口播文案 (Audio)", value=st.session_state.get('gen_script_15s', ""), height=100)
    
    st.markdown("---")
    st.subheader("3. 多图上传 (自动拼图)")
    
    # 🔥 核心：支持多选
    uploaded_files = st.file_uploader("拖入多张产品图 (最多9张)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    
    # 🔥 预览拼图效果
    stitched_preview = None
    final_base64 = None
    if uploaded_files:
        with st.spinner("正在智能拼图..."):
            stitched_preview, final_base64 = stitch_images_to_base64(uploaded_files)
        if stitched_preview:
            st.image(stitched_preview, caption=f"🧩 已将 {len(uploaded_files)} 张图拼合成一张参考图", use_column_width=True)

    # 参数
    c1, c2 = st.columns(2)
    with c1: batch_ratio = st.selectbox("比例", ["16:9", "9:16", "1:1"])
    with c2: size_label = st.selectbox("画质", ["高清 (Large)", "标准 (Small)"])
    batch_size = "large" if "高清" in size_label else "small"

    start_btn = st.button("🚀 开拍 (音画合一)", type="primary", use_container_width=True, disabled=len(uploaded_files)==0)

# --- 右侧：监视器 ---
with col2:
    st.subheader("🎬 导演监视器")
    
    if start_btn:
        if not visual_script or not voice_text:
            st.error("请完善脚本信息！")
        else:
            final_prompt = (
                f"Target Language: {lang_name}.\n\n"
                f"## PART 1: VISUAL DIRECTIVES\n"
                f"Subject: {product_name}.\n"
                f"Visual Style: {visual_script}.\n"
                f"Reference Image: The provided image is a GRID showing multiple angles of the product. Please maintain consistency with these views.\n\n"
                f"## PART 2: AUDIO CONTEXT\n"
                f"Narrative Script: '{voice_text}'.\n"
                f"Requirement: Characters must appear to be speaking {lang_name}."
            )
            
            with st.status("正在制片中...", expanded=True) as status:
                status.write("🧩 拼图参考已上传...")
                
                # 1. 视频
                status.write("🎥 Sora 正在渲染画面...")
                res = submit_video_task(final_prompt, "sora-2", batch_ratio, 15, batch_size, final_base64)
                task_id = res.get("data", {}).get("task_id") or res.get("task_id")
                
                if task_id:
                    video_url = None
                    bar = status.progress(0)
                    for i in range(60):
                        time.sleep(3)
                        check = check_result(task_id)
                        s = check.get("data", {}).get("status")
                        bar.progress(min(i*2+10, 90))
                        if s in ["SUCCESS", "COMPLETED", "succeeded"]:
                            d = check.get("data", {})
                            if d.get("results"): video_url = d["results"][0].get("url")
                            if not video_url: video_url = d.get("url")
                            break
                        elif s in ["FAILED", "failed"]:
                            st.error("视频生成失败")
                            st.stop()
                    
                    # 2. 音频
                    if video_url:
                        status.write("🗣️ 录制口播中...")
                        os.makedirs("temp", exist_ok=True)
                        audio_path = f"temp/{task_id}.mp3"
                        video_path = f"temp/{task_id}.mp4"
                        final_path = f"temp/{task_id}_final.mp4"
                        
                        try:
                            asyncio.run(generate_tts_audio(voice_text, voice_code, audio_path))
                            with open(video_path, 'wb') as f:
                                f.write(requests.get(video_url).content)
                            
                            status.write("🎞️ 剪辑合成中...")
                            if merge_video_audio(video_path, audio_path, final_path):
                                status.update(label="✅ 出片成功！", state="complete")
                                st.success("🎉 您的产品大片已完成！")
                                st.video(final_path)
                                with open(final_path, "rb") as f:
                                    st.download_button("⬇️ 下载原片", f, file_name=f"Product_Ad_{task_id}.mp4")
                            else:
                                st.error("合成失败")
                        except Exception as e:
                            st.error(f"处理错误: {e}")
                else:
                    st.error(f"提交失败: {res}")

    elif st.session_state.get('view_mode') == 'history_video':
        rec = st.session_state['current_record']
        st.info(f"回看：{rec.get('product')}")
        st.video(rec.get('video_url'))

    else:
        st.markdown("""
        <div style='background:#f0f2f6; padding:20px; border-radius:10px; color:gray; text-align:center'>
            👋 请拖入产品多角度图片，开始生成
        </div>
        """, unsafe_allow_html=True)
