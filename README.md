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


## 在 Morphe 里直接用 URL 添加

现在这个仓库已经可以直接作为 **Morphe Remote Patch Source** 使用。

在 Morphe Manager：

1. Sources → +
2. 选择 Remote
3. 粘贴：

```text
https://github.com/zhuzhangxue/youtube-android-bilingual-ai-captions
```

4. 点 Add

Morphe 会读取仓库根目录的 `patches-bundle.json`，自动下载当前稳定版 `.mpp`。以后版本更新时，也可以在 Sources 页面直接点 Update。

也可以在 Android 浏览器直接打开这个一键添加链接：

```text
https://morphe.software/add-source?github=zhuzhangxue/youtube-android-bilingual-ai-captions
```

Morphe 会弹出确认添加补丁源的页面。

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


## Morphe 安装界面一直停在“正在安装”

部分 Android / 厂商 ROM 上，Morphe 的“系统安装程序”会先走 Android PackageInstaller Session。
如果系统没有正常弹出确认界面，可以使用这两个办法：

1. 直接点 Morphe 的「保存」，再从文件管理器点生成的 APK 安装。
2. 在 Morphe → 设置 → 系统 → 默认安装程序 中选择「Play商店安装」。
   这个选项仍然调用系统安装界面，只是把 Google Play 商店记录为安装来源；它不会真的从 Play 商店重新下载 APK。

这个问题属于 Morphe Manager 的安装流程，与双语字幕补丁本身无关。
