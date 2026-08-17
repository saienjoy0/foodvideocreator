#!/usr/bin/env python3
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foodvideocreator.providers.mock import MockVoiceProvider
req=json.load(sys.stdin)
out=MockVoiceProvider().synthesize(req['text'],Path(req['output_path']),req.get('profile') or {})
json.dump(out,sys.stdout,ensure_ascii=False)
