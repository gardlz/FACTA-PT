"""Retrieves LUSA documents for each query unit through the search API.

One search per unit (question, claim span or complete claim), up to the day before the claim;
reissues are collapsed (dedup_versions.py) before cutting to --size. Results go to
<output-dir>/<id>.json and documents to the shared cache outputs/lusa_docs/. Re-running resumes.
"""

import argparse
import json
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from comum import DOCS_DIR, QUESTIONS_FILE, TOP20_DIR, configurar_log, read_jsonl, safe_name, write_json
from dedup_versions import agrupar_por_noticia
from lusa_api import LusaApi, LusaApiError

log = logging.getLogger("retrieval")

DICA_PERGUNTAS = "python src/build_gold_questions.py"


def is_done(question, output_dir):
    """Has the unit already been retrieved? (a readable record with its `dedup` block)"""
    caminho = output_dir / f'{safe_name(question["question_id"])}.json'
    if not caminho.exists():
        return False
    try:
        return json.loads(caminho.read_text(encoding="utf-8")).get("dedup") is not None
    except (json.JSONDecodeError, OSError):
        return False


def select_pending(questions, output_dir, args):
    """Units still to retrieve (resume), unless --overwrite."""
    pendentes = questions if args.overwrite else [
        q for q in questions if not is_done(q, output_dir)]
    return pendentes if args.max_questions is None else pendentes[:args.max_questions]


def date_limit(question):
    """Upper bound of the published_at filter: end of the day before the claim.

    An unreadable publication_time stops the script.
    """
    try:
        vespera = date.fromisoformat(question["publication_time"]) - timedelta(days=1)
    except (KeyError, TypeError, ValueError):
        raise SystemExit(f'{question["question_id"]}: publication_time ausente ou ilegível '
                         f'({question.get("publication_time")!r}).') from None
    return f"{vespera.isoformat()}T23:59:59"   # published_at carries a time


def build_result(api_rank, hit):
    """One entry of ``results``; the final ``rank`` is set after the reissue collapse."""
    return {
        "rank": api_rank,
        "api_rank": api_rank,
        "doc_id": str(hit["doc_id"]) if hit.get("doc_id") else None,
        "headline": hit.get("headline"),
        "published_at": hit.get("published_at"),
        "genre": hit.get("genre"),
        "topics": hit.get("topic_names_pt") or [],
        "snippet": hit.get("snippet"),
        "score": hit.get("score", hit.get("_score")),   # not always returned by the API
    }


def read_documents(doc_ids, docs_dir):
    """{doc_id: document} from the cache; missing or unreadable files are left out."""
    documentos = {}
    for doc_id in doc_ids:
        caminho = docs_dir / f"{safe_name(doc_id)}.json"
        try:
            documentos[doc_id] = dict(json.loads(caminho.read_text(encoding="utf-8")),
                                      doc_id=doc_id)
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as erro:
            log.warning("   documento %s ilegível na cache: %s", doc_id, erro)
    return documentos


def collapse_versions(results, documentos):
    """Collapse versions of the same news item into one result.

    The kept version takes the best API position of its group and lists the others in
    ``versions``. Results without doc_id, or whose document is not cached, stay as they are.
    """
    por_id, sem_id = {}, []
    for resultado in results:
        if not resultado["doc_id"]:
            sem_id.append(resultado)
        else:
            por_id.setdefault(resultado["doc_id"], resultado)

    grupos = agrupar_por_noticia([documentos[d] for d in por_id if d in documentos])
    grupos += [(doc_id, [doc_id]) for doc_id in por_id if doc_id not in documentos]

    ficam = []
    for escolhido, grupo in grupos:
        resultado = dict(por_id[escolhido])
        resultado["rank"] = min(por_id[d]["api_rank"] for d in grupo)
        resultado["n_versions"] = len(grupo)
        resultado["versions"] = [por_id[d] for d in
                                 sorted(grupo, key=lambda d: por_id[d]["api_rank"])
                                 if d != escolhido]
        ficam.append(resultado)
    ficam += [dict(r, n_versions=1, versions=[]) for r in sem_id]

    ficam.sort(key=lambda r: r["rank"])
    for rank, resultado in enumerate(ficam, 1):
        resultado["rank"] = rank
    return ficam


def dedup(brutos, args):
    """Results without reissues, not yet cut to --size."""
    documentos = read_documents([r["doc_id"] for r in brutos if r["doc_id"]], args.docs_dir)
    return collapse_versions(brutos, documentos)


