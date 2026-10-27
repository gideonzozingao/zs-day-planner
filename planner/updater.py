"""Self-update: check the update feed, download + verify the installer, install silently.

Feed: https://github.com/<repo>/releases/download/update-feed/<channel>.json, a manifest
published by CI (scripts/make_manifest.py). Plain release downloads are not subject to
GitHub's 60-requests/hour API limit, which matters when many PCs share one office IP.
If the feed doesn't exist yet, the GitHub Releases API is used as a fallback.

Flow: check() -> checked(info|None, manual) -> download(info) -> progress/downloaded(path)
      -> install(path): a hidden PowerShell waits for this process to exit, runs the Inno
      installer with /VERYSILENT /RELAUNCH, and the installer restarts the app.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__
from .config import UPDATE_ASSET_PATTERN, UPDATE_REPO
from .utils import now_stamp
from .versioning import manifest_to_info, select_release

FEED_URL = "https://github.com/{repo}/releases/download/update-feed/{channel}.json"
API_URL = "https://api.github.com/repos/{repo}/releases?per_page=20"
UPDATE_DIR = Path(tempfile.gettempdir()) / "ZuqongtechPlannerUpdate"


class UpdateManager(QObject):
    checked = Signal(object, bool)        # info dict or None, manual
    checkFailed = Signal(str, bool)       # message, manual
    progress = Signal(object, object)     # received, total (bytes)
    downloaded = Signal(str)              # verified installer path
    downloadFailed = Signal(str)
    installStarted = Signal()             # app should quit now

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.nam = QNetworkAccessManager(self)
        self.available = None
        self.checking = False
        self._busy = False
        self._reply = self._fh = self._hash = self._expected = self._info = self._path = None

    @property
    def can_install(self) -> bool:
        """Only the installed Windows build can replace itself."""
        return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"

    @property
    def downloading(self) -> bool:
        return self._busy

    def _request(self, url, accept=b"application/vnd.github+json"):
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", f"ZuqongtechPlanner/{__version__}".encode())
        req.setRawHeader(b"Accept", accept)
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                         QNetworkRequest.NoLessSafeRedirectPolicy)   # GitHub assets redirect to a CDN
        req.setTransferTimeout(30_000)
        return req

    # ------------------------------------------------------------------ check
    def feed_url(self, channel):
        return FEED_URL.format(repo=UPDATE_REPO, channel=channel)

    def check(self, manual=False):
        if self.checking:
            return
        self.checking = True
        channel = self.settings.get("update_channel", "stable")
        reply = self.nam.get(self._request(self.feed_url(channel), b"application/json"))
        reply.finished.connect(lambda: self._on_feed(reply, manual, channel))

    def _on_feed(self, reply, manual, channel):
        reply.deleteLater()
        if reply.error() == QNetworkReply.ContentNotFoundError:
            return self._check_api(manual, channel)          # feed not published yet
        if reply.error() != QNetworkReply.NoError:
            return self._check_failed(reply.errorString(), manual)
        try:
            manifest = json.loads(bytes(reply.readAll()).decode("utf-8"))
            info = manifest_to_info(manifest, __version__)
        except (ValueError, KeyError, TypeError):
            return self._check_api(manual, channel)          # unreadable feed: try the API
        self._check_succeeded(info, manual)

    def _check_api(self, manual, channel):
        reply = self.nam.get(self._request(API_URL.format(repo=UPDATE_REPO)))
        reply.finished.connect(lambda: self._on_api(reply, manual, channel))

    def _on_api(self, reply, manual, channel):
        reply.deleteLater()
        if reply.error() != QNetworkReply.NoError:
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            msg = {404: "No releases found (check UPDATE_REPO and that the repository is public)",
                   403: "GitHub is rate-limiting this network; will retry later"}.get(status, reply.errorString())
            return self._check_failed(msg, manual)
        try:
            releases = json.loads(bytes(reply.readAll()).decode("utf-8"))
        except ValueError:
            return self._check_failed("Unexpected response from GitHub", manual)
        self._check_succeeded(select_release(releases, __version__, channel, UPDATE_ASSET_PATTERN), manual)

    def _check_succeeded(self, info, manual):
        self.checking = False
        self.available = info
        self.settings["update_last_check"] = now_stamp()
        self.checked.emit(info, manual)

    def _check_failed(self, msg, manual):
        self.checking = False
        self.checkFailed.emit(msg, manual)

    # --------------------------------------------------------------- download
    def download(self, info):
        if self._busy:
            return
        self._busy, self._info, self._expected = True, info, None
        if info.get("sha256"):                       # manifest carries the checksum
            self._expected = info["sha256"]
            self._start_download()
        elif info.get("sha_url"):                    # API fallback: separate .sha256 asset
            r = self.nam.get(self._request(info["sha_url"], b"*/*"))
            r.finished.connect(lambda: self._on_checksum(r))
        else:
            self._start_download()   # no checksum published: rely on HTTPS only

    def _on_checksum(self, r):
        r.deleteLater()
        if r.error() != QNetworkReply.NoError:
            return self._fail(f"Couldn't fetch the checksum: {r.errorString()}")
        parts = bytes(r.readAll()).decode("ascii", "ignore").split()
        if not parts or len(parts[0]) != 64:
            return self._fail("The published checksum is invalid")
        self._expected = parts[0].lower()
        self._start_download()

    def _start_download(self):
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        self._path = UPDATE_DIR / self._info["asset_name"]
        self._fh = open(self._path, "wb")
        self._hash = hashlib.sha256()
        self._reply = self.nam.get(self._request(self._info["url"], b"application/octet-stream"))
        self._reply.readyRead.connect(self._on_chunk)
        self._reply.downloadProgress.connect(lambda got, total: self.progress.emit(got, total))
        self._reply.finished.connect(self._on_downloaded)

    def _on_chunk(self):
        data = bytes(self._reply.readAll())
        if data:
            self._fh.write(data)
            self._hash.update(data)

    def _on_downloaded(self):
        self._on_chunk()
        self._fh.close()
        r, self._reply = self._reply, None
        r.deleteLater()
        if r.error() != QNetworkReply.NoError:
            return self._fail(f"Download failed: {r.errorString()}")
        if self._expected and self._hash.hexdigest() != self._expected:
            return self._fail("The download didn't match its published checksum and was discarded")
        self._busy = False
        self.downloaded.emit(str(self._path))

    def _fail(self, msg):
        self._busy = False
        if self._fh and not self._fh.closed:
            self._fh.close()
        if self._path and Path(self._path).exists():
            try:
                Path(self._path).unlink()
            except OSError:
                pass
        self.downloadFailed.emit(msg)

    # ---------------------------------------------------------------- install
    def install(self, installer_path):
        """Hand over to the installer and ask the app to quit (installStarted)."""
        if not self.can_install:
            self.downloadFailed.emit("Installing updates only works in the installed app")
            return
        log = UPDATE_DIR / "install.log"
        q = lambda s: "'" + str(s).replace("'", "''") + "'"
        args = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                "/RELAUNCH", f'/LOG="{log}"']
        script = (f"Wait-Process -Id {os.getpid()} -Timeout 60 -ErrorAction SilentlyContinue; "
                  f"Start-Process -FilePath {q(installer_path)} -ArgumentList @({', '.join(q(a) for a in args)})")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-WindowStyle", "Hidden", "-Command", script],
                         creationflags=flags, close_fds=True)
        self.installStarted.emit()
