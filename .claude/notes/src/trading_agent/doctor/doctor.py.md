# doctor.py

Each check is its own class in `checks/`, following the user's rule that similar cases get their own self-contained classes rather than one parameterised checker. The doctor builds one backend check per backend in the configuration, choosing the class by the backend's kind.

A check that crashes is reported as failed rather than stopping the report, because the doctor is most needed exactly when something is broken. That is the one deliberate `except Exception` in the project, marked with `# noqa: BLE001`.

The exit status is 1 when any check failed, so the doctor can be used in scripts and before starting the service.
