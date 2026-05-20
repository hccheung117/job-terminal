#!/usr/bin/env bash
cd "$(dirname "$0")"

./spider scrape
./spider upload
./pipeline title filter
./pipeline title judge
./spider enrich
./pipeline jd judge