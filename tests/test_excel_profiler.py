from pathlib import Path

import pandas as pd

from venture_metrics_agent.ingestion.excel_profiler import profile_folder


def test_profile_folder_detects_urls_and_columns(tmp_path: Path) -> None:
    workbook = tmp_path / "sample.xlsx"
    df = pd.DataFrame(
        [
            {
                "Title": "Grant policy",
                "Region": "Hong Kong",
                "Link": "https://www.gov.hk/en/",
            },
            {
                "Title": "Science park",
                "Region": "Hong Kong",
                "Link": "https://www.hkstp.org/",
            },
        ]
    )
    df.to_excel(workbook, index=False)

    report = profile_folder(tmp_path)

    assert report["totals"]["files"] == 1
    assert report["totals"]["sheets"] == 1
    assert report["totals"]["rows"] == 2
    assert report["totals"]["urls"] == 2

    sheet = report["files"][0]["sheets"][0]
    assert sheet["likely_title_columns"] == ["Title"]
    assert sheet["likely_region_columns"] == ["Region"]
    assert sheet["detected_url_columns"] == [{"column_name": "Link", "url_count": 2}]

