import streamlit as st
import requests
import time
import json
import os
from datetime import datetime

# ================= 配置区域 =================
# API_KEY = "sk-xxx"  <-- 这一行删掉或注释掉
API_KEY = st.secrets["API_KEY"]  # <-- 改成这一行！从后台读取密码
HOST = "https://grsaiapi.com"
# ===========================================

st.set_page_config(page_title="Sora 视频工坊 v5.0", layout="wide", page_icon="🎬")

# === 💾 历史记录系统 (本地数据库) ===
HISTORY_FILE = "history.json"

def load_history():
    """读取历史记录"""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_to_history(record):
    """保存一条新记录"""
    history = load_history()
    # 避免重复保存
    if any(h['task_id'] == record['task_id'] for h in history):
        return
    history.append(record)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# CSS 样式优化
st.markdown("""
<style>
    .stTextInput>div>div>input {border-radius: 8px;}
    .stSelectbox>div>div>div {border-radius: 8px;}
    .stButton>button {border-radius: 8px; height: 3.5em; background-color: #6200ea; color: white; font-weight: bold;}
    .script-box {background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #6200ea; margin-bottom: 20px;}
    /* 侧边栏按钮样式 */
    section[data-testid="stSidebar"] button {height: auto; text-align: left; padding: 10px; background-color: #f9f9f9; color: #333; border: 1px solid #eee;}
    section[data-testid="stSidebar"] button:hover {border-color: #6200ea; color: #6200ea;}
</style>
""", unsafe_allow_html=True)

# === ⬅️ 最左侧：历史记录栏 ===
with st.sidebar:
    st.markdown("### 📜 历史记录 (History)")
    st.caption("点击下方列表可回看视频")
    
    history_list = load_history()
    
    if not history_list:
        st.info("暂无记录，快去生成第一个视频吧！")
    else:
        # 倒序遍历，让最新的显示在最上面
        for item in reversed(history_list):
            # 按钮文字：时间 + 产品名
            label = f"🕒 {item['time'][5:-3]} | {item['product']}"
            if st.button(label, key=item['task_id'], use_container_width=True):
                # 点击后，将当前查看的内容设置为这条历史记录
                st.session_state['view_mode'] = 'history'
                st.session_state['current_record'] = item

# === 主界面 ===
st.markdown("## 🎬 电商视频智造局 <span style='font-size:0.8rem; color:purple'>v5.0 (历史回溯版)</span>", unsafe_allow_html=True)

col_config, col_preview = st.columns([1.3, 2]) 

# 脚本模板库
SCRIPT_TEMPLATES = {
    "痛点解决型 (Pain Point)": {
        "visual_prompt": "Split screen comparison or Before/After sequence. Start with a chaotic/problematic scene (black and white), then transition to the product solving the problem (bright colors). Fast paced cuts.",
        "script_structure": "1. 提问痛点 (你还在忍受...吗？)\n2. 引入产品 (试试这个神器...)\n3. 展示效果 (看！瞬间解决...)\n4. 召唤下单 (限时优惠，点击左下角！)"
    },
    "沉浸质感型 (Cinematic/ASMR)": {
        "visual_prompt": "Extreme close-up, macro photography, slow motion. Focus on texture, material, and light reflection. Soft background music mood. Elegant camera movements.",
        "script_structure": "1. 材质特写 (看这个细节...)\n2. 使用感受 (触感像云朵一样...)\n3. 氛围营造 (生活品质的提升...)\n4. 结尾升华 (值得你拥有。)"
    },
    "暴力促销型 (Hard Sell)": {
        "visual_prompt": "Dynamic text overlays, bright flashing colors, rapid transitions. Product shown in use with happy people. High energy commercial style.",
        "script_structure": "1. 利益炸弹 (今天只要9块9！)\n2. 核心卖点 (买一送一，功能强大...)\n3. 紧迫感 (仅限前100名！)\n4. 强力促单 (手慢无，快抢！)"
    }
}

# === 配置区 (Config) ===
with col_config:
    tab_visual, tab_script, tab_setting = st.tabs(["📸 画面素材", "📝 脚本与策略", "⚙️ API设置"])
    
    with tab_visual:
        uploaded_images = st.file_uploader("产品图片", type=['png', 'jpg'], accept_multiple_files=True, label_visibility="collapsed")
        uploaded_video = st.file_uploader("参考视频", type=['mp4'], label_visibility="collapsed")
        st.markdown("---")
        product_name = st.text_input("产品名称", placeholder="例如：蓝色蛋白皮耳机套")
        c1, c2 = st.columns(2)
        with c1: size_label = st.selectbox("比例", ["竖屏 (9:16)", "横屏 (16:9)"])
        with c2: duration_label = st.selectbox("时长", ["5s", "10s", "15s"])
        language = st.selectbox("投放语言", ["英语", "印尼语", "马来语", "越南语", "泰语", "中文"])

    with tab_script:
        script_style = st.radio("视频营销风格", list(SCRIPT_TEMPLATES.keys()))
        selected_template = SCRIPT_TEMPLATES[script_style]
        st.info(selected_template["script_structure"])
        user_script_detail = st.text_area("脚本细节补充", placeholder="例如：强调安装很方便...")

    with tab_setting:
        model_name = st.text_input("模型名称 (Model Name)", value="sora-2")

    st.markdown("---")
    # 如果点击了生成，强制切换回“生成模式”
    if st.button("🚀 生成视频 & 脚本", use_container_width=True):
        st.session_state['view_mode'] = 'generating'
    
    # 逻辑处理
    aspect_ratio = "9:16" if "竖屏" in size_label else "16:9"
    duration_val = int(duration_label.replace("s", ""))

