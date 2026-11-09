#!/usr/bin/env python3
import concurrent.futures as cf
import json, os, pathlib, subprocess, sys, time, wave
REQ=pathlib.Path("voice_batches/tic_egg_sticks_20261110_08g_v1.json")
req=json.loads(REQ.read_text(encoding="utf-8"))
assert len(req["lines"])==11 and req["profile"]["voice_name"]=="Puck"
out=pathlib.Path("voice_outputs/tic_egg_sticks_20261110_08g_rescue")
out.mkdir(parents=True,exist_ok=True)
models=["gemini-3.8-flash-lite-tts","gemini-2.5-flash-preview-tts"]
def make(line, model, tag, limit=95):
    name=line["id"]+"_"+tag
    dest=out/(name+".wav")
    p=dict(req["profile"],model=model)
    payload={"text":line["text"],"output_path":str(dest.resolve()),"profile":p}
    try:
        r=subprocess.run([sys.executable,"examples/gemini_voice_command.py"],input=json.dumps(payload,ensure_ascii=False),text=True,capture_output=True,timeout=limit)
        return {"ok":r.returncode==0 and dest.exists() and dest.stat().st_size>1000,"wav":str(dest),"err":r.stderr[-700:],"model":model}
    except Exception as e: return {"ok":False,"err":str(e)[-700:],"model":model}
with cf.ThreadPoolExecutor(max_workers=2) as e:
    futures=[e.submit(make,req["lines"][0],m,"probe"+str(i),95) for i,m in enumerate(models)]
    results=[f.result() for f in futures]
print("PROBES",[(r["model"],r["ok"],r["err"][:200]) for r in results],flush=True)
selected=next((r for r in results if r["ok"]),None)
if selected is None: raise SystemExit("No supported Gemini model passed probe")
model=selected["model"]
(out/"a01.wav").write_bytes(pathlib.Path(selected["wav"]).read_bytes())
manifest={"sdk":"google-genai==2.25.0","voice":"Puck","model":model,"source_request":REQ.as_posix(),"lines":[]}
def gen(row):
    for i in range(1,4):
        r=make(row,model,"try"+str(i),125)
        if r["ok"]:
            return row,r
        print("RETRY",row["id"],i,r["err"][-300:],flush=True)
        time.sleep(4)
    return row,r
with cf.ThreadPoolExecutor(max_workers=3) as e:
    futures=[e.submit(gen,row) for row in req["lines"][1:]]
    results=[f.result() for f in futures]
for row in req["lines"]:
    lid=row["id"]
    if lid!="a01":
        r=next((r for rr,r in results if rr["id"]==lid),None)
        if r is None or not r["ok"]:
            print("FAILED",lid,flush=True)
            raise SystemExit("Missing "+lid)
        (out/(lid+".wav")).write_bytes(pathlib.Path(r["wav"]).read_bytes())
    with wave.open(str(out/(lid+".wav")),"rb") as wf:
        duration=wf.getnframes()/wf.getframerate()
        entry={"id":lid,"text":row["text"],"duration":round(duration,4),"rate":wf.getframerate()}
    manifest["lines"].append(entry)
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("OK",lid,round(duration,3),flush=True)
print("SUCCESS",len(manifest["lines"]),"MODEL",model,flush=True)
