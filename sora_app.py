import streamlit as st
import requests
import time
import json
import os
import base64
import asyncio
import io
import math
import re
from PIL import Image
from datetime import datetime
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip
import urllib3

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= 🔒 核心隐蔽配置区 =================
# 代码会自动去您截图中的 "Secrets" 区域寻找 Key
# 如果没填，界面会提示错误，而不是崩坏

HOST = "https://grsai.dakka.com.cn" 
LLM_BASE_URL = "https://grsaiapi.com/v1"  
LLM_MODEL = "gemini-2.5-flash" 

try:
    # 对应您在 Secrets 框里填写的名字
    API_KEY = st.secrets["SORA_API_KEY"]
    LLM_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception as e:
    st.error("❌ 启动失败：未检测到 API Key。")
    st.warning("请在 Streamlit Community Cloud 的 App Settings -> Secrets 中填写 SORA_API_KEY 和 GEMINI_API_KEY。")
    st.stop()
# ====================================================

st.set_page_config(page_title="Sora 视频工坊 v11.4", layout="wide", page_icon="🎬")

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

# --- 📡 Sora API 交互核心 ---

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
        response = requests.post(url, headers=get_headers(), json=payload, timeout=60, verify=False, stream=True)
        st.session_state['last_raw_response'] = ""
        extracted_id = None
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                st.session_state['last_raw_response'] += decoded_line + "\n"
                match = re.search(r'"id"\s*:\s*"([^"]+)"', decoded_line)
                if match:
                    extracted_id = match.group(1)
                    return {"id": extracted_id, "status": "submitted"}
                if decoded_line.startswith("data: "):
                    try:
                        data = json.loads(decoded_line[6:].strip())
                        tid = data.get("id") or (data.get("data", {}).get("id") if isinstance(data.get("data"), dict) else None)
                        if tid: return {"id": tid, "status": "submitted"}
                    except: pass
        if extracted_id: return {"id": extracted_id, "status": "submitted"}
        return {"error": "未找到任务ID", "data": st.session_state['last_raw_response']}
    except Exception as e:
        return {"error": str(e), "data": None}

def check_result(task_id):
    url = f"{HOST}/v1/draw/result"
    try:
        res = requests.post(url, headers=get_headers(), json={"id": task_id}, timeout=30, verify=False)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

# --- 🧠 智能脚本生成 ---

def generate_ai_scripts(prod_name, lang, dur, image_base64=None):
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}", 
        "Content-Type": "application/json"
    }
    
    base_instruction = f"""
    你是一位擅长拍摄“生活方式（Lifestyle）”类广告的导演。你的目标是展示产品在真实生活中的应用。
    
    请生成两部分内容，必须用 '|||' 严格分隔：

    1. [Visual Prompt]: 用英文写一段 Sora 视频提示词。
       - **必须包含真人出镜**：根据产品属性，设定一个合适的人物（如：A young woman, A professional man, A happy family）。
       - **必须包含实际交互**：人物必须正在使用这个产品（holding, drinking, wearing, typing on, etc.）。
       - **必须有真实场景**：背景要是真实环境（Cozy living room, Busy office, Sunny park），而不是纯色背景。
       - **画质要求**：Photorealistic, 4k, cinematic lighting, shallow depth of field, highly detailed human face and hands.
       - 格式示例：Medium shot of a smiling young woman in a sunny kitchen, holding the [product], steam rising, cinematic lighting...

    2. [Audio Script]: 用{lang}写一段{dur}秒的口播文案。
       - 语气要像真人在分享体验，而不是冷冰冰的说明书。
       - 侧重于“使用感受”和“生活改变”。
    
    格式要求：
    Visual Prompt Content...
    |||
    Audio Script Content...
    """

    messages = []
    if image_base64:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"请观察这张产品图片，想象一个人正在使用它的场景。{base_instruction}"},
                    {"type": "image_url", "image_url": {"url": image_base64}}
                ]
            }
        ]
    else:
        messages = [{"role": "user", "content": f"产品名称：{prod_name}。{base_instruction}"}]

    payload = {"model": LLM_MODEL, "messages": messages, "stream": False}

    try:
        res = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=60)
        if res.status_code != 200: return "", f"API Error {res.status_code}: {res.text}"
        content = res.json()['choices'][0]['message']['content']
        parts = content.split("|||")
        if len(parts) >= 2: return parts[0].strip(), parts[1].strip()
        else: return content, "AI 未按格式返回"
    except Exception as e: return "", f"请求错误: {str(e)}"

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

# --- 📜 侧边栏 ---
with st.sidebar:
    st.header("📂 历史作品库")
    search_term = st.text_input("🔍 搜索产品名", placeholder="输入关键词...")

    if os.path.exists("history.json"):
        with open("history.json", "r") as f:
            try:
                history_data = json.load(f)
                if not isinstance(history_data, list): history_data = []
                for item in reversed(history_data):
                    product_name = item.get('product', '无标题')
                    if search_term and search_term.lower() not in product_name.lower():
                        continue
                    label = f"{item.get('time', '未知')} | {product_name}"
                    with st.expander(label):
                        st.caption(f"ID: {item.get('task_id')}")
                        if item.get('video_url'):
                            st.video(item.get('video_url'))
                            st.write(f"[🔗 下载视频]({item.get('video_url')})")
                        else: st.warning("链接失效")
            except: st.error("历史记录读取失败")

