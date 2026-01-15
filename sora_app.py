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
# 导入并禁用安全警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= ⚠️ 配置与安全区域 =================
# 自动读取 Secrets，如果不存在则允许手动输入
try:
    API_KEY = st.secrets["API_KEY"]
except:
    API_KEY = "sk-57e392622e3f45c0af35bde21611b0f8"

HOST = "https://grsai.dakka.com.cn" 

# 智谱 AI 配置 (固定为你提供的可用Key)
LLM_API_KEY = "f87cd651378147b58a12828ad95465ee.9yUBYWw6o3DIGWKW" 
LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"     
LLM_MODEL = "glm-4-flash"                                 
# ====================================================

st.set_page_config(page_title="Sora 视频工坊 v9.5", layout="wide", page_icon="🎬")

# === 🛠️ 核心辅助函数 ===

def encode_image_to_base64(uploaded_files):
    if not uploaded_files: return None
    try:
        images = [Image.open(f) for f in uploaded_files]
        if len(images) == 1:
            buf = io.BytesIO()
            images[0].save(buf, format="PNG")
            return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
        cols = math.ceil(math.sqrt(len(images)))
        rows = math.ceil(len(images) / cols)
        cs = 512
        new_img = Image.new('RGB', (cols * cs, rows * cs), (255, 255, 255))
        for i, img in enumerate(images):
            r, c = i // cols, i % cols
            img.thumbnail((cs, cs))
            new_img.paste(img, (c * cs + (cs - img.width)//2, r * cs + (cs - img.height)//2))
        buf = io.BytesIO()
        new_img.save(buf, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
    except: return None

# === 📡 API 核心逻辑 (工业级加固) ===

def get_common_headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

def submit_video_task(prompt, model, aspect_ratio, duration, size, img_data=None):
    url = f"{HOST}/v1/video/sora-video"
    payload = {
        "model": model, "prompt": prompt, "aspect_ratio": aspect_ratio, 
        "duration": duration, "size": size, "expand_prompt": True
    }
    if img_data: payload["url"] = img_data
    
    try:
        # 使用 verify=False 跳过证书校验，延长超时
        response = requests.post(url, headers=get_common_headers(), json=payload, timeout=120, verify=False)
        
        # 记录原始数据用于调试
        st.session_state['last_raw_response'] = response.text
        
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "data": response.text}
        
        try:
            return response.json()
        except:
            return {"error": "JSON解析失败", "data": response.text}
    except Exception as e:
        return {"error": str(e), "data": None}

def check_result(task_id):
    url = f"{HOST}/v1/draw/result"
    try:
        # 🔥 必须使用 id 参数
        res = requests.post(url, headers=get_common_headers(), json={"id": task_id}, timeout=30, verify=False)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

# === 🎬 脚本与合成 ===

def generate_timed_script(product_name, target_lang, duration_sec):
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Write a {duration_sec}s marketing script for {product_name} in {target_lang}. Max 60 words."
    try:
        res = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json={
            "model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}]
        }, timeout=15)
        return res.json()['choices'][0]['message']['content'].strip(), None
    except Exception as e: return None, str(e)

async def generate_tts(text, voice, file):
    await edge_tts.Communicate(text, voice).save(file)

def merge_av(v, a, out):
    try:
        vc = VideoFileClip(v); ac = AudioFileClip(a)
        fa = ac.subclip(0, vc.duration) if ac.duration > vc.duration else ac
        vc.set_audio(fa).write_videofile(out, codec='libx264', audio_codec='aac', logger=None)
        vc.close(); ac.close(); return True
    except: return False

# === 🖥️ UI 界面 ===

with st.sidebar:
    st.title("📜 历史纪录")
    if not API_KEY:
        st.warning("⚠️ 未检测到 API Key")
        API_KEY = st.text_input("在这里输入 Sora API Key", type="password")

st.markdown("## 🏭 Sora 视频工坊 <span style='color:red; font-size:0.8rem;'>v9.5 (终极修复版)</span>", unsafe_allow_html=True)
c1, c2 = st.columns([1, 1.5])

VOICE_MAP = {"Thai (泰语)": "th-TH-NiwatNeural", "English (英语)": "en-US-ChristopherNeural", "Malay (马来语)": "ms-MY-OsmanNeural"}

with c1:
    lang_opt = st.selectbox("目标语言", list(VOICE_MAP.keys()))
    product = st.text_input("产品名称")
    batch_dur = int(st.selectbox("时长", ["5s", "10s", "15s"]).replace("s",""))
    size_label = st.selectbox("画质", ["高清 (Large)", "标准 (Small)"])
    v_script = st.text_area("视觉描述脚本", height=70)
    
    if st.button("✨ 自动生成脚本"):
        s, e = generate_timed_script(product, lang_opt, batch_dur)
        if s: st.session_state['active_script'] = s
    a_script = st.text_area("口播文案", value=st.session_state.get('active_script', ""), height=90)
    
    files = st.file_uploader("产品多角度图片", accept_multiple_files=True)
    b64_data = encode_image_to_base64(files)
    if b64_data: st.image(files[0], width=150, caption="参考图已准备")
    
    start_btn = st.button("🚀 启动视频生成", type="primary", use_container_width=True)

with c2:
    st.subheader("🎬 实时制片监控")
    if start_btn:
        if not API_KEY: st.error("请在侧边栏输入 API Key"); st.stop()
        with st.status("正在处理任务...", expanded=True) as status:
            # 1. 提交
            status.write("📡 正在向服务器提交任务...")
            full_prompt = f"Language: {lang_opt}. Visual: {v_script}. Audio: {a_script}"
            res = submit_video_task(full_prompt, "sora-2", "16:9", batch_dur, "large" if "高清" in size_label else "small", b64_data)
            
            # 🔥 处理提交报错
            if "error" in res:
                status.update(label="❌ 提交失败", state="error")
                st.error(f"服务器报错: {res['error']}")
                with st.expander("查看服务器返回的原始数据 (查错关键)"):
                    st.code(st.session_state.get('last_raw_response', '无内容'))
                st.stop()
            
            # 提取 ID
            data = res.get("data", {})
            tid = data.get("id") or data.get("task_id") or res.get("task_id")
            
            if tid:
                status.write(f"✅ 任务提交成功 ID: {tid}")
                v_url = None
                bar = st.progress(0)
                for i in range(120):
                    time.sleep(4)
                    r = check_result(tid)
                    s = r.get("data", {}).get("status")
                    bar.progress(min(i*1, 95))
                    if s in ["SUCCESS", "COMPLETED", "succeeded"]:
                        results = r.get("data", {}).get("results", [])
                        v_url = results[0].get("url") if results else r.get("data", {}).get("url")
                        break
                    if s in ["FAILED", "failed"]: 
                        st.error("生成失败"); break
                
                if v_url:
                    status.update(label="✨ 画面生成完成", state="complete")
                    st.info("👇 Sora 原始视频 (无声版)")
                    st.video(v_url)
                    
                    # 合成逻辑
                    os.makedirs("temp", exist_ok=True)
                    v_p, a_p, f_p = f"temp/{tid}.mp4", f"temp/{tid}.mp3", f"temp/{tid}_f.mp4"
                    try:
                        with open(v_p, 'wb') as f: f.write(requests.get(v_url).content)
                        asyncio.run(generate_tts(a_script, VOICE_MAP[lang_opt], a_p))
                        if merge_av(v_p, a_p, f_p):
                            st.success("✅ 有声合成版制作成功！")
                            st.video(f_p)
                            with open(f_p, "rb") as f: st.download_button("⬇️ 下载成品", f, file_name=f"Final_{tid}.mp4")
                        else:
                            st.warning("⚠️ 合成失败（ffmpeg未生效），请下载上方原视频")
                    except Exception as e:
                        st.error(f"后期处理出错: {e}")
            else:
                st.error("无法获取任务ID，API可能变动")
