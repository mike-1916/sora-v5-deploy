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
HOST = "https://grsaiapi.com"

# 2. LLM 配置 (这里改成了智谱 AI)
# 去 https://open.bigmodel.cn/ 获取 Key
LLM_API_KEY = "f87cd651378147b58a12828ad95465ee.9yUBYWw6o3DIGWKW" # ⬅️【必填】这里填智谱的 API Key
LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"     # ⬅️ 智谱的接口地址
LLM_MODEL = "glm-4-flash"                                 # ⬅️ 智谱的免费/高速模型
# ===============================================

st.set_page_config(page_title="Sora 视频工坊 v8.2 (智谱版)", layout="wide", page_icon="🌏")

# === 🗣️ 语音库 (支持多国) ===
VOICE_MAP = {
    "English (英语)": "en-US-ChristopherNeural",
    "Chinese (中文)": "zh-CN-YunxiNeural",
    "Malay (马来语)": "ms-MY-OsmanNeural",
    "Indonesian (印尼语)": "id-ID-ArdiNeural",
    "Vietnamese (越南语)": "vi-VN-NamMinhNeural",
    "Thai (泰语)": "th-TH-NiwatNeural",
    "Filipino (菲律宾语)": "fil-PH-AngeloNeural"
}

# === 🛠️ 核心功能函数 ===

# 1. LLM 自动写脚本 (智谱 GLM-4)
def generate_script_by_llm(product_name, target_lang):
    """调用 LLM 根据产品名生成对应语种的口播稿"""
    if "xxxx" in LLM_API_KEY:
        return None, "❌ 请先在代码第21行填入智谱 API Key"
        
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 提示词：让 AI 扮演带货主播
    system_prompt = f"You are a professional e-commerce copywriter. Write a short, energetic video script (15-20 words) for a product video. The output must be in {target_lang} ONLY. Do not include translations or explanations."
    user_prompt = f"Product: {product_name}. Write a sales script in {target_lang}."
    
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7
    }
    
    try:
        res = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content'].strip(), None
        else:
            return None, f"智谱API报错: {res.text}"
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

# 3. 生成配音
async def generate_tts_audio(text, voice, output_filename):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_filename)

# 4. 音画合成
def merge_video_audio(video_path, audio_path, output_path):
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(audio_path)
        
        # 智能调整时长
        final_audio = audio_clip
        if audio_clip.duration > video_clip.duration:
            final_audio = audio_clip.subclip(0, video_clip.duration)
        
        final_clip = video_clip.set_audio(final_audio)
        final_clip.write_videofile(output_path, codec='libx264', audio_codec='aac', logger=None)
        
        video_clip.close()
        audio_clip.close()
        return True
    except Exception as e:
        print(f"合成错误: {e}")
        return False

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

# === 📡 Sora API ===
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
    history_list = load_history()
    if not history_list: st.info("暂无记录")
    else:
        for item in reversed(history_list):
            label = f"🎬 {item.get('time', '')[5:-3]} | {item.get('product')}"
            with st.expander(label):
                if st.button("回看", key=f"btn_{item['task_id']}"):
                    st.session_state['view_mode'] = 'history_video'
                    st.session_state['current_record'] = item

