import os
import re
import json
import traceback
import dashscope
from dashscope import Generation
from dotenv import load_dotenv

# ========== 路径配置 ==========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(BASE_DIR, "output", "cleaned_reviews.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "output", "classified_reviews.json")

# ========== 分类白名单 ==========
VALID_CATEGORIES = ["产品质量", "物流配送", "服务态度", "价格性价比", "其他"]

# ========== 初始化 ==========
load_dotenv(os.path.join(BASE_DIR, ".env"))
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")


def clean_json_text(raw: str) -> str:
    """清洗模型返回文本，提取纯 JSON"""
    print(f"    [清洗-1] 原始文本: [{raw}]")
    if not raw:
        return ""
    # 去除 markdown 代码块
    text = re.sub(r"```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()
    print(f"    [清洗-2] 去markdown后: [{text}]")
    # 剥除外层多余引号
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
        print(f"    [清洗-3] 剥外层引号: [{text}]")
    # 正则提取第一个 {...} 块
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
        print(f"    [清洗-4] 正则提取JSON: [{text}]")
    return text


def classify_one_review(text: str) -> dict:
    """调用 Generation 接口对单条评论分类，全程打印调试信息"""
    prompt = f"""你是一个电商评论分类助手。请对以下评论进行分类，并生成简短摘要。

分类标签只能从以下选项中选择一个：
{', '.join(VALID_CATEGORIES)}

评论内容：
{text}

请严格以 JSON 格式返回，不要包含任何额外文字，格式如下：
{{"category": "分类标签", "summary": "一句话摘要"}}"""

    # ---- 阶段1: 调用 API ----
    print(f"  [阶段1] 调用 Generation.call...")
    response = Generation.call(
        model="qwen-turbo",
        prompt=prompt,
        temperature=0.1,
        result_format="text"
    )
    print(f"  [阶段1] status_code = {response.status_code}")
    print(f"  [阶段1] 完整响应 = {response}")

    if response.status_code != 200:
        code = getattr(response, 'code', 'unknown')
        msg = getattr(response, 'message', str(response))
        raise RuntimeError(f"API错误 code={code}, message={msg}")

    # ---- 阶段2: 提取 text ----
    print(f"  [阶段2] 提取 response.output.text...")
    try:
        raw_content = response.output.text
        print(f"  [阶段2] raw_content = [{raw_content}]")
    except AttributeError as e:
        print(f"  [阶段2] ❌ 提取失败: {e}")
        print(f"  [阶段2] response.output 的属性 = {dir(response.output)}")
        raise RuntimeError(f"响应结构异常: {e}")

    if not raw_content:
        raise RuntimeError("模型返回空文本")

    # ---- 阶段3: 清洗 JSON ----
    print(f"  [阶段3] 清洗JSON...")
    cleaned = clean_json_text(raw_content)

    # ---- 阶段4: 解析 JSON ----
    print(f"  [阶段4] json.loads 解析...")
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  [阶段4] ❌ JSON解析失败: {e}")
        print(f"  [阶段4] 待解析文本: [{cleaned}]")
        raise RuntimeError(f"JSON解析失败: {e}")

    print(f"  [阶段4] 解析结果 = {result}")
    print(f"  [阶段4] result 的键 = {list(result.keys())}")

    # ---- 阶段5: 校验字段 ----
    if "category" not in result:
        raise KeyError(f"返回JSON缺少category字段，实际键: {list(result.keys())}")

    category = result.get("category", "其他")
    if category not in VALID_CATEGORIES:
        print(f"  [阶段5] 分类 '{category}' 不在白名单，归为'其他'")
        category = "其他"

    return {
        "category": category,
        "summary": result.get("summary", "")
    }


def run_classify():
    print(f"[启动] API Key 前8位: {dashscope.api_key[:8]}...")
    try:
        print(f"[启动] dashscope 版本: {dashscope.__version__}")
    except AttributeError:
        import importlib.metadata
        print(f"[启动] dashscope 版本: {importlib.metadata.version('dashscope')}")

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        reviews = json.load(f)
    print(f"[启动] 读取到 {len(reviews)} 条评论")

    stat = {cat: 0 for cat in VALID_CATEGORIES}
    result_list = []

    for idx, item in enumerate(reviews):
        text = item.get("clean_content", "")
        print(f"\n{'='*50}")
        print(f"处理第 {idx+1}/{len(reviews)} 条")
        print(f"评论内容: {text[:80]}")
        print(f"{'='*50}")
        try:
            res = classify_one_review(text)
            item["category"] = res["category"]
            item["summary"] = res["summary"]
            stat[res["category"]] += 1
            print(f"  ✅ 成功: category={res['category']}")
        except Exception as e:
            print(f"\n  ❌ 最终异常类型: {type(e).__name__}")
            print(f"  ❌ 最终异常信息: {e}")
            print(f"  ❌ 完整堆栈:")
            traceback.print_exc()
            item["category"] = "其他"
            item["summary"] = f"解析失败:{str(e)}"
            stat["其他"] += 1
        result_list.append(item)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result_list, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print("分类统计结果:")
    for k, v in stat.items():
        print(f"  {k}: {v} 条")
    print(f"输出文件: {os.path.abspath(OUTPUT_PATH)}")


if __name__ == "__main__":
    run_classify()
