# 示例：封面方案 + 第 1 章四宫格分镜

> 接 `sample-12-episodes.md` 的故事。用户输入：“给这部剧做个封面，再把第 1 章做成彩色四宫格。”
> 采用默认值：封面 3:4、3 个方向；漫画 2x2、彩色（暖调扁平图像小说风，用户确认不微调）。

## 角色外观卡

```text
【外观卡】林晚｜27岁中国女性，齐肩黑色直发，鹅蛋脸，眉眼清冷，左手腕一块旧皮带手表，米色风衣，里面白衬衫
Lin Wan: 27-year-old Chinese woman, shoulder-length straight black hair, oval face, cool calm eyes, worn leather-strap watch on left wrist, beige trench coat over a white shirt

【外观卡】周美芬（母亲）｜55岁中国女性，烫过的短卷发，颧骨高，嘴角下垂，深紫色针织开衫，手指上一枚金戒指
Zhou Meifen: 55-year-old Chinese woman, short permed curly hair, high cheekbones, downturned mouth, dark purple knit cardigan, gold ring on her finger

【外观卡】顾衍｜30岁中国男性，个子高，短碎发，细框眼镜，白大褂，胸前蓝色工作牌
Gu Yan: 30-year-old Chinese man, tall, short textured hair, thin-framed glasses, white doctor's coat, blue ID badge on his chest
```

## 封面方案

```text
方案 A｜悬念道具型（推荐：卖点里的“配型单”就是最强钩子）
画面：林晚低头捏着一张医院报告，指节发白；背景虚化处，母亲站在病房门口，脸色发白
构图：报告和林晚的手在画面中上部；母亲在右上方虚化；下方 40% 是暗色病房地面，放片名（bottom）
配色：医院冷绿 + 暗红强调 #E8423F
中文提示词：竖版短剧海报，写实电影感。27岁中国女性，齐肩黑色直发，鹅蛋脸，眉眼清冷，左手腕一块旧皮带手表，米色风衣，里面白衬衫，低头紧捏一张写满字的医院报告，指节发白，神情震惊而克制。背景虚化，55岁中国女性，烫过的短卷发，颧骨高，嘴角下垂，深紫色针织开衫，站在病房门口，脸色苍白。医院走廊，冷绿色日光灯，侧光，浅景深，中近景。画面下方40%简洁偏暗，留给标题。比例3:4。不要文字、字母、水印、logo。
英文提示词：Vertical drama poster, cinematic realism. Lin Wan: 27-year-old Chinese woman, shoulder-length straight black hair, oval face, cool calm eyes, worn leather-strap watch on left wrist, beige trench coat over a white shirt, looking down, gripping a hospital report so hard her knuckles turn white, shocked but restrained. In the blurred background, a 55-year-old Chinese woman with short permed curly hair, high cheekbones, downturned mouth, dark purple knit cardigan, standing pale at a ward doorway. Hospital corridor, cold green fluorescent light, side lighting, shallow depth of field, medium close-up. Empty darker space in the lower 40% for a title. Aspect ratio 3:4. No text, no letters, no watermark, no logo.
排版命令：
python scripts/render_visuals.py cover --image cover-a.png \
  --title "配型单上写着：无亲缘关系" --tagline "全家逼我捐肾那天，真相露出来了" \
  --tag "女频·逆袭" --ratio 3:4 --position bottom --accent "#E8423F"

方案 B｜人物对峙型
画面：林晚 C 位正面直视镜头；母亲在她身后侧上方，一手按在她肩上，像在压着她
构图：两人在画面上 60%；片名在下方（bottom）
配色：暗红 + 黑，强调色 #E8423F

方案 C｜情绪特写型
画面：林晚脸部大特写，眼眶红但没有掉泪，嘴角一点冷笑；手腕上的旧手表入画
构图：脸占上 2/3，右侧留暗部；片名在下方（bottom）
配色：冷灰蓝 + 暖色手表，强调色 #F2B33D
```

