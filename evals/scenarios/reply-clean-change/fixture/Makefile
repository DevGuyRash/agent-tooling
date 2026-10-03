PYTHON ?= python3

.PHONY: check test examples compile

# Everything that has to pass before a change goes onto the front-desk laptop.
check: test examples compile

test:
	$(PYTHON) -m unittest discover -s tests -t . -q

examples:
	$(PYTHON) scripts/check_examples.py docs/*.md

compile:
	$(PYTHON) -m compileall -q loanbook scripts
