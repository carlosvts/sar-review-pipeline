from .parser import DoiParser
from .api import OpenAlexAPI


def main():
    mf = DoiParser("data/start_set_dois.csv")
    mf.extract_doi()

    oa_api = OpenAlexAPI()
    oa_api.get_referenced_works(mf.dois)
    oa_api.save_raw()
    oa_api.extract_metadata()
    oa_api.save_metadata(oa_api.metadata, "data/jsonl/start_set.jsonl")

    found = {m.doi for m in oa_api.metadata.values()}
    missing = [d for d in mf.dois if d not in found]
    print(f"{len(oa_api.metadata)}/{len(mf.dois)} encontrados | faltando: {missing}")

    # backward, rodada 1
    oa_api.load_backward()
    ids = oa_api.get_backward_ids(oa_api.metadata)
    print(f"IDs a buscar: {len(ids)}")
    oa_api.get_works_by_ids(ids, round=1)
    oa_api.save_backward()

    com_abstract = sum(w.has_abstract for w in oa_api.backward_metadata.values())
    print(f"backward: {len(oa_api.backward_metadata)} no total | "
          f"sem registro (acumulado): {len(oa_api.unresolved)} | com abstract: {com_abstract}")


if __name__ == "__main__":
    main()
