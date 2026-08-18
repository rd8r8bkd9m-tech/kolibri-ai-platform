#!/usr/bin/env python3
import sys,re,os,yaml
ROOT=os.path.join(os.path.dirname(__file__),'..','skills')
errors=[]
for dirpath,_,files in os.walk(ROOT):
    if 'SKILL.md' not in files: continue
    p=os.path.join(dirpath,'SKILL.md'); txt=open(p,encoding='utf8').read()
    if not txt.startswith('---\n'): errors.append(f'{p}: missing frontmatter'); continue
    parts=txt.split('---',2)
    try: meta=yaml.safe_load(parts[1]) or {}
    except Exception as e: errors.append(f'{p}: bad YAML {e}'); continue
    for key in ('name','description','version'):
        if not meta.get(key): errors.append(f'{p}: missing {key}')
    if len(meta.get('name',''))>64: errors.append(f'{p}: name > 64 chars')
    if len(meta.get('description',''))>1024: errors.append(f'{p}: description > 1024 chars')
    if len(txt.splitlines())>500: errors.append(f'{p}: >500 lines')
for e in errors: print(e)
print(f'checked={sum(1 for d,_,f in os.walk(ROOT) if "SKILL.md" in f)} errors={len(errors)}')
sys.exit(1 if errors else 0)
