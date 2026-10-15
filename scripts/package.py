"""Create a submission ZIP containing public project artifacts only."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
output = root.parent / 'Agent_Artist_submission.zip'
with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in {'.git','.venv','__pycache__','.ipynb_checkpoints','.cache'} for part in relative.parts):
            continue
        if path.name.startswith('.env') and path.name != '.env.sample':
            continue
        if path.suffix in {'.pyc','.log','.tmp'}:
            continue
        archive.write(path, Path('Agent_Artist') / relative)
with ZipFile(output) as archive:
    assert archive.testzip() is None
print(f'Created {output.name}: {output.stat().st_size / 2**20:.1f} MiB')
