"""Tiny widget helpers for the property-driven stylesheet."""


def set_kind(w, kind):
    w.setProperty("kind", kind)
    return w


def set_role(w, role):
    w.setProperty("role", role)
    return w


def repolish(w):
    """Re-apply QSS after a dynamic property change."""
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()
