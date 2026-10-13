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
    "version=1.3.0\ncaptionBuildId=bilingual-1.3.0-video-context\n",
)

# Add an independent patch that restores portrait orientation after leaving
# fullscreen on phones. It is separate from the caption feature so it can be
# enabled/disabled in Morphe like any other patch.
write(
    "application-host/src/main/java/app/yydarlinker/deepseekcaptions/KeepMainUiPortrait.java",
    r'''package app.yydarlinker.deepseekcaptions;

import android.app.Activity;
import android.content.pm.ActivityInfo;
import android.content.res.Configuration;
import android.view.View;
import android.view.ViewTreeObserver;

import java.lang.ref.WeakReference;

/**
 * Keeps YouTube's ordinary phone UI in portrait whenever the main bottom
 * navigation bar is actually visible. It does not observe player state and
 * does not special-case swipe exit or the fullscreen back/collapse button.
 */
public final class KeepMainUiPortrait {
    private static WeakReference<Activity> activityRef = new WeakReference<>(null);
    private static boolean portraitLockedByUs;

    private KeepMainUiPortrait() {}

    public static void setMainActivity(Activity activity) {
        activityRef = new WeakReference<>(activity);
        portraitLockedByUs = false;
        installNavigationVisibilityGuard(activity);
    }

    private static boolean isTablet(Activity activity) {
        return activity.getResources().getConfiguration().smallestScreenWidthDp >= 600;
    }

    private static boolean isVisible(View view) {
        return view != null &&
            view.isShown() &&
            view.getVisibility() == View.VISIBLE &&
            view.getAlpha() > 0f;
    }

    private static void installNavigationVisibilityGuard(Activity activity) {
        final View root = activity.getWindow().getDecorView();
        final int pivotBarId = activity.getResources().getIdentifier(
            "pivot_bar", "id", activity.getPackageName());
        if (pivotBarId == 0) return;

        root.getViewTreeObserver().addOnGlobalLayoutListener(
            new ViewTreeObserver.OnGlobalLayoutListener() {
                @Override
                public void onGlobalLayout() {
                    Activity current = activityRef.get();
                    if (current != activity || current == null ||
                        current.isFinishing() || current.isDestroyed() || isTablet(current)) return;

                    View pivotBar = current.findViewById(pivotBarId);
                    boolean ordinaryUiVisible = isVisible(pivotBar);

                    if (ordinaryUiVisible) {
                        if (current.getResources().getConfiguration().orientation ==
                            Configuration.ORIENTATION_LANDSCAPE) {
                            current.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);
                            portraitLockedByUs = true;
                        }
                    } else if (portraitLockedByUs) {
                        // Once ordinary navigation is gone, stop controlling orientation.
                        // YouTube is then free to handle watch/fullscreen orientation itself.
                        current.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
                        portraitLockedByUs = false;
                    }
                }
            }
        );
    }
}
'''
)

write(
    "patches/src/main/kotlin/app/yydarlinker/patches/deepseekcaptions/KeepMainUiPortraitPatch.kt",
    r'''package app.yydarlinker.patches.deepseekcaptions

import app.morphe.patcher.extensions.InstructionExtensions.addInstruction
import app.morphe.patcher.patch.bytecodePatch
import app.yydarlinker.patches.shared.Constants.YOUTUBE

private const val KEEP_MAIN_UI_PORTRAIT_CLASS =
    "Lapp/yydarlinker/deepseekcaptions/KeepMainUiPortrait;"

@Suppress("unused")
val keepMainUiPortraitPatch = bytecodePatch(
    name = "Keep YouTube main UI portrait",
    description = "Keeps YouTube's ordinary phone interface portrait when the bottom navigation is visible.",
    default = true,
) {
    compatibleWith(YOUTUBE)
    dependsOn(captionSupportPatch)

    execute {
        YouTubeActivityOnCreateFingerprint.method.addInstruction(
            0,
            "invoke-static/range { p0 .. p0 }, " +
                "$KEEP_MAIN_UI_PORTRAIT_CLASS->setMainActivity(Landroid/app/Activity;)V",
        )
    }
}
'''
)

