import os
import random
import re
from pathlib import Path

import tweepy


POSTS_FILE = Path("posts.txt")
URL_PATTERN = re.compile(r"(https?://|www\.)", re.IGNORECASE)
MAX_TWEET_LENGTH = 280


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_random_post() -> str:
    if not POSTS_FILE.exists():
        raise FileNotFoundError("posts.txt was not found.")

    posts = [
        line.strip()
        for line in POSTS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not posts:
        raise RuntimeError("posts.txt has no available posts.")

    text = random.choice(posts)

    if URL_PATTERN.search(text):
        raise RuntimeError("URL posts are disabled. Remove URLs from posts.txt.")

    if len(text) > MAX_TWEET_LENGTH:
        raise RuntimeError("Selected post is longer than 280 characters.")

    return text


def main() -> None:
    api_key = get_required_env("X_API_KEY")
    api_secret = get_required_env("X_API_SECRET")
    access_token = get_required_env("X_ACCESS_TOKEN")
    access_token_secret = get_required_env("X_ACCESS_TOKEN_SECRET")

    text = load_random_post()

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )

    response = client.create_tweet(text=text)
    tweet_id = response.data.get("id") if response.data else "unknown"
    print(f"Posted successfully. Tweet ID: {tweet_id}")


if __name__ == "__main__":
    main()
