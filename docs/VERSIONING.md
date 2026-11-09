# Git-flow and versioning

The long-lived branches are `master` (release history) and `develop` (integration).
Work normally starts from `develop`. Git-flow AVH uses `feature/`, `bugfix/`,
`release/`, `hotfix/` and `support/` prefixes. Version tags use the `v` prefix.

The initial imported snapshot is an unreleased beta, tagged `v0.3.0-beta.1` on
both initial branch tips. This bootstrap tag records existing code; it is not a
stable release, GitHub Release, published image or distribution approval. No
historical tags were invented for older development snapshots.

## Local setup after cloning

Git-flow settings live in each checkout's Git config, not in tracked source:

```sh
git switch develop
git flow init -d
git config gitflow.prefix.versiontag v
```

Confirm `gitflow.branch.master=master` and `gitflow.branch.develop=develop` using
`git config --get-regexp '^gitflow\.'`. Keep `develop` checked out for routine work.

## Working branches

```sh
git flow feature start descriptive-name
# Make and verify changes, then commit them.
git flow feature finish descriptive-name
```

Use `bugfix/` for fixes targeting develop and `hotfix/` for urgent fixes to a
released master version. Open pull requests where review is required. Creating a
branch does not authorize deployment or publication.

## Versions and releases

Use Semantic Versioning for Git tags: `vMAJOR.MINOR.PATCH`, with prerelease tags
such as `v0.3.0-beta.2`. Python's equivalent is `0.3.0b2`; keep Python package,
application version, Docker metadata, user agent and changelog consistent.

For an approved future release, use `git flow release start 0.3.0` from develop,
prepare its version/changelog and complete the release gates in RELEASE_GUIDE.md.
Only then finish the release: git-flow merges to master and back into develop and
creates the version tag. Verify the annotated tag and both branch tips before
explicitly pushing them. Do not force-push shared release branches or move a
published version tag; publish a new version for a correction.

Stable releases, registry publishing, signing and GitHub Releases remain deferred.
The bootstrap initialization configures origin but does not push source or tags.
Branch protections and the GitHub default branch are separate repository settings;
use develop as the default integration branch and protect both long-lived branches
when the remote is populated.
