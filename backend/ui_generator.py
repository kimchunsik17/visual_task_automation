import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

# Using the same llm setup as the rest of the app, assuming we can get api keys
def get_llm_for_ui(api_key: str = None, provider: str = "openai"):
    # api_key 가 있으면 사용자가 API 센터에 등록한 자기 키다 — 그대로 존중한다.
    # 없으면(시스템 기본) provider 층에 맡겨 LLM_PROVIDER=openrouter 설정을 따르게 한다.
    # 예전에는 여기서 늘 ChatOpenAI 를 직접 만들어, 시스템 기본이 OpenRouter 여도 openai.com 을
    # 때려 401 이 났다.
    if provider == "gemini":
        return ChatGoogleGenerativeAI(model="gemini-3.5-pro", google_api_key=api_key, temperature=0.2)
    if api_key:
        return ChatOpenAI(model="gpt-4o", openai_api_key=api_key, temperature=0.2)
    from llm.providers import create_runtime_chat_model

    return create_runtime_chat_model(model="gpt-4o")

UI_GENERATION_SYSTEM_PROMPT = """\
너는 전문적인 프론트엔드 개발자이자 UI/UX 디자이너다.
사용자의 요청에 따라 완성된 HTML 문서를 작성한다.

[요구사항]
1. 순수 HTML과 Tailwind CSS(CDN)를 사용하여 단일 HTML 파일을 생성한다.
2. Javascript(Vanilla JS)를 포함하여 동적인 상호작용을 구현한다.
3. React(JSX)는 사용하지 않는다. 반드시 브라우저에서 즉시 실행 가능한 순수 HTML이어야 한다.
4. Tailwind CSS 스크립트는 `<script src="https://cdn.tailwindcss.com"></script>` 를 추가한다.
5. 디자인은 매우 현대적이고 세련되어야 하며, Vercel v0 스타일의 깔끔한 컴포넌트를 지향한다.
6. 백엔드 워크플로우(업무 자동화 로직)와 연동될 수 있도록 주요 폼(form)의 제출 버튼이나 중요한 액션 버튼에는 `data-action="workflow-trigger"` 속성을 부여한다.
7. 응답은 마크다운 코드 블록(```html ... ```) 없이 순수한 HTML 코드 문자열 자체만 반환한다. (<html>부터 </html>까지)

[제약사항]
- 절대로 HTML 외의 설명 텍스트를 포함하지 않는다.
"""

async def generate_custom_ui(prompt: str, api_key: str, provider: str = "openai") -> str:
    llm = get_llm_for_ui(api_key, provider)
    
    chat_prompt = ChatPromptTemplate.from_messages([
        ("system", UI_GENERATION_SYSTEM_PROMPT),
        ("human", "{user_prompt}")
    ])
    
    chain = chat_prompt | llm
    
    response = await chain.ainvoke({"user_prompt": prompt})
    
    content = response.content.strip()
    
    # Remove markdown code blocks if the LLM hallucinated them
    if content.startswith("```html"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
        
    return content.strip()