print("added Keep YouTube main UI portrait patch")

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
              text=bilingualSourceText==null ? "" : bilingualSourceText.trim();
              eventId="source:"+eventId;
              fallbackReason="event_review";
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

replace_once(
    controller,
    '''              if(eventStart<=selectedAt && selectedAt<eventEnd) {
                text=s.states[i]==FAILED ? "" : translating;
                eventId="source:"+i+":"+eventStart+"_"+eventEnd;
              }
''',
    '''              if(eventStart<=selectedAt && selectedAt<eventEnd) {
                // If the AI block ultimately fails, keep the source caption visible rather
                // than turning a known caption window into a blank gap.
                boolean retryingTransient =
                    s.attempts[i] >= 2 && bilingualTransientRetry(s.reasons[i]);
                text=(s.states[i]==FAILED || retryingTransient) ? cue.text : translating;
                eventId="source:"+i+":"+eventStart+"_"+eventEnd;
              }
''',
)

replace_once(
    controller,
    '''  static String unresolvedPhase(int state, String reason) {
    if (state == READY) return "";
    return state == FAILED ? "failed:" + reason : "pending_translation";
  }

''',
    '''  static String unresolvedPhase(int state, String reason) {
    if (state == READY) return "";
    return state == FAILED ? "failed:" + reason : "pending_translation";
  }

  // Provider/network failures are often intermittent. A fresh subtitle toggle succeeding on the
  // same source range is exactly this case, so allow two extra bounded attempts for transient
  // failures without retrying configuration/content-filter failures forever.
  private static boolean bilingualTransientRetry(String reason) {
    if (reason == null || reason.isEmpty()) return false;
    String code = reason;
    int cut = code.indexOf(';');
    if (cut >= 0) code = code.substring(0, cut);
    return code.equals("deadline_expired")
        || code.equals("connection_establishment_timeout")
        || code.equals("connection_establishment_failed")
        || code.equals("connection_socket_exception")
        || code.equals("read_interrupted")
        || code.equals("JSONException")
        || code.equals("output_truncated")
        || code.equals("negotiation_pending")
        || code.equals("http_408")
        || code.equals("http_409")
        || code.equals("http_425")
        || code.equals("http_429")
        || code.startsWith("http_5");
  }

''',
)

replace_once(
    controller,
    '''        int maxAttempts =
            RebuildReview.hasSemanticRepairRisk(s.plans[i])
                ? RebuildReview.MAX_SEMANTIC_ATTEMPTS
                : s.attempts[i] == 2
                        && s.plans[i] == null
                        && RebuildReview.structuralRetry(s.reasons[i])
                        && s.repairCount < RebuildReview.MAX_SESSION_REPAIRS
                    ? 3
                    : 2;
''',
    '''        int maxAttempts =
            RebuildReview.hasSemanticRepairRisk(s.plans[i])
                ? RebuildReview.MAX_SEMANTIC_ATTEMPTS
                : s.plans[i] == null && bilingualTransientRetry(s.reasons[i])
                    ? 4
                    : s.attempts[i] == 2
                            && s.plans[i] == null
                            && RebuildReview.structuralRetry(s.reasons[i])
                            && s.repairCount < RebuildReview.MAX_SESSION_REPAIRS
                        ? 3
                        : 2;
''',
)