# --- 🖥️ 主界面 ---

st.markdown(f"## 🏭 Sora 视频工坊 <span style='color:red; font-size:0.8rem;'>v11.4 (云端安全版)</span>", unsafe_allow_html=True)

main_col1, main_col2 = st.columns([1, 1.5])
VOICE_MAP = {"Thai (泰语)": "th-TH-NiwatNeural", "English (英语)": "en-US-ChristopherNeural", "Malay (马来语)": "ms-MY-OsmanNeural"}

with main_col1:
    st.subheader("1. 创作设置")
    lang_opt = st.selectbox("目标语言", list(VOICE_MAP.keys()))
    product = st.text_input("产品名称")
    batch_dur = int(st.selectbox("时长", ["15s", "10s", "5s"]).replace("s",""))
    size_label = st.selectbox("画质", ["高清 (Large)", "标准 (Small)"])
    
    files = st.file_uploader("参考图 (AI将基于此图构思使用场景)", accept_multiple_files=True)
    b64_data = encode_image_to_base64(files)
    if b64_data: st.image(files[0], width=100, caption="已加载")

    st.markdown("---")
    col_gen_btn, col_tip = st.columns([2, 1])
    
    with col_gen_btn:
        if st.button(f"✨ 生成真人应用脚本", type="secondary", use_container_width=True):
            if not product:
                st.error("请输入产品名称")
            else:
                with st.spinner("🤖 正在构思人物与场景..."):
                    v_res, a_res = generate_ai_scripts(product, lang_opt, batch_dur, b64_data)
                    if v_res:
                        st.session_state['visual_script'] = v_res
                        st.session_state['audio_script'] = a_res
                        st.success("✅ 真人场景脚本已生成！")
                    else: st.error(a_res)

    v_script = st.text_area("视觉指令 (Visual Prompt)", value=st.session_state.get('visual_script', ""), height=100)
    a_script = st.text_area("口播文案 (Audio Script)", value=st.session_state.get('audio_script', ""), height=100)
    
    st.markdown("---")
    start_btn = st.button("🚀 启动视频生成", type="primary", use_container_width=True)

with main_col2:
    st.subheader("🎬 实时制片监控")
    if start_btn:
        if not v_script or not a_script:
            st.error("脚本不能为空！")
        else:
            with st.status("处理中...", expanded=True) as status:
                status.write("📡 正在提交任务...")
                full_p = f"Language: {lang_opt}. Visual: {v_script}. Narrative: {a_script}"
                
                res = submit_video_task(full_p, "sora-2", "16:9", batch_dur, "large" if "高清" in size_label else "small", b64_data)
                tid = res.get("id")
                
                if not tid:
                    status.update(label="❌ 提交失败", state="error")
                    st.error(f"错误: {res.get('error')}")
                    st.stop()
                
                status.write(f"✅ 任务ID: {tid}")
                status.write("⏳ AI 正在生成中 (预计耗时 3-5 分钟)...")
                
                v_url = None
                bar = st.progress(0)
                
                for i in range(120):
                    time.sleep(4)
                    r = check_result(tid)
                    data_layer = r.get("data", r) if isinstance(r.get("data"), dict) else r
                    current_status = str(data_layer.get("status")).lower()
                    
                    if current_status in ["failed", "error", "fail"]:
                        reason = data_layer.get('failure_reason') or data_layer.get('error')
                        status.update(label="❌ 生成失败", state="error")
                        st.error(f"失败原因: {reason}")
                        break
                    elif current_status in ["success", "succeeded", "completed"]:
                        results = data_layer.get("results", [])
                        v_url = results[0].get("url") if results else data_layer.get("url")
                        bar.progress(100)
                        break
                    else:
                        bar.progress(min(i + 1, 95))
                        continue 
                
                if v_url:
                    status.write("🔨 正在进行音画合成...")
                    os.makedirs("temp", exist_ok=True)
                    v_p, a_p, f_p = f"temp/{tid}.mp4", f"temp/{tid}.mp3", f"temp/{tid}_f.mp4"
                    
                    final_video_to_show = None
                    is_merged = False
                    
                    try:
                        with open(v_p, 'wb') as f: f.write(requests.get(v_url).content)
                        asyncio.run(generate_tts(a_script, VOICE_MAP[lang_opt], a_p))
                        if merge_av(v_p, a_p, f_p):
                            is_merged = True
                            final_video_to_show = f_p
                        else:
                            final_video_to_show = v_p 
                            st.warning("音频合成失败，展示无声原片")
                    except Exception as e:
                        st.error(f"处理出错: {e}")
                        final_video_to_show = v_url 
                    
                    status.update(label="✨ 制片完成", state="complete")
                    if final_video_to_show:
                        st.success("✅ 最终成品")
                        st.video(final_video_to_show)
                        with open(final_video_to_show if is_merged else v_p, "rb") as f:
                            st.download_button("⬇️ 下载视频", f, file_name=f"FINAL_{tid}.mp4")
                    
                    save_to_history({"task_id": tid, "product": product, "time": datetime.now().strftime("%H:%M"), "video_url": v_url})
