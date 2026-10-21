"""Only panel geometry/order is tracked; calendar ink keeps its own undo stack."""
class LayoutHistory:
    def __init__(self,workspace):
        self.workspace = workspace
        self.past,self.future = [],[]
        self.before = None

    def snapshot(self):
        w = self.workspace
        return dict(auto=w.auto_layout,order=list(w.order),panels={key:[p.x(),p.y(),p.width(),p.height()] for key,p in w.docks.items()})

    def begin(self):
        if self.before is None:
            self.before = self.snapshot()

    def finish(self):
        if self.before is not None and self.before != self.snapshot():
            self.past.append(self.before)
            self.past = self.past[-50:]
            self.future.clear()
        self.before = None
        self.workspace.guides = []
        self.workspace.canvas.update()

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
            self.apply(source.pop())