replace_once(
    controller,
    '''          boolean structuralRetry =
              s.plans[job.index] == null
                  && s.attempts[job.index] < 3
                  && RebuildReview.structuralRetry(code)
                  && s.repairCount < RebuildReview.MAX_SESSION_REPAIRS;
          s.states[job.index] =
              fatal || filtered || (!structuralRetry && s.attempts[job.index] >= 2)
                  || s.attempts[job.index] >= 3
                  || s.repairCount >= RebuildReview.MAX_SESSION_REPAIRS
                  ? FAILED
                  : WAITING;
          long delay = e instanceof RebuildApi.Failure ? ((RebuildApi.Failure) e).delay : 0;
          s.retryAt[job.index] = SystemClock.elapsedRealtime() + Math.max(1200, delay);
''',
    '''          boolean transientRetry =
              s.plans[job.index] == null
                  && s.attempts[job.index] < 4
                  && bilingualTransientRetry(code)
                  && s.repairCount < RebuildReview.MAX_SESSION_REPAIRS;
          boolean structuralRetry =
              s.plans[job.index] == null
                  && s.attempts[job.index] < 3
                  && RebuildReview.structuralRetry(code)
                  && s.repairCount < RebuildReview.MAX_SESSION_REPAIRS;
          boolean retryable = transientRetry || structuralRetry;
          int hardAttemptLimit = transientRetry ? 4 : 3;
          s.states[job.index] =
              fatal || filtered || (!retryable && s.attempts[job.index] >= 2)
                  || s.attempts[job.index] >= hardAttemptLimit
                  || s.repairCount >= RebuildReview.MAX_SESSION_REPAIRS
                  ? FAILED
                  : WAITING;
          long delay = e instanceof RebuildApi.Failure ? ((RebuildApi.Failure) e).delay : 0;
          s.retryAt[job.index] = SystemClock.elapsedRealtime()
              + Math.max(transientRetry ? 700 : 1200, delay);
''',
)


# 1b) Rescue strict protocol failures with a much simpler one-field JSON response.
replace_once(
    controller,
    '''  private static void render(Session s) {
''',
    '''  private static boolean bilingualProtocolRescue(String reason) {
    if (reason == null || reason.isEmpty()) return false;
    String code = reason;
    int cut = code.indexOf(';');
    if (cut >= 0) code = code.substring(0, cut);
    return code.equals("json")
        || code.equals("source_quote_mismatch")
        || code.equals("source_coverage")
        || code.equals("missing_source")
        || code.equals("crosses_source_break")
        || code.equals("block_identity")
        || code.equals("source_quote_required")
        || code.equals("event_count")
        || code.equals("event_shape")
        || code.equals("index_type")
        || code.equals("text_type")
        || code.equals("protocol_leak")
        || code.equals("output_truncated");
  }

  private static void render(Session s) {
''',
)

api = "translation-core/src/main/java/app/yydarlinker/deepseekcaptions/RebuildApi.java"
replace_once(
    api,
    '''package app.yydarlinker.deepseekcaptions;

import java.io.*;
''',
    '''package app.yydarlinker.deepseekcaptions;

import android.os.SystemClock;
import java.io.*;
''',
)
replace_once(
    api,
    '''    JSONObject payload = RebuildProtocol.payload(s, b, lang, repair,context);
    TranslationBudget layout = TranslationOutput.budget();
''',
    '''    JSONObject payload = RebuildProtocol.payload(s, b, lang, repair,context);
    String videoContextCard=bilingualExistingContext(s,cfg,lang,context,control);
    if(!videoContextCard.isEmpty())payload.put("video_context_card",videoContextCard);
    TranslationBudget layout = TranslationOutput.budget();
''',
)
replace_once(
    api,
    '''    String prompt = prompt(cfg, lang,context);
''',
    '''    String prompt = prompt(cfg, lang,context);
    if(!videoContextCard.isEmpty())
      prompt += " video_context_card is read-only global video context. Use it for terminology and reference resolution, but translate only source_text.";
''',
)
replace_once(
    api,
    '''        TranslationAudit.recordUnitBatchOutcome(audit, 1);
        return plan;
''',
    '''        TranslationAudit.recordUnitBatchOutcome(audit, 1);
        bilingualMaybeBuildContext(s,cfg,lang,context,control);
        return plan;
''',
)

