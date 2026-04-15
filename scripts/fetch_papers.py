#!/usr/bin/env python3
"""
Fetch latest Treatment-Resistant Depression (TRD) research papers from PubMed E-utilities API.
Targets TRD-relevant journals across general psychiatry, affective disorders,
biological psychiatry, psychopharmacology, neuromodulation, and psychotherapy.
"""

import json
import sys
import argparse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import quote_plus

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

JOURNALS = [
    "Journal of Affective Disorders",
    "Journal of Clinical Psychiatry",
    "American Journal of Psychiatry",
    "JAMA Psychiatry",
    "Biological Psychiatry",
    "Brain Stimulation",
    "Molecular Psychiatry",
    "The Lancet Psychiatry",
    "Neuropsychopharmacology",
    "World Psychiatry",
    "Psychological Medicine",
    "British Journal of Psychiatry",
    "Acta Psychiatrica Scandinavica",
    "European Psychiatry",
    "Journal of Psychiatric Research",
    "Psychiatry Research",
    "Depression and Anxiety",
    "Translational Psychiatry",
    "Biological Psychiatry: Cognitive Neuroscience and Neuroimaging",
    "European Neuropsychopharmacology",
    "International Journal of Neuropsychopharmacology",
    "Progress in Neuro-Psychopharmacology & Biological Psychiatry",
    "World Journal of Biological Psychiatry",
    "CNS Drugs",
    "Psychopharmacology",
    "Journal of Psychopharmacology",
    "Journal of Clinical Psychopharmacology",
    "Current Neuropharmacology",
    "Neurotherapeutics",
    "Neuromodulation",
    "Journal of ECT",
    "Psychotherapy and Psychosomatics",
    "Clinical Psychology Review",
    "Behaviour Research and Therapy",
    "Journal of Consulting and Clinical Psychology",
    "Journal of Psychosomatic Research",
    "General Hospital Psychiatry",
    "Frontiers in Psychiatry",
    "BMC Psychiatry",
    "CNS Spectrums",
    "Psychiatry and Clinical Neurosciences",
    "Neuroscience and Biobehavioral Reviews",
    "CNS Neuroscience & Therapeutics",
    "Clinical Psychopharmacology and Neuroscience",
    "Journal of Neural Transmission",
]

TRD_KEYWORDS_CORE = [
    '"treatment-resistant depression"',
    '"treatment resistant depression"',
    '"refractory depression"',
    '"difficult-to-treat depression"',
    "TRD",
]

TRD_KEYWORDS_INTERVENTION = [
    "ketamine",
    "esketamine",
    "augmentation",
    "lithium",
    '"atypical antipsychotic"',
    '"electroconvulsive therapy"',
    "ECT",
    '"transcranial magnetic stimulation"',
    "TMS",
    "rTMS",
    '"theta-burst stimulation"',
    "DBS",
    "VNS",
    "neuromodulation",
    '"rapid-acting antidepressant"',
    "psychedelic",
    "psilocybin",
]

TRD_KEYWORDS_MECHANISM = [
    "inflammation",
    "cytokines",
    "glutamate",
    "GABA",
    "BDNF",
    "neuroimaging",
    "fMRI",
    "EEG",
    "connectivity",
    '"default mode network"',
    '"reward circuitry"',
    "anhedonia",
    "neuroplasticity",
]

TRD_KEYWORDS_CLINICAL = [
    '"anxious depression"',
    '"melancholic depression"',
    '"bipolar depression"',
    "suicidality",
    '"childhood trauma"',
    "dissociation",
    "insomnia",
    "cognition",
    '"executive function"',
    '"medical comorbidity"',
    "nonresponse",
    '"non-remission"',
    '"partial response"',
    "relapse",
    "recurrence",
    '"chronic depression"',
]

HEADERS = {"User-Agent": "TRDBrainBot/1.0 (research aggregator)"}


def build_query(days: int = 7, max_journals: int = 15) -> str:
    journal_part = " OR ".join([f'"{j}"[Journal]' for j in JOURNALS[:max_journals]])

    trd_core = " OR ".join([f"{k}[Title/Abstract]" for k in TRD_KEYWORDS_CORE])
    trd_intervention = " OR ".join(
        [f"{k}[Title/Abstract]" for k in TRD_KEYWORDS_INTERVENTION]
    )
    trd_context = " OR ".join(
        [f"{k}[Title/Abstract]" for k in TRD_KEYWORDS_MECHANISM + TRD_KEYWORDS_CLINICAL]
    )

    lookback = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y/%m/%d")
    date_part = f'"{lookback}"[Date - Publication] : "3000"[Date - Publication]'

    query = (
        f"(({journal_part})) AND "
        f"({trd_core} OR "
        f'((depress*[Title/Abstract] OR "major depressive disorder"[Title/Abstract]) '
        f"AND ({trd_intervention} OR {trd_context}))) AND "
        f"{date_part}"
    )
    return query


