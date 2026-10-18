"""
    Etapa 1 da triagem por abstract: junta os candidatos da triagem por título
    com o registro completo do work, roda a cascata de abstracts, aplica a
    regra de decisão e monta o relatório de cobertura.
"""
import json
import random
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from sar_review_pipeline.abstracts.fetch import AbstractFetcher
from sar_review_pipeline.work import Work

SEED = 42  # semente fixa: a mesma amostra em toda execução


class AbstractStage:
    CANDIDATES_PATH = Path("data/jsonl/candidates.jsonl")
    WORKS_PATH = Path("data/jsonl/backward.jsonl")
    OUTPUT_PATH = Path("data/jsonl/candidates_abstracts.jsonl")
    REPORT_PATH = Path("data/abstracts/coverage_report.json")
    SCREENING_FIELDS = ("status", "matched_rule", "matched_keyword")
    # limites das faixas de tamanho (em palavras) no relatório
    WORD_BINS = (10, 20, 30, 40, 50, 75, 100, 150, 200, 300)

    @classmethod
    def load_candidates(cls) -> list[tuple[dict, Work]]:
        """Linhas de candidates.jsonl com o Work completo (oa_locations, autores...) do backward."""
        works = Work.load_jsonl(str(cls.WORKS_PATH))
        candidates = []
        with open(cls.CANDIDATES_PATH, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                candidates.append((row, works[row["id"]]))
        return candidates

    @classmethod
    def sample(cls, candidates: list[tuple[dict, Work]], n: int, seed: int = SEED) -> list[tuple[dict, Work]]:
        """Amostra reprodutível de n candidatos."""
        ordered = sorted(candidates, key=lambda c: c[0]["id"])
        return random.Random(seed).sample(ordered, min(n, len(ordered)))

    @classmethod
    def build_record(cls, row: dict, work: Work, found: dict) -> dict:
        """
        Schema do Work + campos da triagem por título + campos do abstract.
        Regra de decisão:
          - needs_context sem abstract válido: exclusion_reason = "sem_abstract"
          - passed_title sem abstract válido: segue com title_only = True
            pois o passed_title as vezes pode ser conseguido via acesso cafe
        """
        record = asdict(work)
        for field in cls.SCREENING_FIELDS:
            record[field] = row.get(field)
        record["abstract"] = found["abstract"]
        record["abstract_source"] = found["abstract_source"]
        record["abstract_match"] = found["abstract_match"]
        record["abstract_status"] = found["abstract_status"]
        record["abstract_flags"] = found["abstract_flags"]

        has_abstract = found["abstract_status"] == "ok"
        record["title_only"] = row["status"] == "passed_title" and not has_abstract
        if row["status"] == "needs_context" and not has_abstract:
            record["exclusion_reason"] = "sem_abstract"
        else:
            record["exclusion_reason"] = None
        return record

    @classmethod
    def run(cls, candidates: list[tuple[dict, Work]]) -> list[dict]:
        """Cascata em todos os candidatos. Devolve [{record, rejected, errors}]."""
        results = []
        total = len(candidates)
        for i, (row, work) in enumerate(candidates, start=1):
            found = AbstractFetcher.find_abstract(work)
            record = cls.build_record(row, work, found)
            results.append({"record": record, "rejected": found["rejected"], "errors": found["errors"]})
            print(f"[{i}/{total}] {work.id}  {found['abstract_status']} ({found['abstract_source']})")
        return results

    @classmethod
    def save(cls, results: list[dict], path: Path = OUTPUT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r["record"], ensure_ascii=False) + "\n")

    @classmethod
    def word_bin(cls, n_words: int) -> str:
        lower = 0
        for upper in cls.WORD_BINS:
            if n_words < upper:
                return f"{lower}-{upper - 1}"
            lower = upper
        return f"{lower}+"

    @classmethod
    def coverage_report(cls, results: list[dict]) -> dict:
        """Contadores de cobertura por fonte e por status, mais as listas para conferir à mão."""
        by_status = Counter()
        by_source = Counter()
        by_match = Counter()
        by_title_status = {}
        flags = Counter()
        words = Counter()
        rejected_by_source = Counter()
        suspects = []
        rejected = []
        errors = []

        for r in results:
            record = r["record"]
            by_status[record["abstract_status"]] += 1
            title_status = by_title_status.setdefault(record["status"], Counter())
            title_status[record["abstract_status"]] += 1

            if record["abstract_status"] == "ok":
                by_source[record["abstract_source"]] += 1
                by_match[record["abstract_match"]] += 1
                words[cls.word_bin(len(record["abstract"].split()))] += 1
            for flag in record["abstract_flags"]:
                flags[flag] += 1
            if record["abstract_flags"]:
                suspects.append({
                    "id": record["id"],
                    "title": record["title"],
                    "source": record["abstract_source"],
                    "flags": record["abstract_flags"],
                })

            for rej in r["rejected"]:
                rejected_by_source[rej["source"]] += 1
                rejected.append({"id": record["id"], **rej})
            if r["errors"]:
                errors.append({"id": record["id"], "errors": r["errors"]})

        ordered_words = {}
        for label in [cls.word_bin(0)] + [cls.word_bin(b) for b in cls.WORD_BINS]:
            ordered_words[label] = words[label]

        return {
            "total": len(results),
            "por_status": dict(by_status),
            "por_fonte": dict(by_source),
            "por_tipo_de_match": dict(by_match),
            "por_status_do_titulo": {k: dict(v) for k, v in by_title_status.items()},
            "excluidos_sem_abstract": sum(1 for r in results if r["record"]["exclusion_reason"] == "sem_abstract"),
            "so_titulo": sum(1 for r in results if r["record"]["title_only"]),
            "palavras_dos_validos": ordered_words,
            "rejeitados_por_fonte": dict(rejected_by_source),
            "suspeitos_por_flag": dict(flags),
            "com_erro_de_api": len(errors),
            "suspeitos": suspects,
            "rejeitados": rejected,
            "erros": errors,
        }

    @classmethod
    def save_report(cls, report: dict, path: Path = REPORT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
