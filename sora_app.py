import streamlit as st
import requests
import time
import json
import os
import base64
import asyncio
import io
import math
from PIL import Image
from datetime import datetime
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip

# ================= 配置区域 =================
# API_KEY = "sk-xxx"  <-- 这一行删掉或注释掉
API_KEY = st.secrets["API_KEY"]  # <-- 改成这一行！从后台读取密码
HOST = "https://grsai.dakka.com.cn" 

LLM_API_KEY = "f87cd651378147b58a12828ad95465ee.9yUBYWw6o3DIGWKW" 
LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"     
LLM_MODEL = "glm-4-flash"                                 
# ===============================================

st.set_page_config(page_title="Sora 视频工坊 v8.8", layout="wide", page_icon="🛡️")

# === 🛠️ 核心功能 ===

# 1. 拼图
def stitch_images_to_base64(uploaded_files):
    if not uploaded_files: return None, None
    try:
        images = [Image.open(f) for f in uploaded_files]
        count = len(images)
        if count == 1:
            buffered = io.BytesIO()
            images[0].save(buffered, format="PNG")
            return images[0], f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
        
        cols = math.ceil(math.sqrt(count))
        rows = math.ceil(count / cols)
        cell_size = 512
        new_image = Image.new('RGB', (cols * cell_size, rows * cell_size), (255, 255, 255))
        
        for idx, img in enumerate(images):
            r = idx // cols
            c = idx % cols
            img.thumbnail((cell_size, cell_size))
            new_image.paste(img, (c * cell_size + (cell_size - img.width)//2, r * cell_size + (cell_size - img.height)//2))
            
        buffered = io.BytesIO()
        new_image.save(buffered, format="PNG")
        return new_image, f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
    except: return None, None

# 2. 写脚本
def generate_timed_script(product_name, target_lang, duration_sec):
    if "xxxx" in LLM_API_KEY:
        return None, "❌ 请配置智谱 API Key"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    
    length_guide = "Short (20-30 words)" if duration_sec <= 10 else "Standard (40-50 words)"
    system_prompt = f"Write a {duration_sec}s video script in {target_lang}. {length_guide}. Hook->Benefit->CTA."
    user_prompt = f"Product: {product_name}."
    
    try:
        res = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json={
            "model": LLM_MODEL, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": 0.7
        }, timeout=15)
        return res.json()['choices'][0]['message']['content'].strip(), None
    except Exception as e: return None, str(e)

# 3. TTS
async def generate_tts_audio(text, voice, output_filename):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_filename)

# 4. 合成 (增加容错)
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
    except Exception as e:
        print(f"合成报错: {e}") # 打印错误到后台
        return False

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
    payload = {"prompt": prompt, "model": model, "aspect_ratio": aspect_ratio, "duration": duration, "size": size, "expand_prompt": True}
    if img_data: payload["url"] = img_data
    try:
        return requests.post(url, headers=headers, json=payload, timeout=60).json()
    except Exception as e:
        return {"error": str(e), "data": None}

# === 💾 历史记录 ===
HISTORY_FILE = "history.json"
def load_history():
    if not os.path.exists(HISTORY_FILE): return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return []

def save_to_history(record):
    history = load_history()
    if any(h.get('task_id') == record['task_id'] for h in history): return
    history.append(record)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# === 侧边栏 ===
with st.sidebar:
    st.markdown("### 📜 历史记录")
    history_list = load_history()
    if not history_list: st.info("暂无记录")
    else:
        for item in reversed(history_list):
            label = f"🎥 {item.get('time', '')[5:-3]} | {item.get('product')}"
            with st.expander(label):
                if st.button("回看", key=f"btn_{item['task_id']}"):
                    st.session_state['view_mode'] = 'history_video'
                    st.session_state['current_record'] = item

