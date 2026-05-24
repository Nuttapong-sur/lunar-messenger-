import streamlit as st
import requests
import json
import base64
import re
import os

# ตั้งค่าหน้าเว็บให้เป็นแบบกว้าง
st.set_page_config(page_title="AI Roleplay Messenger", layout="wide")

# =================================================================
# ระบบจัดหน้าตาเว็บแอปให้เป็นสไตล์ Messenger UI (โหลดตลอดเวลา)
# =================================================================
messenger_css = """
<style>
/* จัดสไตล์กล่องแชตรวม */
.chat-container {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 10px 5px;
    width: 100%;
}
.msg-row {
    display: flex;
    width: 100%;
}
/* ข้อความฝั่งผู้ใช้ (ชิดขวา) */
.user-row {
    justify-content: flex-end;
}
/* ข้อความฝั่งบอท (ชิดซ้าย) */
.bot-row {
    justify-content: flex-start;
    flex-direction: column;
    align-items: flex-start;
}
/* สไตล์บับเบิ้ลข้อความ */
.bubble {
    max-width: 70%;
    padding: 12px 18px;
    border-radius: 20px;
    font-size: 16px;
    line-height: 1.5;
    box-shadow: 0px 2px 8px rgba(0,0,0,0.05);
    word-wrap: break-word;
    white-space: pre-wrap;
}
.user-bubble {
    background-color: #0084ff; /* สีฟ้า Messenger */
    color: white;
    border-bottom-right-radius: 4px;
}
.bot-bubble {
    background-color: rgba(255, 255, 255, 0.92); /* สีขาวโปร่งแสง */
    color: #1c1e21;
    border-bottom-left-radius: 4px;
}
/* สไตล์กล่องคลี่ดูความคิดในใจสไตล์ Messenger Extension */
.thought-details {
    max-width: 70%;
    width: 100%;
    margin-top: 6px;
    background: rgba(255, 255, 255, 0.7);
    padding: 10px 14px;
    border-radius: 14px;
    border-left: 4px solid #0084ff;
    box-shadow: 0px 2px 6px rgba(0,0,0,0.04);
}
.thought-summary {
    cursor: pointer;
    color: #0084ff;
    font-weight: bold;
    font-size: 14px;
    outline: none;
    user-select: none;
}
.thought-content {
    margin-top: 6px;
    font-size: 14px;
    color: #444;
    font-style: italic;
    white-space: pre-wrap;
}
/* ซ่อนไอคอนและกล่องแชตเดิมๆ ของ Streamlit ออกไป */
[data-testid="stChatMessage"] {
    background-color: transparent !important;
    box-shadow: none !important;
    padding: 0 !important;
}
</style>
"""
st.markdown(messenger_css, unsafe_allow_html=True)

# =================================================================
# ฟังก์ชันคัดแยกกล่องข้อความระดับอัจฉริยะ (เสถียร 100%)
# =================================================================
def parse_bot_reply(raw_text):
    thought = ""
    reply = raw_text
    
    thought_match = re.search(r'\[THOUGHT\](.*?)\[/THOUGHT\]', raw_text, re.IGNORECASE | re.DOTALL)
    if thought_match:
        thought = thought_match.group(1).strip()
    else:
        thought_start = re.search(r'\[THOUGHT\](.*)', raw_text, re.IGNORECASE | re.DOTALL)
        if thought_start:
            content_after = thought_start.group(1)
            reply_tag = re.search(r'\[REPLY\]', content_after, re.IGNORECASE)
            if reply_tag:
                thought = content_after[:reply_tag.start()].strip()
            else:
                thought = content_after.strip()

    reply_match = re.search(r'\[REPLY\](.*?)\[/REPLY\]', raw_text, re.IGNORECASE | re.DOTALL)
    if reply_match:
        reply = reply_match.group(1).strip()
    else:
        reply_start = re.search(r'\[REPLY\](.*)', raw_text, re.IGNORECASE | re.DOTALL)
        if reply_start:
            reply = reply_start.group(1).strip()
        else:
            thought_end = re.search(r'\[/THOUGHT\](.*)', raw_text, re.IGNORECASE | re.DOTALL)
            if thought_end:
                reply = thought_end.group(1).strip()

    reply = re.sub(r'\[/?THOUGHT\]', '', reply, flags=re.IGNORECASE).strip()
    reply = re.sub(r'\[/?REPLY\]', '', reply, flags=re.IGNORECASE).strip()
    
    if not reply:
        reply = re.sub(r'\[/?THOUGHT\]', '', raw_text, flags=re.IGNORECASE)
        reply = re.sub(r'\[/?REPLY\]', '', reply, flags=re.IGNORECASE).strip()
        
    return thought, reply

