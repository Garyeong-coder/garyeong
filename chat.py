import google.generativeai as genai
from dotenv import load_dotenv
import os
import streamlit as st
import json
import time
import sys

# --- 초기 설정 ---
# 환경 변수 및 API 키 설정
try:
    load_dotenv()
except Exception as e:
    # .env 파일이 없어도 계속 진행
    pass

# API 키 설정 - 여러 방식으로 시도
api_key = None

# 방법 1: 환경변수에서 가져오기
api_key = os.getenv("GOOGLE_API_KEY")

# 방법 2: Streamlit secrets에서 가져오기 (수정된 방식)
if not api_key:
    try:
        if hasattr(st, 'secrets') and 'GOOGLE_API_KEY' in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
    except Exception as e:
        pass

# API 키가 없으면 에러 처리
if not api_key:
    st.error("🔑 Google API Key가 필요합니다!")
    st.info("""
    **API Key 설정 방법:**
    
    **방법 1: .env 파일 사용 (권장)**
    1. 프로젝트 폴더에 `.env` 파일 생성
    2. 파일에 다음과 같이 작성: `GOOGLE_API_KEY=your_actual_api_key_here`
    
    **방법 2: Streamlit Secrets 사용**
    1. `.streamlit/secrets.toml` 파일 생성
    2. 파일에 다음과 같이 작성: `GOOGLE_API_KEY = "your_actual_api_key_here"`
    
    **API Key 발급 방법:**
    - Google AI Studio (https://makersuite.google.com/app/apikey)에서 발급
    """)
    st.stop()

# API 키 설정
try:
    genai.configure(api_key=api_key)
except Exception as e:
    st.error(f"❌ API 키 설정 중 오류가 발생했습니다: {e}")
    st.info("API 키가 올바른지 확인해주세요.")
    st.stop()

# 모델 로드 (캐시 사용)
@st.cache_resource
def get_model():
    """Gemini 1.5 Flash 모델을 가져옵니다."""
    try:
        return genai.GenerativeModel('gemini-1.5-flash-latest')
    except Exception as e:
        st.error(f"❌ 모델을 불러오는 중 오류가 발생했습니다: {e}")
        return None

model = get_model()
if not model:
    st.error("모델을 로드할 수 없습니다. 페이지를 새로고침해주세요.")
    st.stop()

# --- 핵심 기능 함수 ---

