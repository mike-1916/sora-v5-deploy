import streamlit as st
import requests
import time
import json
import os
import base64
import asyncio
from datetime import datetime
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip

# ================= 配置区域 =================
# API_KEY = "sk-xxx"  <-- 这一行删掉或注释掉
API_KEY = st.secrets["API_KEY"]  # <-- 改成这一行！从后台读取密码
HOST = "https://grsai.dakka.com.cn"

# 智谱 AI 配置 (用于精准控时写脚本)
LLM_API_KEY = "f87cd651378147b58a12828ad95465ee.9yUBYWw6o3DIGWKW" 
LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"     
LLM_MODEL = "glm-4-flash"                                 
# ===============================================

st.set_page_config(page_title="Sora 视频工坊 v8.5", layout="wide", page_icon="🎬")

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

# 1. LLM 写脚本 (15秒精准控时版)
def generate_timed_script(product_name, target_lang):
    if "xxxx" in LLM_API_KEY:
        return None, "❌ 请配置智谱 API Key"
        
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 🔥🔥🔥 核心：15秒控时指令
    # 英文语速约 2.5词/秒 -> 15s = 35-40词
    # 东南亚语系通常音节较多，也控制在 40词左右比较安全
    system_prompt = (
        "You are a professional video scriptwriter. "
        "Write a concise product narration script strictly for a **15-second video**. "
        "Word count limit: 30-40 words (or 60 characters for Asian languages). "
        "Do NOT exceed 15 seconds when read aloud. "
        "Structure: Hook -> Benefit -> CTA. "
        f"Output must be in {target_lang} ONLY."
    )
    user_prompt = f"Product: {product_name}. Write a 15s sales script in {target_lang}."
    
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
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

# 2. 图片转 Base64
def encode_image_to_base64(uploaded_file):
    if uploaded_file is None: return None
    try:
        bytes_data = uploaded_file.getvalue()
        base64_str = base64.b64encode(bytes_data).decode('utf-8')
        return f"data:{uploaded_file.type};base64,{base64_str}"
    except: return None

# 3. TTS 生成
async def generate_tts_audio(text, voice, output_filename):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_filename)

# 4. 音画合成
def merge_video_audio(video_path, audio_path, output_path):
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(audio_path)
        
        # 逻辑：强制对齐。
        # 如果音频比视频短，音频放完后视频继续放（静音）。
        # 如果音频比视频长，强制截断音频（因为视频只有15s）。
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
    st.info("💡 **导演模式**：视觉指令与口播文案已严格分离并同步传送。")

