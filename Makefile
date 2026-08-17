.PHONY: test validate compile clean

test:
	pytest -q

validate:
	python -m foodvideocreator.cli validate
	python -m foodvideocreator.cli validate --step THUMBNAIL_TEXT

compile:
	python -m compileall -q foodvideocreator tests examples

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache build dist *.egg-info
