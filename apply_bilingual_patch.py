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
        description = "Context-aware bilingual YouTube captions: one source line plus one AI translation line"
        source = "https://github.com/zhuzhangxue/youtube-android-bilingual-ai-captions"
        author = "zhuzhangxue (bilingual fork) / YYDarlinker (upstream)"
        contact = "https://github.com/zhuzhangxue/youtube-android-bilingual-ai-captions/issues"
        website = "https://github.com/zhuzhangxue/youtube-android-bilingual-ai-captions"
'''
)

replace_once(
    "gradle.properties",
    "version=1.5.1\ncaptionBuildId=release-1.5.1\n",
    "version=1.0.3\ncaptionBuildId=bilingual-1.0.3-two-line\n",
)

# 1) Carry the exact source subtitle with each accepted translated unit.
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

# 2) One source line + one translated line per timed page.
# The pair is split proportionally inside the same accepted event. No extra API call is made.
presentation = "translation-core/src/main/java/app/yydarlinker/deepseekcaptions/TranslationPresentation.java"
replace_once(
    presentation,
    '''        TranslationBudget budget=new TranslationBudget(geometry.width,geometry.minimumPx,geometry.preferredPx,spec);
        List<RebuildPageLayout.Page> planned=RebuildPageLayout.plan(text,start,end,budget,spec);
''',
    '''        TranslationBudget budget=new TranslationBudget(geometry.width,geometry.minimumPx,geometry.preferredPx,spec);
        int bilingualBreak=text==null?-1:text.indexOf('\\n');
        if(bilingualBreak>0 && bilingualBreak<text.length()-1){
            String source=text.substring(0,bilingualBreak).trim();
            String translated=text.substring(bilingualBreak+1).trim();
            List<CaptionDisplayPage> bilingual=bilingualPages(source,translated,start,end,budget,spec);
            if(!bilingual.isEmpty())return bilingual;
            // If the event is too short to show a readable 1+1 pair, keep translation readable.
            text=translated;
        }
        List<RebuildPageLayout.Page> planned=RebuildPageLayout.plan(text,start,end,budget,spec);
''',
)

# Add compact bilingual page helpers before the class closing brace.
replace_once(
    presentation,
    '''        if(!result.isEmpty()&&from!=text.length())throw new IllegalStateException("upstream_page_coverage");
        return Collections.unmodifiableList(result);
    }
}
''',
    '''        if(!result.isEmpty()&&from!=text.length())throw new IllegalStateException("upstream_page_coverage");
        return Collections.unmodifiableList(result);
    }

    private static List<CaptionDisplayPage> bilingualPages(String source,String translated,
        long start,long end,TranslationBudget budget,CaptionRenderSpec spec){
        if(source==null||translated==null||source.isEmpty()||translated.isEmpty()||end<=start)
            return Collections.emptyList();
        long duration=end-start;
        int maxPages=(int)Math.max(1,Math.min(8,duration/900L));
        for(int count=1;count<=maxPages;count++){
            List<String> sources=balancedParts(source,count);
            List<String> targets=balancedParts(translated,count);
            if(sources.size()!=count||targets.size()!=count)continue;
            List<Float> sizes=new ArrayList<>();
            boolean ok=true;
            for(int i=0;i<count;i++){
                String pair=sources.get(i)+"\\n"+targets.get(i);
                float size=largestFittingSize(pair,budget,spec);
                if(size<0){ok=false;break;}
                sizes.add(size);
            }
            if(!ok)continue;
            List<CaptionDisplayPage> result=new ArrayList<>();
            for(int i=0;i<count;i++){
                String pair=sources.get(i)+"\\n"+targets.get(i);
                float size=sizes.get(i);
                StaticLayout layout=spec.layout(pair,size,budget.width);
                if(layout.getLineCount()!=2) { ok=false; break; }
                int cut=sources.get(i).length()+1;
                CaptionLinePlan line=new CaptionLinePlan(
                    pair,0,pair.length(),cut,
                    layout.getLineMax(0),layout.getLineMax(1),
                    CaptionLinePlan.CutClass.LANGUAGE_BOUNDARY);
                long pageStart=start+(duration*i)/count;
                long pageEnd=i==count-1?end:start+(duration*(i+1))/count;
                result.add(new CaptionDisplayPage(
                    line.displayText,pageStart,pageEnd,0,pair.length(),
                    "BILINGUAL_ONE_PLUS_ONE",line));
            }
            if(ok&&!result.isEmpty())return Collections.unmodifiableList(result);
        }
        return Collections.emptyList();
    }

    private static float largestFittingSize(String pair,TranslationBudget budget,CaptionRenderSpec spec){
        float size=budget.preferredPx;
        while(size>budget.minimumPx && !spec.fits(pair,size,budget.width,2))
            size=Math.max(budget.minimumPx,size-.5f);
        return spec.fits(pair,size,budget.width,2)?size:-1;
    }

    private static List<String> balancedParts(String value,int count){
        String text=value==null?"":value.trim();
        if(count<=0||text.isEmpty())return Collections.emptyList();
        if(count==1)return Collections.singletonList(text);
        int codePoints=text.codePointCount(0,text.length());
        if(codePoints<count)return Collections.emptyList();
        List<String> result=new ArrayList<>();
        int from=0;
        java.text.BreakIterator breaks=java.text.BreakIterator.getLineInstance(Locale.ROOT);
        breaks.setText(text);
        for(int part=1;part<count;part++){
            int targetCp=(int)Math.round(codePoints*(part/(double)count));
            int target=text.offsetByCodePoints(0,targetCp);
            int min=nextCodePoint(text,from);
            int remaining=count-part;
            int max=text.offsetByCodePoints(0,codePoints-remaining);
            int cut=nearestLineBoundary(breaks,target,min,max);
            if(cut<=from||cut>=text.length())return Collections.emptyList();
            String piece=text.substring(from,cut).trim();
            if(piece.isEmpty())return Collections.emptyList();
            result.add(piece);
            from=cut;
            while(from<text.length()&&Character.isWhitespace(text.codePointAt(from)))
                from+=Character.charCount(text.codePointAt(from));
        }
        String last=text.substring(from).trim();
        if(last.isEmpty())return Collections.emptyList();
        result.add(last);
        return result;
    }

    private static int nextCodePoint(String text,int from){
        if(from>=text.length())return text.length();
        return from+Character.charCount(text.codePointAt(from));
    }

    private static int nearestLineBoundary(java.text.BreakIterator breaks,int target,int min,int max){
        int before=breaks.preceding(Math.min(target+1,max+1));
        int after=breaks.following(Math.max(target,min-1));
        int best=-1;
        if(before>=min&&before<=max)best=before;
        if(after>=min&&after<=max&&(best<0||Math.abs(after-target)<Math.abs(best-target)))best=after;
        if(best>=min&&best<=max)return best;
        return Math.max(min,Math.min(max,target));
    }
}
''',
)

# 3) Existing single TextView stays capped at two lines. For bilingual pages only,
# shrink within Anchored's existing min/max size range until both lines fit.
overlay = "ui/src/main/java/app/yydarlinker/deepseekcaptions/CaptionOverlayV2.java"
replace_once(
    overlay,
    '''    String reason=shown.isEmpty() && currentGuard!=null ? currentGuard.blankReason() : "";
