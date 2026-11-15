import csv


class DoiParser:
    def __init__(self, csvfile: str):
        self.csvfile: str = csvfile
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
