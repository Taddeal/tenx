PYTHON := python

.PHONY: film radio-cut validate narration keyframes shots music assemble smoke test

film:
	$(PYTHON) run_pipeline.py

radio-cut:
	$(PYTHON) run_pipeline.py --radio-cut

smoke:
	$(PYTHON) pipeline/smoke_test.py

validate:
	$(PYTHON) run_pipeline.py --stage 0

narration:
	$(PYTHON) run_pipeline.py --stage 1

keyframes:
	$(PYTHON) run_pipeline.py --stage 2

shots:
	$(PYTHON) run_pipeline.py --stage 3

music:
	$(PYTHON) run_pipeline.py --stage 4

assemble:
	$(PYTHON) run_pipeline.py --stage 5

test:
	$(PYTHON) -m unittest discover -s tests -v