# === 主界面 ===
st.markdown("## 🏭 Sora 视频工坊 <span style='font-size:0.8rem; color:red'>v8.8 (稳健防丢版)</span>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 1.5])

VOICE_MAP = {
    "English (英语)": "en-US-ChristopherNeural",
    "Chinese (中文)": "zh-CN-YunxiNeural",
    "Malay (马来语)": "ms-MY-OsmanNeural",
    "Indonesian (印尼语)": "id-ID-ArdiNeural",
    "Vietnamese (越南语)": "vi-VN-NamMinhNeural",
    "Thai (泰语)": "th-TH-NiwatNeural",
    "Filipino (菲律宾语)": "fil-PH-AngeloNeural"
}

with col1:
    st.subheader("1. 基础设置")
    target_lang_label = st.selectbox("目标语言", list(VOICE_MAP.keys()))
    voice_code = VOICE_MAP[target_lang_label]
    lang_name = target_lang_label.split("(")[0].strip()
    product_name = st.text_input("产品名称", placeholder="例如：美白牙膏")

    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1: batch_dur = int(st.selectbox("时长", ["5s", "10s", "15s"]).replace("s",""))
    with c2: batch_ratio = st.selectbox("比例", ["16:9", "9:16", "1:1"])
    with c3: 
        size_label = st.selectbox("画质", ["高清 (Large)", "标准 (Small)"])
        batch_size = "large" if "高清" in size_label else "small"

    st.markdown("---")
    visual_script = st.text_area("🎥 视觉脚本", placeholder="特写展示...", height=80)
    
    c_gen, c_txt = st.columns([1, 2])
    with c_gen:
        if st.button(f"✨ 生成 {batch_dur}s 文案", use_container_width=True):
            if not product_name: st.error("缺产品名")
            else:
                with st.spinner("生成中..."):
                    script, err = generate_timed_script(product_name, lang_name, batch_dur)
                    if script: st.session_state['gs'] = script; st.success("已生成")
                    else: st.error(err)
    with c_txt:
        voice_text = st.text_area("🗣️ 口播文案", value=st.session_state.get('gs', ""), height=100)
    
    st.markdown("---")
    uploaded_files = st.file_uploader("拖入多张图片", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    stitched_preview, final_base64 = None, None
    if uploaded_files:
        stitched_preview, final_base64 = stitch_images_to_base64(uploaded_files)
        if stitched_preview: st.image(stitched_preview, caption="拼图预览", use_column_width=True)

    start_btn = st.button(f"🚀 生成 {batch_dur}s 视频", type="primary", use_container_width=True, disabled=len(uploaded_files)==0)

with col2:
    st.subheader("🎬 进度监控")
    if start_btn:
        if not visual_script or not voice_text:
            st.error("脚本信息不全")
        else:
            final_prompt = f"Language: {lang_name}. Duration: {batch_dur}s. Visual: {visual_script}. Audio Context: {voice_text}."
            
            with st.status(f"正在制作...", expanded=True) as status:
                status.write("🎥 正在渲染画面...")
                res = submit_video_task(final_prompt, "sora-2", batch_ratio, batch_dur, batch_size, final_base64)
                task_id = res.get("data", {}).get("task_id") or res.get("task_id")
                
                if task_id:
                    video_url = None
                    bar = status.progress(0)
                    for i in range(60):
                        time.sleep(3)
                        check = check_result(task_id)
                        s = check.get("data", {}).get("status")
                        bar.progress(min(i*2+10, 95))
                        if s in ["SUCCESS", "COMPLETED", "succeeded"]:
                            d = check.get("data", {})
                            if d.get("results"): video_url = d["results"][0].get("url")
                            if not video_url: video_url = d.get("url")
                            break
                        elif s in ["FAILED", "failed"]:
                            st.error(f"Sora 生成失败: {check.get('msg')}")
                            st.stop()
                    
                    if video_url:
                        # 🔥🔥🔥 改进点：拿到视频链接后，立即展示，防止后面合成报错导致啥都看不到
                        status.write("✅ 画面生成成功！正在尝试配音合成...")
                        st.info("👇 这是 Sora 生成的原始画面 (无声版)")
                        st.video(video_url) # 先展示无声版保底
                        
                        # 尝试合成音频
                        os.makedirs("temp", exist_ok=True)
                        audio_path = f"temp/{task_id}.mp3"
                        video_path = f"temp/{task_id}.mp4"
                        final_path = f"temp/{task_id}_final.mp4"
                        
                        try:
                            # 下载视频
                            v_data = requests.get(video_url).content
                            with open(video_path, 'wb') as f: f.write(v_data)
                            
                            # 生成音频
                            asyncio.run(generate_tts_audio(voice_text, voice_code, audio_path))
                            
                            # 合成
                            if merge_video_audio(video_path, audio_path, final_path):
                                status.update(label="🎉 完美出片！", state="complete")
                                st.success("✅ 有声合成版已就绪：")
                                st.video(final_path) # 展示有声版
                                
                                with open(final_path, "rb") as f:
                                    st.download_button("⬇️ 下载有声视频", f, file_name=f"Final_{task_id}.mp4")
                            else:
                                status.update(label="⚠️ 合成失败 (显示原片)", state="error")
                                st.warning("音频合成失败 (可能缺少 ffmpeg)，请直接下载上方的【无声原片】。")
                                
                        except Exception as e:
                            status.update(label="⚠️ 处理出错", state="error")
                            st.error(f"合成过程报错: {e}")
                        
                        # 无论如何都保存记录
                        save_to_history({
                            "task_id": task_id, "product": product_name, 
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "video_url": video_url, "script": voice_text
                        })
                    else:
                        st.error("未能获取视频 URL")
                else:
                    st.error(f"提交失败: {res}")

    elif st.session_state.get('view_mode') == 'history_video':
        rec = st.session_state['current_record']
        st.info(f"回看：{rec.get('product')}")
        st.video(rec.get('video_url'))
        st.caption(f"脚本：{rec.get('script')}")

    else:
        st.markdown("<div style='text-align:center; color:gray; padding:20px;'>👋 准备就绪</div>", unsafe_allow_html=True)


