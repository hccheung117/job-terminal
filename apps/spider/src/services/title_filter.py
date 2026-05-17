import re

import pandas as pd


def title_pattern(keywords: list[str]) -> str | None:
    parts = [re.escape(k.strip()) for k in keywords if k and k.strip()]
    if not parts:
        return None
    return r"\b(?:" + "|".join(parts) + r")\b"


def split_by_title(
    df: pd.DataFrame,
    pattern: str,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    matched = df["title"].str.contains(pattern, case=False, regex=True, na=False)
    kept_titles = df.loc[matched, "title"].tolist()
    dropped_titles = df.loc[~matched, "title"].tolist()
    return df[matched], kept_titles, dropped_titles
