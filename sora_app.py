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
import hashlib
from PIL import Image
from datetime import datetime, timedelta
import urllib3
# 必须安装: pip install extra-streamlit-components
import extra_streamlit_components as stx

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= 🔒 核心配置 =================
HOST = "https://grsai.dakka.com.cn" 
LLM_BASE_URL = "https://grsaiapi.com/v1"  
LLM_MODEL = "gemini-2.5-flash" 

try:
    API_KEY = st.secrets["SORA_API_KEY"]
    LLM_API_KEY = st.secrets["GEMINI_API_KEY"]
    ADMIN_USER = st.secrets.get("ADMIN_USERNAME", "admin")
    ADMIN_PASS = st.secrets.get("ADMIN_PASSWORD", "admin123")
except Exception as e:
    st.error("❌ 启动配置错误")
    st.warning("请检查 secrets.toml 配置")
    st.stop()
# ===============================================

st.set_page_config(page_title="Sora 视频工坊 v13.2", layout="wide", page_icon="🎬")

# --- 🍪 Cookie 管理器 (单例模式) ---
@st.cache_resource(experimental_allow_widgets=True)
def get_manager():
    return stx.CookieManager(key="sora_cookie_manager")

cookie_manager = get_manager()

# --- 🔐 用户认证系统 ---
USER_DB_FILE = "users.json"

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

def generate_token_signature(username):
    raw = f"{username}:{API_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()

def load_users():
    if not os.path.exists(USER_DB_FILE): return {}
    try:
        with open(USER_DB_FILE, "r") as f: return json.load(f)
    except: return {}

def save_users(users):
    with open(USER_DB_FILE, "w") as f: json.dump(users, f, indent=4)

def init_admin():
    users = load_users()
    if ADMIN_USER not in users:
        users[ADMIN_USER] = {
            "password": make_hashes(ADMIN_PASS),
            "approved": True,
            "role": "admin",
            "created_at": str(datetime.now())
        }
        save_users(users)

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = None
    st.session_state["role"] = None

init_admin()

# --- 🍪 自动登录检查 (增强版) ---
if not st.session_state["logged_in"]:
    # 尝试读取 Cookie
    # 注意：在 Streamlit 中，组件加载需要时间，首次刷新可能读到 None
    auth_cookie = cookie_manager.get(cookie="sora_auth_token")
    
    if auth_cookie:
        try:
            c_user, c_sign = auth_cookie.split("|")
            if c_sign == generate_token_signature(c_user):
                users = load_users()
                if c_user in users and users[c_user].get("approved", False):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = c_user
                    st.session_state["role"] = users[c_user].get("role", "user")
                    st.rerun() # 立即刷新进入
        except: pass

# --- 🔐 登录页面 ---
def login_page():
    st.markdown("## 🔐 Sora 视频工坊 - 身份验证")
    
    # 显示一个小提示，如果是刚刷新还在加载Cookie
    if not st.session_state["logged_in"]:
        time.sleep(0.3) # 给 Cookie 管理器一点时间挂载
    
    tab1, tab2 = st.tabs(["登录", "注册新账号"])
    
    with tab1:
        username = st.text_input("用户名", key="login_user")
        password = st.text_input("密码", type="password", key="login_pass")
        remember_me = st.checkbox("保持长期登录 (7天)", value=True)
        
        if st.button("登录", type="primary"):
            users = load_users()
            if username in users:
                user_data = users[username]
                if check_hashes(password, user_data["password"]):
                    if user_data.get("approved", False):
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = username
                        st.session_state["role"] = user_data.get("role", "user")
                        
                        if remember_me:
                            token = f"{username}|{generate_token_signature(username)}"
                            # 🔥 核心修复：使用 UTC 时间，避免时区差异导致 Cookie 无效
                            expires_at = datetime.utcnow() + timedelta(days=7)
                            cookie_manager.set("sora_auth_token", token, expires_at=expires_at)
                        
                        st.success("登录成功！")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.warning("⚠️ 您的账号正在等待管理员审核。")
                else:
                    st.error("❌ 密码错误")
            else:
                st.error("❌ 用户名不存在")

    with tab2:
        new_user = st.text_input("设置用户名", key="reg_user")
        new_pass = st.text_input("设置密码", type="password", key="reg_pass")
        new_pass_confirm = st.text_input("确认密码", type="password", key="reg_pass2")
        
        if st.button("提交注册申请"):
            users = load_users()
            if new_user in users:
                st.error("该用户名已被占用")
            elif new_pass != new_pass_confirm:
                st.error("两次输入的密码不一致")
            elif len(new_pass) < 6:
                st.error("密码长度至少需要6位")
            else:
                users[new_user] = {
                    "password": make_hashes(new_pass),
                    "approved": False,
                    "role": "user",
                    "created_at": str(datetime.now())
                }
                save_users(users)
                st.success("✅ 注册申请已提交！")

