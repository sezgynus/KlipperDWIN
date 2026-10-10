"""User-requested, asynchronous updates scoped to the KlipperDWIN updater."""
from moonraker_client import MoonrakerClient


class SoftwareUpdate:
    def __init__(self, printer):
        self.printer = printer
        self.future = None
        self.phase = 'idle'
        self.message = ''
        self.name = None
        self.confirm_epoch = None

    @property
    def label(self):
        return {'checking': 'Checking...', 'available': 'Update',
                'updating': 'Updating...', 'restarting': 'Restarting...',
                'dirty': 'Soft recovery', 'confirm_recovery': 'Confirm recovery',
                'recovering': 'Recovering...'}.get(
                    self.phase, 'Check for updates')

    def start(self):
        if self.future is not None or self.phase == 'restarting':
            return
        printer = self.printer
        snapshot = printer.subscription.snapshot()
        if snapshot.get('state') != 'ready' or snapshot.get('status', {}).get('print_stats', {}).get('state') in ('printing', 'paused'):
            self.message = 'Printer must be idle'
            return
        if self.phase == 'dirty':
            self.phase = 'confirm_recovery'
            self.confirm_epoch = snapshot.get('epoch')
            self.message = 'Discard local changes? Press again'
            return
        recover = self.phase == 'confirm_recovery'
        if recover and snapshot.get('epoch') != self.confirm_epoch:
            self.cancel_confirmation()
            self.message = 'Printer state changed; check again'
            self.phase = 'error'
            return
        upgrade = self.phase == 'available'
        epoch = snapshot.get('epoch')
        name = self.name

        def work():
            # Update calls may take much longer than normal UI telemetry reads.
            client = MoonrakerClient(printer.client.url,
                                    printer.client.headers.get('X-Api-Key', ''), timeout=120)
            try:
                current = printer.subscription.snapshot()
                if current.get('state') != 'ready' or current.get('epoch') != epoch or current.get('status', {}).get('print_stats', {}).get('state') in ('printing', 'paused'):
                    raise ValueError('Printer state changed')
                if recover:
                    versions = client.get('/machine/update/status')['result']['version_info']
                    item = versions.get(name, {})
                    if not name or name.casefold() != 'klipperdwin' or not item or (item.get('is_valid', False) and not item.get('is_dirty', False)):
                        raise ValueError('Check updates again')
                    client.request('POST', '/machine/update/recover', {'name': name, 'hard': False})
                    refreshed = client.request('POST', '/machine/update/refresh', {'name': name})
                    item = refreshed['result']['version_info'][name]
                    if not item.get('is_valid', False) or item.get('is_dirty', False):
                        raise ValueError('Recovery incomplete; check Mainsail')
                    return name, self.available(item)
                if upgrade:
                    # Re-check validity and revision before installing a previously checked update.
                    versions = client.get('/machine/update/status')['result']['version_info']
                    item = versions.get(name, {})
                    if not self.available(item):
                        raise ValueError('Check updates again')
                    client.request('POST', '/machine/update/client', {'name': name})
                    return name, None
                versions = client.get('/machine/update/status')['result']['version_info']
                name_found = next((key for key in versions if key.casefold() == 'klipperdwin'), None)
                if name_found is None:
                    raise ValueError('Updater not configured')
                refreshed = client.request('POST', '/machine/update/refresh', {'name': name_found})
                item = refreshed['result']['version_info'][name_found]
                if not item.get('is_valid', False) or item.get('is_dirty', False):
                    return name_found, 'dirty'
                return name_found, self.available(item)
            finally:
                client.close()

        self.phase = 'recovering' if recover else ('updating' if upgrade else 'checking')
        self.message = 'Please wait...'
        self.future = printer._read_worker.submit(work)

    def cancel_confirmation(self):
        if self.phase == 'confirm_recovery':
            self.phase, self.message = 'dirty', 'Repo invalid or modified'
        self.confirm_epoch = None

    @staticmethod
    def available(item):
        return (item.get('is_valid', False) and not item.get('is_dirty', False)
                and bool(item.get('current_hash')) and bool(item.get('remote_hash'))
                and item['current_hash'] != item['remote_hash'])

    def poll(self):
        if self.future is None or not self.future.done():
            return False
        future, self.future = self.future, None
        try:
            self.name, available = future.result()
            if available == 'dirty':
                self.phase, self.message = 'dirty', 'Repo invalid or modified'
            elif available is None:
                self.phase, self.message = 'restarting', 'Restarting KlipperDWIN'
            elif available:
                self.phase, self.message = 'available', 'Update available'
            else:
                self.phase, self.message = 'current', 'Up to date'
        except Exception as error:
            upgrading = self.phase == 'updating'
            recovering = self.phase == 'recovering'
            self.phase = 'error'
            self.message = ('Update unconfirmed; check Mainsail' if upgrading else
                            'Recovery unconfirmed; check Mainsail' if recovering else str(error))
        return True
