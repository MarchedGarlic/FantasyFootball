#!/usr/bin/env python3
"""
Storage abstraction for analysis output and cross-run caching.

Every analysis artifact is keyed by (league_id, season) so two leagues, or two seasons of the
same league, never share a directory and can never overwrite each other. This is the intended
swap point for Azure Blob Storage later (see CLAUDE.md section 7): a future AzureBlobStorage
class implementing the same method signatures can replace AnalysisStorage without any caller
changes.
"""

import os
import json
import shutil
import threading
import time


def _is_safe_filename(filename):
    """Reject any path separator/traversal component before it ever reaches os.path.join -
    server.py's /results/<filename> route takes this straight from the URL."""
    return filename == os.path.basename(filename) and filename not in ('', '.', '..')


class AnalysisStorage:
    """Local-disk implementation of the (league_id, season)-keyed storage interface."""

    def __init__(self, base_dir="fantasy_analysis_output"):
        self.base_dir = base_dir
        self.leagues_dir = os.path.join(base_dir, "leagues")
        self.cache_dir = os.path.join(base_dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    def paths_for(self, league_id, season, clear=False):
        """Return (and create) the output directories for one league+season.

        Only this league's/season's own directory is ever touched here - never the shared
        cache dir, and never another league or season's directory.
        """
        league_season_dir = os.path.join(self.leagues_dir, str(league_id), str(season))

        if clear and os.path.exists(league_season_dir):
            shutil.rmtree(league_season_dir)

        html_dir = os.path.join(league_season_dir, "html_reports")
        json_dir = os.path.join(league_season_dir, "json_data")
        text_dir = os.path.join(league_season_dir, "text_reports")

        for directory in (html_dir, json_dir, text_dir):
            os.makedirs(directory, exist_ok=True)

        return {
            'base': league_season_dir,
            'html': html_dir,
            'json': json_dir,
            'text': text_dir,
            'league_id': str(league_id),
            'season': str(season),
        }

    def write_json(self, league_id, season, name, data):
        paths = self.paths_for(league_id, season)
        path = os.path.join(paths['json'], name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    def read_json(self, league_id, season, name):
        path = os.path.join(self.paths_for(league_id, season)['json'], name)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def write_text(self, league_id, season, name, text):
        paths = self.paths_for(league_id, season)
        path = os.path.join(paths['text'], name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    def write_html(self, league_id, season, name, html):
        paths = self.paths_for(league_id, season)
        path = os.path.join(paths['html'], name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        return path

    def write_meta(self, league_id, season, meta):
        paths = self.paths_for(league_id, season)
        path = os.path.join(paths['base'], "meta.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        return path

    def read_meta(self, league_id, season):
        path = os.path.join(self.paths_for(league_id, season)['base'], "meta.json")
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def list_analyzed_seasons(self, league_id):
        league_dir = os.path.join(self.leagues_dir, str(league_id))
        if not os.path.exists(league_dir):
            return []
        return sorted(os.listdir(league_dir), reverse=True)

    def list_analyzed_leagues(self):
        if not os.path.exists(self.leagues_dir):
            return []
        return os.listdir(self.leagues_dir)

    def list_html_reports(self, league_id, season):
        html_dir = self.paths_for(league_id, season)['html']
        return [f for f in os.listdir(html_dir) if f.endswith('.html')]

    def list_json_data(self, league_id, season):
        json_dir = self.paths_for(league_id, season)['json']
        return [f for f in os.listdir(json_dir) if f.endswith('.json')]

    def html_report_path(self, league_id, season, filename):
        if not _is_safe_filename(filename):
            return None
        path = os.path.join(self.paths_for(league_id, season)['html'], filename)
        return path if os.path.exists(path) else None

    def json_data_path(self, league_id, season, filename):
        if not _is_safe_filename(filename):
            return None
        path = os.path.join(self.paths_for(league_id, season)['json'], filename)
        return path if os.path.exists(path) else None

    # ---- cross-league cache (e.g. Sleeper's global /players/nfl payload, ESPN rankings) ----

    def cache_get(self, key, max_age_seconds):
        """Return cached data for `key` if it exists and is younger than max_age_seconds."""
        path = os.path.join(self.cache_dir, f"{key}.json")
        if not os.path.exists(path):
            return None
        age = time.time() - os.path.getmtime(path)
        if age > max_age_seconds:
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def cache_set(self, key, data):
        path = os.path.join(self.cache_dir, f"{key}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        return path


# ---- per (league_id, season) locks so the same league+season can't run twice concurrently ----
# Different leagues/seasons never wait on each other; they write to disjoint directories anyway.

_locks = {}
_locks_guard = threading.Lock()


def get_analysis_lock(league_id, season):
    key = (str(league_id), str(season))
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]
