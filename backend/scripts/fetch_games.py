#!/usr/bin/env python3


import os
import time
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

USER_AGENT = "Gameok/1.0"

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "games_library"
)

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------------------------
# Console QIDs
# --------------------------------------------------------------------

CONSOLES = {
    "Game Boy": "Q186437",
    "Game Boy Color": "Q203992",
    "Nintendo 64": "Q184839",
    "Nintendo DS": "Q170323",
    "Nintendo Switch": "Q19610114",
    "Nintendo GameCube": "Q182172",
    "Super Nintendo Entertainment System": "Q183259",
    "Wii": "Q8079",
    "Xbox": "Q132020",
    "Xbox 360": "Q48263",
    "Xbox One": "Q132020",
    "Xbox Series X/S": "Q98973368",
    "Sega Genesis": "Q10676",
    "PlayStation": "Q10677",
    "PlayStation 2": "Q10680",
    "PlayStation 3": "Q10683",
    "PlayStation 4": "Q5014725",
    "PlayStation 5": "Q63184502",
}

QUERY_TEMPLATE = """
SELECT DISTINCT
    ?game
    ?title
    ?year
    ?developerLabel
    ?seriesLabel
    ?coverPhoto
WHERE {

    VALUES ?platform { wd:%s }

    {
        ?game wdt:P31 wd:Q7889 ;
              wdt:P400 ?platform .
    }

    UNION

    {
        ?release wdt:P31 wd:Q1066707 ;
                 wdt:P400 ?platform ;
                 wdt:P1441 ?game .
    }

    OPTIONAL {
        ?game wdt:P1476 ?officialTitle .
        FILTER(LANG(?officialTitle) = "en")
    }

    OPTIONAL {
        ?game wdt:P577 ?releaseDate .
        BIND(YEAR(?releaseDate) AS ?year)
    }

    OPTIONAL {
        ?game wdt:P178 ?developer .
    }

    OPTIONAL {
        ?game wdt:P179 ?series .
    }

    OPTIONAL {
        ?game wdt:P18 ?coverPhoto .
    }

    SERVICE wikibase:label {
        bd:serviceParam wikibase:language "en".

        ?game rdfs:label ?gameLabel .
        ?developer rdfs:label ?developerLabel .
        ?series rdfs:label ?seriesLabel .
    }

    BIND(COALESCE(?officialTitle, ?gameLabel) AS ?title)
}
ORDER BY ?title
"""

# ----------------------------------------------------------------------
# HTTP Session
# ----------------------------------------------------------------------

session = requests.Session()

retry = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
)

adapter = HTTPAdapter(max_retries=retry)

session.mount("https://", adapter)

session.headers.update({
    "Accept": "application/sparql-results+json",
    "User-Agent": USER_AGENT,
})


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def run_query(query: str):
    response = session.get(
        SPARQL_ENDPOINT,
        params={"query": query},
        timeout=180,
    )

    response.raise_for_status()

    return response.json()["results"]["bindings"]


def commons_url(value):
    """
    Convert Commons filename/URI into a direct image URL.
    """

    if not value:
        return None

    filename = value.split("/")[-1]

    if filename.startswith("File:"):
        filename = filename[5:]

    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + quote(filename)
    )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():

    print(f"Saving CSVs to:\n{OUTPUT_DIR}\n")

    for console_name, qid in CONSOLES.items():

        print("=" * 70)
        print(f"{console_name}")
        print(f"QID: {qid}")

        query = QUERY_TEMPLATE % qid

        try:
            print ("Running query...")
            rows = run_query(query)

        except Exception as ex:
            print(f"Failed: {ex}")
            continue

        games = []

        for row in rows:

            title = row.get("title", {}).get("value")

            # Skip data without title or year
            if not title:
                continue

            year = None

            if "year" in row:
                try:
                    year = int(row["year"]["value"])
                except Exception:
                    continue
            else:
                continue

            developer = row.get(
                "developerLabel",
                {}
            ).get("value")

            series = row.get(
                "seriesLabel",
                {}
            ).get("value")

            cover = row.get(
                "coverPhoto",
                {}
            ).get("value")

            game_uri = row["game"]["value"]

            wikidata_id = game_uri.rsplit("/", 1)[-1]

            games.append({
                "wikidata_id": wikidata_id,
                "console": console_name,
                "title": title,
                "year": year,
                "developer": developer,
                "series": series,
                "cover_url": commons_url(cover),
            })

        df = pd.DataFrame(games)
        if df.empty:
            print("No games found.")
            continue

        # Remove completely identical rows
        df = df.drop_duplicates()

        df = df.drop_duplicates(
            subset=[
                "title",
                "year",
                "developer",
            ],
            keep="first",
        )

        df = df.sort_values(
            by=[
                "title",
                "year",
                "developer",
            ],
            na_position="last",
        )

        filename = (
            console_name
            .replace("/", "-")
            .replace(" ", "_")
            + ".csv"
        )

        output_path = os.path.join(
            OUTPUT_DIR,
            filename
        )

        df.to_csv(
            output_path,
            index=False,
            encoding="utf-8-sig",
        )

        print(f"Saved {len(df):,} games")
        print(output_path)

        # be nice to Wikidata server
        time.sleep(1.5)

    print("\nFinished.")


if __name__ == "__main__":
    main()