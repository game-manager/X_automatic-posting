import json
import os
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import tweepy
from google import genai


POSTED_IDEAS_FILE = Path("posted_ideas.txt")
URL_PATTERN = re.compile(r"(https?://|www\.)", re.IGNORECASE)
MAX_TWEET_LENGTH = 280
MAX_GENERATION_ATTEMPTS = 5
SIMILARITY_LIMIT = 0.72
GEMINI_MODEL = "gemini-2.5-flash"


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_posted_ideas() -> list[str]:
    if not POSTED_IDEAS_FILE.exists():
        return []

    return [
        line.strip()
        for line in POSTED_IDEAS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def is_too_similar(new_text: str, old_ideas: list[str]) -> bool:
    for old_text in old_ideas:
        similarity = SequenceMatcher(None, new_text, old_text).ratio()
        if similarity >= SIMILARITY_LIMIT:
            return True
    return False


def extract_json(text: str) -> dict:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).replace("JSON\n", "", 1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError(f"Gemini response did not contain JSON: {text}")

    return json.loads(cleaned[start : end + 1])


def generate_idea_with_gemini(past_ideas: list[str]) -> tuple[str, str]:
    client = genai.Client()

    recent_ideas = "\n".join(f"- {idea}" for idea in past_ideas[-80:])
    prompt = f"""
あなたはXで毎日投稿する「生活を便利にするアプリ案」を考える企画者です。
次の条件をすべて守って、まだ出していない新しいアプリ案を1つだけ作ってください。

条件:
- 日本語
- URLやハッシュタグは入れない
- 医療診断、投資助言、危険行為、個人情報の悪用につながる案は避ける
- 中学生にもわかりやすい
- アプリ名は短く、覚えやすい
- 特徴は45文字以内
- 出力はJSONのみ
- JSONのキーは name と feature の2つだけ

過去に投稿した案:
{recent_ideas if recent_ideas else "まだありません"}

出力例:
{{"name":"忘れ物ガード","feature":"明日の予定から必要な持ち物を自動で通知してくれる"}}
""".strip()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    data = extract_json(response.text or "")

    name = str(data.get("name", "")).strip()
    feature = str(data.get("feature", "")).strip()

    if not name or not feature:
        raise RuntimeError(f"Gemini response is missing name or feature: {data}")

    return name, feature


def format_message(name: str, feature: str) -> str:
    message = (
        "【今日のアプリ案】\n"
        f"アプリ名（仮）：{name}\n"
        f"特徴：{feature}\n"
        "気に入ったらいいねやリポストをお願いします！反応が多ければアプリ化を検討します。\n"
        "※すぐにアプリ化を保証するものではありません。疑問点はコメントやDMでどうぞ。"
    )

    if URL_PATTERN.search(message):
        raise RuntimeError("URL posts are disabled. Gemini generated a URL.")

    if len(message) > MAX_TWEET_LENGTH:
        raise RuntimeError(f"Generated post is longer than 280 characters: {len(message)}")

    return message


def generate_unique_post() -> tuple[str, str, str]:
    past_ideas = load_posted_ideas()

    last_error: Exception | None = None
    for _ in range(MAX_GENERATION_ATTEMPTS):
        try:
            name, feature = generate_idea_with_gemini(past_ideas)
            message = format_message(name, feature)
            similarity_check_text = f"{name} {feature}"

            if is_too_similar(similarity_check_text, past_ideas):
                last_error = RuntimeError("Generated idea was too similar to a past idea.")
                time.sleep(1)
                continue

            return name, feature, message
        except Exception as exc:
            last_error = exc
            time.sleep(1)

    raise RuntimeError(f"Failed to generate a unique post: {last_error}")


def save_posted_idea(name: str, feature: str) -> None:
    posted_at = datetime.now(timezone.utc).isoformat()
    line = f"{posted_at} | {name} | {feature}\n"

    with POSTED_IDEAS_FILE.open("a", encoding="utf-8") as file:
        file.write(line)


def post_to_x(message: str) -> str:
    api_key = get_required_env("X_API_KEY")
    api_secret = get_required_env("X_API_SECRET")
    access_token = get_required_env("X_ACCESS_TOKEN")
    access_token_secret = get_required_env("X_ACCESS_TOKEN_SECRET")

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )

    response = client.create_tweet(text=message)
    return response.data.get("id") if response.data else "unknown"


def main() -> None:
    get_required_env("GEMINI_API_KEY")

    name, feature, message = generate_unique_post()
    tweet_id = post_to_x(message)
    save_posted_idea(name, feature)

    print("Posted successfully.")
    print(f"Tweet ID: {tweet_id}")
    print(message)


if __name__ == "__main__":
    main()
