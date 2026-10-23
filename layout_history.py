"""Only panel geometry/order is tracked; calendar ink keeps its own undo stack.

The stacks persist in the database so a restart keeps the last layout steps:
snapshots reference panel keys, and applying one ignores keys whose module is
gone, so a stale entry can only do nothing, never crash.
"""
KEY = 'layout:history:v1'
LIMIT = 50


def _clean(values):
    """Keep only well-formed snapshots: bool auto, string order, four-int rects."""
    result = []
    for state in values if isinstance(values, list) else []:
        if not isinstance(state, dict):
            continue
        panels, order = state.get('panels'), state.get('order')
        if not isinstance(panels, dict) or not isinstance(order, list):
            continue
        clean = {}
        for key, rect in panels.items():
            if (isinstance(key, str) and isinstance(rect, list) and len(rect) == 4
                    and all(isinstance(value, int) and not isinstance(value, bool) for value in rect)):
                clean[key] = list(rect)
        result.append(dict(auto=bool(state.get('auto', False)),
                           order=[name for name in order if isinstance(name, str)],
                           panels=clean))
    return result[-LIMIT:]


class LayoutHistory:
    def __init__(self,workspace):
        self.workspace = workspace
        self.past,self.future = [],[]
        self.before = None
        self._load()

    def _load(self):
        saved = self.workspace.owner.store.get(KEY, {})
        if isinstance(saved, dict):
            self.past = _clean(saved.get('past'))
            self.future = _clean(saved.get('future'))

    def _save(self):
        self.workspace.owner.persist(KEY, dict(past=self.past[-LIMIT:], future=self.future[-LIMIT:]))

    def snapshot(self):
        w = self.workspace
        return dict(auto=w.auto_layout,order=list(w.order),panels={key:[p.x(),p.y(),p.width(),p.height()] for key,p in w.docks.items()})

    def begin(self):
        if self.before is None:
            self.before = self.snapshot()

    def finish(self):
        changed = self.before is not None and self.before != self.snapshot()
        if changed:
            self.past.append(self.before)
            self.past = self.past[-LIMIT:]
            self.future.clear()
        self.before = None
        self.workspace.guides = []
        self.workspace.canvas.update()
        if changed:
            self._save()

    def apply(self,state):
        w = self.workspace
        w.arranging = True
        try:
            w.auto_layout = state['auto']
            for key,rect in state['panels'].items():
                if key in w.docks:
                    w.docks[key].setGeometry(*rect)
            w.order = [k for k in state['order'] if k in w.docks]+[k for k in w.order if k not in state['order']]
            for key in w.order:
                w.docks[key].raise_()
        finally:
            w.arranging = False
        w.resize_canvas()
        w.save_workspace()

    def undo(self,redo=False):
        if self.workspace.locked:
            return
        source,target = (self.future,self.past) if redo else (self.past,self.future)
        if source:
            target.append(self.snapshot())
            target[:] = target[-LIMIT:]
            self.apply(source.pop())
            self._save()
