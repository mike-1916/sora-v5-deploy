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
import urllib3

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= ⚠️ 配置区域 =================
try:
    API_KEY = st.secrets["API_KEY"]
except:
    # ⚠️ 请确保这里填入的是你真实的 sk-xxx Key
    API_KEY = "sk-57e392622e3f45c0af35bde21611b0f8" 

HOST = "https://grsai.dakka.com.cn" 

# 智谱 AI 配置
LLM_API_KEY = "f87cd651378147b58a12828ad95465ee.9yUBYWw6o3DIGWKW" 
LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"     
LLM_MODEL = "glm-4-flash"                                 
# ===============================================

st.set_page_config(page_title="Sora 视频工坊 v9.9", layout="wide", page_icon="🎬")

# --- 🛠️ 辅助功能函数 ---

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

# --- 📡 API 交互核心 (适配流式返回) ---

def get_headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
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
        # 使用 stream=True 兼容流式返回格式
        response = requests.post(url, headers=get_headers(), json=payload, timeout=60, verify=False, stream=True)
        st.session_state['last_raw_response'] = ""
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                st.session_state['last_raw_response'] += decoded_line + "\n"
                # 剥离 "data: " 前缀提取 JSON
                clean_json = decoded_line.replace("data: ", "").strip()
                try:
                    data = json.loads(clean_json)
                    # 优先获取顶层 id，其次获取 data 内部的 id
                    tid = data.get("id") or (data.get("data", {}).get("id") if isinstance(data.get("data"), dict) else None)
                    if tid: return data
                except: continue
        return {"error": "流式解析失败", "data": st.session_state['last_raw_response']}
    except Exception as e:
        return {"error": str(e), "data": None}

def check_result(task_id):
    url = f"{HOST}/v1/draw/result"
    try:
        # 结果查询必须使用 id 参数
        res = requests.post(url, headers=get_headers(), json={"id": task_id}, timeout=30, verify=False)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

# --- 🎬 脚本/配音/历史 ---

def generate_script(prod_name, lang, dur):
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Write a {dur}s marketing script for {prod_name} in {lang}. Max 60 words. Pure script only."
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

def save_to_history(record):
    history = []
    if os.path.exists("history.json"):
        with open("history.json", "r") as f:
            try: history = json.load(f)
            except: history = []
    history.append(record)
    with open("history.json", "w") as f: json.dump(history, f, indent=2)

# --- 🖥️ UI 界面布局 ---

st.markdown("## 🏭 Sora 视频工坊 <span style='color:red; font-size:0.8rem;'>v9.9 (全功能修复版)</span>", unsafe_allow_html=True)
# 🔥 定义 col1, col2 确保变量在全局作用域内可用
col1, col2 = st.columns([1, 1.5])

VOICE_MAP = {"Thai (泰语)": "th-TH-NiwatNeural", "English (英语)": "en-US-ChristopherNeural", "Malay (马来语)": "ms-MY-OsmanNeural"}

with col1:
    st.subheader("1. 创作设置")
    lang_opt = st.selectbox("语言", list(VOICE_MAP.keys()))
    product = st.text_input("产品名")
    batch_dur = int(st.selectbox("时长", ["5s", "10s", "15s"]).replace("s",""))
    size_label = st.selectbox("画质", ["高清 (Large)", "标准 (Small)"])
    v_script = st.text_area("视觉描述脚本", height=70)
    
    if st.button("✨ 自动生成脚本"):
        if not product: st.error("请先填产品名")
        else:
            s, e = generate_script(product, lang_opt, batch_dur)
            if s: st.session_state['active_script'] = s
    a_script = st.text_area("口播文案", value=st.session_state.get('active_script', ""), height=90)
    
    files = st.file_uploader("素材图片 (多选拼图)", accept_multiple_files=True)
    b64_data = encode_image_to_base64(files)
    if b64_data and files: st.image(files[0], width=100, caption="参考图准备完毕")
    
    start_btn = st.button("🚀 启动生成任务", type="primary", use_container_width=True)

# 🔥 严格对应变量名 col2
with col2:
    st.subheader("🎬 实时制片监控")
    if start_btn:
        if not v_script or not a_script:
            st.error("视觉脚本或口播文案不能为空！")
        else:
            with st.status("制片流程启动中...", expanded=True) as status:
                status.write("📡 提交任务并解析流数据...")
                full_p = f"Language: {lang_opt}. Visual: {v_script}. Narrative: {a_script}"
                res = submit_video_task(full_p, "sora-2", "16:9", batch_dur, "large" if "高清" in size_label else "small", b64_data)
                
                if "error" in res:
                    status.update(label="❌ 提交失败", state="error")
                    st.error(f"解析错误: {res['error']}")
                    with st.expander("原始流数据排查"):
                        st.code(st.session_state.get('last_raw_response', '无内容'))
                    st.stop()
                
                # 提取任务 ID
                tid = res.get("id") or (res.get("data", {}).get("id") if isinstance(res.get("data"), dict) else None)
                
                if tid:
                    status.write(f"✅ 任务接收 ID: {tid}")
                    v_url = None
                    bar = st.progress(0)
                    for i in range(120): # 最多等待8分钟
                        time.sleep(4)
                        r = check_result(tid)
                        check_data = r.get("data", {})
                        s = check_data.get("status")
                        
                        bar.progress(min(i*1, 95))
                        if s in ["SUCCESS", "COMPLETED", "succeeded"]:
                            results = check_data.get("results", [])
                            v_url = results[0].get("url") if results else check_data.get("url")
                            break
                        if s in ["FAILED", "failed"]: 
                            st.error("渲染失败"); break
                    
                    if v_url:
                        status.update(label="✨ 画面渲染完成", state="complete")
                        st.video(v_url)
                        
                        # 合成逻辑
                        os.makedirs("temp", exist_ok=True)
                        v_p, a_p, f_p = f"temp/{tid}.mp4", f"temp/{tid}.mp3", f"temp/{tid}_f.mp4"
                        try:
                            with open(v_p, 'wb') as f: f.write(requests.get(v_url).content)
                            asyncio.run(generate_tts(a_script, VOICE_MAP[lang_opt], a_p))
                            if merge_av(v_p, a_p, f_p):
                                st.success("✅ 音画合成成功！")
                                st.video(f_p)
                                with open(f_p, "rb") as f: st.download_button("⬇️ 下载成品", f, file_name=f"AD_{tid}.mp4")
                            else:
                                st.warning("合成异常，请下载无声版")
                        except Exception as e:
                            st.error(f"处理错误: {e}")
                        
                        save_to_history({"task_id": tid, "product": product, "time": datetime.now().strftime("%H:%M"), "video_url": v_url})
                else:
                    st.error("未在响应中解析到任务 ID")