def evaluate_writing(user_input, grade, subject, writing_type):
    """[평가] 모드: 루브릭을 기준으로 글을 채점하고 피드백을 반환합니다."""
    if not user_input or len(user_input.strip()) < 10:
        return 0, "글이 너무 짧아요. 10자 이상 작성 후 '평가 받기'를 다시 시도해 주세요."
    
    prompt = f"""
당신은 '{grade}' 학생을 가르치는 친절한 AI 글쓰기 선생님입니다. 특히 '{subject}' 과목과 관련된 글쓰기에 대한 조언을 해주는 전문가입니다.
학생이 제출한 '{writing_type}' 글을 아래의 루브릭에 따라 채점하고, 학생의 학년과 선택한 과목에 맞는 맞춤형 피드백을 제공해주세요.

<루브릭>
1. 주제의 명확성 (30점): 글의 중심 생각이나 이야기가 명확하게 드러나는가?
2. 내용의 풍부함 (40점): 구체적인 예시, 묘사, 느낌이 잘 표현되어 글이 생생한가?
3. 글의 구조 (30점): 서론-본론-결론 혹은 시작-중간-끝의 흐름이 자연스러운가?

<처리 지침>
1. 루브릭에 따라 글을 채점하여 총점을 계산합니다.
2. 총점이 80점 이상이면, 피드백은 "정말 훌륭해요! {grade} 학생의 눈높이에서 볼 때 이 글은 완성된 것 같아요."와 같이 더 이상 수정할 필요가 없다는 최종 칭찬과 격려의 메시지를 담아주세요.
3. 총점이 80점 미만이면, 칭찬할 부분과 함께 개선할 점 한 가지를 구체적인 예시를 들어 친절하게 설명해주세요. 특히 '{subject}' 과목의 특성을 고려한 조언을 포함하면 더욱 좋습니다.
4. 반드시 아래와 같은 JSON 형식으로만 응답해야 합니다. 다른 설명은 절대 추가하지 마세요.

{{
  "score": <계산된 총점>,
  "feedback": "<점수에 따른 맞춤형 피드백 내용>"
}}

<학생의 글>
{user_input}
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # API 호출 시 더 안전한 설정 사용
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=800,
                )
            )
            
            # 응답 텍스트 정리
            response_text = response.text.strip()
            
            # JSON 코드 블록 제거
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()
            
            # JSON 파싱
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError:
                # JSON 파싱 실패 시 재시도
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                else:
                    return 50, "응답을 처리하는 중에 문제가 발생했어요. 다시 시도해주세요."
            
            # 필수 필드 확인
            if 'score' not in result or 'feedback' not in result:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                else:
                    return 50, "평가 결과를 처리하는 중에 문제가 발생했어요. 다시 시도해주세요."
            
            # 점수 검증 및 변환
            try:
                score = int(result['score'])
                feedback = str(result['feedback'])
            except (ValueError, KeyError):
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                else:
                    return 50, "점수를 처리하는 중에 문제가 발생했어요. 다시 시도해주세요."
            
            # 점수 범위 보정
            if not (0 <= score <= 100):
                score = max(0, min(100, score))
            
            return score, feedback
            
        except Exception as e:
            print(f"평가 오류 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return 30, f"죄송해요. 평가를 완료할 수 없었습니다. 잠시 후 다시 시도해주세요."
            time.sleep(2)  # 재시도 전 대기 시간 증가
    
    return 30, "여러 번 시도했지만 평가를 완료할 수 없었어요. 네트워크 상태를 확인하고 다시 시도해주세요."

def have_conversation(user_input, grade, subject, writing_type, chat_history):
    """[대화] 모드: 이전 대화 내용을 바탕으로 자유로운 대화를 진행합니다."""
    
    # 대화 기록 생성 (최근 8개만 사용하여 토큰 절약)
    history_str = ""
    recent_messages = chat_history[-8:] if len(chat_history) > 8 else chat_history
    
    for msg in recent_messages:
        role = "학생" if msg["role"] == "user" else "선생님"
        content = msg["content"]
        
        # 내용이 너무 길면 요약
        if len(content) > 100:
            content = content[:97] + "..."
        
        if "score" in msg:
            history_str += f"{role}: (점수: {msg['score']}점) {content}\n"
        else:
            history_str += f"{role}: {content}\n"

    prompt = f"""
당신은 '{grade}' 학생을 가르치는 친절하고 다정한 AI 글쓰기 선생님입니다. 
학생과 글쓰기에 대한 자유로운 대화를 나눠주세요.
'{subject}' 과목과 '{writing_type}' 글쓰기에 대한 대화의 맥락을 유지해주세요.

학생의 질문에 답하고, 글쓰기 실력을 향상시키는 데 도움이 되는 격려와 조언을 해주세요.
답변은 2-3문장의 짧고 친근한 대화체로 해주세요.

<최근 대화 내용>
{history_str}

학생의 새로운 질문: {user_input}

