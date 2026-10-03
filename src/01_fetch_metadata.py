import requests
import csv

class DoiParser:
    def __init__(self, csvfile: str, base_url: str ="https://api.openalex.org"):
        self.csvfile:  str  = csvfile
        self.base_url: str  = base_url 
        self.dois: list[str] = []

    def extract_doi(self):
        """
            Extract DOI's from a csvfile
            format is always a csv only file that
            contains the first colunm with DOI's
        """
        with open(self.csvfile, newline="", encoding="utf-8") as f:
            lines = csv.reader(f)
            for line in lines:
                self.dois.append(line[0])
            # removendo a coluna
            self.dois = self.dois[1:]
   
if __name__ == "__main__":
    mf = DoiParser("data/start_set_dois.csv")
    mf.extract_doi()
    print(mf.dois)

