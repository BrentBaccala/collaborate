#!/bin/bash
# repo-status.sh - what is built here vs what is published in the apt repo.
#
# Run via `make status`.  Read-only: it inspects .deb files and asks reprepro
# what is published; it changes nothing.
#
# This exists because the two never had to agree and nothing checked. A package
# rebuilt in its own directory and published from there leaves build/ holding a
# months-old copy (freesoft-gnome-desktop was two months stale); a package built
# but never published leaves build/ ahead of the repo (bbb-wss-proxy 0.3.0-16 vs
# a published -15). Both were invisible until someone went looking.
#
# Statuses:
#   OK           every local .deb for this package matches what is published
#   UNPUBLISHED  a local .deb is NEWER than the repo -- built but not published
#   STALE        a local .deb is OLDER than the repo -- a leftover artifact
#   NOT IN REPO  built here but absent from the repo: either not published yet,
#                or deliberately retired (vnc-desktop was retired in favour of
#                grid-desktop; its source is kept on purpose)
#   NOT BUILT    published, but nothing built here (normal for packages built
#                elsewhere, e.g. libxft*, vnc-tunnel)
set -uo pipefail
shopt -s nullglob

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${REPO:-$HOME/website/jammy-300}"
CODENAME="${CODENAME:-bigbluebutton-jammy}"

if [ ! -d "$REPO/conf" ]; then
    echo "repo-status: no apt repo at $REPO" >&2
    exit 1
fi

declare -A published local_debs

# --- what is published -----------------------------------------------------
# reprepro list prints:  codename|component|arch: <package> <version>
while read -r pkg ver; do
    [ -n "$pkg" ] && published["$pkg"]="$ver"
done < <(reprepro -b "$REPO" list "$CODENAME" 2>/dev/null | sed 's/^[^:]*: //')

# --- what is built here ----------------------------------------------------
# Package .debs live in three places: the repo root (dpkg-buildpackage drops
# bbb-plugin-remote-desktop and bbb-wss-proxy there), each package's own
# directory (the build.sh packages), and build/ (the fpm-from-Makefile and
# fetched ones).  Skipped: jammy-300 (a symlink to the published repo), and
# deb_dist/ + dist/, which are stdeb/setuptools intermediates rather than the
# artifact anyone publishes.
#
# Within one directory only the newest .deb matters -- a directory can hold
# several old builds (the repo root accumulates them, since only the packages
# named in the Makefile get an `rm -f` first).  Across directories they are all
# kept, because a package directory disagreeing with build/ is the drift this
# script exists to show.
declare -A newest
for deb in "$HERE"/*.deb "$HERE"/*/*.deb; do
    case "$deb" in
        */jammy-300/*|*/deb_dist/*|*/dist/*) continue ;;
    esac
    pkg=$(dpkg-deb -f "$deb" Package 2>/dev/null) || continue
    ver=$(dpkg-deb -f "$deb" Version 2>/dev/null)
    [ -n "$pkg" ] || continue
    rel="${deb#$HERE/}"
    dir="$(dirname "$rel")"
    key="$pkg|$dir"
    if [ -n "${newest[$key]:-}" ]; then
        prev="${newest[$key]##*|}"
        dpkg --compare-versions "$ver" gt "$prev" || continue
    fi
    newest["$key"]="$rel|$ver"
done
for key in "${!newest[@]}"; do
    local_debs["${key%%|*}"]+="${newest[$key]} "
done

# --- report ----------------------------------------------------------------
printf '%-38s %-12s %s\n' "PACKAGE" "STATUS" "DETAIL"
printf '%-38s %-12s %s\n' "--------------------------------------" "------------" \
       "----------------------------------------"

drift=0
for pkg in $(printf '%s\n' "${!published[@]}" "${!local_debs[@]}" | sort -u); do
    pub="${published[$pkg]:-}"
    entries="${local_debs[$pkg]:-}"

    if [ -z "$entries" ]; then
        printf '%-38s %-12s %s\n' "$pkg" "NOT BUILT" "repo $pub"
        continue
    fi

    # Classify every local artifact against the published version.  Several can
    # exist for one package (its own directory *and* a copy in build/), and they
    # are exactly what drifts apart, so report each rather than picking one.
    status="OK"
    detail=""
    for entry in $entries; do
        path="${entry%%|*}"
        ver="${entry##*|}"
        if [ -z "$pub" ]; then
            status="NOT IN REPO"
            detail+="$path=$ver  "
        elif dpkg --compare-versions "$ver" gt "$pub"; then
            [ "$status" = "STALE" ] || status="UNPUBLISHED"
            detail+="$path=$ver > repo $pub  "
        elif dpkg --compare-versions "$ver" lt "$pub"; then
            status="STALE"
            detail+="$path=$ver < repo $pub  "
        fi
    done

    [ "$status" = "OK" ] && detail="$pub"
    [ "$status" = "OK" ] || drift=$((drift + 1))
    printf '%-38s %-12s %s\n' "$pkg" "$status" "${detail% }"
done

echo
if [ "$drift" -eq 0 ]; then
    echo "Everything built here matches what is published."
else
    echo "$drift package(s) differ from the repo (see above)."
    echo "To publish one:  reprepro -b $REPO includedeb $CODENAME <path/to.deb>"
    echo "                 make rsync"
fi