replace_once(
    api,
    '''  private static void trace(DeepSeekApiClient.RequestControl control,String stage,String detail) {
''',
    '''  /**
   * Last-resort protocol rescue. The provider only has to return one translated string.
   * Source ownership, timing and the final event JSON are rebuilt locally.
   */
  private static final ConcurrentHashMap<String,String> BILINGUAL_VIDEO_CONTEXT =
      new ConcurrentHashMap<>();
  private static final ConcurrentHashMap<String,Long> BILINGUAL_CONTEXT_RETRY =
      new ConcurrentHashMap<>();
  private static final Set<String> BILINGUAL_CONTEXT_LOADING = ConcurrentHashMap.newKeySet();
  private static final ExecutorService BILINGUAL_CONTEXT_IO =
      Executors.newSingleThreadExecutor(r -> {
        Thread t=new Thread(r,"BilingualVideoContextIO");t.setDaemon(true);return t;
      });

  private static String bilingualContextKey(RebuildSource s, TranslationSettings cfg, String lang,
      CaptionLanguageContext context, DeepSeekApiClient.RequestControl control) {
    if(control instanceof RebuildController.Job) {
      RebuildController.Job job=(RebuildController.Job)control;
      if(job.session.cacheKey!=null&&!job.session.cacheKey.isEmpty())
        return RebuildCache.hash("bilingual-video-context-v1|"+job.session.cacheKey+"|"+lang);
    }
    String transcript=s.words.isEmpty()?"":s.text(0,s.words.size()-1);
    return RebuildCache.hash("bilingual-video-context-v1|"+cfg.model+"|"+lang+"|"+RebuildCache.hash(transcript));
  }

  private static File bilingualContextFile(android.content.Context c,String key) {
    return new File(RebuildCache.directory(c),"video-context-"+key+".txt");
  }

  private static String bilingualExistingContext(RebuildSource s, TranslationSettings cfg,String lang,
      CaptionLanguageContext context,DeepSeekApiClient.RequestControl control) {
    String key=bilingualContextKey(s,cfg,lang,context,control);
    String memory=BILINGUAL_VIDEO_CONTEXT.get(key);
    if(memory!=null)return memory;
    if(control instanceof RebuildController.Job) {
      try {
        File f=bilingualContextFile(((RebuildController.Job)control).session.context,key);
        if(f.isFile()&&f.length()>0&&f.length()<=16384) {
          String card=new String(java.nio.file.Files.readAllBytes(f.toPath()),StandardCharsets.UTF_8).trim();
          if(!card.isEmpty()) {
            BILINGUAL_VIDEO_CONTEXT.put(key,card);
            return card;
          }
        }
      } catch(Exception ignored) {}
    }
    return "";
  }

  private static String bilingualTranscriptDigest(RebuildSource s) {
    if(s.words.isEmpty())return "";
    String all=s.text(0,s.words.size()-1);
    if(all.length()<=16000)return all;
    int windows=6,per=180,total=s.words.size();
    StringBuilder out=new StringBuilder();
    for(int w=0;w<windows;w++) {
      int center=(int)((long)(total-1)*w/Math.max(1,windows-1));
      int from=Math.max(0,Math.min(total-1,center-per/2));
      int to=Math.min(total-1,from+per-1);
      if(out.length()>0)out.append("\\n---\\n");
      out.append(s.text(from,to));
    }
    return out.toString();
  }

  private static void bilingualMaybeBuildContext(RebuildSource s,TranslationSettings cfg,String lang,
      CaptionLanguageContext context,DeepSeekApiClient.RequestControl control) {
    if(!(control instanceof RebuildController.Job)||s.words.isEmpty())return;
    RebuildController.Job job=(RebuildController.Job)control;
    String key=bilingualContextKey(s,cfg,lang,context,control);
    if(!bilingualExistingContext(s,cfg,lang,context,control).isEmpty())return;
    long now=SystemClock.elapsedRealtime();
    Long retry=BILINGUAL_CONTEXT_RETRY.get(key);
    if(retry!=null&&retry>now)return;
    if(!BILINGUAL_CONTEXT_LOADING.add(key))return;
    android.content.Context app=job.session.context.getApplicationContext();
    BILINGUAL_CONTEXT_IO.submit(() -> {
      try {
        String digest=bilingualTranscriptDigest(s);
        if(digest.isEmpty())return;
        JSONObject payload=new JSONObject()
            .put("target_language",context.canApplyEnglishToChinese?lang:context.targetCode)
            .put("transcript",digest)
            .put("instruction",
                "Create a compact video translation context card: topic/domain, recurring technical terms with preferred target-language wording, named products/people, and important reference relationships. Do not translate the transcript.");
        String prompt="Analyze this video's transcript for later subtitle translation consistency. "
            +"Return only {\\\"card\\\":\\\"...\\\"}. Keep card under 900 characters; prefer a compact glossary and topic notes.";
        JSONObject request=ProviderRequestPolicy.request(cfg,prompt,payload,900);
        request.put("stream",false);
        request.put("response_format",new JSONObject().put("type","json_object"));
        long deadline=System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(12000);
        Response response=send(cfg,request.toString(),null,deadline,null);
        if(response.status<200||response.status>=300)throw new IOException("context_http_"+response.status);
        JSONObject root=new JSONObject(response.body);
        String raw=root.getJSONArray("choices").getJSONObject(0)
            .getJSONObject("message").optString("content","").trim();
        String card=new JSONObject(raw).optString("card","").replace('\\r',' ').replace('\\n',' ').trim();
        if(card.length()>1400)card=card.substring(0,1400);
        if(card.isEmpty())throw new IOException("context_empty");
        BILINGUAL_VIDEO_CONTEXT.put(key,card);
        File dest=bilingualContextFile(app,key),tmp=File.createTempFile("video-context-",".tmp",RebuildCache.directory(app));
        try(FileOutputStream out=new FileOutputStream(tmp)) {
          out.write(card.getBytes(StandardCharsets.UTF_8));out.getFD().sync();
        }
        java.nio.file.Files.move(tmp.toPath(),dest.toPath(),
            java.nio.file.StandardCopyOption.REPLACE_EXISTING,
            java.nio.file.StandardCopyOption.ATOMIC_MOVE);
      } catch(Exception ignored) {
        BILINGUAL_CONTEXT_RETRY.put(key,SystemClock.elapsedRealtime()+30000);
      } finally {
        BILINGUAL_CONTEXT_LOADING.remove(key);
      }
    });
  }

  static RebuildProtocol.Plan rescueSimple(RebuildSource s, RebuildPlanner.Block b,
      TranslationSettings cfg, String lang, DeepSeekApiClient.RequestControl control,
      boolean priority, CaptionLanguageContext context) throws Exception {
    String videoContextCard=bilingualExistingContext(s,cfg,lang,context,control);
    JSONObject payload = new JSONObject()
        .put("language", context.canApplyEnglishToChinese ? lang : context.targetCode)
        .put("source_text", s.text(b.from,b.to))
        .put("context_before", RebuildPlanner.context(s,b.from-96,b.from-1))
        .put("context_after", RebuildPlanner.context(s,b.to+1,b.to+48))
        .put("instruction",
            "Translate source_text faithfully. Context is read-only. Return only a JSON object with one string field named text.");
    if(!videoContextCard.isEmpty())payload.put("video_context_card",videoContextCard);
    String rescuePrompt =
        "Translate only source_text into the selected target language. Preserve meaning, names, numbers, negation and technical terms. "
        + "Use context only to resolve meaning. Do not summarize. Return exactly {\\\"text\\\":\\\"translation\\\"}.";
    JSONObject request = ProviderRequestPolicy.request(
        cfg,rescuePrompt,payload,Math.min(1800,Math.max(500,s.text(b.from,b.to).length()*2+300)));
    request.put("stream",false);
    request.put("response_format",new JSONObject().put("type","json_object"));
    long deadline = System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(priority?9000:13000);
    Response response=send(cfg,request.toString(),control,deadline,null);
    if ((response.status==400||response.status==422)&&ProviderRequestPolicy.inspected(response.body))
      throw new Failure(ProviderRequestPolicy.INSPECTION_CODE,false,0);
    if(response.status<200||response.status>=300)
      throw new Failure("http_"+response.status,
          response.status==401||response.status==403||response.status==404,response.retryAfter);
    JSONObject root=new JSONObject(response.body);
    JSONObject choice=root.getJSONArray("choices").getJSONObject(0);
    String finish=choice.optString("finish_reason");
    if("length".equals(finish))throw new RebuildProtocol.Invalid("output_truncated");
    if("content_filter".equals(finish))throw new Failure("content_filter",false,0);
    String raw=choice.getJSONObject("message").optString("content","").trim();
    JSONObject answer=new JSONObject(raw);
    String text=answer.optString("text","").replace('\\r',' ').replace('\\n',' ').trim();
    if(text.isEmpty())throw new RebuildProtocol.Invalid("empty_translation");

    JSONObject event=new JSONObject()
        .put("from",b.from).put("to",b.to)
        .put("source",s.text(b.from,b.to)).put("text",text);
    JSONObject local=new JSONObject().put("block",b.id())
        .put("events",new JSONArray().put(event));
    RebuildProtocol.Plan plan=RebuildProtocol.parseBound(local.toString(),s,b,context);
    trace(control,"BILINGUAL_RESCUE_ACCEPTED",
        "block="+b.index+";range="+b.from+"-"+b.to+";mode=simple_local_ownership");
    bilingualMaybeBuildContext(s,cfg,lang,context,control);
    return plan;
  }

  private static void trace(DeepSeekApiClient.RequestControl control,String stage,String detail) {
''',
)

