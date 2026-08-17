from foodvideocreator.checks import script_lab_structure_result


def good_lab():
    return {
        'angles':['Gap','Origin','Problem/Solution'],
        'hooks':['h1','h2','h3','h4','h5','h6'],
        'drafts':[{'id':'a','text':'x'},{'id':'b','text':'y'}],
        'critics':{'viewer':{'pass':True},'shorts_editor':{'pass':True},'fact':{'pass':True}},
        'pairwise_result':{'winner_id':'a'},'rewrite_count':1,
        'beat_map':[{'start_sec':0,'end_sec':3,'new_information':'a'},{'start_sec':3,'end_sec':6,'new_information':'b'}],
        'hook_payoff':{'status':'CLOSED'},'selected_text':'本文','used_claim_ids':['c1']
    }


def test_script_lab_structure_passes_complete_contract():
    assert script_lab_structure_result(good_lab(),6)['result']=='PASS'


def test_script_lab_structure_rejects_single_hook_or_draft():
    x=good_lab();x['hooks']=['h'];x['drafts']=[{'id':'a','text':'x'}]
    assert script_lab_structure_result(x,6)['result']=='FAIL'
