from dotenv import load_dotenv
import os
from pathlib import Path

env_path = Path(__file__).parent / ".env"
print(f"env完整路径：{env_path}")
print(f"文件是否存在：{env_path.exists()}")

load_dotenv(env_path)

print("LLM_API_KEY =", os.getenv("LLM_API_KEY"))
print("HTTP_PROXY =", os.getenv("HTTP_PROXY"))
