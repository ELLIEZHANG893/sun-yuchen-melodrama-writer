# 短剧连载写作器

一个 Codex / Claude Skill：你只写一个主题和大致故事框架，AI 按番茄爆款网文与竖屏狗血短剧的手法，帮你连续更新 10—20 章（集）。每章不长，但每章都有一个爽点或反转，结尾都切在最想看下一集的地方。

## 它会做什么

1. **设定卡**：一句话卖点、题材公式、主角底牌、对手、情感线、核心秘密。
2. **分集节奏表**：每集的爽点、反转和集尾钩子类型，黄金三集和卡点位置都排好。
3. **正文**：每次 3—5 集，章节默认 800—1500 字，剧本默认 1—2 分钟。
4. **连载状态卡**：记录已揭秘密和未回收伏笔，说“继续”就能接着写不崩。
5. **封面方案**（可选）：3 个方向的画面、构图和中英文提示词，出图后用脚本叠上片名和卖点。
6. **竖屏宫格漫画**（可选）：把一章做成彩色或黑白的四宫格 / 九宫格分镜，每格提示词 + 分镜 JSON，出图后用脚本拼版、加对白气泡。画风固定两套：彩色是暖调扁平图像小说风（自由错落分格，有无框大格、插入特写小格和速度线），黑白是日式都市恋爱漫画风（斜切分格、竖排宋体对白）；人物按“画法固定、长相每部作品单独设计”的方式保证画风稳定又有特色；第一次做漫画时会先给你看风格卡，问你要不要微调。

### 关于出图

这个 skill 不绑定任何画图工具，也不需要 API Key。它负责“从故事里想出画面、写好提示词”，你把提示词复制到即梦、Midjourney 等任意工具里出图，再交给排版脚本：

```bash
pip install pillow
# 封面：叠片名、一句话卖点、题材标签
python scripts/render_visuals.py cover --image cover.png --title "片名" --tagline "一句话卖点" --tag "女频·逆袭"
# 漫画：按分镜 JSON 拼成 1080×1920 竖屏漫画（加 --bw 转黑白）
# 彩色默认自由分格，查看模板：python scripts/render_visuals.py layouts
python scripts/render_visuals.py comic examples/ep01-comic.json
```

图里的中文全部由脚本叠加，避免图像模型写错字。脚本会自动找系统中文字体（苹方 / 微软雅黑 / 思源黑体），找不到时用 `--font` 指定。

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
- 给这部剧做个封面。
- 把第 3 章做成黑白九宫格漫画。

## 文件

- `SKILL.md`：工作流和输出规则。
- `references/hook-and-pacing.md`：节奏、钩子、卡点手册。
- `references/trope-library.md`：题材公式库。
- `references/case-notes.md`：热门 IP 拆解笔记。
- `references/voice-guide.md`：可选的零度冷叙述文风（原“零度狗血写作器”）。
- `references/cover-guide.md`：封面方向、构图、配色、提示词结构。
- `references/comic-guide.md`：宫格漫画选格、镜头、对白、人物一致性。
- `references/design.md`：漫画两套固定画风（彩色暖调扁平图像小说风 / 黑白日式都市恋爱漫画风）的风格卡、配色、分格模板、排版、提示词前缀；人物设计三层结构（画风层 / 作品层 / 角色层）、定妆表、提示词拼装顺序和出图质检；可调项。
- `examples/sample-12-episodes.md`：试跑样例（设定卡 + 节奏表 + 前三章）。
- `examples/sample-cover-and-comic.md`：同一个故事的外观卡、封面方案和第 1 章四宫格分镜。
- `examples/ep01-comic.json`、`examples/ep01-comic-bw.json`：彩色 / 黑白分镜 JSON 样例，可直接用脚本预览。
- `scripts/check_episodes.py`：检查每集字数和结尾钩子。
- `scripts/render_visuals.py`：封面叠字、宫格漫画排版、黑白转换。
- `agents/openai.yaml`：Codex 界面元数据。
