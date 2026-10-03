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

if __name__ == "__main__":
    main()
