import requests
import csv

class DoiParser:
    def __init__(self, csvfile: str):
        self.csvfile:  str  = csvfile
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
  
 
class OpenAlexAPI:
    def __init__(self, base_url: str = "https://api.openalex.org"):
        self.base_url = base_url

    def get_referenced_works(self, dois:list[str]):
        """
            Gets all OpenAlexID and referenced works from a doi
        """
        # thanks to https://blog.openalex.org/fetch-multiple-dois-in-one-openalex-api-request/
        pipe_separated_dois = "|".join(dois)
        endpoint = self.base_url + f"/works?filter=doi:{pipe_separated_dois}&per-page=50&mailto=carlosvtsdev@gmail.com" 
        response = requests.get(endpoint)
        works = response.json()["results"]
        for work in works:
            print(f"ID:{work['id']}\nTITLE:{work['title']}")
            print()


if __name__ == "__main__":
    mf = DoiParser("data/start_set_dois.csv")
    mf.extract_doi()
    print(mf.dois)
    oa_api = OpenAlexAPI()
    oa_api.get_referenced_works(mf.dois)
