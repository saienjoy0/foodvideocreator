from __future__ import annotations

import argparse, json, os, shlex
from pathlib import Path

from .assets import import_asset
from .db import create_project, init_db
from .directives import set_directive
from .providers import (
    MockAIProvider, MockVoiceProvider, MockImageProvider,
    CommandJSONProvider, CommandVoiceProvider, CommandImageProvider,
)
from .runner import PipelineApp
from .startup import validate_startup


def _cmd(value: str | None) -> list[str] | None:
    return shlex.split(value) if value else None


def providers_for(args):
    ai_cmd=_cmd(args.ai_command or os.environ.get("FVC_AI_COMMAND"))
    voice_cmd=_cmd(args.voice_command or os.environ.get("FVC_VOICE_COMMAND"))
    image_cmd=_cmd(args.image_command or os.environ.get("FVC_IMAGE_COMMAND"))
    ai=CommandJSONProvider(ai_cmd) if ai_cmd else MockAIProvider()
    voice=CommandVoiceProvider(voice_cmd) if voice_cmd else MockVoiceProvider()
    image=CommandImageProvider(image_cmd) if image_cmd else MockImageProvider()
    return ai,voice,image


def main(argv=None):
    p=argparse.ArgumentParser(prog="fvc")
    p.add_argument("--db",default="job.db")
    p.add_argument("--project",default="demo")
    p.add_argument("--artifacts",default="artifacts")
    p.add_argument("--contract",default="workflow/workflow_contract.yaml")
    p.add_argument("--rules",default="rules/v4")
    p.add_argument("--assets-dir",default="assets")
    p.add_argument("--ai-command",help="External AI JSON command; alternatively FVC_AI_COMMAND")
    p.add_argument("--voice-command",help="External voice command; alternatively FVC_VOICE_COMMAND")
    p.add_argument("--image-command",help="External image command; alternatively FVC_IMAGE_COMMAND")
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("init")
    q=sub.add_parser("validate"); q.add_argument("--step")
    q=sub.add_parser("import-asset"); q.add_argument("role"); q.add_argument("path"); q.add_argument("--kind")
    q=sub.add_parser("directive"); q.add_argument("type"); q.add_argument("value")
    q=sub.add_parser("run"); q.add_argument("step"); q.add_argument("--json",default="{}")
    q=sub.add_parser("user"); q.add_argument("text"); q.add_argument("--json",default="{}")
    q=sub.add_parser("decide"); q.add_argument("decision",choices=["APPROVE","REQUEST_REVISION"],default="APPROVE",nargs="?")
    q=sub.add_parser("confirm-dish"); q.add_argument("dish_name")
    sub.add_parser("status")
    a=p.parse_args(argv)
    con=init_db(a.db)
    if a.cmd=="init":
        try:create_project(con,a.project,None)
        except Exception as e:
            if "UNIQUE" not in str(e): raise
        print(json.dumps({"project_id":a.project,"db":a.db},ensure_ascii=False,indent=2));return
    if a.cmd=="validate":
        result=validate_startup(contract_path=a.contract,rules_dir=a.rules,con=con,project_id=a.project,assets_dir=a.assets_dir,step=a.step)
        print(json.dumps(result,ensure_ascii=False,indent=2));
        if result["result"]!="PASS": raise SystemExit(2)
        return
    ai,voice,image=providers_for(a)
    app=PipelineApp(con=con,project_id=a.project,artifact_root=a.artifacts,contract_path=a.contract,ai_provider=ai,voice_provider=voice,image_provider=image,rules_dir=a.rules,assets_dir=a.assets_dir)
    if a.cmd=="import-asset":
        print(json.dumps(app.import_user_asset(a.role,a.path,{"kind":a.kind} if a.kind else {}),ensure_ascii=False,indent=2));return
    if a.cmd=="directive":
        try:v=json.loads(a.value)
        except Exception:v=a.value
        set_directive(con,a.project,a.type,v);print(json.dumps({"ok":True,"type":a.type,"value":v},ensure_ascii=False));return
    if a.cmd=="run": print(json.dumps(app.execute(a.step,**json.loads(a.json)),ensure_ascii=False,indent=2,default=str));return
    if a.cmd=="user": print(json.dumps(app.handle_user_command(a.text,**json.loads(a.json)),ensure_ascii=False,indent=2,default=str));return
    if a.cmd=="decide": print(json.dumps(app.approve_open_gate(decision=a.decision),ensure_ascii=False,indent=2,default=str));return
    if a.cmd=="confirm-dish": print(json.dumps(app.confirm_dish_identity(a.dish_name),ensure_ascii=False,indent=2,default=str));return
    if a.cmd=="status": print(json.dumps(app.status(),ensure_ascii=False,indent=2,default=str));return

if __name__=="__main__": main()
