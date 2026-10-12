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
    "version=1.0.2\ncaptionBuildId=bilingual-1.0.2-layout\n",
)

# 1) Carry the exact source subtitle with each accepted translated display unit.
# Translation itself remains completely upstream-owned: same context window, API call,
# cache, validation and timing.
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

# 2) Keep a bilingual pair on one timed page whenever it can fit in four lines.
# If even the minimum subtitle size cannot fit it, fall back to the translated half only
# rather than paging source and translation separately.
presentation = "translation-core/src/main/java/app/yydarlinker/deepseekcaptions/TranslationPresentation.java"
replace_once(
    presentation,
    '''        TranslationBudget budget=new TranslationBudget(geometry.width,geometry.minimumPx,geometry.preferredPx,spec);
        List<RebuildPageLayout.Page> planned=RebuildPageLayout.plan(text,start,end,budget,spec);
''',
    '''        TranslationBudget budget=new TranslationBudget(geometry.width,geometry.minimumPx,geometry.preferredPx,spec);
        int bilingualBreak=text==null?-1:text.indexOf('\n');
        if(bilingualBreak>0 && bilingualBreak<text.length()-1){
            float size=budget.preferredPx;
            while(size>budget.minimumPx && !spec.fits(text,size,budget.width,4))
                size=Math.max(budget.minimumPx,size-.5f);
            if(spec.fits(text,size,budget.width,4)){
                StaticLayout layout=spec.layout(text,size,budget.width);
                int cut=layout.getLineCount()>1?layout.getLineEnd(0):text.length();
                CaptionLinePlan line=new CaptionLinePlan(
                    text,0,text.length(),cut,
                    layout.getLineMax(0),
                    layout.getLineCount()>1?layout.getLineMax(1):0,
                    CaptionLinePlan.CutClass.LANGUAGE_BOUNDARY);
                return Collections.singletonList(new CaptionDisplayPage(
                    line.displayText,start,end,0,text.length(),
                    "BILINGUAL_SOURCE_EVENT",line));
            }
            text=text.substring(bilingualBreak+1).trim();
        }
        List<RebuildPageLayout.Page> planned=RebuildPageLayout.plan(text,start,end,budget,spec);
''',
)

# 3) Let the existing overlay render bilingual pages in up to four lines.
# This deliberately does NOT add new views, settings classes or lifecycle hooks;
# v1.0.0 did that and crashed on the user's device. Here we only widen the existing
# TextView's line budget when the already-prepared display text is bilingual.
overlay = "ui/src/main/java/app/yydarlinker/deepseekcaptions/CaptionOverlayV2.java"

replace_once(
    overlay,
    '''    String reason=shown.isEmpty() && currentGuard!=null ? currentGuard.blankReason() : "";
''',
    '''    boolean bilingualBody=ownedCaption && shown.indexOf('\n')>=0;
    int visibleMaxLines=bilingualBody?4:2;
    if(bilingualBody){
      while(size>minimum && !measuredSpec.fits(shown,size,inner,visibleMaxLines))
        size=Math.max(minimum,size-.5f);
    }
    String reason=shown.isEmpty() && currentGuard!=null ? currentGuard.blankReason() : "";
''',
)

replace_once(
    overlay,
    '''    text.setTextSize(TypedValue.COMPLEX_UNIT_PX,size);
    text.setSingleLine(false);text.setMaxLines(2);text.setEllipsize(null);
''',
    '''    text.setTextSize(TypedValue.COMPLEX_UNIT_PX,size);
    text.setSingleLine(false);text.setMaxLines(visibleMaxLines);text.setEllipsize(null);
''',
)

replace_once(
    overlay,
    '''  private static int applyVisibleText(TextView text,String shown,float size,int maximumInnerPx,CaptionRenderSpec spec,CaptionLinePlan line) {
    boolean same=CaptionSettingPreference.sameText(text.getText(),shown)&&text.getTextSize()==size&&text.getPaint().equalsForTextMeasurement(spec.paint(size));
    spec.apply(text);if(text.getTextSize()!=size)text.setTextSize(TypedValue.COMPLEX_UNIT_PX,size);if(!CaptionSettingPreference.sameText(text.getText(),shown))text.setText(shown);
    if(text.getMaxLines()!=2){text.setSingleLine(false);text.setMaxLines(2);}if(text.getEllipsize()!=null)text.setEllipsize(null);
''',
    '''  private static int applyVisibleText(TextView text,String shown,float size,int maximumInnerPx,CaptionRenderSpec spec,CaptionLinePlan line) {
    int maxLines=shown.indexOf('\n')>=0?4:2;
    boolean same=CaptionSettingPreference.sameText(text.getText(),shown)&&text.getTextSize()==size&&text.getPaint().equalsForTextMeasurement(spec.paint(size));
    spec.apply(text);if(text.getTextSize()!=size)text.setTextSize(TypedValue.COMPLEX_UNIT_PX,size);if(!CaptionSettingPreference.sameText(text.getText(),shown))text.setText(shown);
    if(text.getMaxLines()!=maxLines){text.setSingleLine(false);text.setMaxLines(maxLines);}if(text.getEllipsize()!=null)text.setEllipsize(null);
''',
)

replace_once(
    overlay,
    '''    float contentWidthPx=line!=null?Math.max(line.line1Px,line.line2Px):same&&text.getLayout()!=null&&text.getLayout().getLineCount()==1?text.getLayout().getLineMax(0):spec.actualWidth(spec.layout(shown,size,maximumInnerPx));
''',
    '''    float contentWidthPx=maxLines>2?spec.actualWidth(spec.layout(shown,size,maximumInnerPx))
        :line!=null?Math.max(line.line1Px,line.line2Px)
        :same&&text.getLayout()!=null&&text.getLayout().getLineCount()==1?text.getLayout().getLineMax(0)
        :spec.actualWidth(spec.layout(shown,size,maximumInnerPx));
''',
)

text = read(overlay)
needle = "spec.fits(shown,text.getLayout(),boxWidthPx-padding,2))return boxWidthPx;"
count = text.count(needle)
if count != 2:
    raise SystemExit(f"{overlay}: expected 2 two-line fit checks, found {count}")
write(overlay, text.replace(
    needle,
    "spec.fits(shown,text.getLayout(),boxWidthPx-padding,maxLines))return boxWidthPx;"
))
print("patched bilingual fit checks")

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

presentation_sha = hashlib.sha256((ROOT / presentation).read_bytes()).hexdigest()
presentation_hits = 0
for row in provenance.get("new_files", []):
    if row.get("path") == presentation:
        row["sha256"] = presentation_sha
        presentation_hits += 1
if presentation_hits != 1:
    raise SystemExit(f"expected one provenance row for TranslationPresentation, found {presentation_hits}")

provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("updated core provenance")
print("Bilingual v1.0.2 layout patch applied.")
