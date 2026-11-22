import json,sys
def short(x,n=1500):
    s=x if isinstance(x,str) else json.dumps(x,ensure_ascii=False)
    return s if len(s)<=n else s[:n]+f"... [{len(s)-n} more chars]"
for line in open(sys.argv[1],errors='replace'):
    try: e=json.loads(line)
    except: continue
    t=e.get('type')
    if t=='assistant':
        for c in e['message'].get('content',[]):
            if c.get('type')=='text': print("ASSISTANT:",c['text'],"\n")
            elif c.get('type')=='tool_use': print(f"TOOL CALL [{c['name']}]:",short(c.get('input'),3000),"\n")
    elif t=='user':
        m=e.get('message',{}); cs=m.get('content')
        if isinstance(cs,str): print("USER:",cs,"\n"); continue
        for c in cs or []:
            if c.get('type')=='tool_result':
                cc=c.get('content'); 
                if isinstance(cc,list): cc="\n".join(x.get('text','') for x in cc if isinstance(x,dict))
                print("TOOL RESULT:",short(cc),"\n")
            elif c.get('type')=='text': print("USER:",c['text'],"\n")
    elif t=='result':
        print(f"== RESULT: cost_usd={e.get('total_cost_usd')} turns={e.get('num_turns')} subtype={e.get('subtype')}\n")