# === 主界面 ===
st.markdown("## 🏭 Sora 视频工坊 <span style='font-size:0.8rem; color:red'>v8.5 (导演·双轨制版)</span>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 1.5])

# --- 左侧：设置 ---
with col1:
    st.subheader("1. 基础设置")
    target_lang_label = st.selectbox("目标语言", list(VOICE_MAP.keys()))
    voice_code = VOICE_MAP[target_lang_label]
    lang_name = target_lang_label.split("(")[0].strip()
    
    product_name = st.text_input("产品名称", placeholder="例如：美白牙膏")

    st.markdown("---")
    st.subheader("2. 视觉与听觉 (双轨输入)")
    
    # 🔥 输入框 A: 视觉指令 (给摄像师)
    visual_script = st.text_area(
        "🎥 视觉脚本/导演指令 (Visual Directives)", 
        placeholder="在这里输入专业的拍摄要求。\n例如：赛博朋克风格，霓虹灯光效，从下往上的仰拍视角，展示产品的高级金属质感。背景要是模糊的城市夜景。",
        height=120,
        help="这些内容会明确告诉 Sora '画面怎么拍'，不涉及声音。"
    )

    # 🔥 输入框 B: 口播文案 (给配音员 + 剧情参考)
    c_gen, c_txt = st.columns([1, 3])
    with c_gen:
        # 智能生成按钮
        if st.button("✨ 自动生成\n15s 文案", use_container_width=True):
            if not product_name:
                st.error("缺产品名")
            else:
                with st.spinner("正在控时生成..."):
                    script, err = generate_timed_script(product_name, lang_name)
                    if script:
                        st.session_state['gen_script_15s'] = script
                        st.success("已生成")
                    else:
                        st.error(err)
    
    with c_txt:
        voice_text = st.text_area(
            "🗣️ 口播文案 (Audio Script)", 
            value=st.session_state.get('gen_script_15s', ""), 
            height=120,
            help="这部分内容会被 TTS 朗读，同时也会告诉 Sora '这时候在说什么'。"
        )
    
    st.markdown("---")
    st.subheader("3. 素材与参数")
    uploaded_files = st.file_uploader("参考图片", type=['png', 'jpg'], accept_multiple_files=True)
    
    # 强制锁定 15s (为了配合文案)
    st.info("⏱️ 视频时长已锁定为 **15s** 以匹配口播节奏。")
    batch_dur = 15 
    
    c1, c2 = st.columns(2)
    with c1: batch_ratio = st.selectbox("比例", ["16:9", "9:16", "1:1"])
    with c2: 
        size_label = st.selectbox("画质", ["高清 (Large)", "标准 (Small)"])
        batch_size = "large" if "高清" in size_label else "small"

    start_btn = st.button("🚀 开拍 (Action!)", type="primary", use_container_width=True)

# --- 右侧：监视器 ---
with col2:
    st.subheader("🎬 导演监视器")
    
    if start_btn:
        if not visual_script or not voice_text:
            st.error("请完整填写【视觉指令】和【口播文案】！")
        else:
            # 🔥🔥🔥 核心升级：结构化 Prompt 注入 🔥🔥🔥
            # 我们用明确的标签把两部分分开喂给 Sora
            final_prompt = (
                f"Target Language: {lang_name}.\n\n"
                f"## PART 1: VISUAL DIRECTIVES (Camera & Lighting)\n"
                f"Subject: {product_name}.\n"
                f"Visual Style & Action: {visual_script}.\n\n"
                f"## PART 2: AUDIO CONTEXT (Narrative Match)\n"
                f"The video content must visually reflect this spoken narration: '{voice_text}'.\n\n"
                f"## REQUIREMENTS\n"
                f"Photorealistic, Cinematic Lighting, Characters must look like they are speaking {lang_name}."
            )
            
            img_base64 = None
            if uploaded_files: img_base64 = encode_image_to_base64(uploaded_files[0])
            
            with st.status("正在制片中...", expanded=True) as status:
                status.write("📝 指令已分层发送给 Sora (视觉层 + 叙事层)")
                
                # 1. 视频
                status.write("🎥 Sora 正在根据视觉脚本拍摄...")
                res = submit_video_task(final_prompt, "sora-2", batch_ratio, batch_dur, batch_size, img_base64)
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
                        status.write("🗣️ 正在录制 15s 口播...")
                        os.makedirs("temp", exist_ok=True)
                        audio_path = f"temp/{task_id}.mp3"
                        video_path = f"temp/{task_id}.mp4"
                        final_path = f"temp/{task_id}_final.mp4"
                        
                        try:
                            asyncio.run(generate_tts_audio(voice_text, voice_code, audio_path))
                            with open(video_path, 'wb') as f:
                                f.write(requests.get(video_url).content)
                            
                            status.write("🎞️ 正在剪辑合成...")
                            if merge_video_audio(video_path, audio_path, final_path):
                                status.update(label="✅ 出片成功！", state="complete")
                                st.success("🎉 15s 广告片制作完成！")
                                st.video(final_path)
                                with open(final_path, "rb") as f:
                                    st.download_button("⬇️ 下载原片", f, file_name=f"Ad_15s_{task_id}.mp4")
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
            👋 导演就位。<br>请填写视觉指令和口播文案。
        </div>
        """, unsafe_allow_html=True)
