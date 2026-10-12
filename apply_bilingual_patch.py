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


# Give the fork a distinct bundle identity.
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
        source = "https://github.com/zhuzhangxue/youtube-android-double-translated_titles"
        author = "zhuzhangxue (bilingual fork) / YYDarlinker (upstream)"
        contact = "https://github.com/zhuzhangxue/youtube-android-double-translated_titles/issues"
        website = "https://github.com/zhuzhangxue/youtube-android-double-translated_titles"
'''
)

replace_once(
    "gradle.properties",
    "version=1.5.1\ncaptionBuildId=release-1.5.1\n",
    "version=1.5.1-bilingual.1\ncaptionBuildId=bilingual-1.5.1-1\n",
)

# Persistent setting.
replace_once(
    "infrastructure/src/main/java/app/yydarlinker/deepseekcaptions/DeepSeekConfig.java",
    '    private static final String DISPLAY_TEXT_DEBUG = "display_text_debug";\n',
    '    private static final String DISPLAY_TEXT_DEBUG = "display_text_debug";\n'
    '    private static final String BILINGUAL_CAPTIONS = "bilingual_captions";\n',
)
replace_once(
    "infrastructure/src/main/java/app/yydarlinker/deepseekcaptions/DeepSeekConfig.java",
    "    static final boolean DEFAULT_DISPLAY_TEXT_DEBUG = false;\n",
    "    static final boolean DEFAULT_DISPLAY_TEXT_DEBUG = false;\n"
    "    static final boolean DEFAULT_BILINGUAL_CAPTIONS = true;\n",
)
replace_once(
    "infrastructure/src/main/java/app/yydarlinker/deepseekcaptions/DeepSeekConfig.java",
    '''    static void saveDisplayTextDebugEnabled(Context context, boolean enabled) {
        prefs(context).edit().putBoolean(DISPLAY_TEXT_DEBUG, enabled).apply();
        if(!enabled)CaptionQualityTrace.clear(context);
    }
''',
    '''    static void saveDisplayTextDebugEnabled(Context context, boolean enabled) {
        prefs(context).edit().putBoolean(DISPLAY_TEXT_DEBUG, enabled).apply();
        if(!enabled)CaptionQualityTrace.clear(context);
    }

    static boolean bilingualCaptionsEnabled(Context context) {
        return prefs(context).getBoolean(BILINGUAL_CAPTIONS, DEFAULT_BILINGUAL_CAPTIONS);
    }

    static void saveBilingualCaptionsEnabled(Context context, boolean enabled) {
        prefs(context).edit().putBoolean(BILINGUAL_CAPTIONS, enabled).apply();
    }
''',
)

# Simple settings switch.
write(
    "ui/src/main/java/app/yydarlinker/deepseekcaptions/BilingualCaptionPreference.java",
    '''package app.yydarlinker.deepseekcaptions;

import android.content.Context;
import android.util.AttributeSet;

/** Enables source text above the context-aware AI translation. */
@SuppressWarnings("deprecation")
public final class BilingualCaptionPreference extends AddonSwitchPreference {
    public BilingualCaptionPreference(Context context) { super(context); initialize(); }
    public BilingualCaptionPreference(Context context, AttributeSet attrs) { super(context, attrs); initialize(); }
    public BilingualCaptionPreference(Context context, AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr); initialize();
    }
    public BilingualCaptionPreference(Context context, AttributeSet attrs, int defStyleAttr, int defStyleRes) {
        super(context, attrs, defStyleAttr, defStyleRes); initialize();
    }

    private void initialize() {
        setPersistent(false);
        setChecked(DeepSeekConfig.bilingualCaptionsEnabled(getContext()));
        setOnPreferenceChangeListener((preference, value) -> {
            boolean enabled = Boolean.TRUE.equals(value);
            DeepSeekConfig.saveBilingualCaptionsEnabled(getContext(), enabled);
            setChecked(enabled);
            CaptionActions.appearanceChanged();
            return false;
        });
    }

    @Override protected void onBindView(android.view.View view) {
        boolean saved = DeepSeekConfig.bilingualCaptionsEnabled(getContext());
        if (isChecked() != saved) setChecked(saved);
        super.onBindView(view);
    }
}
''',
)
print("added BilingualCaptionPreference.java")

replace_once(
    "patches/src/main/kotlin/app/yydarlinker/patches/deepseekcaptions/DeepSeekCaptionResourcePatch.kt",
    '''private const val DISPLAY_TEXT_DEBUG_PREF_CLASS =
    "app.yydarlinker.deepseekcaptions.DeepSeekDisplayTextDebugPreference"
