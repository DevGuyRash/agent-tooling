.PHONY: test publish

test:
	python3 -m unittest discover -s tests -q

publish: test
	rm -rf dist && python3 -m build && python3 -m twine upload dist/*
