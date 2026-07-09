#!/usr/bin/env python3
"""Update the Internal Medicine Review Hub catalog from PubMed.

The script uses NCBI E-utilities with standard-library Python only. Newly
imported records are marked as pending review so the public UI can separate
automatic discovery from clinician-curated exam/clinical recommendations.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CURATION_FIELDS = {
    "curationStatus",
    "examPriority",
    "clinicalPriority",
    "examWeight",
    "clinicalWeight",
    "localNotes",
    "reviewedBy",
    "reviewedAt",
    "examTags",
    "clinicalTags",
    "keyPoints",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch recent internal medicine reviews and guidelines from PubMed.")
    parser.add_argument("--topics", default="data/topics.json", help="Path to topic query definitions.")
    parser.add_argument("--catalog", default="data/catalog.json", help="Path to catalog JSON.")
    parser.add_argument("--years", type=int, default=10, help="Publication date window in years.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum PubMed records per topic.")
    parser.add_argument("--sleep", type=float, default=0.4, help="Delay between NCBI requests in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report counts without writing the catalog.")
    parser.add_argument("--replace-pending", action="store_true", help="Drop pending auto-imported records before importing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    topics_path = (root / args.topics).resolve() if not Path(args.topics).is_absolute() else Path(args.topics)
    catalog_path = (root / args.catalog).resolve() if not Path(args.catalog).is_absolute() else Path(args.catalog)

    topics = read_json(topics_path)
    catalog = read_json(catalog_path) if catalog_path.exists() else {"meta": {}, "articles": []}
    existing_articles = catalog.get("articles", [])
    if args.replace_pending:
        existing_articles = [item for item in existing_articles if item.get("curationStatus") != "pending"]
    existing_by_pmid = {str(item.get("pmid")): item for item in existing_articles if item.get("pmid")}
    existing_by_id = {str(item.get("id")): item for item in existing_articles if item.get("id")}

    imported: list[dict[str, Any]] = []
    for topic in topics:
        ids = search_pubmed(topic, args.years, args.limit, args.sleep)
        if not ids:
            continue
        imported.extend(fetch_pubmed_records(ids, topic, args.sleep))

    merged = merge_articles(existing_articles, imported, existing_by_pmid, existing_by_id)
    next_catalog = {
        "meta": {
            "generatedAt": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
            "source": "PubMed E-utilities",
            "notice": "Automatically imported records are pending review until curated.",
            "importedCount": len(imported),
            "topicCount": len(topics),
        },
        "articles": sort_articles(merged),
    }

    if args.dry_run:
        print(f"Fetched {len(imported)} PubMed records. Catalog would contain {len(next_catalog['articles'])} records.")
        return 0

    catalog_path.write_text(json.dumps(next_catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {catalog_path} with {len(next_catalog['articles'])} records ({len(imported)} fetched this run).")
    return 0


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def search_pubmed(topic: dict[str, Any], years: int, limit: int, sleep: float) -> list[str]:
    current_year = dt.date.today().year
    start_year = current_year - years + 1
    article_types = "Review[Publication Type] OR Guideline[Publication Type] OR Practice Guideline[Publication Type] OR Meta-Analysis[Publication Type]"
    date_filter = f'"{start_year}/01/01"[Date - Publication] : "{current_year}/12/31"[Date - Publication]'
    adult_internal_filter = "english[Language] NOT (pregnan*[Title/Abstract] OR obstetric*[Title/Abstract] OR postpartum[Title/Abstract] OR maternal[Title/Abstract] OR neonatal[Title/Abstract] OR pediatric*[Title/Abstract] OR paediatric*[Title/Abstract] OR child[Title/Abstract] OR children[Title/Abstract] OR infant[Title/Abstract])"
    term = f"({topic['query']}) AND ({article_types}) AND ({date_filter}) AND ({adult_internal_filter})"
    params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": str(limit),
        "sort": "pub+date",
        "term": term,
        **ncbi_identity_params(),
    }
    data = request_json(f"{BASE_URL}/esearch.fcgi", params, sleep)
    return data.get("esearchresult", {}).get("idlist", [])


def fetch_pubmed_records(ids: list[str], topic: dict[str, Any], sleep: float) -> list[dict[str, Any]]:
    params = {
        "db": "pubmed",
        "retmode": "xml",
        "id": ",".join(ids),
        **ncbi_identity_params(),
    }
    root = request_xml(f"{BASE_URL}/efetch.fcgi", params, sleep)
    records = []
    for node in root.findall(".//PubmedArticle"):
        article = parse_pubmed_article(node, topic)
        if article:
            records.append(article)
    return records


def ncbi_identity_params() -> dict[str, str]:
    params = {
        "tool": os.environ.get("NCBI_TOOL", "internal-medicine-review-hub"),
        "email": os.environ.get("NCBI_EMAIL", "maintainer@example.com"),
    }
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def request_json(url: str, params: dict[str, str], sleep: float) -> dict[str, Any]:
    with urllib.request.urlopen(build_request(url, params), timeout=30) as response:
        payload = response.read().decode("utf-8")
    time.sleep(sleep)
    return json.loads(payload)


def request_xml(url: str, params: dict[str, str], sleep: float) -> ET.Element:
    with urllib.request.urlopen(build_request(url, params), timeout=30) as response:
        payload = response.read()
    time.sleep(sleep)
    return ET.fromstring(payload)


def build_request(url: str, params: dict[str, str]) -> urllib.request.Request:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}")
    request.add_header("User-Agent", "internal-medicine-review-hub/0.1")
    return request


def parse_pubmed_article(node: ET.Element, topic: dict[str, Any]) -> dict[str, Any] | None:
    pmid = text(node.find(".//PMID"))
    title_node = node.find(".//ArticleTitle")
    title = iter_text(title_node)
    if not pmid or not title:
        return None

    pubtypes = [iter_text(item) for item in node.findall(".//PublicationTypeList/PublicationType")]
    journal = iter_text(node.find(".//Journal/Title")) or iter_text(node.find(".//MedlineTA")) or "PubMed"
    year = extract_year(node)
    doi = article_id(node, "doi")
    pmcid = normalize_pmcid(article_id(node, "pmc"))
    article_type = classify_article_type(pubtypes)

    return {
        "id": f"pmid-{pmid}",
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "title": normalize_space(title),
        "journal": normalize_space(journal),
        "year": year,
        "department": topic.get("department"),
        "disease": topic.get("disease"),
        "articleType": article_type,
        "curationStatus": "pending",
        "examPriority": "unrated",
        "clinicalPriority": "unrated",
        "examWeight": topic.get("examWeight", 0),
        "clinicalWeight": topic.get("clinicalWeight", 0),
        "freeFullText": bool(pmcid),
        "tags": topic.get("tags", []),
        "publicationTypes": pubtypes,
        "score": score_record(year, article_type, journal, bool(pmcid), topic),
        "lastChecked": dt.date.today().isoformat(),
        "links": build_links(pmid, pmcid, doi),
    }


def article_id(node: ET.Element, id_type: str) -> str | None:
    for item in node.findall(".//ArticleIdList/ArticleId"):
        if item.attrib.get("IdType") == id_type:
            return normalize_space(iter_text(item))
    return None


def normalize_pmcid(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_space(value)
    return normalized if normalized.upper().startswith("PMC") else f"PMC{normalized}"


def build_links(pmid: str, pmcid: str | None, doi: str | None) -> dict[str, str]:
    links = {"pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}
    if pmcid:
        links["pmc"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
    if doi:
        links["doi"] = f"https://doi.org/{doi}"
    return links


def classify_article_type(pubtypes: list[str]) -> str:
    joined = " ".join(pubtypes).lower()
    if "practice guideline" in joined or re.search(r"\bguideline\b", joined):
        return "Guideline"
    if "meta-analysis" in joined or "systematic review" in joined:
        return "Meta-analysis"
    if "review" in joined:
        return "Review"
    return "Article"


def extract_year(node: ET.Element) -> int | None:
    candidates = [
        text(node.find(".//ArticleDate/Year")),
        text(node.find(".//JournalIssue/PubDate/Year")),
        text(node.find(".//PubMedPubDate[@PubStatus='pubmed']/Year")),
        text(node.find(".//PubDate/MedlineDate")),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        match = re.search(r"(19|20)\d{2}", candidate)
        if match:
            return int(match.group(0))
    return None


def score_record(year: int | None, article_type: str, journal: str, free_full_text: bool, topic: dict[str, Any]) -> int:
    current_year = dt.date.today().year
    recency = max(0, 12 - (current_year - int(year or current_year)))
    type_bonus = {"Guideline": 18, "Meta-analysis": 14, "Review": 10}.get(article_type, 0)
    journal_bonus = 8 if re.search(r"nejm|lancet|jama|bmj|annals|nature|mayo|cleveland", journal, re.I) else 0
    access_bonus = 4 if free_full_text else 0
    topic_bonus = int(topic.get("examWeight", 0)) + int(topic.get("clinicalWeight", 0))
    return recency + type_bonus + journal_bonus + access_bonus + topic_bonus


def merge_articles(
    existing_articles: list[dict[str, Any]],
    imported: list[dict[str, Any]],
    existing_by_pmid: dict[str, dict[str, Any]],
    existing_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_by_id = {item.get("id"): dict(item) for item in existing_articles if item.get("id")}
    for item in imported:
        existing = existing_by_pmid.get(str(item.get("pmid"))) or existing_by_id.get(str(item.get("id")))
        if existing:
            combined = {**existing, **item}
            for field in CURATION_FIELDS:
                if field in existing:
                    combined[field] = existing[field]
            merged_by_id[combined["id"]] = combined
        else:
            merged_by_id[item["id"]] = item
    return list(merged_by_id.values())


def sort_articles(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (int(item.get("year") or 0), int(item.get("score") or 0), item.get("title") or ""), reverse=True)


def iter_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext())


def text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    return normalize_space(node.text)


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"update failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