def bloco_dedup(brutos, distintas, results):
    """Dedup counters; the three parts add up to n_raw_results."""
    return {
        "n_raw_results": len(brutos),
        "n_duplicates_removed": len(brutos) - len(distintas),
        "n_dropped_by_size": len(distintas) - len(results),
    }


# Field holding the query in the span-level modes: `claim` is the claim span and `frase` the
# complete claim (the CLEVER text_segment).
CAMPO_DA_QUERY = {"claim": "claim_span", "frase": "text_segment"}


def unidades(caminho, modo):
    """Retrieval units: one per gold question, or one per claim span.

    With --query claim or frase the unit is the span: `question_id` holds the span id and
    `question` the text sent to the API. A span without the field is an error.
    """
    registos = read_jsonl(caminho, DICA_PERGUNTAS)
    if modo == "pergunta":
        return registos
    campo = CAMPO_DA_QUERY[modo]
    spans, sem_campo = {}, []
    for registo in registos:
        span_id = registo["span_id"]
        if span_id in spans:
            continue
        texto = registo.get(campo)
        if not texto:
            sem_campo.append(span_id)
            continue
        unidade = dict(registo)
        unidade["question_id"] = span_id
        unidade["question"] = texto
        spans[span_id] = unidade
    if sem_campo:
        raise SystemExit(
            f"{len(sem_campo)} span(s) sem `{campo}` em {caminho} — ex.: {sem_campo[:3]}.\n"
            f"Com --query {modo} a query sai desse campo; sem ele a condição ficaria com "
            f"menos spans do que as outras e as tabelas deixavam de ser comparáveis.")
    return list(spans.values())


def build_record(question, brutos, distintas, total_hits, args, date_to):
    """Content of <output-dir>/<question_id>.json; reissues are counted before the cut."""
    results = distintas[:args.size]
    return {
        "question_id": question["question_id"],
        "span_id": question["span_id"],
        "question": question["question"],   # also the query sent to the API
        "query_mode": args.query,
        "claim_span": question.get("claim_span"),
        "dataset": args.dataset,
        "size": args.size,
        "api_size": api_size(args),
        "date_filter": {"published_at": {"lte": date_to}},
        "dedup": bloco_dedup(brutos, distintas, results),
        "total_hits": total_hits,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_results": len(results),
        "results": results,
    }


def fetch_documents(api, doc_ids, docs_dir, workers):
    """Download the documents missing from the cache; returns the counts."""
    unicos = list(dict.fromkeys(doc_id for doc_id in doc_ids if doc_id))
    em_falta = [d for d in unicos if not (docs_dir / f"{safe_name(d)}.json").exists()]
    contagens = Counter({"em_cache": len(unicos) - len(em_falta), "pedidos": len(em_falta)})
    if not em_falta:
        return contagens
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = {pool.submit(api.get_document, doc_id): doc_id for doc_id in em_falta}
        try:
            for futuro in as_completed(futuros):
                doc_id = futuros[futuro]
                try:
                    write_json(docs_dir / f"{safe_name(doc_id)}.json", futuro.result())
                except (LusaApiError, OSError) as error:
                    contagens["falhados"] += 1
                    log.warning("   documento %s não obtido: %s", doc_id, error)
        except KeyboardInterrupt:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    return contagens


def duracao(segundos):
    """Seconds -> 'h:mm:ss'."""
    return str(timedelta(seconds=int(segundos)))


def eta(inicio, feitas, total):
    """Estimated time left at the average pace of this run."""
    restantes = total - feitas
    if not feitas or not restantes:
        return duracao(0)
    return duracao(restantes * (time.time() - inicio) / feitas)


def print_summary(stats, pendentes, decorrido, args):
    log.info("Concluído: %d/%d perguntas (%d sem resultados, %d falhadas) em %s",
             stats["feitas"], pendentes, stats["sem_resultados"], stats["falhadas"],
             duracao(decorrido))
    log.info("Documentos: %d pedidos à API, %d já em cache, %d falhados",
             stats["pedidos"], stats["em_cache"], stats["falhados"])
    if stats["falhados"]:
        log.warning("As perguntas destes documentos ficaram gravadas na mesma: para "
                    "voltar a tentar descarregá-los, reexecutar com --overwrite.")
    log.info("Pesquisas: %s | Documentos: %s", args.output_dir, args.docs_dir)


