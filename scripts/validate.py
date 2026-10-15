"""Validate actual submission artifacts, provenance, selection rule and notebook."""
from pathlib import Path
import hashlib
import json
import re
import sys
import nbformat
from PIL import Image

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from agent_artist import BRIEFS, TEAM

errors = []
def check(condition, message):
    if not condition:
        errors.append(message)

gallery = json.loads((root / 'docs/gallery.json').read_text(encoding='utf-8'))
check(gallery['team'] == TEAM, 'Team differs from requested team.')
check(len(gallery['works']) == 4, 'Exactly four completed paintings are required.')
for brief in BRIEFS:
    data_path = root / 'data' / f'{brief["id"]}.json'
    check(data_path.exists(), f'Missing data for {brief["id"]}')
    if not data_path.exists():
        continue
    work = json.loads(data_path.read_text(encoding='utf-8'))
    check(len(work['candidates']) == 2, f'{work["id"]}: need two real versions.')
    stages = {event['stage'] for event in work['dialogue'] if event.get('parsed')}
    check({'curator-concept','artist-proposal','curator-challenge','artist-prompt-v1',
           'artist-prompt-v2','critic-v1','critic-v2'} <= stages, f'{work["id"]}: missing agent turn.')
    for candidate in work['candidates']:
        image_path = root / 'docs/assets' / candidate['image']
        check(image_path.exists(), f'Missing image {image_path.name}')
        if image_path.exists():
            with Image.open(image_path) as image:
                image.verify()
            check(hashlib.sha256(image_path.read_bytes()).hexdigest() == candidate['sha256'],
                  f'Image hash changed: {image_path.name}')
        scores = candidate.get('review', {}).get('scores', {})
        check(all(type(scores.get(key)) is int and 1 <= scores[key] <= 5
                  for key in ['metaphor','composition','materiality','series_fit']),
              f'{image_path.name}: invalid scores.')
        check(candidate.get('review', {}).get('total') == sum(scores.values()),
              f'{image_path.name}: score sum mismatch.')
        critique = next((event for event in work['dialogue']
                         if event['stage'] == f'critic-v{candidate["version"]}' and event.get('parsed')), None)
        check(critique is not None and critique['image'] == candidate['image'],
              f'{image_path.name}: critic did not receive this image.')
        prompt_event = next((event for event in work['dialogue']
                            if event['stage'] == f'artist-prompt-v{candidate["version"]}' and event.get('parsed')), None)
        check(prompt_event is not None and prompt_event['parsed']['image_prompt'] == candidate['prompt'],
              f'{image_path.name}: renderer prompt differs from artist output.')
    best = max(work['candidates'], key=lambda item:(item['review']['total'], -item['version']))
    check(best['version'] == work['selected_version'], f'{work["id"]}: wrong selected version.')
    check(work == next((entry for entry in gallery['works'] if entry['id'] == work['id']), None),
          f'{work["id"]}: gallery not synchronized with source data.')

if gallery.get('openweight'):
    entry = gallery['openweight']
    image_path = root / 'docs/assets' / entry['image']
    check(image_path.exists(), 'Open-weight image missing.')
    check(bool(entry.get('revision')) and entry.get('seed') == 2126, 'Open-weight provenance incomplete.')
    check(hashlib.sha256(image_path.read_bytes()).hexdigest() == entry['sha256'], 'Open-weight hash mismatch.')

nb = nbformat.read(root / 'Agent_Artist.ipynb', as_version=4)
nbformat.validate(nb)
code = [cell for cell in nb.cells if cell.cell_type == 'code']
check(all(cell.execution_count is not None for cell in code), 'Notebook has unexecuted cells.')
check(not any(output.output_type == 'error' for cell in code for output in cell.outputs), 'Notebook has cell errors.')
check(any('class Studio' in cell.source for cell in code), 'Notebook must include full implementation.')
for path in root.rglob('*'):
    if not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts:
        continue
    check(path.name != '.env', 'Secret .env present in submission directory.')
    if path.suffix in {'.py','.md','.json','.ipynb','.html','.js','.yml','.txt'}:
        text = path.read_text(encoding='utf-8')
        check(not re.search(r'AQVN[A-Za-z0-9_-]{20,}', text), f'Possible API key: {path.name}')
print('Validation errors: ' + str(len(errors)))
for error in errors:
    print('-', error)
if errors:
    raise SystemExit(1)
print('PASS: paintings, dialogues, VLM inputs, hashes, selection, notebook, and secret scan.')
