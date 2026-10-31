# view_image_tool.py

`view_image` lets a trader look at a picture file: a chart it drew, an earlier screenshot, or a picture the user sent in a past message. Pictures sent with a message are shown only in that turn, and part 3 drops them from the history, so this tool is how a trader sees one again.

Reading follows the same `PathPolicy.readable` rule as `read_file`: anywhere except the hidden secrets. The file is checked as a real picture by its contents before it is opened, then resized by `ImagePreparer.prepare` to at most 1,568 pixels, the same copy a picture sent by the user gets. Both steps read the disk and decode the picture, so they run in a worker thread to keep the gateway's event loop free.

`picture_trader_path` is set only for a picture inside the trader folder, because the pictures route serves nothing outside it.
