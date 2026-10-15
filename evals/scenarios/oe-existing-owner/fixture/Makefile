PYTHON ?= python3

.PHONY: check test compile

# Run before handing work back.
check: test compile

test:
	$(PYTHON) -m unittest discover -s tests -t . -q

compile:
	$(PYTHON) -m compileall -q clubroll
