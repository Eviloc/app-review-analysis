import os
import dashscope
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")

print("=" * 50)
print(f"API Key 前8位: {dashscope.api_key[:8]}...")
print(f"API Key 长度: {len(dashscope.api_key)}")
# 修复：用 try 包裹，部分版本没有 __version__
try:
    print(f"dashscope 版本: {dashscope.__version__}")
except AttributeError:
    import importlib.metadata
    print(f"dashscope 版本: {importlib.metadata.version('dashscope')}")
print("=" * 50)

# ===== 测试1: Generation 接口 =====
print("\n【测试1】Generation.call 接口")
try:
    from dashscope import Generation
    resp = Generation.call(
        model="qwen-turbo",
        prompt="说一个字：好",
        result_format="text"
    )
    print(f"  status_code: {resp.status_code}")
    print(f"  完整响应对象: {resp}")
    print(f"  resp.output 类型: {type(resp.output)}")
    print(f"  resp.output: {resp.output}")
    if hasattr(resp.output, 'text'):
        print(f"  resp.output.text: {resp.output.text}")
    else:
        print(f"  resp.output 没有 text 属性，可用属性: {dir(resp.output)}")
except Exception as e:
    print(f"  ❌ 异常类型: {type(e).__name__}")
    print(f"  ❌ 异常信息: {e}")
    import traceback
    traceback.print_exc()

# ===== 测试2: Chat 接口 =====
print("\n【测试2】Chat.call 接口")
try:
    from dashscope.chat import Chat
    resp = Chat.call(
        model="qwen-turbo",
        messages=[{"role": "user", "content": "说一个字：好"}],
        result_format="message"
    )
    print(f"  status_code: {resp.status_code}")
    print(f"  完整响应对象: {resp}")
    print(f"  resp.output 类型: {type(resp.output)}")
    print(f"  resp.output: {resp.output}")
    if hasattr(resp.output, 'choices'):
        print(f"  choices: {resp.output.choices}")
        if resp.output.choices:
            msg = resp.output.choices[0].message
            print(f"  message.content: {msg.content}")
except Exception as e:
    print(f"  ❌ 异常类型: {type(e).__name__}")
    print(f"  ❌ 异常信息: {e}")
    import traceback
    traceback.print_exc()
