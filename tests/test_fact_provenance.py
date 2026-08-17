import json
from pathlib import Path
from foodvideocreator.providers.mock import MockAIProvider

class InventingPublishing(MockAIProvider):
    def publishing(self,payload):
        out=super().publishing(payload)
        out['fact_check']={'used_claim_ids':['NOT_APPROVED'],'new_fact_detected':True}
        return out

class InventingThumbnail(MockAIProvider):
    def thumbnail_copy(self,payload):
        out=super().thumbnail_copy(payload)
        out['new_fact_detected']=True
        return out

def test_mock_publishing_has_fact_provenance():
    out=MockAIProvider().publishing({'route':'A','claims':{'claims':[{'claim_id':'c1'}]}})
    assert out['fact_check']['new_fact_detected'] is False
    assert out['fact_check']['used_claim_ids']==['c1']

def test_mock_thumbnail_has_fact_provenance(tmp_path):
    p=tmp_path/'claims.json';p.write_text(json.dumps({'claims':[{'claim_id':'c1'}]}),encoding='utf-8')
    out=MockAIProvider().thumbnail_copy({'approved_claims':[{'claim_id':'c1'}]})
    assert out['new_fact_detected'] is False
    assert out['used_claim_ids']==['c1']
