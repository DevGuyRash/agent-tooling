.PHONY: test lint check release

test:
	python3 -m unittest discover -s tests -q

lint:
	python3 -m compileall -q pantry tests

check: test lint

release: check
	rm -rf dist && python3 -m build && python3 -m twine upload dist/*
