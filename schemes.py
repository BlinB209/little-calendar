"""Named layout schemes: geometry, visibility and stacking order only.

Schemes intentionally share module instances and their data: switching one only
rearranges the same panels, so no note, list or calendar content is ever copied,
duplicated or lost.
"""
KEY = 'workspace:schemes:v1'
CURRENT_KEY = 'workspace:scheme:v1'
DEFAULT_NAME = '默认'
LIMIT = 12
MAX_NAME = 20


def _rect(value):
    return (isinstance(value, list) and len(value) == 4
            and all(isinstance(item, int) and not isinstance(item, bool) for item in value))


def normalize(raw):
    result = {}
    for name, value in (raw.items() if isinstance(raw, dict) else []):
        if not isinstance(name, str) or not isinstance(value, dict):
            continue
        name = name.strip()[:MAX_NAME]
        if not name or name in result:
            continue
        panels = {}
        for key, rect in (value.get('panels') or {}).items():
            if isinstance(key, str) and _rect(rect):
                panels[key] = list(rect)
        visible = {}
        for key, flag in (value.get('visible') or {}).items():
            if isinstance(key, str):
                visible[key] = bool(flag)
        order = [key for key in (value.get('order') or []) if isinstance(key, str)]
        result[name] = dict(auto=bool(value.get('auto', False)), panels=panels,
                            visible=visible, order=order)
        if len(result) >= LIMIT:
            break
    return result


def load(store):
    return normalize(store.get(KEY, {}))


def save(store, values):
    cleaned = normalize(values)
    store.put(KEY, cleaned)
    return cleaned


def current(store):
    name = store.get(CURRENT_KEY, DEFAULT_NAME)
    return name.strip()[:MAX_NAME] if isinstance(name, str) and name.strip() else DEFAULT_NAME


def set_current(store, name):
    store.put(CURRENT_KEY, str(name).strip()[:MAX_NAME] or DEFAULT_NAME)


def snapshot(workspace):
    return dict(auto=bool(workspace.auto_layout),
                order=list(workspace.order),
                panels={key: [panel.x(), panel.y(), panel.width(), panel.height()]
                        for key, panel in workspace.docks.items()},
                visible={key: not panel.isHidden() for key, panel in workspace.docks.items()})


def apply(workspace, snapshot_value):
    """Re-arrange the existing panels to match one saved scheme."""
    if not isinstance(snapshot_value, dict):
        return
    workspace.arranging = True
    try:
        workspace.auto_layout = bool(snapshot_value.get('auto', False))
        panels = snapshot_value.get('panels') or {}
        visible = snapshot_value.get('visible') or {}
        records = {record['id']: record for record in workspace.records}
        for key, panel in workspace.docks.items():
            rect = panels.get(key)
            if _rect(rect):
                panel.setGeometry(*rect)
            record = records.get(key)
            allowed = record is None or record['plugin'] in workspace.installed
            panel.setVisible(bool(visible.get(key, not panel.isHidden())) and allowed)
        order = [key for key in (snapshot_value.get('order') or []) if key in workspace.docks]
        order += [key for key in workspace.order if key not in order]
        workspace.order = order
        for key in workspace.order:
            workspace.docks[key].raise_()
    finally:
        workspace.arranging = False
    workspace.resize_canvas()