# === 主界面 ===
st.markdown("## 🏭 Sora 视频工坊 <span style='font-size:0.8rem; color:red'>v8.2 (智谱AI版)</span>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 1.5])

# --- 左侧 ---
with col1:
    st.info("💡 **当前配置**：脚本生成使用智谱 AI (GLM-4-Flash)，视频生成使用 Sora-2。")
    
    # 1. 语种
    st.subheader("1. 目标市场")
    target_lang_label = st.selectbox("选择语言", list(VOICE_MAP.keys()))
    voice_code = VOICE_MAP[target_lang_label]
    lang_name = target_lang_label.split("(")[0].strip()

    # 2. 内容创作
    st.subheader("2. 内容创作")
    product_desc = st.text_input("🅰️ 产品定义 (中文)", placeholder="例如：蓝色降噪耳机，音质好")
    
    # 🔥 智谱 AI 写脚本按钮
    if st.button("✨ 用智谱AI生成本地化脚本"):
        if not product_desc:
            st.error("请先填写【产品定义】！")
        else:
            with st.spinner(f"智谱 AI 正在撰写 {lang_name} 脚本..."):
                ai_script, err = generate_script_by_llm(product_desc, lang_name)
                if ai_script:
                    st.session_state['generated_script'] = ai_script
                    st.success("✅ 脚本已生成！")
                else:
                    st.error(f"生成失败: {err}")

    default_script = st.session_state.get('generated_script', "")
    voiceover_text = st.text_area("🅱️ 口播文案 (自动/手动)", value=default_script, height=100)
    
    # 3. 参数
    st.subheader("3. 素材与参数")
    uploaded_files = st.file_uploader("参考图片", type=['png', 'jpg'], accept_multiple_files=True)
    c1, c2 = st.columns(2)
    with c1: batch_dur = int(st.selectbox("时长", ["5s", "10s", "15s"]).replace("s",""))
    with c2: 
        size_label = st.selectbox("画质", ["高清 (Large)", "标准 (Small)"])
        batch_size = "large" if "高清" in size_label else "small"

    start_btn = st.button("🚀 生成有声视频", type="primary", use_container_width=True)

# --- 右侧 ---
with col2:
    st.subheader("🎬 制片进度")
    
    if start_btn:
        if not product_desc or not voiceover_text:
            st.error("请完善信息！")
        else:
            # 1. 构造 Prompt
            final_prompt = (
                f"Target Language: {lang_name}. "
                f"Subject: {product_desc}. "
                f"Requirements: Commercial lighting, high resolution. "
                f"CRITICAL: Characters must appear to be speaking {lang_name}."
            )
            
            # 2. 图片
            img_base64 = None
            if uploaded_files: img_base64 = encode_image_to_base64(uploaded_files[0])
            
            with st.status("正在制片中...", expanded=True) as status:
                
                # A. 视频
                status.write("🎥 [1/3] Sora 正在渲染画面...")
                res = submit_video_task(final_prompt, "sora-2", "16:9", batch_dur, batch_size, img_base64)
                task_id = res.get("data", {}).get("task_id") or res.get("task_id")
                
                if not task_id:
                    status.update(label="❌ 提交失败", state="error")
                    st.error(res)
                else:
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
                            status.update(label="❌ 失败", state="error")
                            st.stop()
                    
                    if not video_url:
                        st.error("无法获取视频")
                        st.stop()

                    # B. 音频
                    status.write(f"🗣️ [2/3] 正在生成配音...")
                    os.makedirs("temp", exist_ok=True)
                    audio_path = f"temp/{task_id}.mp3"
                    video_path = f"temp/{task_id}.mp4"
                    final_path = f"temp/{task_id}_final.mp4"
                    
                    try:
                        asyncio.run(generate_tts_audio(voiceover_text, voice_code, audio_path))
                        
                        status.write("📥 下载素材中...")
                        with open(video_path, 'wb') as f:
                            f.write(requests.get(video_url).content)
                            
                        # C. 合成
                        status.write("🎞️ [3/3] 音画同步中...")
                        if merge_video_audio(video_path, audio_path, final_path):
                            status.update(label="✅ 完成！", state="complete", expanded=False)
                            st.success(f"🎉 {lang_name} 视频制作完成！")
                            st.video(final_path)
                            
                            with open(final_path, "rb") as f:
                                st.download_button("⬇️ 下载成品", f, file_name=f"Final_{task_id}.mp4")
                            
                            save_to_history({
                                "task_id": task_id, "product": f"{product_desc} (智谱脚本)",
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "video_url": video_url, "voice_text": voiceover_text
                            })
                        else:
                            st.error("合成失败")
                            st.video(video_url)
                    except Exception as e:
                        st.error(f"出错: {e}")

    elif st.session_state.get('view_mode') == 'history_video':
        rec = st.session_state['current_record']
        st.info(f"回看：{rec.get('product')}")
        st.video(rec.get('video_url'))
        st.caption(f"文案：{rec.get('voice_text')}")

    else:
        st.markdown("""
        <div style='background:#f0f2f6; padding:20px; border-radius:10px; color:gray; text-align:center'>
            👋 欢迎使用 v8.2 智谱AI版<br>请填写 API Key 后开始使用
        </div>
        """, unsafe_allow_html=True)