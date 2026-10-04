.PHONY: run demo test rehearse check
run:
	python3 scripts/dev.py
demo:
	python3 scripts/dev.py --demo
test:
	python3 -m unittest discover -s tests -v
rehearse:
	python3 scripts/rehearse.py
check: test
	python3 -m compileall -q releaseops scripts tests
	bash -n scripts/deploy.sh scripts/rollback.sh
