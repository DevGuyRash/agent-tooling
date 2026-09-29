.PHONY: test check

test:
	python3 -m unittest discover -s tests -q

check: test
	python3 scripts/check_docs.py