def api_size(args):
    """How many documents to request so that --size distinct news items remain."""
    return max(args.size, round(args.size * args.overfetch))


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--input", type=Path, default=QUESTIONS_FILE,
                   help="Query units (JSONL), by default the gold questions.")
    p.add_argument("--output-dir", type=Path, default=TOP20_DIR,
                   help="Folder for the search results, one file per unit.")
    p.add_argument("--docs-dir", type=Path, default=DOCS_DIR,
                   help="Document cache, one file per doc_id.")
    p.add_argument("--query", choices=("pergunta", "claim", "frase"), default="pergunta",
                   help="What is sent as the query: the question (default, one search per "
                        "question), the claim span (`claim`) or the complete claim (`frase`, "
                        "the CLEVER text_segment), one search per span. Use a different "
                        "--output-dir for each.")
    p.add_argument("--dataset", default="LUSA", help="API dataset (default: LUSA).")
    p.add_argument("--size", type=int, default=20,
                   help="Distinct news items kept per search, after reissue collapse (default: 20).")
    p.add_argument("--overfetch", type=float, default=2.0,
                   help="Request this many times --size documents to make up for collapsed "
                        "reissues (default: 2.0).")
    p.add_argument("--workers", type=int, default=4,
                   help="Threads used to fetch the documents of one search (default: 4).")
    p.add_argument("--sleep", type=float, default=0.3,
                   help="Pause (s) between searches (default: 0.3).")
    p.add_argument("--retries", type=int, default=4,
                   help="Attempts per API request (default: 4).")
    p.add_argument("--max-questions", type=int,
                   help="Limit the number of units processed in this run.")
    p.add_argument("--overwrite", action="store_true",
                   help="Redo searches already saved (the document cache is kept).")
    return p.parse_args()


def main():
    args = parse_args()
    configurar_log(args.output_dir.with_name(args.output_dir.name + ".log"))

    questions = unidades(args.input, args.query)
    pendentes = select_pending(questions, args.output_dir, args)
    log.info("Unidades: %d no total | %d nesta execução | dataset=%s size=%d "
             "(pede %d à API)",
             len(questions), len(pendentes), args.dataset, args.size, api_size(args))
    if not pendentes:
        log.info("Nada a fazer nesta execução (%s).",
                 "--max-questions 0" if args.max_questions == 0
                 else f"todas as perguntas já têm resultados em {args.output_dir}")
        return

    api = LusaApi(dataset=args.dataset, retries=args.retries)
    try:
        api.login()
    except LusaApiError as error:
        log.error("%s", error)
        sys.exit(1)

    stats = Counter()
    inicio = time.time()
    try:
        for indice, question in enumerate(pendentes, 1):
            question_id = question["question_id"]
            date_to = date_limit(question)
            try:
                resposta = api.search(question["question"], api_size(args), date_to=date_to)
            except LusaApiError as error:
                stats["falhadas"] += 1
                log.error("[%d/%d] %s: pesquisa falhou (%s)",
                          indice, len(pendentes), question_id, error)
                continue

            brutos = [build_result(rank, hit)
                      for rank, hit in enumerate(resposta.get("results") or [], 1)]
            # Documents are needed before deciding: reissues are compared on the text.
            contagens = fetch_documents(api, [r["doc_id"] for r in brutos],
                                        args.docs_dir, args.workers)
            distintas = dedup(brutos, args)

            registo = build_record(question, brutos, distintas,
                                   resposta.get("total"), args, date_to)
            write_json(args.output_dir / f"{safe_name(question_id)}.json", registo)

            stats["feitas"] += 1
            stats["sem_resultados"] += registo["n_results"] == 0
            stats.update(contagens)
            log.info("[%d/%d] %s -> %d notícias distintas de %d resultados | docs: %d em "
                     "cache, %d pedidos, %d falhados | faltam ~%s",
                     indice, len(pendentes), question_id, registo["n_results"], len(brutos),
                     contagens["em_cache"], contagens["pedidos"], contagens["falhados"],
                     eta(inicio, indice, len(pendentes)))
            if args.sleep > 0 and indice < len(pendentes):
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        log.warning("Interrompido (Ctrl+C) — o que já foi gravado mantém-se; "
                    "reexecutar para continuar de onde ficou.")

    print_summary(stats, len(pendentes), time.time() - inicio, args)


if __name__ == "__main__":
    main()
