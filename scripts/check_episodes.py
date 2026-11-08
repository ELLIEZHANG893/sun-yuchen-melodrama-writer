#!/usr/bin/env python3
"""检查连载正文：每章（集）字数是否在范围内，并列出每集最后一句供人工检查钩子。

用法：
    python scripts/check_episodes.py 正文.md            # 默认章节 800—1500 字
    python scripts/check_episodes.py 正文.md --script   # 剧本 400—800 字
    python scripts/check_episodes.py 正文.md --min 600 --max 1200
"""
import argparse
import re
import sys

HEADING = re.compile(r"^\s*#*\s*第\s*([0-9一二三四五六七八九十百零两]+)\s*[章集]")
SKIP = re.compile(r"^\s*(【(下集预告|连载状态)|-{3,}\s*$|\*{3,}\s*$)")
WEAK_ENDINGS = ("终于明白", "暗暗发誓", "心想", "从此", "一切都结束了", "松了一口气")


def count_chars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def split_episodes(lines):
    episodes, current = [], None
    for line in lines:
        if HEADING.match(line):
            current = {"title": line.strip().lstrip("#").strip(), "body": []}
            episodes.append(current)
        elif current is not None and not SKIP.match(line):
            current["body"].append(line.rstrip("\n"))
    return episodes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--script", action="store_true", help="剧本形态，默认 400—800 字")
    p.add_argument("--min", type=int)
    p.add_argument("--max", type=int)
    a = p.parse_args()

    lo, hi = (400, 800) if a.script else (800, 1500)
    lo = a.min or lo
    hi = a.max or hi

    with open(a.file, encoding="utf-8") as f:
        episodes = split_episodes(f.readlines())
    if not episodes:
        sys.exit("没有找到“第N章 / 第N集”标题。")

    problems = 0
    for ep in episodes:
        body = [l for l in ep["body"] if l.strip()]
        n = count_chars("".join(body))
        last = body[-1].strip() if body else ""
        flags = []
        if n < lo * 0.7:
            flags.append("偏短")
        elif n > hi * 1.3:
            flags.append("偏长")
        if any(w in last for w in WEAK_ENDINGS):
            flags.append("结尾像总结，钩子可能偏弱")
        problems += bool(flags)
        mark = "⚠ " + "，".join(flags) if flags else "OK"
        print(f"{ep['title']}｜{n} 字｜{mark}\n    最后一句：{last[:60]}")

    print(f"\n共 {len(episodes)} 集，目标 {lo}—{hi} 字，需检查 {problems} 集。")


if __name__ == "__main__":
    main()