def search_papers(query: str, retmax: int = 50) -> list[str]:
    params = (
        f"?db=pubmed&term={quote_plus(query)}&retmax={retmax}&sort=date&retmode=json"
    )
    url = PUBMED_SEARCH + params
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"[ERROR] PubMed search failed: {e}", file=sys.stderr)
        return []


def fetch_details(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    ids = ",".join(pmids)
    params = f"?db=pubmed&id={ids}&retmode=xml"
    url = PUBMED_FETCH + params
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=60) as resp:
            xml_data = resp.read().decode()
    except Exception as e:
        print(f"[ERROR] PubMed fetch failed: {e}", file=sys.stderr)
        return []

    papers = []
    try:
        root = ET.fromstring(xml_data)
        for article in root.findall(".//PubmedArticle"):
            medline = article.find(".//MedlineCitation")
            art = medline.find(".//Article") if medline else None
            if art is None:
                continue

            title_el = art.find(".//ArticleTitle")
            title = (
                (title_el.text or "").strip()
                if title_el is not None and title_el.text
                else ""
            )

            abstract_parts = []
            for abs_el in art.findall(".//Abstract/AbstractText"):
                label = abs_el.get("Label", "")
                text = "".join(abs_el.itertext()).strip()
                if label and text:
                    abstract_parts.append(f"{label}: {text}")
                elif text:
                    abstract_parts.append(text)
            abstract = " ".join(abstract_parts)[:2000]

            journal_el = art.find(".//Journal/Title")
            journal = (
                (journal_el.text or "").strip()
                if journal_el is not None and journal_el.text
                else ""
            )

            pub_date = art.find(".//PubDate")
            date_str = ""
            if pub_date is not None:
                year = pub_date.findtext("Year", "")
                month = pub_date.findtext("Month", "")
                day = pub_date.findtext("Day", "")
                parts = [p for p in [year, month, day] if p]
                date_str = " ".join(parts)

            pmid_el = medline.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else ""
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

            keywords = []
            for kw in medline.findall(".//KeywordList/Keyword"):
                if kw.text:
                    keywords.append(kw.text.strip())

            authors = []
            for author in art.findall(".//AuthorList/Author")[:6]:
                last = author.findtext("LastName", "")
                fore = author.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {fore}".strip())
            if len(art.findall(".//AuthorList/Author")) > 6:
                authors.append("et al.")

            papers.append(
                {
                    "pmid": pmid,
                    "title": title,
                    "authors": "; ".join(authors),
                    "journal": journal,
                    "date": date_str,
                    "abstract": abstract,
                    "url": link,
                    "keywords": keywords,
                }
            )
    except ET.ParseError as e:
        print(f"[ERROR] XML parse failed: {e}", file=sys.stderr)

    return papers


def main():
    parser = argparse.ArgumentParser(description="Fetch TRD papers from PubMed")
    parser.add_argument("--days", type=int, default=7, help="Lookback days")
    parser.add_argument(
        "--max-papers", type=int, default=50, help="Max papers to fetch"
    )
    parser.add_argument("--output", default="-", help="Output file (- for stdout)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    query = build_query(days=args.days)
    print(
        f"[INFO] Searching PubMed for TRD papers from last {args.days} days...",
        file=sys.stderr,
    )

    pmids = search_papers(query, retmax=args.max_papers)
    print(f"[INFO] Found {len(pmids)} papers", file=sys.stderr)

    if not pmids:
        print("NO_CONTENT", file=sys.stderr)
        if args.json:
            print(
                json.dumps(
                    {
                        "date": datetime.now(timezone(timedelta(hours=8))).strftime(
                            "%Y-%m-%d"
                        ),
                        "count": 0,
                        "papers": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return

    papers = fetch_details(pmids)
    print(f"[INFO] Fetched details for {len(papers)} papers", file=sys.stderr)

    output_data = {
        "date": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d"),
        "count": len(papers),
        "papers": papers,
    }

    out_str = json.dumps(output_data, ensure_ascii=False, indent=2)

    if args.output == "-":
        print(out_str)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_str)
        print(f"[INFO] Saved to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
