# Internal Medicine Review Hub

內科專科醫師考試與臨床文獻追蹤用的靜態網站原型。前端負責搜尋、分類、免費全文、專考高頻、臨床必讀與收藏；後端更新用 `scripts/update_pubmed.py` 從 PubMed E-utilities 匯入 review、guideline、practice guideline、meta-analysis 類文獻。

## Run locally

```bash
python3 -m http.server 4173
```

Open `http://127.0.0.1:4173/`.

## Update from PubMed

```bash
NCBI_EMAIL=your-email@example.com python3 scripts/update_pubmed.py --years 10 --limit 25
```

New PubMed records are marked as `curationStatus: "pending"` and `examPriority` / `clinicalPriority` as `unrated`. Keep that behavior for clinical safety: automatic discovery should not equal clinical recommendation.

To refresh auto-imported candidates after changing query rules:

```bash
NCBI_EMAIL=your-email@example.com python3 scripts/update_pubmed.py --replace-pending --years 10 --limit 25
```

## Data model

- `data/topics.json`: disease-level PubMed query seeds and rough exam/clinical weights.
- `data/catalog.json`: public catalog consumed by the website.
- `curationStatus`: `seed`, `pending`, `reviewed`, or `curated`.
- `examPriority`: `unrated`, `low`, `medium`, `high`, or `core`.
- `clinicalPriority`: `unrated`, `low`, `medium`, `high`, or `core`.

## Automation

The GitHub Actions workflow in `.github/workflows/update-pubmed.yml` runs weekly and can also be triggered manually. Add repository secrets:

- `NCBI_EMAIL`: maintainer email for NCBI E-utilities requests.
- `NCBI_API_KEY`: optional, raises the default request rate when configured.

## Clinical content policy

Use the auto-update pipeline to find candidate literature. Use clinician review before marking anything as exam-core or clinical-core. For bedside decisions, link back to the original guideline, article, local formulary, drug label, and hospital policy.
