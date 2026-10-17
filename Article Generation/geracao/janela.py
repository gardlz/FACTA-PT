"""Claim context window: the claim span's sentence(s) plus one sentence on each side.

Sentences come from a small regex splitter with no dependencies (`split_sentences`).
"""

import re

# A sentence ends at ".", "!" or "?" followed by whitespace, but not after these common
# abbreviations or after an initial (whitespace + a single capital letter).
_ABBREV = (r"(?<!\bSr)(?<!\bSra)(?<!\bDr)(?<!\bDra)(?<!\bEng)(?<!\bProf)(?<!\bex)(?<!\bp)"
           r"(?<!\bfig)(?<!\bart)(?<!\bpág)(?<!\bvs)"
           r"(?<!\s[A-ZÀ-Þ])")
_SENT_END_RE = re.compile(r"(?<=[.!?])(?=\s)")


def _find_span(context: str, claim_span: str):
    """(start, end) of the claim span in the context, or None if it does not occur verbatim."""
    if not context or not claim_span:
        return None
    i = context.find(claim_span)
    if i >= 0:
        return i, i + len(claim_span)
    return None


def split_sentences(text: str):
    """Split the text into sentences, returning (start, end) in characters for each."""
    if not text:
        return []
    cuts = [0]
    for m in _SENT_END_RE.finditer(text):
        i = m.start()
        if re.search(_ABBREV + r"[.!?]$", text[:i]):
            cuts.append(i)
    cuts.append(len(text))
    spans = []
    for a, b in zip(cuts, cuts[1:]):
        if text[a:b].strip():
            spans.append((a, b))
    return spans or [(0, len(text))]


def sentence_window(context: str, claim_span: str, n_before: int = 1, n_after: int = 1):
    """The claim span's sentence(s) with `n_before` sentences before and `n_after` after."""
    span = _find_span(context, claim_span)
    if span is None:
        return None
    start, end = span
    sents = split_sentences(context)
    hit = [i for i, (a, b) in enumerate(sents) if a < end and b > start]  # sentences the span hits
    if not hit:
        return None
    lo = max(0, hit[0] - n_before)
    hi = min(len(sents) - 1, hit[-1] + n_after)
    return context[sents[lo][0]:sents[hi][1]].strip()
