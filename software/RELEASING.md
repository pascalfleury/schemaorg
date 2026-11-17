# Releasing a New Version of Schema.org

This guide covers cutting an official numbered Schema.org release (`X.Y`),
committing its frozen artifacts to GitHub, and deploying it to
`https://staging.schema.org` and `https://schema.org`. See
[SOFTWARE_README.md](SOFTWARE_README.md) for local setup and daily development.

> **Permissions:** Cutting and deploying a release requires write access to the
> `schemaorg/schemaorg` GitHub repository and deployment access to the Google
> Cloud App Engine projects (`schemaorg-staging` and `schemaorgae`).

## 1. How `next` and Numbered Releases Relate

- **`data/releases/next/`** is the unreleased, rolling snapshot checked into VCS
  and updated on every pull request that modifies schemas, examples, or
  exporters. It has no release date and does not appear in `versions.json`.
- **`data/releases/X.Y/`** is a frozen, dated release archive created when
  cutting version `X.Y`.
- **`versions.json`** records published numbered releases only (`schemaversion`
  pointing to the newest `X.Y`, plus `releaseLog` mapping each `"X.Y"` to its
  `"YYYY-MM-DD"` date). Once recorded, `--version latest` resolves to `X.Y`.

## 2. Pre-Release Checklist & Staging Preview

Before cutting `X.Y`:

1. **Governance & freeze:** Steering Group has signed off on the release plan
   and no blocking disputes remain open in the Community Group.
2. **Release notes:** `docs/releases.html` documents version `X.Y` (including an
   HTML `id` matching `X.Y` and no leftover `X.*` placeholders).
3. **Clean `main` checkout:** `main` is checked out with up-to-date dependencies
   (`pip install -e software`), and CI is green.
4. **Candidate preview on staging (optional before cutting `X.Y`):**
   ```bash
   ./software/scripts/buildsite.py -a --version next
   ./software/gcloud/deploy2staging.schema.org.sh
   ```
   Inspect `https://staging.schema.org/docs/qa.html` and
   `https://staging.schema.org/docs/releases.html`.

## 3. Cut and Commit Release `X.Y`

From the repository root on `main` (or a dedicated release PR branch) with the
virtual environment activated:

```bash
# 1. Record X.Y in versions.json (--date defaults to today if omitted)
./software/scripts/schemaversion.py --add X.Y --date YYYY-MM-DD

# 2. Generate all 35 release files in data/releases/X.Y/
./software/scripts/buildfiles.py --version X.Y

# 3. Run unit tests and validate all JSON-LD examples against X.Y's SHACL shapes
./software/scripts/runtests.py
./software/scripts/validate_examples_shacl.py --version X.Y
```

> **Shortcut:** Steps 2 and 3 can be run together via
> `./software/scripts/buildsite.py --release --version X.Y`.

Commit the release metadata, notes, and generated snapshot, then push / merge to
`main` and verify GitHub CI passes:

```bash
git add versions.json docs/releases.html data/releases/X.Y/
git commit -m "Release X.Y"
```

*(Note: `data/releases/next/` is unaffected by `versions.json` updates.)*

## 4. Build Site and Deploy

Once `X.Y` is on `main` and CI is green, build the full static site in
`software/site/` targeting `latest` (`X.Y`), verify on staging, and deploy to
production:

```bash
# 1. Build software/site against the newly recorded latest release (X.Y)
./software/scripts/buildsite.py -a --version latest

# 2. Deploy to https://staging.schema.org and review /docs/qa.html
./software/gcloud/deploy2staging.schema.org.sh

# 3. Deploy to https://schema.org
#    (Pass -m to upload without migrating traffic immediately)
./software/gcloud/deploy2schema.org.sh
```

- **App Engine Version ID:** Use the release number with `-` in place of `.`
  (for example, `30-2` for release `30.2`).
- **CDN propagation:** Cloud caching can take up to ~10 minutes after traffic
  migration to serve new CSS/JS and pages consistently; perform a hard refresh
  after ~10 minutes before final post-deploy checks.

## 5. Tag the GitHub Release

Tag the release commit on `main` using the `vX.Y-release` naming convention and
push the tag:

```bash
git tag vX.Y-release
git push origin vX.Y-release
```

Pushing a `v*` tag triggers `.github/workflows/create-release.yml`, which
automatically publishes the corresponding GitHub Release.
