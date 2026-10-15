# Day-to-day commands for the whole monorepo (Python via uv, TypeScript via Bun).
BIN_DIR ?= $(HOME)/.local/bin
.PHONY: install setup test lint fmt check viewer viewer-dev cli cli-check release-local demo skills-check skills-sync skills-xcode

install: setup viewer cli   ## from a checkout: everything, plus the `appscreenmap` command in ~/.local/bin (BIN_DIR=…)
	mkdir -p $(BIN_DIR)
	install -m 755 apps/cli/dist/appscreenmap $(BIN_DIR)/appscreenmap
	@echo "installed $(BIN_DIR)/appscreenmap (it uses this checkout's engine). Next: appscreenmap setup"

setup:        ## install everything: Python workspace (uv) + TypeScript workspace (Bun)
	uv sync
	bun install

test:         ## Python tests (no device needed)
	uv run pytest -q

lint:         ## ruff lint + format check, as CI runs them
	uv run ruff check
	uv run ruff format --check
	bun .claude/skills/design-system/scripts/type-guard.ts

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

skills-check:  ## do the vendored Android skills differ from github.com/android/skills? (changes nothing)
	@scripts/sync-android-skills.sh check

skills-sync:   ## update the vendored Android skills from github.com/android/skills and re-pin scripts/android-skills.lock
	@scripts/sync-android-skills.sh sync

skills-xcode:  ## copy Apple's agent skills (scripts/xcode-skills.list) from the installed Xcode 27+ into .claude/skills/ (git-ignored)
	@scripts/sync-xcode-skills.sh sync
