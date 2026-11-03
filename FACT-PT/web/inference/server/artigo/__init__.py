"""The fact-checking article, written by a model behind an API (`redator_api.py`), prompted with
the configuration evaluated.

Ported from `article_generation/v2_campanha2`, the configuration the dissertation evaluated as
`full` (2026-09-27): the same base prompt, content plan, verdict texts and grammar, with the
same decoding. Each module names the file it comes from; the texts the model reads are copied
verbatim, and `tools/verificar_porte_artigo.py` proves it against the plans of that run.
"""
