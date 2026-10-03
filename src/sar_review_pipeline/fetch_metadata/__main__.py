from .parser import DoiParser
from .api import OpenAlexAPI


def main():
    mf = DoiParser("data/start_set_dois.csv")
    mf.extract_doi()
    oa_api = OpenAlexAPI()
    oa_api.get_referenced_works(mf.dois)
    oa_api.save_raw()
    oa_api.extract_metadata()
    # conferência: algum DOI do start set não voltou do OpenAlex?
    found = {m.doi for m in oa_api.metadata.values()}
    missing = [d for d in mf.dois if d not in found]
    print(f"{len(oa_api.metadata)}/{len(mf.dois)} encontrados | faltando: {missing}")

    for m in oa_api.metadata.values():
        print(m.has_abstract, m.publisher, m.type, m.doi)
    
    all_refs = set()
    for m in oa_api.metadata.values():
        all_refs.update(m.referenced_works)

    total = sum(m.referenced_works_count or 0 for m in oa_api.metadata.values())
    print(f"referências somadas: {total} | únicas: {len(all_refs)}")

    ids = oa_api.get_backward_ids()
    print(f"IDs a buscar: {len(ids)}")
    oa_api.get_works_by_ids(ids)
    oa_api.save_raw("data/raw/backward.json", works=oa_api.backward_works)
    oa_api.extract_backward_metadata()

    returned = set(oa_api.backward_metadata)
    not_returned = [x for x in ids if x not in returned]
    com_abstract = sum(w.has_abstract for w in oa_api.backward_metadata.values())
    print(f"{len(returned)}/{len(ids)} retornaram | sem retorno: {len(not_returned)} | com abstract: {com_abstract}")


if __name__ == "__main__":
    main()
