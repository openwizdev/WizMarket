import json, subprocess, sys, time, os
OUT='/tmp/w/data/repos.json'
repos=json.load(open(OUT)) if os.path.exists(OUT) else {}
def search(q, page):
    for _ in range(5):
        r=subprocess.run(['gh','api','-X','GET','search/repositories','-f',f'q={q}','-f','per_page=100','-f',f'page={page}','-f','sort=stars'],capture_output=True,text=True)
        if r.returncode==0: return json.loads(r.stdout)
        print('retry',r.stderr[:200],file=sys.stderr); time.sleep(30)
    raise SystemExit('fail')
def total(q):
    return search(q,1)
def walk(topic, lo, hi):
    q=f'topic:{topic} stars:{lo}..{hi} pushed:>=2025-11-24 archived:false'
    d=search(q,1); n=d['total_count']
    if n>1000 and hi>lo:
        mid=(lo+hi)//2; walk(topic,lo,mid); walk(topic,mid+1,hi); return
    items=d['items']; p=2
    while len(items)<min(n,1000) and p<=10:
        d=search(q,p); items+=d['items']; p+=1; time.sleep(2)
    for it in items:
        k=it['full_name']
        repos.setdefault(k,{}).update({kk:it[kk] for kk in ['full_name','html_url','description','stargazers_count','fork','archived','pushed_at','default_branch','topics']})
        repos[k]['license']=(it.get('license') or {}).get('spdx_id')
        repos[k].setdefault('via',[])
        if topic not in repos[k]['via']: repos[k]['via'].append(topic)
    print(topic,lo,hi,n,len(items),len(repos),file=sys.stderr)
    json.dump(repos,open(OUT,'w'))
    time.sleep(2)
for t in sys.argv[1:]:
    walk(t,10,1000000)
