PYTHON ?= python3
RUFF ?= ruff
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: help test-llm check-llm

help:
	@printf '%s\n' 'test-llm   Run llm unit and local mock-HTTP tests (requires Python 3.11+, uv, xh).' 'check-llm  Check llm lint/formatting and run its tests (also requires ruff).'

test-llm:
	@command -v uv >/dev/null || { printf '%s\n' 'Missing dependency: uv' >&2; exit 1; }
	@command -v xh >/dev/null || { printf '%s\n' 'Missing dependency: xh' >&2; exit 1; }
	$(PYTHON) -m unittest discover -s "$(ROOT)llm/tests" -v

check-llm:
	$(RUFF) check "$(ROOT)llm"
	$(RUFF) format --check "$(ROOT)llm"
	$(MAKE) -f "$(ROOT)Makefile" test-llm