replace_once(
    controller,
    '''      String redactedReason = TranslationRuntime.redact(rejectionReason, s.config.apiKey, 400);
      notices.clear();
      synchronized (s) {
''',
    '''      String redactedReason = TranslationRuntime.redact(rejectionReason, s.config.apiKey, 400);
      boolean filteredFailure =
          e instanceof RebuildApi.Failure && "content_filter".equals(((RebuildApi.Failure)e).code);
      RebuildProtocol.Plan rescued = null;
      if (!fatal && !filteredFailure && s.plans[job.index] == null
          && s.attempts[job.index] >= 2 && bilingualProtocolRescue(code)) {
        try {
          rescued=RebuildApi.rescueSimple(
              s.source,b,s.config,s.target,job,job.priority,s.languageContext);
        } catch (Exception rescueFailure) {
          String rescueCode=rescueFailure instanceof RebuildProtocol.Invalid
              ? ((RebuildProtocol.Invalid)rescueFailure).code
              : rescueFailure instanceof RebuildApi.Failure
                  ? ((RebuildApi.Failure)rescueFailure).code
                  : rescueFailure instanceof RebuildApi.TransportFailure
                      ? ((RebuildApi.TransportFailure)rescueFailure).reason
                      : rescueFailure.getClass().getSimpleName();
          notice(notices,"BILINGUAL_RESCUE_REJECTED",
              "session="+s.id+";block="+b.index+";reason="+rescueCode);
        }
      }
      if (rescued != null) {
        synchronized (s) {
          if (!current(s) || s.jobs[job.index] != job || job.cancelled) return;
          s.plans[job.index]=rescued;
          if(s.provisional!=null)s.provisional[job.index]=null;
          s.states[job.index]=READY;
          s.reasons[job.index]="";
          s.jobs[job.index]=null;
          s.everReady=true;
          if(job.priority&&s.focusAcceptedAt<0)s.focusAcceptedAt=SystemClock.elapsedRealtime();
        }
        notice(notices,"BILINGUAL_RESCUE_READY",
            "session="+s.id+";block="+b.index+";after_attempts="+s.attempts[job.index]);
        flush(s,notices);
        render(s);
        return;
      }
      notices.clear();
      synchronized (s) {
''',
)

