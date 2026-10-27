"""Single-instance guard over a local socket.

A second launch hands its request ("show" or "tray") to the running copy and exits,
so autostart + a Start Menu click never produce two tray icons or two DB writers.
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    messageReceived = Signal(str)

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        self.server = None

    def notify_running(self, message: str) -> bool:
        """True if another instance is running (and it got the message)."""
        sock = QLocalSocket()
        sock.connectToServer(self.key)
        if not sock.waitForConnected(400):
            return False
        sock.write(message.encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(400)
        sock.disconnectFromServer()
        return True

    def listen(self):
        QLocalServer.removeServer(self.key)   # clears a stale socket after a crash (Unix)
        self.server = QLocalServer(self)
        self.server.listen(self.key)
        self.server.newConnection.connect(self._on_connection)

    def _on_connection(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.readyRead.connect(
                lambda s=sock: self.messageReceived.emit(bytes(s.readAll()).decode("utf-8", "ignore")))
            sock.disconnected.connect(sock.deleteLater)
