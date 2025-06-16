#!/usr/bin/env python3
"""
fotoshare_album_downloader.py

Download full‑resolution images from a public or password‑protected fotoshare.co album.

Features
--------
* Scrapes the album page for high‑resolution image URLs.
* Optional login using e‑mail + password for private/password‑protected albums.
* Concurrent downloads with a thread pool and resumable operation (skips files that already exist).
* Simple, standard Python 3 script with minimal dependencies.

Usage
-----
    # Public album
    python fotoshare_album_downloader.py https://fotoshare.co/i/ABC123 

    # Private album that requires login + custom output dir + 8 parallel workers
    python fotoshare_album_downloader.py \
        https://fotoshare.co/i/XYZ789 -o ./my_event --email you@example.com --password "SuperSecret" --workers 8

Dependencies
------------
    pip install requests beautifulsoup4 tqdm

Limitations
-----------
* If the album owner disabled downloads, the script will still be able to fetch the original images because it looks for the file URLs embedded in the page.  Make sure you have permission to do so.
* fotoshare.co occasionally changes its markup—if you notice the extractor failing, adjust the CSS selectors in ``_extract_image_urls``.

"""
from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Sequence
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


###############################################################################
#  Low‑level helpers
###############################################################################


def _log(msg: str, *, file=sys.stderr) -> None:  # noqa: D401 (imperative mood)
    """Lightweight logger that never clobbers the progress‑bar."""
    tqdm.write(msg, file=file)


def _login(session: requests.Session, email: str, password: str) -> None:
    """Attempt to sign‑in so we can access private albums.

    The endpoint is based on the form action on the fotoshare.co login page.  If
    the site changes its auth flow (e.g., moves to oauth/2‑factor), adjust this
    function accordingly.
    """
    login_url = "https://fotoshare.co/login"
    data = {"email": email, "password": password}
    resp = session.post(login_url, data=data, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed with HTTP {resp.status_code}")
    if "invalid" in resp.text.lower():
        raise RuntimeError("Login appears to have failed (credentials rejected)")


###############################################################################
#  Scraping logic
###############################################################################


def _absolute(base: str, link: str) -> str:
    """Return *link* as an absolute URL relative to *base*."""
    return urljoin(base, link)


def _is_image(url: str) -> bool:
    return re.search(r"\.(?:jpe?g|png|gif)(?:\?|$)", url, re.I) is not None


# Patterns used by fotoshare for full‑res images seen as of June 2025
_FULL_RES_ATTRS = (
    "data-full",          # preferred attr used by viewer when downloads allowed
    "data-original",      # seen on some templates
    "data-src",           # lazy‑loaded images
    "src",                # fall‑back
)


def _extract_image_urls(session: requests.Session, album_url: str) -> List[str]:
    """Parse *album_url* and return a **unique, sorted** list of image URLs."""
    resp = session.get(album_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    candidates: set[str] = set()

    # Case 1: direct <a> or <img> tags that reference the full image.
    for tag in soup.find_all(["a", "img"]):
        href = tag.get("href") if tag.name == "a" else None
        srcs: Sequence[str | None] = [href] if href else []
        if tag.name == "img":
            srcs += [tag.get(attr) for attr in _FULL_RES_ATTRS]
        for src in srcs:
            if src and _is_image(src):
                clean_url = _absolute(album_url, src).split('?')[0]
                candidates.add(clean_url)

    # Case 2: thumbnails only – follow each photo page to find the high‑res img
    if not candidates:
        thumb_links = [
            _absolute(album_url, a["href"])
            for a in soup.select("a[href]")
            if re.search(r"/p/\w+", a["href"])
        ]
        for tlink in thumb_links:
            try:
                pr = session.get(tlink, timeout=15)
                pr.raise_for_status()
                psoup = BeautifulSoup(pr.text, "lxml")
                img = psoup.find("img", src=True)
                if img and _is_image(img["src"]):
                    candidates.add(_absolute(tlink, img["src"]))
            except Exception as exc:  # pylint: disable=broad-except
                _log(f"⚠️  Could not inspect {tlink}: {exc}")

    return sorted(candidates)


###############################################################################
#  Downloader
###############################################################################


def _download_one(session: requests.Session, url: str, dest: Path) -> None:
    """Fetch *url* (streaming) into *dest*; skip if file already exists."""
    if dest.exists():
        return  # resumable

    with session.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    fh.write(chunk)
        tmp.rename(dest)


###############################################################################
#  Entry‑point
###############################################################################


def main(argv: Sequence[str] | None = None) -> None:  # noqa: D401
    parser = argparse.ArgumentParser(description="Download a fotoshare.co album")
    parser.add_argument("album_url", help="URL of the fotoshare.co album")
    parser.add_argument("-o", "--output", default="./album", help="Download directory")
    parser.add_argument("--email", help="Email address (if album is private)")
    parser.add_argument("--password", help="Password (if album is private)")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent downloads")
    args = parser.parse_args(argv)

    out_dir = Path(args.output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Prepare HTTP session (with optional sign‑in)
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (compatible; fotoshare-downloader/1.0)"})
    if args.email and args.password:
        _log("🔑  Signing‑in…")
        _login(sess, args.email, args.password)

    _log("🔎  Scanning album for images…")
    images = _extract_image_urls(sess, args.album_url)
    if not images:
        _log("❌  No images found — aborting.")
        sys.exit(1)

    _log(f"✅  Found {len(images)} images. Starting downloads…")
    with tqdm(total=len(images), unit="img", ascii=" ░█", dynamic_ncols=True) as bar:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(
                    _download_one,
                    sess,
                    url,
                    out_dir / Path(urlparse(url).path).name,
                ): url
                for url in images
            }
            for fut in as_completed(futures):
                url = futures[fut]
                try:
                    fut.result()
                except Exception as exc:  # pylint: disable=broad-except
                    _log(f"⚠️  {url} failed: {exc}")
                bar.update(1)

    _log(f"🎉  All done! Files saved to {out_dir}")


if __name__ == "__main__":
    main()