''',
    '''private const val DISPLAY_TEXT_DEBUG_PREF_CLASS =
    "app.yydarlinker.deepseekcaptions.DeepSeekDisplayTextDebugPreference"
private const val BILINGUAL_PREF_CLASS =
    "app.yydarlinker.deepseekcaptions.BilingualCaptionPreference"
''',
)
replace_once(
    "patches/src/main/kotlin/app/yydarlinker/patches/deepseekcaptions/DeepSeekCaptionResourcePatch.kt",
    '''                addPreference("app.yydarlinker.deepseekcaptions.SubtitleStylePreview",
                    "deepseek_caption_style_preview", "字幕预览")
''',
    '''                addPreference("app.yydarlinker.deepseekcaptions.SubtitleStylePreview",
                    "deepseek_caption_style_preview", "字幕预览")
                addPreference(
                    BILINGUAL_PREF_CLASS,
                    "deepseek_caption_bilingual",
                    "双语字幕",
                    "同时显示原文和译文；原文在上，译文在下",
                )
''',
)

# Carry the exact source range with each rendered translated unit.
controller = "translation-core/src/main/java/app/yydarlinker/deepseekcaptions/RebuildController.java"
replace_once(controller, '    String text = "";\n', '    String text = "", sourceText = "";\n')
replace_once(
    controller,
    '''            text = unit.text;
            unitEvents = unit.events.size();
''',
    '''            text = unit.text;
            sourceText = s.source.text(unit.from, unit.to);
            unitEvents = unit.events.size();
''',
)
replace_once(
    controller,
    '''    final String appliedIdentity=s.id+":"+generation+":"+eventId;
    final long appliedStart=eventStart,appliedEnd=eventEnd;
''',
    '''    final String appliedIdentity=s.id+":"+generation+":"+eventId;
    final String appliedSourceText=sourceText;
    final long appliedStart=eventStart,appliedEnd=eventEnd;
