#!/usr/bin/env python3
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foodvideocreator.providers.mock import MockAIProvider

req=json.load(sys.stdin); op=req['operation']; payload=req.get('payload') or {}
p=MockAIProvider()
fn=getattr(p,op)
json.dump(fn(payload),sys.stdout,ensure_ascii=False)
