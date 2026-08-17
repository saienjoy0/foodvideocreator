#!/usr/bin/env python3
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foodvideocreator.providers.mock import MockImageProvider
req=json.load(sys.stdin)
out=MockImageProvider().reconstruct_food_background(Path(req['source_path']),Path(req['output_path']),req.get('payload') or {})
json.dump(out,sys.stdout,ensure_ascii=False)
