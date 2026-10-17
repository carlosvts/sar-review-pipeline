from sar_review_pipeline.fetch_metadata.parser import DoiParser
from sar_review_pipeline.fetch_metadata.api import OpenAlexSnowballer
from sar_review_pipeline.screening import (
    OUTPUT_JSON_PATH,
    OUTPUT_JSONL_PATH,
    filter,
    load_screening_rows,
    run,
)
from itertools import count
from pathlib import Path

START_SET_PATH = Path("data/start_set_dois.csv")
# MAX_ROUNDS = 5
# só passed_title alimenta a fronteira; needs_context vai para candidates.jsonl
# (via filter) e fica para a triagem de abstract, mas não expande o snowballing
FRONTIER_STATUSES = ("passed_title",)


def main():
    mf = DoiParser(str(START_SET_PATH))
    mf.extract_doi()

    sn = OpenAlexSnowballer()
    sn.fetch_startset(mf.dois)
    # carrega o que já foi baixado antes de calcular os pendentes
    sn.load_backward()

    # fronteira: works cujas referências ainda vamos buscar
    # na rodada 1 é o start set; depois, só os novos que passaram pelo título
    frontier = sn.startset

    # for round in range(1, MAX_ROUNDS + 1):
    for round in count(1):
        print(f"ITERAÇÃO: {round}")
        ids = sn.pending_ids(frontier)
        # recalcula o que deve ser buscado, se não houver mais nada
        # pula para aproxima rodada ou encerra o snowballing (se fronteira vazia)
        if ids:
            sn.fetch_backward(ids, round=round)
        else:
            print("Nenhuma referência nova para buscar nesta rodada.")
        sn.save()
        run()
        filter(OUTPUT_JSONL_PATH)

        # nova fronteira: works que entraram nesta rodada e passaram pelo título
        rows = load_screening_rows(OUTPUT_JSONL_PATH, OUTPUT_JSON_PATH)
        frontier = {}
        for work_id, w in sn.backward.items():
            if w.backward_round != round:
                continue
            row = rows.get(work_id)
            if row and row["status"] in FRONTIER_STATUSES:
                frontier[work_id] = w
        print(f"{len(ids)} buscados, {len(frontier)} passaram pelo título")
        if not frontier:
            print("Fronteira vazia, snowballing convergiu.")
            break


if __name__ == "__main__":
    main()
