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

## Citation support checker prototype

After running the pipeline, start the local checker from this folder:

```bash
.venv/bin/python citation_checker.py
```

On Windows, use `.venv\Scripts\python.exe citation_checker.py`. Open
`http://127.0.0.1:8765` in your browser. Choose a saved source and a PDF page
(or use the saved post/message ID), load its text, keep an exact relevant
passage, enter a claim and your TypeSafe API key, then check support. The key is
used for that request and is not saved by the checker. JEV also receives the
source metadata from its MEDFORD record, excluding the saved passage and earlier
JEV score. The page shows the original source link and the full saved MEDFORD
record when you choose a source. The NouL score estimates
whether the cited passage supports the claim; it does not establish historical
truth or create a MEDFORD record.
