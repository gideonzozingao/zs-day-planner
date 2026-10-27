"""Material motion: easing curves, property animations, cross-fades."""
from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPointF, QPropertyAnimation, Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel


def curve(kind):
    c = QEasingCurve(QEasingCurve.Type.BezierSpline)
    p1, p2 = {"decel": ((.05, .7), (.1, 1.0)), "std": ((.2, 0), (0, 1)),
              "accel": ((.3, 0), (.8, .15))}[kind]
    c.addCubicBezierSegment(QPointF(*p1), QPointF(*p2), QPointF(1, 1))
    return c


def animate(target, prop, start, end, ms=300, kind="std", finished=None):
    a = QPropertyAnimation(target, prop, target)
    a.setStartValue(start)
    a.setEndValue(end)
    a.setDuration(ms)
    a.setEasingCurve(curve(kind))
    if finished:
        a.finished.connect(finished)
    a.start(QAbstractAnimation.DeleteWhenStopped)
    return a


def crossfade(widget, apply, ms=260):
    """Snapshot the widget, run apply(), then fade the snapshot away."""
    if not widget.isVisible() or widget.width() < 2:
        apply()
        return
    ov = QLabel(widget)
    ov.setPixmap(widget.grab())
    ov.setGeometry(widget.rect())
    ov.setAttribute(Qt.WA_TransparentForMouseEvents)
    ov.show()
    ov.raise_()
    eff = QGraphicsOpacityEffect(ov)
    ov.setGraphicsEffect(eff)
    apply()
    a = QPropertyAnimation(eff, b"opacity", ov)
    a.setStartValue(1.0)
    a.setEndValue(0.0)
    a.setDuration(ms)
    a.setEasingCurve(curve("std"))
    a.finished.connect(ov.deleteLater)
    a.start(QAbstractAnimation.DeleteWhenStopped)
