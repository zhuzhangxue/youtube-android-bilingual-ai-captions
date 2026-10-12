# YouTube Android 双语 AI 字幕

这是一个基于 **Anchored AI Captions** 的 Morphe 补丁构建仓库。

目标很简单：

- 外语视频同时显示 **原文 + 中文翻译**
- 中文翻译继续使用 Anchored AI Captions 的 **上下文翻译**
- 双语显示不会额外发起一次翻译请求，因此不会因为显示原文而额外增加 API Token 消耗

示例：

```text
This isn't what I was getting at.
我想表达的并不是这个意思。
```

## 当前状态

- 基线：Anchored AI Captions v1.5.1
- 目标 YouTube：21.20.405
- 已通过 GitHub Actions 编译
- 生成包：`anchored-ai-captions-bilingual.mpp`
- 双语字幕默认开启，也可以在 AI 字幕设置里的「双语字幕」开关关闭

## 使用方式

1. 在 Morphe Manager 中导入生成的 `.mpp`
2. 用它修补 YouTube 21.20.405
3. 不要同时勾选原版 Anchored AI Captions 的同名 AI 字幕补丁，以免冲突
4. 在 YouTube → Settings → Morphe → Video → AI caption translation 中配置你的 OpenAI-compatible API
5. 播放外语视频，在字幕自动翻译菜单里选择简体中文

## 显示策略

正常情况下：

```text
原文
AI 译文
```

如果某一段双语文本太长、无法在当前字幕区域内可靠显示，会优先保证译文可读，自动回退为仅显示译文。

## 上游与许可

本项目基于 [YYDarlinker/morphe-ai-caption-translator](https://github.com/YYDarlinker/morphe-ai-caption-translator) 修改，遵循其 GPLv3 许可。
