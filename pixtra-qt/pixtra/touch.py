from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QScroller,
    QScrollerProperties,
)


def enable_touch_scroll(widget) -> None:
    target = widget.viewport() if hasattr(widget, "viewport") else widget
    if hasattr(widget, "viewport"):
        QScroller.grabGesture(
            target,
            QScroller.ScrollerGestureType.LeftMouseButtonGesture,
        )
        scroller = QScroller.scroller(target)
        props = scroller.scrollerProperties()
        props.setScrollMetric(
            QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy,
            QScrollerProperties.OvershootPolicy.OvershootAlwaysOff,
        )
        props.setScrollMetric(
            QScrollerProperties.ScrollMetric.AxisLockThreshold,
            0.66,
        )
        scroller.setScrollerProperties(props)
    if isinstance(widget, QAbstractScrollArea):
        widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    if isinstance(widget, QAbstractItemView):
        widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        widget.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
