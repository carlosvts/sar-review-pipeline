from sar_review_pipeline.fetch_metadata.parser import DoiParser
from sar_review_pipeline.fetch_metadata.api import OpenAlexSnowballer
from sar_review_pipeline.title_screening import run


def main():
    mf = DoiParser("data/start_set_dois.csv")
    mf.extract_doi()

    sn = OpenAlexSnowballer()
    sn.fetch_startset(mf.dois)
    ids = sn.pending_ids(sn.startset) 
    sn.load_backward()
   
    for i in range(3):
        print(f"ITERAÇÃO: {i}")
        # TODO: Fazer o title_screening retornar um jsonl já filtrado
        # TODO: fazer a funcao que transforma jsonl em dicionario para passar para
        # o pending_ids
        ids = sn.pending_ids(jsonl_into_dict(""))
        sn.fetch_backward(ids, round=i)
        sn.save()
        run(round=i)

if __name__ == "__main__":
    main()
