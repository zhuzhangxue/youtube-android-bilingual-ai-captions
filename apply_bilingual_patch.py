#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def replace_once(rel, old, new):
    text = read(rel)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{rel}: expected 1 match, found {count}: {old[:120]!r}")
    write(rel, text.replace(old, new, 1))
    print("patched", rel)


# Bundle identity.
replace_once(
    "patches/build.gradle.kts",
    '''        name = "Anchored AI Captions"
        description = "Real-time multilingual YouTube captions through a user-provided OpenAI-compatible API"
        source = "https://github.com/YYDarlinker/morphe-ai-caption-translator"
        author = "YYDarlinker"
        contact = "https://github.com/YYDarlinker/morphe-ai-caption-translator/issues"
        website = "https://github.com/YYDarlinker/morphe-ai-caption-translator"
''',
    '''        name = "Anchored AI Captions Bilingual"
        description = "Context-aware bilingual YouTube captions: original source plus AI translation"
        source = "https://github.com/zhuzhangxue/youtube-android-bilingual-ai-captions"
        author = "zhuzhangxue (bilingual fork) / YYDarlinker (upstream)"
        contact = "https://github.com/zhuzhangxue/youtube-android-bilingual-ai-captions/issues"
        website = "https://github.com/zhuzhangxue/youtube-android-bilingual-ai-captions"
'''
)

replace_once(
    "gradle.properties",
    "version=1.5.1\ncaptionBuildId=release-1.5.1\n",
    "version=1.0.1\ncaptionBuildId=bilingual-1.0.1-safe\n",
)

# Safe bilingual implementation:
# Keep the entire upstream overlay/settings stack untouched. Only at the final
# translated-unit boundary, prepend the exact source span to the translated text.
# This preserves Anchored's context-aware translation, cache, timing and API behavior,
# while avoiding the v1.0.0 overlay changes that caused launch crashes on a real device.
controller = "translation-core/src/main/java/app/yydarlinker/deepseekcaptions/RebuildController.java"

replace_once(
    controller,
    '    String text = "";\n',
    '    String text = "", bilingualSourceText = "";\n    boolean bilingualTranslatedUnit = false;\n',
)

replace_once(
    controller,
    '''            text = unit.text;
            unitEvents = unit.events.size();
''',
    '''            text = unit.text;
            bilingualSourceText = s.source.text(unit.from, unit.to);
            unitEvents = unit.events.size();
''',
)

replace_once(
    controller,
    '''            if(unit.blocked) {
              text="";eventId="source:"+eventId;fallbackReason="event_review";
            } else {
''',
    '''            if(unit.blocked) {
              text="";eventId="source:"+eventId;fallbackReason="event_review";
            } else {
              bilingualTranslatedUnit = !text.isEmpty() && bilingualSourceText != null
                  && !bilingualSourceText.trim().isEmpty();
''',
)

replace_once(
    controller,
    '''      String signature = (status ? "status:" : "caption:") + eventId + "|" + text + "|";
''',
    '''      if (bilingualTranslatedUnit) {
        text = bilingualSourceText.trim() + "\\n" + text;
      }
      String signature = (status ? "status:" : "caption:") + eventId + "|" + text + "|";
''',
)

# Keep upstream integration verification truthful after the intentional core adaptation.
provenance_path = ROOT / "docs/core-provenance.json"
provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
controller_sha = hashlib.sha256((ROOT / controller).read_bytes()).hexdigest()
hits = 0
for row in provenance.get("files", []):
    if row.get("destination") == controller:
        row["sha256"] = controller_sha
        hits += 1
if hits != 1:
    raise SystemExit(f"expected one provenance row for RebuildController, found {hits}")
provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("updated core provenance")
print("Bilingual safe-mode patch applied.")
