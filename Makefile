# Day-to-day commands for the whole monorepo (Python via uv, TypeScript via Bun). See docs/MONOREPO.md.
.PHONY: setup test lint fmt check viewer viewer-dev cli cli-check release-local demo

setup:        ## install everything: Python workspace (uv) + TypeScript workspace (Bun)
	uv sync
	bun install

test:         ## Python tests (no device needed)
	uv run pytest -q

lint:         ## ruff lint + format check, as CI runs them
	uv run ruff check
	uv run ruff format --check

fmt:          ## fix lint and formatting
	uv run ruff check --fix
	uv run ruff format

check: lint test   ## everything CI checks on the Python side

viewer:       ## build the dashboard (apps/viewer/dist), needed by `appscreenmap serve`
	cd apps/viewer && bun run build

viewer-dev:   ## dashboard dev server with hot reload
	cd apps/viewer && bun run dev

cli:          ## build the appscreenmap binary (apps/cli/dist/appscreenmap), wired to this checkout's engine
	cd apps/cli && bun build ./src/index.tsx --compile --define 'process.env.APPSCREENMAP_ROOT="$(CURDIR)"' --outfile dist/appscreenmap

cli-check:    ## CLI tests and type check
	cd apps/cli && bun test && bun run typecheck

release-local: ## build dist/release/: what a release holds, to test setup, update and install.sh (nothing is published)
	bun apps/cli/scripts/build-release.ts

demo:         ## crawl every sample scenario (needs an emulator; see samples/README.md)
	samples/demo.sh