# =================================================================
# ระบบเซฟและโหลดข้อมูลแบบผูกมัดค่าปุ่มฝั่งซ้ายทั้งหมดลงไฟล์ถาวร
# =================================================================
DB_FILE = "chat_history.json"
DEFAULT_PERSONA = "คุณคือ ลูนาร์ แฟรี่ดราก้อนสายน้ำแข็งผู้ซื่อสัตย์ พลังเวทถูกผนึกด้วยปลอกคอโซ่ นิสัยนอบน้อมและพูดจาไพเราะกับนายท่าน"
DEFAULT_STYLE = "ยาวขึ้น 【ยาว / ฉลาดที่สุด】"

def save_data_permanently():
    """ฟังก์ชันเซฟข้อมูลทุกอย่างหน้าเว็บลงไฟล์ JSON ล็อกสถานะถาวร"""
    data = {
        "messages": st.session_state.get("messages", []),
        "summary": st.session_state.get("summary", ""),
        "persona": st.session_state.get("persona_val", DEFAULT_PERSONA),
        "style": st.session_state.get("style_val", DEFAULT_STYLE)
    }
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_data_permanently():
    """ฟังก์ชันดึงค่าข้อมูลตัวละครและสไตล์ล่าสุดกลับมาเรนเดอร์ใหม่หลังโดน F5"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                st.session_state.messages = data.get("messages", [])
                st.session_state.summary = data.get("summary", "")
                st.session_state.persona_val = data.get("persona", DEFAULT_PERSONA)
                st.session_state.style_val = data.get("style", DEFAULT_STYLE)
        except:
            st.session_state.messages = []
            st.session_state.summary = ""
            st.session_state.persona_val = DEFAULT_PERSONA
            st.session_state.style_val = DEFAULT_STYLE
    else:
        st.session_state.messages = []
        st.session_state.summary = ""
        st.session_state.persona_val = DEFAULT_PERSONA
        st.session_state.style_val = DEFAULT_STYLE

# ✨ [ใหม่!] ฟังก์ชัน Callback สำหรับล้างข้อมูลอย่างปลอดภัย รันก่อนหน้าจอวาดใหม่ ป้องกันตัวแดงกวนใจ
def reset_all_data_callback():
    st.session_state.messages = []
    st.session_state.summary = ""
    st.session_state.persona_val = DEFAULT_PERSONA
    st.session_state.style_val = DEFAULT_STYLE
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except:
            pass

# สั่งเช็กและโหลดค่าความจำกลับมาจากดิสก์ทันทีตั้งแต่เริ่มต้นรันหน้าเว็บแอป
if "messages" not in st.session_state:
    load_data_permanently()

# =================================================================
# 1. แถบควบคุมด้านข้าง (Sidebar) สำหรับตั้งค่าบอท
# =================================================================
st.sidebar.title("⚙️ การตั้งค่าระบบบอท")

default_api_key = ""
try:
    if "OPENROUTER_API_KEY" in st.secrets:
        default_api_key = st.secrets["OPENROUTER_API_KEY"]
except:
    pass

api_key = st.sidebar.text_input("1. ใส่ OpenRouter API Key", value=default_api_key, type="password")
model_name = st.sidebar.text_input("2. ชื่อโมเดล AI", value="deepseek/deepseek-chat")
bg_file = st.sidebar.file_uploader("3. อัปโหลดรูปภาพพื้นหลัง (ลากไฟล์วาง)", type=["png", "jpg", "jpeg"])

persona = st.sidebar.text_area(
    "4. ข้อมูลตัวละคร (Character Persona)", 
    key="persona_val",
    on_change=save_data_permanently
)

style_presets = {
    "ดั้งเดิม-พื้นฐาน 【สั้น / สำหรับมือใหม่】": "จงเขียนตอบกลับแบบสั้น กระชับ คุยสบายๆ เป็นกันเอง ไม่ต้องเน้นการบรรยายท่าทางหรือสภาพแวดล้อมยาวเกินไป เหมาะกับการโต้ตอบอย่างรวดเร็ว",
    "ดั้งเดิม-ขั้นสูง 【สั้น / เน้นอารมณ์】": "จงเขียนตอบกลับค่อนข้างสั้น แต่ให้เน้นการเข้าใจและแสดงออกทางอารมณ์ ความรู้สึกเบื้องลึกของตัวละครให้ดื่มด่ำยิ่งขึ้น",
    "ดั้งเดิม-แพลทินัม 【สั้น / ฉลาดที่สุด】": "จงเน้นคุณภาพการตอบกลับขั้นสูงสุด คมคาย มีไหวพริบ แสดงตัวตนของตัวละครได้อย่างชัดเจนที่สุดในบทสนทนาที่กระชับและได้ใจความ",
    "ยาวขึ้น 【ยาว / ฉลาดที่สุด】": "จงเขียนตอบกลับในรูปแบบที่ยาวขึ้น บรรยายมิติทางจิตวิทยา ความคิดในหัว ท่าทาง พฤติกรรม และการกระทำของตัวละครอย่างละเอียดและสมบูรณ์แบบที่สุด",
    "เรื่องราว 【ยาว / ฉลาดที่สุด】": "จงสร้างประสบการณ์เนื้อเรื่องสไตล์การเขียนนิยายแฟนตาซีระดับพรีเมียม บรรยายฉาก บรรยากาศ อารมณ์ และเหตุการณ์รอบตัวอย่างประณีตและลื่นไหลลึกซึ้ง"
}

style_list = list(style_presets.keys())
try:
    default_style_index = style_list.index(st.session_state.get("style_val", DEFAULT_STYLE))
except:
    default_style_index = 3

selected_style = st.sidebar.selectbox(
    "5. สไตล์การบรรยายบทบาท",
    style_list,
    index=default_style_index,
    key="style_val",
    on_change=save_data_permanently
)

st.sidebar.markdown(" ")
with st.sidebar.popover("🧹 ล้างประวัติการแชท (Reset)", use_container_width=True):
    st.warning("⚠️ แน่ใจใช่ไหมคะ? ประวัติแชตทั้งหมดและไดอารี่ความจำของลูนาร์จะถูกลบถาวรทันที ไม่สามารถกู้คืนได้!")
    # ✨ [แก้ไขปุ่ม] ผูกปุ่มเข้ากับระบบ Callback ตัวใหม่ ล้างไพ่เรียบเนียนไม่บึ้มหน้าจอแน่นอน
    st.button(
        "🔥 ยืนยันล้างข้อมูลทั้งหมด", 
        type="primary", 
        use_container_width=True, 
        on_click=reset_all_data_callback
    )

st.sidebar.markdown("---")
st.sidebar.subheader("🧠 บันทึกไดอารี่ความจำบอท")
with st.sidebar.expander("🔍 คลิกเปิดอ่านบันทึกความจำของตัวละคร"):
    if "summary" in st.session_state and st.session_state.summary:
        st.write(st.session_state.summary)
    else:
        st.caption("ตัวละครยังไม่ได้บันทึกอะไรลงไดอารี่ (จะเริ่มบันทึกอัตโนมัติเมื่อคุยกันยาวขึ้น)")

# =================================================================
# 2. ระบบโหลดภาพพื้นหลังครอบทับระบบแอป
# =================================================================
if bg_file is not None:
    file_bytes = bg_file.read()
    base64_image = base64.b64encode(file_bytes).decode()
    bg_css_contain = f"""
    <style>
    .stApp {{
        background-image: url("data:image/jpeg;base64,{base64_image}");
        background-size: contain;
        background-repeat: no-repeat;
        background-position: center;
        background-attachment: fixed;
        background-color: #262730;
    }}
    </style>
    """
    st.markdown(bg_css_contain, unsafe_allow_html=True)

# =================================================================
# 3. เตรียมระบบเรียกใช้ OpenRouter API
# =================================================================
def call_openrouter(messages_payload):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": messages_payload
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"⚠️ เกิดข้อผิดพลาดจาก API: {response.text}"
    except Exception as e:
        return f"⚠️ ไม่สามารถเชื่อมต่อ API ได้: {str(e)}"

def auto_summarize_chat():
    if len(st.session_state.messages) > 8 and len(st.session_state.messages) % 5 == 0:
        to_summarize = st.session_state.messages[:-4]
        
        reconstructed_summary_context = []
        for msg in to_summarize:
            if msg["role"] == "assistant" and msg.get("thought"):
                full_content = f"[THOUGHT]\n{msg['thought']}\n[/THOUGHT]\n[REPLY]\n{msg['content']}\n[/REPLY]"
                reconstructed_summary_context.append({"role": "assistant", "content": full_content})
            else:
                reconstructed_summary_context.append(msg)
                
        summary_prompt = [
            {"role": "system", "content": f"คุณคือตัวละครตามข้อกำหนดบทบาทนี้: {st.session_state.persona_val}\nจงสรุปเนื้อหาสำคัญ เหตุการณ์ และความรู้สึกที่คุณมีต่อนายท่านจากประวัติการคุยที่กำหนด โดยให้เขียนเรียบเรียงใหม่ทั้งหมดในลักษณะ 'ไดอารี่ความทรงจำส่วนตัวในมุมมองของคุณเองเท่านั้น' ใช้สรรพนามแทนตัวเอง (เช่น ข้า, ลูนาร์) และเรียกผู้ใช้ว่า นายท่าน ให้ตรงนิสัยอย่างเคร่งครัด เขียนให้กระชับและสลวย"},
            {"role": "user", "content": str(reconstructed_summary_context)}
        ]
        
        fresh_summary = call_openrouter(summary_prompt)
        if "⚠️" not in fresh_summary:
            st.session_state.summary = fresh_summary
            save_data_permanently()

# =================================================================
# 4. หน้าต่างแชทหลัก (Messenger Interface)
# =================================================================
st.title("💬 AI Roleplay Space")

st.markdown('<div class="chat-container">', unsafe_allow_html=True)

for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f'<div class="msg-row user-row"><div class="bubble user-bubble">{msg["content"]}</div></div>', unsafe_allow_html=True)
    else:
        thought_html = ""
        if msg.get("thought"):
            thought_html = f'<details class="thought-details"><summary class="thought-summary">💭 เปิดดูความคิดในใจของตัวละคร</summary><div class="thought-content">{msg["thought"]}</div></details>'
        st.markdown(f'<div class="msg-row bot-row"><div class="bubble bot-bubble">{msg["content"]}</div>{thought_html}</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ช่องรับข้อความจากผู้ใช้
if user_input := st.chat_input("พิมพ์บทสนทนาของคุณที่นี่..."):
    if not api_key:
        st.error("กรุณากรอก OpenRouter API Key ที่แถบด้านซ้ายก่อนเริ่มคุยนะครับ!")
        st.stop()

    st.markdown(f'<div class="msg-row user-row"><div class="bubble user-bubble">{user_input}</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="msg-row bot-row"><div class="bubble bot-bubble" style="opacity: 0.5; font-style: italic; background-color: rgba(255,255,255,0.6);">🔮 ลูนาร์กำลังเรียบเรียงคำพูดและคิดในใจ...</div></div>', unsafe_allow_html=True)

    st.session_state.messages.append({"role": "user", "content": user_input})
    save_data_permanently()
    auto_summarize_chat()

    thought_instruction = (
        "\n\n[กฎเหล็กเรื่องความคิดในใจ]\n"
        "ทุกครั้งที่คุณตอบกลับผู้ใช้ คุณจะต้องแบ่งโครงสร้างข้อความออกเป็น 2 ส่วนอย่างเคร่งครัดโดยใช้แท็กครอบดังนี้:\n"
        "[THOUGHT] เขียนความคิดในใจ ความรู้สึกที่แท้จริง แผนการ หรือสิ่งที่คุณคิดแต่ไม่กล้าพูดออกไปหาผู้ใช้โดยตรงในสถานการณ์นี้ [/THOUGHT]\n"
        "[REPLY] คำพูด บทสนทนา หรือพฤติกรรมภายนอกที่คุณแสดงออกไปให้ผู้ใช้เห็นจริงๆ [/REPLY]"
    )
    
    style_rule = f"\n\n[กฎเหล็กด้านรูปแบบการเขียนในรอบนี้]\n{style_presets[st.session_state.style_val]}"
    full_system_instruction = f"{st.session_state.persona_val}\n\n[ไดอารี่ความทรงจำส่วนตัวของคุณเกี่ยวกับเรื่องราวที่ผ่านมา: {st.session_state.summary}]{thought_instruction}{style_rule}"
    
    recent_context = st.session_state.messages[-8:]
    reconstructed_context = []
    
    for msg in recent_context:
        if msg["role"] == "assistant" and msg.get("thought"):
            full_content = f"[THOUGHT]\n{msg['thought']}\n[/THOUGHT]\n[REPLY]\n{msg['content']}\n[/REPLY]"
            reconstructed_context.append({"role": "assistant", "content": full_content})
        else:
            reconstructed_context.append(msg)

    api_messages = [{"role": "system", "content": full_system_instruction}] + reconstructed_context

    with st.spinner(""):
        bot_raw_reply = call_openrouter(api_messages)
    
    thought_content, reply_content = parse_bot_reply(bot_raw_reply)
            
    st.session_state.messages.append({
        "role": "assistant", 
        "content": reply_content,
        "thought": thought_content
    })
    save_data_permanently()
    
    st.rerun()