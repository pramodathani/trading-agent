# browser_screenshot_tool.py

The screenshot is returned to the model as a PNG `MessageImage`, and its path relative to the desk folder is returned as `picture_desk_path` so the web page shows it in the tool's card. Playwright already saves it under `scratch/screenshots/`, inside the desk folder, so the pictures route can serve it without making a copy.