# --- 🛠️ 业务功能函数 (内置懒加载加速) ---
def process_uploaded_images(uploaded_files):
    if not uploaded_files: return None, None
    try:
        images = [Image.open(f) for f in uploaded_files]
        if len(images) == 1:
            buf = io.BytesIO()
            images[0].save(buf, format="PNG")
            b64_str = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
            return b64_str, images[0]
        count = len(images)
        cols = math.ceil(math.sqrt(count))
        rows = math.ceil(count / cols)
        cell_size = 512
        merged_img = Image.new('RGB', (cols * cell_size, rows * cell_size), (255, 255, 255))
        for i, img in enumerate(images):
            r_idx = i // cols
            c_idx = i % cols
            img.thumbnail((cell_size, cell_size))
            x = c_idx * cell_size + (cell_size - img.width) // 2
            y = r_idx * cell_size + (cell_size - img.height) // 2
            merged_img.paste(img, (x, y))
        buf = io.BytesIO()
        merged_img.save(buf, format="PNG")
        b64_str = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
        return b64_str, merged_img
    except Exception as e: return None, None

def get_headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

def submit_video_task(prompt, model, aspect_ratio, duration, size, img_data=None):
    url = f"{HOST}/v1/video/sora-video"
    payload = {"model": model, "prompt": prompt, "aspect_ratio": aspect_ratio, "duration": duration, "size": size, "expand_prompt": True}
    if img_data: payload["url"] = img_data
    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=60, verify=False, stream=True)
        extracted_id = None
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                match = re.search(r'"id"\s*:\s*"([^"]+)"', decoded_line)
                if match: return {"id": match.group(1), "status": "submitted"}
                if decoded_line.startswith("data: "):
                    try:
                        data = json.loads(decoded_line[6:].strip())
                        tid = data.get("id") or (data.get("data", {}).get("id") if isinstance(data.get("data"), dict) else None)
                        if tid: return {"id": tid, "status": "submitted"}
                    except: pass
        return {"error": "未找到任务ID"}
    except Exception as e: return {"error": str(e)}

def check_result(task_id):
    try:
        res = requests.post(f"{HOST}/v1/draw/result", headers=get_headers(), json={"id": task_id}, timeout=30, verify=False)
        return res.json()
    except Exception as e: return {"error": str(e)}

def generate_ai_scripts(prod_name, lang, dur, image_base64=None):
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    base_instruction = f"""
    你是一位擅长拍摄“生活方式（Lifestyle）”类广告的导演。
    请生成两部分内容，必须用 '|||' 严格分隔：
    1. [Visual Prompt]: 用英文写一段 Sora 视频提示词。必须包含真人出镜、实际交互和真实场景。画质4K。
    2. [Audio Script]: 用{lang}写一段{dur}秒的口播文案，语气自然。
    """
    messages = []
    if image_base64:
        messages = [{"role": "user", "content": [{"type": "text", "text": f"产品：{prod_name}。{base_instruction}"}, {"type": "image_url", "image_url": {"url": image_base64}}]}]
    else:
        messages = [{"role": "user", "content": f"产品：{prod_name}。{base_instruction}"}]
    try:
        res = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json={"model": LLM_MODEL, "messages": messages}, timeout=60)
        content = res.json()['choices'][0]['message']['content']
        parts = content.split("|||")
        return (parts[0].strip(), parts[1].strip()) if len(parts) >= 2 else (content, "格式解析错误")
    except Exception as e: return "", str(e)

async def generate_tts(text, voice, file):
    import edge_tts
    await edge_tts.Communicate(text, voice).save(file)

def merge_av(v, a, out):
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip
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

# --- 🖥️ 主程序 ---
if not st.session_state["logged_in"]:
    login_page()
