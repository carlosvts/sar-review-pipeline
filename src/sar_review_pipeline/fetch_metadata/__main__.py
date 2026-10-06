from .api import OpenAlexSnowballer
from .parser import DoiParser


def main():
    mf = DoiParser("data/start_set_dois.csv")
    mf.extract_doi()

    sn = OpenAlexSnowballer()
    sn.fetch_startset(mf.dois)
    sn.load_backward()

    ids = sn.pending_ids(sn.startset)
    sn.fetch_backward(ids, round=1)
    sn.save()
    print(f"backward: {len(sn.backward)} | sem registro: {len(sn.unresolved)}")


if __name__ == "__main__":
    main()
