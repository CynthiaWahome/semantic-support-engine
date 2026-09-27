# Contributing

This project is intended for a private repository under CynthiaWahome.

## Branches and reviews

- Seed `main` with the initial scaffold commit.
- Create `dev` from that baseline and make it the default branch.
- Branch from `dev` using `<type>/<issue-or-ticket>-<short-slug>`.
- Open subsequent feature PRs against `dev` using
  `.github/PULL_REQUEST_TEMPLATE.md`.
- Use regular merges, not squash merges. Release changes reach `main` through
  a reviewed PR from `dev`.

Use signed Conventional Commits, for example:
`chore(scaffold): initialize FastAPI application`. Use the account's GitHub
noreply email and verify signatures on GitHub after publication.

Committing, pushing, and opening or editing PRs each require the owner's explicit
approval. Run the checks in the README before requesting a commit or push.

## Migrating existing features

Identify the source commit or PR for each imported feature and retain applicable
attribution and license notices. Bring its relevant tests along with the code.
Keep private notes, credentials, and raw workspace exports out of commits.