''',
    '''    boolean bilingualBody=ownedCaption && shown.indexOf('\\n')>=0;
    if(bilingualBody){
      while(size>minimum && !measuredSpec.fits(shown,size,inner,2))
        size=Math.max(minimum,size-.5f);
    }
    String reason=shown.isEmpty() && currentGuard!=null ? currentGuard.blankReason() : "";
''',
)

# 4) Fresh installs include Simplified Chinese in Auto-translate by default.
languages = "ui/src/main/java/app/yydarlinker/deepseekcaptions/CaptionLanguageSelection.java"
replace_once(
    languages,
    '''    static Set<String> read(Context c) {
        if(c==null)return Collections.emptySet();
        try{Set<String> raw=c.getSharedPreferences(STORE,Context.MODE_PRIVATE).getStringSet(KEY,Collections.emptySet());return normalize(new HashSet<>(raw));}
        catch(IllegalArgumentException | ClassCastException invalid) { CaptionDiagnostics.mark(c,"LANGUAGE_SELECTION_INVALID","reason=unsupported_stored_code");return Collections.emptySet(); }
    }
''',
    '''    static Set<String> read(Context c) {
        if(c==null)return Collections.singleton("zh-Hans");
        try{
            Set<String> raw=c.getSharedPreferences(STORE,Context.MODE_PRIVATE).getStringSet(KEY,null);
            if(raw==null)return Collections.singleton("zh-Hans");
            return normalize(new HashSet<>(raw));
        }
        catch(IllegalArgumentException | ClassCastException invalid) {
            CaptionDiagnostics.mark(c,"LANGUAGE_SELECTION_INVALID","reason=unsupported_stored_code");
            return Collections.singleton("zh-Hans");
        }
    }
''',
)

# Keep upstream integration verification truthful after intentional core/presentation adaptations.
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

# This fork intentionally changes one UI preference default, so update the upstream
# preservation manifest for that single file while leaving every other protected UI file exact.
ui_manifest_path = ROOT / "docs/ui-preservation.json"
ui_manifest = json.loads(ui_manifest_path.read_text(encoding="utf-8"))
language_path = languages
language_bytes = (ROOT / language_path).read_bytes()
language_hits = 0
for row in ui_manifest.get("files", []):
    if row.get("path") == language_path:
        row["sha256"] = hashlib.sha256(language_bytes).hexdigest()
        row["bytes"] = len(language_bytes)
        language_hits += 1
if language_hits != 1:
    raise SystemExit(f"expected one UI preservation row for CaptionLanguageSelection, found {language_hits}")
ui_manifest_path.write_text(json.dumps(ui_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("updated core provenance and intentional UI preservation hash")
print("Bilingual v1.0.3 two-line patch applied.")
