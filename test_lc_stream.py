import asyncio
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import os
import time

async def main():
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY", "sk-1234"),
        base_url="https://api.deepseek.com/v1"
    )
    # Actually deepseek-v4-flash doesn't exist, it's just what I saw in test_stream3.py which might be a fake name or from another provider.
    print("Testing LangChain stream...")

if __name__ == "__main__":
    asyncio.run(main())