''',
)
replace_once(
    controller,
    '''      TranslationOutput.showEvent(
          text, guard, () -> "", s.id + ":" + generation + ":" + eventId,
''',
    '''      TranslationOutput.showEvent(
          text, guard, () -> appliedSourceText, s.id + ":" + generation + ":" + eventId,
''',
)

# Keep the upstream boundary verifier aware of the intentional core adaptation.
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

# Compose source + translation in the existing overlay. Translation pagination remains upstream-owned.
overlay = "ui/src/main/java/app/yydarlinker/deepseekcaptions/CaptionOverlayV2.java"
replace_once(
    overlay,
    '''  private static RenderGuard currentGuard;
  private static Supplier<String> fallback;
''',
    '''  private static RenderGuard currentGuard;
  private static Supplier<String> fallback;

  private static String bilingualSource() {
    Activity activity = activityRef.get();
    if (activity == null || fallback == null || !DeepSeekConfig.bilingualCaptionsEnabled(activity)) return "";
    try {
      String source = fallback.get();
      return source == null ? "" : source.trim();
    } catch (RuntimeException ignored) {
      return "";
    }
  }

  private static String bilingualText(String translation, String source) {
    return source == null || source.isEmpty() ? translation : source + "\n" + translation;
  }
''',
)

# Page transitions must use the same bilingual composition as first render.
replace_once(
    overlay,
    '''    CaptionPageLayout.Page page=pendingPages.get(next);LayoutBudget budget=layoutBudget;
    if(text==null||budget==null)return;
    final long applyStarted=SystemClock.uptimeMillis();
    if(applyVisibleText(text,page.text,budget.preferredPx,budget.width,pendingRenderSpec,page.linePlan)<0){text.setText("");hideView();return;}
    placeVisibleText(activityRef.get(),hostRef.get(),anchorRef.get(),text,previous,budget.width+text.getPaddingLeft()+text.getPaddingRight());
''',
    '''    CaptionPageLayout.Page page=pendingPages.get(next);LayoutBudget budget=layoutBudget;
    if(text==null||budget==null)return;
    final long applyStarted=SystemClock.uptimeMillis();
    String source=bilingualSource(), visible=bilingualText(page.text,source);
    int maxLines=source.isEmpty()?2:4;
    float size=budget.preferredPx;
    while(maxLines==4 && size>budget.minimumPx && linesPx(visible,size,budget.width,pendingRenderSpec)>maxLines)
      size=Math.max(budget.minimumPx,size-.5f);
    if(maxLines==4 && linesPx(visible,size,budget.width,pendingRenderSpec)>maxLines){
      source="";visible=page.text;maxLines=2;size=budget.preferredPx;
    }
    if(applyVisibleText(text,visible,size,budget.width,pendingRenderSpec,source.isEmpty()?page.linePlan:null,maxLines)<0){text.setText("");hideView();return;}
    placeVisibleText(activityRef.get(),hostRef.get(),anchorRef.get(),text,previous,budget.width+text.getPaddingLeft()+text.getPaddingRight());
''',
)

replace_once(
    overlay,
    '''    text.setTextSize(TypedValue.COMPLEX_UNIT_PX,size);
    text.setSingleLine(false);text.setMaxLines(2);text.setEllipsize(null);
    text.setAutoSizeTextTypeWithDefaults(TextView.AUTO_SIZE_TEXT_TYPE_NONE);
    text.setTextColor(pendingStatus ? 0xE6FFFFFF : Color.WHITE);
    int compact=0;
    if(!shown.isEmpty()) {
      compact=applyVisibleText(text,shown,size,inner,measuredSpec,ownedCaption&&shownPage>=0?pendingPages.get(shownPage).linePlan:null);
''',
    '''    String source=ownedCaption?bilingualSource():"";
    boolean bilingual=!source.isEmpty()&&!shown.isEmpty();
    String visibleShown=bilingualText(shown,source);
    int visibleMaxLines=bilingual?4:2;
    if(bilingual){
      while(size>minimum && linesPx(visibleShown,size,inner,measuredSpec)>visibleMaxLines)
        size=Math.max(minimum,size-.5f);
      if(linesPx(visibleShown,size,inner,measuredSpec)>visibleMaxLines){
        bilingual=false;source="";visibleShown=shown;visibleMaxLines=2;size=preferred;
      } else mode="caption_bilingual";
    }
    text.setTextSize(TypedValue.COMPLEX_UNIT_PX,size);
    text.setSingleLine(false);text.setMaxLines(visibleMaxLines);text.setEllipsize(null);
    text.setAutoSizeTextTypeWithDefaults(TextView.AUTO_SIZE_TEXT_TYPE_NONE);
    text.setTextColor(pendingStatus ? 0xE6FFFFFF : Color.WHITE);
    int compact=0;
    if(!shown.isEmpty()) {
      compact=applyVisibleText(text,visibleShown,size,inner,measuredSpec,bilingual?null:ownedCaption&&shownPage>=0?pendingPages.get(shownPage).linePlan:null,visibleMaxLines);
''',
)

# Keep the original 2-line helper as a wrapper and add a max-line-aware version.
replace_once(
    overlay,
    '''  private static int applyVisibleText(TextView text,String shown,float size,int maximumInnerPx,CaptionRenderSpec spec,CaptionLinePlan line) {
    boolean same=CaptionSettingPreference.sameText(text.getText(),shown)&&text.getTextSize()==size&&text.getPaint().equalsForTextMeasurement(spec.paint(size));
''',
    '''  private static int applyVisibleText(TextView text,String shown,float size,int maximumInnerPx,CaptionRenderSpec spec,CaptionLinePlan line) {
    return applyVisibleText(text,shown,size,maximumInnerPx,spec,line,2);
  }
  private static int applyVisibleText(TextView text,String shown,float size,int maximumInnerPx,CaptionRenderSpec spec,CaptionLinePlan line,int maxLines) {
    boolean same=CaptionSettingPreference.sameText(text.getText(),shown)&&text.getTextSize()==size&&text.getPaint().equalsForTextMeasurement(spec.paint(size));
''',
)
replace_once(
    overlay,
    '''    if(text.getMaxLines()!=2){text.setSingleLine(false);text.setMaxLines(2);}if(text.getEllipsize()!=null)text.setEllipsize(null);
''',
    '''    if(text.getMaxLines()!=maxLines){text.setSingleLine(false);text.setMaxLines(maxLines);}if(text.getEllipsize()!=null)text.setEllipsize(null);
''',
)
text = read(overlay)
needle = "spec.fits(shown,text.getLayout(),boxWidthPx-padding,2))return boxWidthPx;"
count = text.count(needle)
if count != 2:
    raise SystemExit(f"{overlay}: expected 2 fit checks, found {count}")
write(overlay, text.replace(needle, "spec.fits(shown,text.getLayout(),boxWidthPx-padding,maxLines))return boxWidthPx;"))
print("patched fit checks")

print("Bilingual patch applied.")