B、C 的提示词按 A 的结构写，人物描述照抄外观卡。用户选定后写进 `story-bible.md`。

## 第 1 章 4 格分镜（彩色，自由分格 `4-inset`）

本章结尾是配型报告的揭露，所以选“插入特写”模板：第 4 格是压在第 3 格左下角的特写小格。各格比例来自 `python scripts/render_visuals.py sizes --layout 4-inset`。

先确认画风（第一次做漫画时）：

> 这部漫画准备用【彩色｜暖调扁平图像小说风】：奶油色纸底 + 粗黑格框，干净的黑色描线、平涂上色，配色是暖粉、蜜桃、天蓝、奶黄、鼠尾草绿；背景用纯色块衬托情绪，人物大眼睛、腮红，汗珠和抖动线表现紧张；气泡白底黑框横排，音效字是大号黑色手写体。
> 直接用这个风格，还是想微调？可以调：色调、线条粗细、人物比例、背景写实程度、对白横排 / 竖排、字体。

用户回答“就这样”，写进 `story-bible.md` 的“画风”一节。

风格前缀（每格原样复制，来自 design.md）：flat-color graphic novel illustration, clean even black outlines, minimal shading, soft warm palette of coral pink, peach, sky blue, butter yellow and sage green, cream paper texture, solid pastel color-block background behind the character, large expressive eyes, rosy blush, freckles, cute and expressive, comic emotion marks like sweat drops and shake lines

```text
格1 起｜中景｜病房，母亲把笔硬塞进林晚手里，指甲掐进她手背；病床上的年轻男人扭头看墙
  气泡：母亲「签吧，就一个字的事。」（右上）
  旁白：市医院 肾内科病房
  提示词（英）：[风格前缀], [林晚外观卡], [周美芬外观卡], the mother forcing a pen into Lin Wan's hand, nails digging into the back of her hand, a young man in a hospital bed turning his face to the wall, crowded hospital ward, medium shot, empty space at the top right for a speech bubble, aspect ratio 1:1, no text, no letters, no speech bubbles, no watermark

格2 承｜近景｜母亲一巴掌拍在床头柜上，水杯跳起；林晚低头不动
  气泡（爆炸）：母亲「我养你二十七年，你跟我讲条件？」（左下）
  音效：啪！（右上）
  提示词（英）：……furious mother slamming her palm on the bedside table, a water glass jumping, Lin Wan standing still with her head down, close shot, low angle on the mother, empty space at the bottom left……

格3 转｜大场景格｜走廊尽头，顾衍把牛皮纸文件袋递给林晚，手却没有松开（人物放右侧和上方，左下角会被第 4 格盖住）
  气泡：顾衍「有没有人跟你提过……你是领养的？」（左上）
  气泡（内心）：林晚「我是我妈亲生的。」（右上）
  提示词（英）：……[顾衍外观卡] handing a kraft paper envelope to Lin Wan but not letting go, end of a quiet hospital corridor, window light, medium shot, empty space at the top left and bottom right……

格4 合（钩子）｜插入小格·特写｜林晚手里报告的最后一页，背景虚化处母亲站在病房门口，脸色一点点发白
  旁白：无生物学亲缘关系
  气泡：母亲「谁让你们查这个的？」（右下）
  提示词（英）：……close-up of a hospital report page in Lin Wan's hands, in the blurred background the mother standing at the ward door turning pale, tense atmosphere, close-up, empty space at the bottom right……
```

分镜 JSON 见 `examples/ep01-comic.json`。没有图片时直接运行也能预览排版：

```bash
python scripts/render_visuals.py comic examples/ep01-comic.json
```

换成黑白时：贴黑白风格卡再确认一次，风格前缀换成 design.md 第二节的黑白前缀，JSON 里写 `"mode": "bw"`，对白会自动竖排。黑白四宫格样例见 `examples/ep01-comic-bw.json`；九宫格按选格表把第 1 章拆成 9 格，写 `"layout": "3x3"`。
