"""
Merge db_wudc_motions_2020_2026.json, db_wudc_grand_finals_1981_2019.json,
and db_nsda_topics.json into motions-version-01.json.

Deduplicates by 'id'. Normalises NSDA style field:
  'LD' -> 'Lincoln-Douglas'
  'Policy' -> 'Policy'
  (PF and WSDC are already correct)
"""
import json
import os

BASE = os.path.dirname(__file__)

MAIN    = os.path.join(BASE, 'motions-version-01.json')
WUDC    = os.path.join(BASE, 'db_wudc_motions_2020_2026.json')
GF      = os.path.join(BASE, 'db_wudc_grand_finals_1981_2019.json')
NSDA    = os.path.join(BASE, 'db_nsda_topics.json')

# Style normalisation for NSDA entries so the API _STYLE_MAP picks them up
STYLE_NORM = {
    'LD':     'Lincoln-Douglas',
    'Policy': 'Policy',
    'PF':     'Public Forum',
    'WSDC':   'World Schools',
    'BP':     'BP',
}

print("Loading main JSON …")
with open(MAIN, encoding='utf-8') as f:
    data = json.load(f)
print(f"  {len(data):,} existing records")

existing_ids = {m['id'] for m in data}

def load_and_filter(path, label):
    with open(path, encoding='utf-8') as f:
        entries = json.load(f)
    new = [e for e in entries if e['id'] not in existing_ids]
    print(f"  {label}: {len(entries)} total, {len(new)} new (not already in main)")
    return new

print("Loading new files …")
new_wudc = load_and_filter(WUDC, 'WUDC 2020-2026')
new_gf   = load_and_filter(GF,   'WUDC Grand Finals 1981-2019')
new_nsda = load_and_filter(NSDA, 'NSDA topics')

# Normalise style values for NSDA entries
for entry in new_nsda:
    raw = entry.get('style', '')
    entry['style'] = STYLE_NORM.get(raw, raw)

total_new = new_wudc + new_gf + new_nsda
print(f"\nAdding {len(total_new)} new records to main JSON …")

data.extend(total_new)
print(f"Total after merge: {len(data):,} records")

print("Writing merged JSON …")
with open(MAIN, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

print("Done.")
