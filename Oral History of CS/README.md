# Oral History of CS

Install Python 3.12+ and Git. Open a terminal in this folder.

**macOS:**
```bash
bash run.sh
```

**Windows:**
```powershell
.\run.cmd
```

These commands set up dependencies and process all HTML/PDF sources.
Matching saved JEV evaluations are reused.

To evaluate new or changed evidence, add `--evaluate`:
```bash
bash run.sh --evaluate
```
On Windows, use `.\run.cmd --evaluate`. Enter the TypeSafe API key when prompted;
no prompt appears if saved evaluations suffice or `TYPESAFE_API_KEY` is set.

Add `--offline` to use only saved files, or `--source chm-knuth-2007`
to run one source. With the virtual environment already active, the same options
work with `python main.py`.

Results and percentages: `output/run-summary.json`. MEDFORD records: `output/medford/`.
