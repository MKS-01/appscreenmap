# Day-to-day commands for the whole monorepo (Python via uv, TypeScript via Bun). See docs/MONOREPO.md.
.PHONY: setup test lint fmt check viewer viewer-dev demo

setup:        ## install everything: Python workspace + viewer deps
	uv sync
	cd web && bun install

test:         ## Python tests (no device needed)
	uv run pytest -q

lint:         ## ruff lint + format check, as CI runs them
	uv run ruff check
	uv run ruff format --check

fmt:          ## fix lint and formatting
	uv run ruff check --fix
	uv run ruff format

check: lint test   ## everything CI checks on the Python side

viewer:       ## build the dashboard (web/dist), needed by `appscreenmap serve`
	cd web && bun run build

viewer-dev:   ## dashboard dev server with hot reload
	cd web && bun run dev

demo:         ## crawl every sample scenario (needs an emulator; see samples/README.md)
	samples/demo.sh
