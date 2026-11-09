#!/usr/bin/env python3
"""Generate the user-approved SHORT version at natural speed, no time stretching."""
import json,os,pathlib,subprocess,sys,time,wave
REQ=pathlib.Path("voice_batches/tic_egg_sticks_20261110_natural_short_v2.json")
OUT=pathlib.Path("voice_outputs/tic_egg_sticks_20261110_natural_short_v2")
OUT.mkdir(parents=True,exist_ok=True)
request=json.loads(REQ.read_text(encoding="utf-8"))
assert len(request["lines"])==11
assert request["profile"]["voice_name"]=="Puck"
models=["gemini-2.5-flash-preview-tts","gemini-3.8-flash-lite-tts"]
manifest={"source_request":str(REQ),"sdk":"google-genai==2.25.0","voice":"Puck","natural_speed":True,"atempo_applied":False,"lines":[],"failures":{}}
def save():
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
for row in request["lines"]:
    lid=row["id"]
    dest=OUT/(lid+".wav")
    done=False
    for model in models:
        for attempt in (1,2):
            profile=dict(request["profile"],model=model)
            payload={"text":row["text"],"output_path":str(dest.resolve()),"profile":profile}
            try:
                proc=subprocess.run([sys.executable,"examples/gemini_voice_command.py"],
                    input=json.dumps(payload,ensure_ascii=False),text=True,capture_output=True,timeout=70,env=os.environ.copy())
                if proc.returncode!=0 or not dest.exists() or dest.stat().st_size<1500:
                    raise RuntimeError((proc.stderr or "WAV missing")[-400:])
                with wave.open(str(dest),"rb") as w:
                    secs=w.getnframes()/w.getframerate()
                    rate=w.getframerate()
                    assert w.getnframes()>1000
                manifest["lines"].append({"id":lid,"text":row["text"],"duration_sec":round(secs,4),"sample_rate":rate,"model":model})
                save()
                print("OK",lid,"duration",round(secs,3),"model",model,flush=True)
                done=True
                break
            except Exception as e:
                print("RETRY",lid,model,attempt,type(e).__name__,str(e)[-320:],flush=True)
                dest.unlink(missing_ok=True)
                time.sleep(3)
        if done: break
    if not done:
        manifest["failures"][lid]="All supported models retried without a WAV"
        save()
        print("FAILED",lid,flush=True)
save()
if len(manifest["lines"])!=11:
    raise SystemExit("Incomplete voice batch: "+str(len(manifest["lines"]))+"/11")
print("SUCCESS 11/11",flush=True)
