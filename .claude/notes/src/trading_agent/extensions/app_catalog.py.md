# app_catalog.py

Apps are read afresh from the installed packages each time, like the other package parts, so installing or removing a package changes the sidebar without a restart.

An app counts as up when its health address answers with any status below 500 within three seconds. A login page, a 401 or a 404 all mean the program is running; sridhara's own /api/health answers 401 without a login, which is why the sample package checks its page instead. The page check and the systemd question run at the same time.
