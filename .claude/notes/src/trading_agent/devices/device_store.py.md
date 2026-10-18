# device_store.py

Follows `channels/pairing_store.py`: one JSON file in `workspace/shared` (`phone_devices.json`), written atomically through a temporary file, guarded by a lock, readable by desks but not writable. Unlike Telegram there is no pairing code: the app registers with the gateway's own access token, which already proves the phone is the owner's. A re-registration with a known token renames instead of adding, because Android hands the app the same token on every launch. Ten phones at most, so a leaked access token cannot fill the file.
