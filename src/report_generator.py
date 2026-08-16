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

# ========== 分类白名单（和 report_generator.py 保持一致）==========
VALID_CATEGORIES = ["好评", "功能Bug", "体验问题", "功能建议", "其他"]

# ========== 初始化 ==========
load_dotenv(os.path.join(BASE_DIR, ".env"))
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")


def clean_json_text(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return text


def classify_one_review(text: str) -> dict:
    prompt = f"""你是一个APP用户评论分类助手。请对以下评论进行分类，并生成简短摘要。

分类标签定义（只能选一个）：
- 好评：用户明确表达满意、推荐、赞美，无明显负面诉求
- 功能Bug：功能失效、崩溃、卡顿、计时错误、数据异常等程序缺陷
- 体验问题：付费墙频繁、广告过多、交互繁琐、订阅提示骚扰等使用体验不佳
- 功能建议：用户希望新增功能、优化内容、增加免费计划等改进建议
- 其他：无法归入以上四类的评论

评论内容：
{text}

请严格以 JSON 格式返回，不要包含任何额外文字，格式如下：
{{"category": "分类标签", "summary": "一句话摘要"}}"""

    response = Generation.call(
        model="qwen-turbo",
        prompt=prompt,
        temperature=0.1,
        result_format="text"
    )

    if response.status_code != 200:
        raise RuntimeError(f"API错误: {getattr(response, 'message', response)}")

    raw_content = response.output.text
    if not raw_content:
        raise RuntimeError("模型返回空文本")

    cleaned = clean_json_text(raw_content)
    result = json.loads(cleaned)

    if "category" not in result:
        raise KeyError(f"返回JSON缺少category字段，实际键: {list(result.keys())}")

    category = result.get("category", "其他")
    if category not in VALID_CATEGORIES:
        category = "其他"

    return {
        "category": category,
        "summary": result.get("summary", "")
    }


def run_classify():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        reviews = json.load(f)

    stat = {cat: 0 for cat in VALID_CATEGORIES}
    result_list = []

    for idx, item in enumerate(reviews):
        text = item.get("clean_content", "")
        print(f"\n=======处理第 {idx+1} 条=======")
        try:
            res = classify_one_review(text)
            item["category"] = res["category"]
            item["summary"] = res["summary"]
            stat[res["category"]] += 1
            print(f"  ✅ {res['category']}: {res['summary']}")
        except Exception as e:
            print(f"  ❌ 异常: {e}")
            item["category"] = "其他"
            item["summary"] = f"解析失败:{str(e)}"
            stat["其他"] += 1
        result_list.append(item)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result_list, f, ensure_ascii=False, indent=2)

    print("\n=====分类统计结果=====")
    for k, v in stat.items():
        print(f"  {k}: {v} 条")
    print(f"输出文件: {os.path.abspath(OUTPUT_PATH)}")


if __name__ == "__main__":
    run_classify()
