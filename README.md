# yt-dlp-gtk
A simple GUI for [yt-dlp](https://github.com/yt-dlp/yt-dlp), a fork of YoutubeDL.

Dependencies: 
```
yt-dlp==2023.3.4
PyGObject==3.44.1
pycairo==1.23.0
```

You can run `pip install -r requirements.txt` to download all the necessary packages.

Note: You will still also have to set up GTK4 on your respective operating system. Refer to [this page](https://pygobject.readthedocs.io/en/latest/getting_started.html) to get started.

To use, just enter the links of the videos you want to download, separated by new lines.
`yt-dlp` is not limited to just YouTube, it can download videos from most websites in general.

![demo](img/demo.gif)
