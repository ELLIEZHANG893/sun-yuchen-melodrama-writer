# 短剧连载写作器

一个 Codex / Claude Skill：你只写一个主题和大致故事框架，AI 按番茄爆款网文与竖屏狗血短剧的手法，帮你连续更新 10—20 章（集）。每章不长，但每章都有一个爽点或反转，结尾都切在最想看下一集的地方。

## 它会做什么

1. **设定卡**：一句话卖点、题材公式、主角底牌、对手、情感线、核心秘密。
2. **分集节奏表**：每集的爽点、反转和集尾钩子类型，黄金三集和卡点位置都排好。
3. **正文**：每次 3—5 集，章节默认 800—1500 字，剧本默认 1—2 分钟。
4. **连载状态卡**：记录已揭秘密和未回收伏笔，说“继续”就能接着写不崩。

## 研究基础

- 24 部番茄热门网文与红果等平台爆款短剧的设定、题材标签和业内拆解（见 `references/case-notes.md`）。
- 黄金三章、情绪循环、单集秒数结构、八种集尾钩子、二卡三卡卡点（见 `references/hook-and-pacing.md`）。
- 14 个女频 / 男频题材公式（见 `references/trope-library.md`）。

只学机制，不复用任何作品的人物、设定组合或句子。

## 安装

Codex：

```bash
git clone https://github.com/ELLIEZHANG893/sun-yuchen-melodrama-writer.git ~/.codex/skills/short-drama-serial-writer
```

Claude Code：

```bash
git clone https://github.com/ELLIEZHANG893/sun-yuchen-melodrama-writer.git ~/.claude/skills/short-drama-serial-writer
```

重新打开后即可使用。

## 示例

- 写一部 12 集女频短剧：被退婚的女配其实是集团真正的继承人。
- 主题“重生回到高考前一天”，写 15 章网文，每章 1000 字左右。
- 把这个框架写成 10 集竖屏短剧剧本：外卖员给前女友的婚礼送餐。
- 继续更新下一批。
- 用零度冷叙述文风写一部 10 集豪门分手短剧。

## 文件

- `SKILL.md`：工作流和输出规则。
- `references/hook-and-pacing.md`：节奏、钩子、卡点手册。
- `references/trope-library.md`：题材公式库。
- `references/case-notes.md`：热门 IP 拆解笔记。
- `references/voice-guide.md`：可选的零度冷叙述文风（原“零度狗血写作器”）。
- `examples/sample-12-episodes.md`：试跑样例（设定卡 + 节奏表 + 前三章）。
- `scripts/check_episodes.py`：检查每集字数和结尾钩子。
- `agents/openai.yaml`：Codex 界面元数据。