replace_once(
    controller,
    '''          boolean filtered =
              e instanceof RebuildApi.Failure
                  && "content_filter".equals(((RebuildApi.Failure) e).code);
''',
    '''          boolean filtered = filteredFailure;
''',
)



# 1c) Increase read-only local context without increasing the block that must be translated.
protocol = "translation-core/src/main/java/app/yydarlinker/deepseekcaptions/RebuildProtocol.java"
replace_once(
    protocol,
    '''            .put("context_before", RebuildPlanner.context(s, b.from - 24, b.from - 1))
            .put("context_after", RebuildPlanner.context(s, b.to + 1, b.to + 24));
''',
    '''            .put("context_before", RebuildPlanner.context(s, b.from - 96, b.from - 1))
            .put("context_after", RebuildPlanner.context(s, b.to + 1, b.to + 48));
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
        int maxPages=(int)Math.max(1,Math.min(10,Math.max(1,duration/700L)));
        float readableFloor=Math.max(budget.minimumPx,budget.preferredPx*.84f);

        // First pass: preserve a comfortable subtitle size. If a pair is too long,
        // split it into more timed 1+1 pages instead of shrinking the whole pair.
        for(int count=1;count<=maxPages;count++){
            List<String> sources=balancedParts(source,count);
            List<String> targets=balancedParts(translated,count);
            if(sources.size()!=count||targets.size()!=count)continue;
            List<Float> sizes=new ArrayList<>();
            boolean ok=true;
            for(int i=0;i<count;i++){
                String pair=sources.get(i)+"\\n"+targets.get(i);
                float size=largestFittingSize(pair,budget,spec,readableFloor);
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

        // Emergency pass: only if no readable split fits within the available event time.
        // This preserves content for unusually dense/fast speech, but ordinary long lines
        // should now be split before reaching this smaller-size path.
        for(int count=maxPages;count>=1;count--){
            List<String> sources=balancedParts(source,count);
            List<String> targets=balancedParts(translated,count);
            if(sources.size()!=count||targets.size()!=count)continue;
            List<CaptionDisplayPage> result=new ArrayList<>();
            boolean ok=true;
            for(int i=0;i<count;i++){
                String pair=sources.get(i)+"\\n"+targets.get(i);
                float size=largestFittingSize(pair,budget,spec,budget.minimumPx);
                if(size<0){ok=false;break;}
                StaticLayout layout=spec.layout(pair,size,budget.width);
                if(layout.getLineCount()!=2){ok=false;break;}
                int cut=sources.get(i).length()+1;
                CaptionLinePlan line=new CaptionLinePlan(
                    pair,0,pair.length(),cut,
                    layout.getLineMax(0),layout.getLineMax(1),
                    CaptionLinePlan.CutClass.LANGUAGE_BOUNDARY);
                long pageStart=start+(duration*i)/count;
                long pageEnd=i==count-1?end:start+(duration*(i+1))/count;
                result.add(new CaptionDisplayPage(
                    line.displayText,pageStart,pageEnd,0,pair.length(),
                    "BILINGUAL_ONE_PLUS_ONE_EMERGENCY",line));
            }
            if(ok&&!result.isEmpty())return Collections.unmodifiableList(result);
        }
        return Collections.emptyList();
    }

    private static float largestFittingSize(String pair,TranslationBudget budget,
        CaptionRenderSpec spec,float floorPx){
        float floor=Math.max(budget.minimumPx,Math.min(budget.preferredPx,floorPx));
        float size=budget.preferredPx;
        while(size>floor && !spec.fits(pair,size,budget.width,2))
            size=Math.max(floor,size-.5f);
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
      float readableFloor=Math.max(minimum,preferred*.84f);
      while(size>readableFloor && !measuredSpec.fits(shown,size,inner,2))
        size=Math.max(readableFloor,size-.5f);
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

# RebuildApi intentionally adds a bilingual rescue request/prompt in this fork.
# Keep the upstream literal-integrity check for RebuildProtocol, but do not claim RebuildApi literals are untouched.
verify_integration = "tools/verify_integration.py"
replace_once(
    verify_integration,
    '''    for name in ['RebuildApi','RebuildProtocol']:
''',
    '''    for name in ['RebuildProtocol']:
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

api_sha = hashlib.sha256((ROOT / api).read_bytes()).hexdigest()
api_hits = 0
for row in provenance.get("files", []):
    if row.get("destination") == api:
        row["sha256"] = api_sha
        api_hits += 1
if api_hits != 1:
    raise SystemExit(f"expected one provenance row for RebuildApi, found {api_hits}")

protocol_sha = hashlib.sha256((ROOT / protocol).read_bytes()).hexdigest()
protocol_hits = 0
for row in provenance.get("files", []):
    if row.get("destination") == protocol:
        row["sha256"] = protocol_sha
        protocol_hits += 1
if protocol_hits != 1:
    raise SystemExit(f"expected one provenance row for RebuildProtocol, found {protocol_hits}")

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
print("Bilingual v1.3.0 video-context + rescue pipeline + readable two-line + main-UI portrait-only patch applied.")
