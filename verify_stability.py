import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
from pathlib import Path
from app import QApplication, CalendarApp, Store, configure_style
from module_appearance import ModuleAppearanceDialog

app = QApplication([])
configure_style(app)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    window = CalendarApp(Store(Path(folder)/'calendar.sqlite3'))
    window.show()
    app.processEvents()
    w = window.body
    panel = w.docks['daily-editor']
    before = w.history.snapshot()
    w.history.begin()
    w.auto_layout = False
    panel.move(340,120)
    panel.resize(350,300)
    w.history.finish()
    after = w.history.snapshot()
    assert before != after
    w.undo_layout()
    assert w.history.snapshot()==before
    w.redo_layout()
    assert w.history.snapshot()==after
    w.arrange('cascade')
    w.undo_layout()
    assert w.history.snapshot()==after
    panel.move(18000,18000)
    w.recover_panels()
    assert panel.x()<1000 and panel.y()<1000
    w.undo_layout()
    assert panel.x()==18000
    w.recover_panels()
    x,y = w.snap_position(panel,15,15)
    assert (x,y)==(12,12)
    w.set_snap(False)
    assert w.snap_position(panel,15,15)==(15,15)
    w.set_locked(True)
    state = w.history.snapshot()
    w.undo_layout()
    assert w.history.snapshot()==state
    w.set_locked(False)
    dialog = ModuleAppearanceDialog(w,'daily-editor')
    dialog.show()
    dialog.background_opacity.setValue(25)
    dialog.inputs['background'].setText('#ffffff')
    dialog.inputs['foreground'].setText('#ffffff')
    assert '对比偏低' in dialog.contrast_hint.text()
    assert w.get_module_style('daily-editor')['background_opacity']==25
    assert panel.graphicsEffect() is None or not panel.graphicsEffect().isEnabled()
    dialog.reject()
    assert w.get_module_style('daily-editor')['background_opacity']==100
    # Core editor uses a high-specificity QFrame selector: it must not obscure
    # the transparent panel even though generic plugin inputs already pass.
    w.set_module_style('daily-editor',dict(background='#ff0000',foreground='#111111',background_opacity=0))
    app.processEvents()
    from qt_compat import QWidget
    content = panel.findChild(QWidget,'editorPanel')
    assert content is not None
    assert content.palette().window().color().alpha()==0
    # Layout history persists: the same steps stay undoable after a restart.
    before_move = w.history.snapshot()
    w.history.begin()
    panel.move(260,180)
    w.history.finish()
    assert w.history.snapshot() != before_move
    window.close()
    window.store.db.close()
    reopened = Store(Path(folder)/'calendar.sqlite3')
    second = CalendarApp(reopened)
    second.show()
    app.processEvents()
    restored_panel = second.body.docks['daily-editor']
    assert (restored_panel.x(),restored_panel.y()) == (260,180), 'geometry should restore from the saved layout'
    assert second.body.history.past, 'layout history was not persisted'
    assert second.body.history.past[-1]['panels']['daily-editor'][:2] == before_move['panels']['daily-editor'][:2]
    second.body.undo_layout()
    assert (restored_panel.x(),restored_panel.y()) == tuple(before_move['panels']['daily-editor'][:2])
    assert second.body.history.future, 'undo should push onto the redo stack'
    second.body.redo_layout()
    assert (restored_panel.x(),restored_panel.y()) == (260,180)
    second.close()
    reopened.db.close()
print('PASS: layout undo/redo, arrange history, offscreen recovery, optional snapping, locking, separate background opacity and persisted history')