# === API 函数 ===
def submit_task():
    url = f"{HOST}/v1/video/sora-video"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    prompt_text = f"Commercial product video for {product_name}. Language: {language}."
    prompt_text += f" [Visual Style]: {SCRIPT_TEMPLATES[script_style]['visual_prompt']}."
    if user_script_detail: prompt_text += f" {user_script_detail}"
    if uploaded_images: prompt_text += f" [Ref: {len(uploaded_images)} images]"
    
    payload = {
        "prompt": prompt_text,
        "model": model_name,
        "aspect_ratio": aspect_ratio,
        "duration": duration_val,
        "expand_prompt": True 
    }
    try:
        return requests.post(url, headers=headers, json=payload, timeout=30).json()
    except Exception as e:
        return {"error": str(e), "data": None}

def check_result(task_id):
    url = f"{HOST}/v1/draw/result"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        return requests.post(url, headers=headers, json={"task_id": task_id}, timeout=30).json()
    except Exception as e:
        return {"error": str(e)}

# === 预览区 (Preview) ===
with col_preview:
    # 模式 A: 正在查看历史记录
    if st.session_state.get('view_mode') == 'history' and st.session_state.get('current_record'):
        record = st.session_state['current_record']
        st.info(f"📜 正在回看历史记录：{record['time']}")
        
        # 显示视频
        st.video(record['video_url'])
        
        # 显示当时生成的脚本
        st.markdown(f"""
        <div class='script-box'>
            <strong>历史脚本：</strong><br>
            {record['script']}
        </div>
        """, unsafe_allow_html=True)
        
        # 下载按钮
        st.download_button("下载此视频", data=requests.get(record['video_url']).content, file_name=f"{record['product']}.mp4")

    # 模式 B: 正在生成新视频 (或准备生成)
    elif st.session_state.get('view_mode') == 'generating':
        if not product_name:
            st.warning("⚠️ 请输入产品名称")
        else:
            # 1. 准备脚本显示
            raw_script = SCRIPT_TEMPLATES[script_style]['script_structure']
            formatted_script = raw_script.replace("1.", "🎤 1.").replace("\n", "<br>")
            
            st.markdown(f"""
            <div class='script-box'>
                <strong>为您生成的带货脚本：</strong><br>
                {formatted_script}
            </div>
            """, unsafe_allow_html=True)
            
            status_box = st.status(f"正在使用 [{model_name}] 提交...", expanded=True)
            res = submit_task()
            
            data_part = res.get("data") or {} 
            task_id = data_part.get("task_id") or res.get("task_id") or data_part.get("id")
            
            if not task_id:
                status_box.update(label="❌ 提交失败", state="error")
                st.error("API 报错信息：")
                st.json(res)
            else:
                status_box.write(f"✅ 任务 ID: {task_id}")
                progress_bar = status_box.progress(0, text="排队中...")
                
                retry = 0
                while True:
                    time.sleep(4)
                    check = check_result(task_id)
                    check_data = check.get("data") or {}
                    status = check_data.get("status")
                    video_url = check_data.get("video_url")
                    
                    if status in ["SUCCESS", "COMPLETED"]:
                        progress_bar.progress(100, text="渲染完成！")
                        status_box.update(label="✨ 生成完成", state="complete", expanded=False)
                        
                        # === 🔥 关键步骤：存入历史数据库 ===
                        new_record = {
                            "task_id": task_id,
                            "product": product_name,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "video_url": video_url,
                            "script": formatted_script
                        }
                        save_to_history(new_record)
                        st.toast("✅ 已自动保存到历史记录") # 弹出小提示
                        
                        # 显示结果
                        st.success("🎥 视频已就绪")
                        st.video(video_url)
                        break
                        
                    elif status == "FAILED":
                        status_box.update(label="❌ 失败", state="error")
                        st.error(f"原因: {check_data.get('message')}")
                        break
                    else:
                        retry += 1
                        sim_progress = min(retry * 2, 95)
                        msg = check_data.get("message") or status or "PROCESSING"
                        progress_bar.progress(sim_progress, text=f"AI 渲染中... {sim_progress}% [{msg}]")
                        if retry > 150: 
                            status_box.update(label="⚠️ 超时", state="error")
                            break
    
    # 模式 C: 默认空状态
    else:
        st.info("👈 请在左侧输入产品信息并点击生成，或者在最左侧点击历史记录回看。")
        st.markdown("""
        <div style='text-align:center; padding:50px; color:#ccc; border:2px dashed #eee;'>
            <h3>Sora 视频工坊</h3>
            <p>支持断点续传 | 历史回溯 | 脚本生成</p>
        </div>

        """, unsafe_allow_html=True)
