import asyncio
from app_agent import generate_app

async def main():
    print("Testing with complexity_level='low' (gpt-5.4-mini)")
    try:
        res = await generate_app("버튼 1개 있는 빈 화면", provider="openai", complexity_level="low", generate_mode="code")
        print("SUCCESS! UI Components:", len(res.ui_components))
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(main())
