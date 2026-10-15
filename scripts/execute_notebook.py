from pathlib import Path
import sys
import nbformat
from nbclient import NotebookClient
from jupyter_client.kernelspec import KernelSpecManager
import tempfile
import json

root = Path(__file__).resolve().parents[1]
path = root / 'Agent_Artist.ipynb'
notebook = nbformat.read(path, as_version=4)
# A task-local kernel spec avoids installing anything into the user's Jupyter setup.
with tempfile.TemporaryDirectory(prefix='agent-artist-kernel-') as directory:
    spec = Path(directory) / 'task-python'
    spec.mkdir()
    (spec / 'kernel.json').write_text(json.dumps({
        'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        'display_name': 'Task Python', 'language': 'python',
    }), encoding='utf-8')
    manager = KernelSpecManager(kernel_dirs=[directory])
    client = NotebookClient(notebook, timeout=180, kernel_name='task-python',
                            resources={'metadata': {'path': str(root)}})
    client.km = client.create_kernel_manager()
    client.km.kernel_spec_manager = manager
    client.execute()
nbformat.write(notebook, path)
print('Executed notebook saved; no generation calls were requested.')
