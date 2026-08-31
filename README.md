# 零度狗血写作器

一个独立构建的 Codex Skill，用于创作或改写中文第一人称狗血故事、独白和短剧。

它研究孙宇晨公开虚构长文《我的女友景甜》的可观察文本特征，但不复刻原文人物、事件或句子，也不用于冒充现实人物。

## 特点

- 情节激烈，叙述克制。
- 用数字表现关系代价，用物件保存记忆。
- 呈现维持主角世界的第三方劳动。
- 用第一次拒绝制造转折，用残留程序完成结尾。
- 长文默认使用自然段落，不机械地一句一行。

## 安装

```bash
git clone https://github.com/ELLIEZHANG893/sun-yuchen-melodrama-writer.git ~/.codex/skills/sun-yuchen-melodrama-writer
```

重新打开 Codex 后即可使用。

## 示例

- 用零度狗血风格写一篇第一人称豪门分手故事。
- 把现有剧情改成 90 秒克制独白，保留自然段落。
- 为亲缘题材设计一个由旧物推动的八集季纲。

## 文件

- `SKILL.md`：触发范围、工作流和输出规则。
- `references/voice-guide.md`：来源、独立统计与详细文体机制。
- `agents/openai.yaml`：Codex 界面元数据。

主锚点来自[公开 X 帖子](https://x.com/justinsuntron/status/2092932777612390850)及其[官方排版源](https://github.com/HEJustinSun/my-girlfriend-jingtian-latex/blob/main/main.tex)。原作明确标注为虚构，本仓库不收录原文全文。
