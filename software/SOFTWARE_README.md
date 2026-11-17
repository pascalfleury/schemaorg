# Schema.org Software Guide

This document explains how to set up a local Schema.org environment, keep the
checked-in `next` snapshot up to date before sending a pull request, and build
or serve the website locally.

- Coding conventions: [CODE_README.md](CODE_README.md)
- Contributing vocabulary & examples: [CONTRIBUTING.md](CONTRIBUTING.md)
- Cutting and deploying an official numbered release: [RELEASING.md](RELEASING.md)
- License: [Apache 2.0](../LICENSE)

## Setup

The toolchain requires **Python 3.11+** in a POSIX environment (Linux, macOS, or
WSL2 on Windows). Run all commands from the repository root (`schemaorg/`) with
your virtual environment activated:

```bash
git clone https://github.com/schemaorg/schemaorg.git
cd schemaorg
python3 -m venv .venv
source .venv/bin/activate
pip install -e software
```

To include development linters and test runners (`mypy`, `pytest`):

```bash
pip install -e "software[dev]"
```

If you ever hit `ModuleNotFoundError` after pulling new changes, re-run
`pip install -e software` inside the active virtual environment.

### Script Aliases

Installing `software` registers console aliases equivalent to the scripts under
`./software/scripts/`:

| Alias             | Script                                |
| ----------------- | ------------------------------------- |
| `build_schema`    | `./software/scripts/buildfiles.py`    |
| `build_site`      | `./software/scripts/buildsite.py`     |
| `build_term_list` | `./software/scripts/buildtermlist.py` |
| `reorg`           | `./software/scripts/reorg.py`         |
| `run_tests`       | `./software/scripts/runtests.py`      |
| `dev_server`      | `./software/scripts/devserv.py`       |

## The `next` Release and Pull Request Workflow

### What `next` Is

`data/releases/next/` is the checked-in, unreleased snapshot of all 35 generated
schema release artifacts (RDF dumps in Turtle, N-Triples, N-Quads, RDF/XML, and
JSON-LD; CSV type/property tables; `schemaorgcontext.jsonld`; `schemaorg.owl`;
`httpequivs.ttl`; ShEx/SHACL shapes; and `schemaorg-all-examples.txt`).

- It continuously reflects the current state of `data/*.ttl`,
  `data/ext/**/*.ttl`, `*examples.txt`, and the exporter code on `main`.
- Unlike frozen historical releases (`data/releases/30.1/`, etc.), `next` has no
  release date and never appears in `versions.json` (which tracks only published
  `X.Y` releases).
- Reviewing diffs in `data/releases/next/` on pull requests makes every change
  to published outputs explicit before merge.

### Required Steps Before Sending a Pull Request

Whenever you change `.ttl` schema files, `*examples.txt` files, or exporter
code, regenerate `data/releases/next/`, run the test suites, and commit any
resulting changes in `data/releases/next/` as part of your pull request:

```bash
# 1. Regenerate all 35 artifacts in data/releases/next/
./software/scripts/buildfiles.py

# 2. Run unit and graph-integrity tests
./software/scripts/runtests.py

# 3. Validate all JSON-LD examples against the generated SHACL shapes
./software/scripts/validate_examples_shacl.py
```

> **Shortcut:** `./software/scripts/buildsite.py --release` runs unit tests,
> regenerates `data/releases/next/`, and runs SHACL validation in one command.

GitHub CI runs `./software/scripts/buildfiles.py` on every pull request and
fails if `data/releases/next/` has uncommitted diffs or untracked files.

## Building and Serving the Website Locally

Vocabulary definitions live in `data/*.ttl` and `data/ext/*/*.ttl`; examples
live in `data/*examples.txt` and `data/ext/*/*examples.txt`.

`buildsite.py` renders static HTML pages and `docs/*` supporting files into
`software/site/` (which is git-ignored, never committed). By default it reads
vocabulary terms from `data/releases/next/`.

### Full Site Build

```bash
./software/scripts/buildsite.py -a
```

To build `software/site/` against the latest published numbered release instead
of `next`:

```bash
./software/scripts/buildsite.py -a --version latest
```

To build the full site while running both unit tests and SHACL validation:

```bash
./software/scripts/buildsite.py -a -r --shacltests
```

### Incremental Rebuilds During Development

Because `buildsite.py` reads terms from `data/releases/<version>/schemaorg-all-https.ttl`,
run `./software/scripts/buildfiles.py` first whenever you edit `.ttl` files:

```bash
./software/scripts/buildfiles.py
./software/scripts/buildsite.py -t Book sameAs
```

Other selective rebuild flags (see `./software/scripts/buildsite.py -h`):

- `./software/scripts/buildsite.py -t All` — all term pages.
- `./software/scripts/buildsite.py -d PendingHome` (or `-d All`) — dynamic docs
  pages (`docs/pending.home.html`, etc.).
- `./software/scripts/buildsite.py -f All` — `docs/*` supporting files
  (`docs/jsonldcontext.jsonld`, `docs/schemaorg.owl`, `docs/tree.jsonld`,
  `docs/jsoncounts.json`, `docs/sitemap.xml`).
- `./software/scripts/buildsite.py -s` — copy static `docs/` HTML/CSS/JS assets.

### Serving Locally

```bash
./software/scripts/devserv.py
```

Opens `http://localhost:8080` serving `software/site/` and mapping
`/version/<ver>/...` (including `/version/next/...` and `/version/latest/...`)
directly to `data/releases/<ver>/...` (use `--host` and `--port` to override).
Page rebuilds show up on refresh without restarting `devserv.py`.

## Releasing a New Version

Cutting an official numbered release (`X.Y`), recording it in `versions.json`,
and deploying to `staging.schema.org` and `schema.org` are covered step by step
in [RELEASING.md](RELEASING.md).

## Deploying a Custom Preview to Google App Engine

To share a branch preview on your own App Engine project (with Google Cloud SDK
installed and initialized via `gcloud init`):

```bash
./software/scripts/buildsite.py -a
./software/gcloud/deploy2gcloud.sh
```

`deploy2gcloud.sh` stages `data/releases/` into the upload directory
automatically; supply your App Engine project name, a version ID, and accept the
default `other.yaml` configuration when prompted.
