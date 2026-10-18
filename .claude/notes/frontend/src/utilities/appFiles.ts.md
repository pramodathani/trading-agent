# appFiles.ts

Inside the Android WebView there are no browser tabs, so the web page's `window.open('', '_blank')` plus blob URL trick for opening documents does nothing useful. The app instead writes the file into the app's cache folder with `@capacitor/filesystem` and hands it to Android with `@capacitor-community/file-opener`, which opens the phone's viewer for that type (a PDF reader, the gallery, a spreadsheet app). The plan first named `@capacitor/share`; the file opener was chosen because it opens the file directly, the way tapping a file in the Claude app does, instead of showing a share sheet.

Links in desk replies open in `@capacitor/browser`, an in-app Chrome Custom Tab, so the chat stays where it was.
