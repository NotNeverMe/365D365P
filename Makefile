.PHONY: setup test run refresh-data

setup:
	pip install -e ".[dev]"

test:
	pytest

# make run P=001   -> launches projects/001-*/app.py
run:
	streamlit run $$(ls -d projects/$(P)-*)/app.py

# Delete cached downloads so the next run fetches fresh data from the source APIs.
refresh-data:
	rm -rf data/worldbank/*.csv.gz data/fred/*.csv.gz data/bigmac/*.csv
