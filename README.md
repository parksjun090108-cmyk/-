# 김포고 급식 챗봇

김포고등학교 급식과 학사일정을 조회하는 Streamlit 챗봇입니다.

## 실행

```powershell
cd C:\Users\User\Downloads\gimpo_high_chatbot
python -m streamlit run streamlit_app.py
```

## 사용

채팅창에 질문을 입력하거나 사이드바 캘린더에서 날짜를 선택합니다. 로그인하면 선택한 날짜에 개인 일정을 저장할 수 있습니다.

OpenAI API를 쓰려면 `.env` 파일에 키를 넣습니다.

```env
OPENAI_API_KEY=your_openai_api_key_here
```