선생님의 답변:
"""

    try:
        response = model.generate_content(
            prompt, 
            generation_config=genai.GenerationConfig(
                temperature=0.7, 
                max_output_tokens=500
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"대화 생성 오류: {e}")
        return "죄송해요. 답변을 생성하는 중에 문제가 발생했어요. 다시 질문해 주세요! 😊"

# --- Streamlit 앱 UI ---
st.set_page_config(
    page_title="AI 글쓰기 튜터", 
    page_icon="✍️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("✍️ AI 글쓰기 튜터")
st.markdown("글을 제출하여 평가받거나, AI 튜터와 자유롭게 대화하며 글쓰기 실력을 키워보세요! 🌟")

# 사이드바 설정
with st.sidebar:
    st.header("📝 학습 설정")
    
    grade = st.selectbox(
        "학년을 선택하세요:",
        ('1-2학년군', '3-4학년군', '5-6학년군'), 
        index=1  # 기본값: 3-4학년군
    )
    
    subject = st.selectbox(
        "관련 과목을 선택하세요:", 
        ('국어', '수학', '사회', '과학', '그 외'), 
        index=0
    )
    
    writing_type = st.radio(
        "글의 종류를 선택하세요:", 
        ('편지글', '주장하는 글', '일기', '독후감', '설명하는 글'), 
        index=2
    )
    
    st.divider()
    
    # 현재 설정 표시
    st.info(f"**현재 설정**\n- 학년: {grade}\n- 과목: {subject}\n- 글 종류: {writing_type}")
    
    if st.button("🔄 대화 초기화", use_container_width=True):
        # 안전한 세션 초기화
        if "messages" in st.session_state:
            st.session_state.messages = []
        if "mode" in st.session_state:
            st.session_state.mode = 'evaluate'
        st.success("✅ 대화가 초기화되었습니다!")
        time.sleep(0.5)
        st.rerun()

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

if 'mode' not in st.session_state:
    st.session_state.mode = 'evaluate'  # 기본 모드는 '평가'

# 모드 변경 콜백 함수
def set_mode(mode_name):
    st.session_state.mode = mode_name

# 모드 선택 버튼
col1, col2 = st.columns(2)
with col1:
    st.button(
        "📝 평가 받기", 
        on_click=set_mode, 
        args=('evaluate',), 
        use_container_width=True,
        type="primary" if st.session_state.mode == 'evaluate' else "secondary",
        help="글을 작성하면 AI가 채점해줍니다"
    )
with col2:
    st.button(
        "💬 자유롭게 대화하기", 
        on_click=set_mode, 
        args=('chat',), 
        use_container_width=True,
        type="primary" if st.session_state.mode == 'chat' else "secondary",
        help="AI 선생님과 자유롭게 대화할 수 있습니다"
    )

# 현재 모드 표시
if st.session_state.mode == 'evaluate':
    st.info("📝 **평가 모드**: 글을 입력하면 AI가 채점하고 피드백을 제공합니다.")
else:
    st.info("💬 **대화 모드**: AI 선생님과 자유롭게 글쓰기에 대해 대화할 수 있습니다.")

# 이전 대화 내용 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # 평가 점수가 있는 메시지 처리
        if message["role"] == "assistant" and "score" in message:
            score = message["score"]
            if score >= 80:
                st.success(f"🎉 **훌륭해요! 총점: {score}점** / 100점")
            elif score >= 60:
                st.info(f"📝 **좋아요! 총점: {score}점** / 100점")
            elif score >= 40:
                st.warning(f"📚 **조금 더! 총점: {score}점** / 100점")
            elif score > 0:
                st.error(f"💪 **힘내요! 총점: {score}점** / 100점")
            else:
                st.error("❌ 평가 중 오류가 발생했습니다")
        
        st.write(message["content"])

# 사용자 입력 처리
current_mode_text = "평가 받기 📝" if st.session_state.mode == 'evaluate' else "자유 대화 💬"
placeholder = f"현재 모드: {current_mode_text} - 여기에 입력하세요..."

if prompt := st.chat_input(placeholder):
    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 사용자 메시지 표시
    with st.chat_message("user"):
        st.write(prompt)

    # AI 응답 생성 및 표시
    with st.chat_message("assistant"):
        if st.session_state.mode == 'evaluate':
            # 평가 모드
            with st.spinner("📝 AI 선생님이 꼼꼼히 평가하고 있어요..."):
                score, feedback = evaluate_writing(prompt, grade, subject, writing_type)
                
                # 점수에 따른 표시
                if score >= 80:
                    st.success(f"🎉 **훌륭해요! 총점: {score}점** / 100점")
                elif score >= 60:
                    st.info(f"📝 **좋아요! 총점: {score}점** / 100점")
                elif score >= 40:
                    st.warning(f"📚 **조금 더! 총점: {score}점** / 100점")
                elif score > 0:
                    st.error(f"💪 **힘내요! 총점: {score}점** / 100점")
                else:
                    st.error("❌ 평가 중 오류가 발생했습니다")
                
                st.write(feedback)
                
                # 세션에 저장
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": feedback, 
                    "score": score
                })
        else:
            # 대화 모드
            with st.spinner("💭 AI 선생님이 생각하고 있어요..."):
                response_text = have_conversation(prompt, grade, subject, writing_type, st.session_state.messages)
                st.write(response_text)
                
                # 세션에 저장
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response_text
                })

# 하단 안내
st.divider()
st.caption("💡 **평가 받기**: 글을 제출하면 AI가 루브릭에 따라 채점해줘요 | 💬 **자유 대화**: 글쓰기에 대한 질문이나 조언을 구할 수 있어요")

# 디버깅 정보 (개발용)
if st.checkbox("🔧 디버깅 정보 표시", value=False):
    st.json({
        "현재 모드": st.session_state.mode,
        "메시지 수": len(st.session_state.messages),
        "API 키 설정됨": bool(api_key),
        "Python 버전": sys.version,
    })
  
