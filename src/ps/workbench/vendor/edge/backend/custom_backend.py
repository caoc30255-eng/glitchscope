"""Public facade; no model, test, PYNQ or device-service imports."""
from custom_plan import compile_plan, validate_plan, raw
from pathlib import Path


def preview(request):
    return compile_plan(request)


def seal(plan, directory):
    validate_plan(plan)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    with (directory/'plan.json').open('xb') as f:
        f.write(raw(plan)+b'\n')
    return dict(plan_sha256=plan['sha256'], hardware_permission=False,
                state='SEALED_NOT_STARTED')


class Backend:
    def __init__(self, owner, step=None, save=None):
        self.owner = owner
        self._step = step or owner.step
        self._save = save

    preview = staticmethod(preview)
    seal = staticmethod(seal)

    def start_once(self, key): return self.owner.start_once(key)
    def step(self, key, selection=None): return self._step(key, selection)
    def status(self): return self.owner.status()
    def stop(self):
        self.owner.request_stop()
        return self.status()
    def statistics(self):
        from custom_stats import aggregate
        result=aggregate(self.owner.plan, self.owner.checked_records(), self.owner.session.root.name)
        result['confirmation_groups']=self.owner.confirmation_groups()
        return result
    def next_suggestion(self): return self.owner.next_suggestion()
    def export(self, directory=None):
        if directory is None and self._save: return self._save()
        if directory is None: raise ValueError('NEW_EXPORT_DIRECTORY_REQUIRED')
        from custom_io import export
        return export(directory, self.owner)
