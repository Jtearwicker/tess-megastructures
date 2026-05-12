# One-off scripts

Standalone scripts that aren't pipeline stages. Examples:

- Manual catalog refresh (re-download Prsa+22 with a new version)
- Ad-hoc data exploration scripts
- Diagnostic plots for a single TIC

Anything that gets called more than once should be promoted to a module
in `src/tess_megastructures/` with a CLI entry point.