else:
    with st.sidebar:
        st.write(f"👤 用户: **{st.session_state['username']}**")
        if st.button("🚪 退出"):
            # 删除 Cookie 时也要指定 key，否则可能删不掉
            cookie_manager.delete("sora_auth_token")
            st.session_state["logged_in"] = False
            st.rerun()
        
        st.markdown("---")
        if st.session_state["role"] == "admin":
            st.subheader("🛡️ 管理")
            users = load_users()
            pending_users = [u for u, d in users.items() if not d.get("approved")]
            if pending_users:
                st.warning(f"待审核: {len(pending_users)}")
                for pu in pending_users:
                    col_u, col_btn = st.columns([2, 1])
                    col_u.write(pu)
                    if col_btn.button("✅", key=f"app_{pu}"):
                        users[pu]["approved"] = True
                        save_users(users)
                        st.success("已批准")
                        st.rerun()
            else: st.info("无待审核")
            st.markdown("---")

        st.header("📂 历史")
        search_term = st.text_input("🔍 搜索", placeholder="关键词...")
        if os.path.exists("history.json"):
            with open("history.json", "r") as f:
                try:
                    history_data = json.load(f)
                    if not isinstance(history_data, list): history_data = []
                    for item in reversed(history_data):
                        product_name = item.get('product', '无标题')
                        if search_term and search_term.lower() not in product_name.lower(): continue
                        label = f"{item.get('time', '未知')} | {product_name}"
                        with st.expander(label):
                            st.caption(f"ID: {item.get('task_id')}")
                            if item.get('video_url'):
                                st.video(item.get('video_url'))
                                st.write(f"[🔗 下载]({item.get('video_url')})")
                except: pass

    st.markdown(f"## 🏭 Sora 视频工坊 <span style='color:red; font-size:0.8rem;'>v13.2 (Cookie修复版)</span>", unsafe_allow_html=True)
    main_col1, main_col2 = st.columns([1, 1.5])
    
    VOICE_MAP = {
        "Thai (泰语)": "th-TH-NiwatNeural", "English (英语)": "en-US-ChristopherNeural",
        "Malay (马来语)": "ms-MY-OsmanNeural", "Indonesian (印尼语)": "id-ID-ArdiNeural",
        "Vietnamese (越南语)": "vi-VN-NamMinhNeural", "Filipino (菲律宾语)": "fil-PH-AngeloNeural",
        "Spanish (西班牙语)": "es-ES-AlvaroNeural"
    }

    with main_col1:
        st.subheader("1. 创作设置")
        lang_opt = st.selectbox("目标语言", list(VOICE_MAP.keys()))
        product = st.text_input("产品名称")
        batch_dur = int(st.selectbox("时长", ["15s", "10s", "5s"]).replace("s",""))
        size_label = st.selectbox("画质", ["高清 (Large)", "标准 (Small)"])
        
        files = st.file_uploader("参考图", accept_multiple_files=True)
        b64_data, merged_img = process_uploaded_images(files)
        if merged_img: st.image(merged_img, caption=f"✅ 已拼合 {len(files)} 张图", use_column_width=True)

        st.markdown("---")
        col_gen_btn, col_tip = st.columns([2, 1])
        with col_gen_btn:
            if st.button(f"✨ 生成真人应用脚本", type="secondary", use_container_width=True):
                if not product: st.error("请输入产品名称")
                else:
                    with st.spinner("🤖 正在构思场景..."):
                        v_res, a_res = generate_ai_scripts(product, lang_opt, batch_dur, b64_data)
                        if v_res:
                            st.session_state['visual_script'] = v_res
                            st.session_state['audio_script'] = a_res
                            st.success("✅ 脚本已生成！")
                        else: st.error(a_res)

        v_script = st.text_area("视觉指令", value=st.session_state.get('visual_script', ""), height=100)
        a_script = st.text_area("口播文案", value=st.session_state.get('audio_script', ""), height=100)
        st.markdown("---")
        start_btn = st.button("🚀 启动视频生成", type="primary", use_container_width=True)

    with main_col2:
        st.subheader("🎬 实时制片监控")
        if start_btn:
            if not v_script or not a_script: st.error("脚本不能为空！")
            else:
                with st.status("处理中...", expanded=True) as status:
                    status.write("📡 提交任务...")
                    full_p = f"Language: {lang_opt}. Visual: {v_script}. Narrative: {a_script}"
                    res = submit_video_task(full_p, "sora-2", "16:9", batch_dur, "large" if "高清" in size_label else "small", b64_data)
                    tid = res.get("id")
                    if not tid:
                        status.update(label="❌ 提交失败", state="error")
                        st.error(f"错误: {res.get('error')}")
                        st.stop()
                    status.write(f"✅ 任务ID: {tid}")
                    status.write("⏳ 生成中...")
                    
                    v_url = None
                    bar = st.progress(0)
                    for i in range(120):
                        time.sleep(4)
                        r = check_result(tid)
                        data_layer = r.get("data", r) if isinstance(r.get("data"), dict) else r
                        current_status = str(data_layer.get("status")).lower()
                        if current_status in ["failed", "error"]:
                            status.update(label="❌ 失败", state="error")
                            st.error(f"失败: {data_layer.get('failure_reason')}")
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
                        status.write("🔨 合成音画 (首次运行较慢请耐心等待)...")
                        os.makedirs("temp", exist_ok=True)
                        v_p, a_p, f_p = f"temp/{tid}.mp4", f"temp/{tid}.mp3", f"temp/{tid}_f.mp4"
                        final_v = v_url
                        is_merged = False
                        try:
                            with open(v_p, 'wb') as f: f.write(requests.get(v_url).content)
                            asyncio.run(generate_tts(a_script, VOICE_MAP[lang_opt], a_p))
                            if merge_av(v_p, a_p, f_p):
                                is_merged = True
                                final_v = f_p
                            else: st.warning("音频合成失败，使用原片")
                        except: pass
                        status.update(label="✨ 完成", state="complete")
                        st.video(final_v)
                        with open(final_v if is_merged else v_p, "rb") as f:
                            st.download_button("⬇️ 下载视频", f, file_name=f"FINAL_{tid}.mp4")
                        save_to_history({"task_id": tid, "product": product, "time": datetime.now().strftime("%H:%M"), "video_url": v_url, "user": st.session_state["username"]})
