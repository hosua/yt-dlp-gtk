import yt_dlp
import gi
from gi.repository import Gtk, Gdk, GObject, GLib, Pango
import os
import sys
import json
from queue import Queue
from time import sleep

import subprocess
from threading import Thread

gi.require_version("Gtk", "4.0")
SEP = os.sep
DOWNLOAD_DIR = 'downloads'

class YTDLogger():
    def __init__(self, prog_dict: dict):
        self._prog_dict = prog_dict

    def debug(self, msg):
        if msg.startswith('[debug] '):
            pass
        else:
            self.info(msg)

    def info(self, msg):
        print(msg)
        if msg.startswith("[download] "):
            prog_percent_done = msg.split()[1].strip('%')
            try:
                prog_percent_done = float(prog_percent_done)
            except ValueError:
                prog_percent_done = 0.0
            self._prog_dict['progress'] = prog_percent_done
        self._prog_dict['stdout'] += msg + "\n"

    def warning(self, msg):
        self._prog_dict['stderr'] += msg + "\n"
        print(msg)

    def error(self, msg):
        self._prog_dict['stderr'] += msg + "\n"
        print(msg)

def select_hq(ctx):
    """ Select the best video and the best audio that won't result in an mkv.
    NOTE: This is just an example and does not handle all cases """

    # formats are already sorted worst to best
    formats = ctx.get('formats')[::-1]

    # acodec='none' means there is no audio
    best_video = next(f for f in formats if (f['vcodec'] == 'none') and (f['acodec'] == None == 'none'))
    # find compatible audio extension
    audio_ext = {'mp4': 'm4a', 'webm': 'webm'}[best_video['ext']]
    # vcodec='none' means there is no video
    best_audio = next(f for f in formats if (
        f['acodec'] != 'none' and f['vcodec'] == 'none' and f['ext'] == audio_ext))

    # These are the minimum required fields for a merged format
    yield {
        'format_id': f'{best_video["format_id"]}+{best_audio["format_id"]}',
        'ext': best_video['ext'],
        'requested_formats': [best_video, best_audio],
        # Must be + separated list of protocols
        'protocol': f'{best_video["protocol"]}+{best_audio["protocol"]}'
    }

def longer_than_interval(info, *, interval: int):
    """Download only videos longer than the interval (or with unknown duration)"""
    duration = info.get('duration')
    if duration and duration < interval:
        return 'The video is too short'

ydl_best_quality = { # Does not work for every website
    # 'logger': YTDLogger(),
    'outtmpl': DOWNLOAD_DIR + SEP + '%(title)s.%(ext)s',
    'format': select_hq,
}

ydl_audio_only = { # Extract audio from video
    # 'logger': YTDLogger(),
    'outtmpl': DOWNLOAD_DIR + SEP + '%(title)s.%(ext)s',
    'format': 'm4a/bestaudio/best',
    # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
    'postprocessors': [{  # Extract audio using ffmpeg
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'm4a',
    }]
}

ydl_mp4 = {
    # 'logger': YTDLogger(),
    'outtmpl': DOWNLOAD_DIR + SEP + '%(title)s.%(ext)s',
    'format': 'mp4/bv*+mergeall[vcodec=none]" best',
}

ydl_filter_length = {
    # 'logger': YTDLogger(),
    'outtmpl': DOWNLOAD_DIR + SEP + '%(title)s.%(ext)s',
    'match_filter': longer_than_interval,
}

class YTDLThread(Thread):
    def __init__(self, prog_dict: dict, url: str, lineno: int):
        Thread.__init__(self)
        self._prog_dict = prog_dict
        self._url = url
        self._lineno = lineno
        self._errcode = 0

    def run(self):
        # TODO: Implement ability to choose different ydl_opts
        # TODO: Implement a download progress bar
        ydl_mp4['logger'] = YTDLogger(self._prog_dict)
        with yt_dlp.YoutubeDL(ydl_mp4) as ydl:
            # ydl.download(url)
            metadata = ydl.extract_info(self._url)
            with open('metadata.json', 'w') as f:
                json.dump(ydl.sanitize_info(metadata), f)
            ydl.download(self._url)
            self._errcode = ydl._download_retcode

class YTDLWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Gtk.ApplicationWindow.__init__(self)

        self.set_default_size(1280, 720)
        self.set_title("YTDL-GUI")

        self._dl_thread = None
        self._prog_dict = {'id': 0, 'progress': 0.00, 'finished': False, 'stdout': "", 'stderr': ""}

        self._errcode = 0 # Non-zero errcode indicates an error
        self._grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self._box_btn = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self._box_dl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self._box_console = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self._btn_dl = Gtk.Button(label="Download All")
        self._btn_exit = Gtk.Button(label="Exit")
        self._btn_clear = Gtk.Button(label="Clear")
        self._label_title = Gtk.Label()
        self._label_title.set_markup("<span size='20.0pt'>YoutubeDL GUI - Made By Hosua</span>")
        self.set_titlebar(self._label_title)
        self._label_links = Gtk.Label()
        self._label_links.set_markup("<span size='18.0pt'>Links</span>")
        self._label_help = Gtk.Label()
        self._label_help.set_wrap_mode(Pango.WrapMode.CHAR)
        self._label_help.set_markup("<span size='10.5pt'>Enter your video links in the links textbox on the left. If you wish to\ndownload multiple videos, separate each link on their own lines.</span>")
        self._label_dl = Gtk.Label()
        self._label_dl.set_markup("<span size='18.0pt'> Downloads Directory Listing</span>")
        self._label_dl_dir = Gtk.Label()
        self._label_dl_dir.set_markup(f"<span size='12.5pt'>Your files are being downloaded to:\n</span><span size='9.0pt'>{os.path.abspath(DOWNLOAD_DIR)}</span>")
        self._label_dl_prog  = Gtk.Label()
        self._label_dl_prog.set_markup("<span size='17.5pt'>Download Progress</span>")
        self._dl_prog_bar = Gtk.ProgressBar()
        self._dl_prog_bar.set_fraction(0);

        self._box_dl.append(self._label_dl_prog)
        self._box_dl.append(self._dl_prog_bar)

        # TODO: Allow user to change download folder location, and save this setting.
        self._textview_input = Gtk.TextView(editable=True) # Textbox where user enters links
        self._textview_fm = Gtk.TextView(editable=False, cursor_visible=False) # Shows the user the downloads folder
        self._textview_console = Gtk.TextView(editable=False, cursor_visible=False) # Display stdout and stderr output from yt-dlp
        self._ctx = self._textview_input.get_style_context()

        self._scr_win_input = Gtk.ScrolledWindow()
        self._scr_win_input.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        self._scr_win_input.set_child(self._textview_input)
        self._scr_win_input.set_kinetic_scrolling(True)

        self._scr_win_fm = Gtk.ScrolledWindow()
        self._scr_win_fm.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        self._scr_win_fm.set_child(self._textview_fm)
        self._scr_win_fm.set_kinetic_scrolling(True)

        self._scr_win_console = Gtk.ScrolledWindow()
        self._scr_win_console.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        self._scr_win_console.set_child(self._textview_console)
        self._scr_win_console.set_kinetic_scrolling(True)
        self.refresh_directory()

        self._btn_dl.connect('clicked', lambda x : self.download_videos())
        self._btn_exit.connect('clicked', lambda x : self.close())
        self._btn_clear.connect('clicked', lambda x : self.clear_buffer(self._textview_input))

        self._box_btn.append(self._btn_dl)
        self._box_btn.append(self._btn_clear)
        self._box_btn.append(self._btn_exit)

        self._grid.attach(self._label_title, 50, 0, 3, 1)
        self._grid.attach_next_to(self._label_title, self._scr_win_input, Gtk.PositionType(2), 1, 1)
        self._grid.attach(self._textview_input, 0, 1, 30, 20)
        self._grid.attach(self._scr_win_input, 0, 1, 50, 20)

        self._grid.attach(self._textview_fm, 0, 52, 30, 20)
        self._grid.attach(self._scr_win_fm, 0, 52, 50, 20)

        self._grid.attach(self._label_dl, 24, 51, 3, 1)
        self._grid.attach(self._label_links, 25, 0, 1, 1)
        self._box_dl.append(self._label_dl_dir)
        self._grid.attach_next_to(self._box_btn, self._scr_win_input, Gtk.PositionType(1), 1, 1)
        self._grid.attach_next_to(self._label_help, self._box_btn, Gtk.PositionType(3), 1, 1)
        self._grid.attach_next_to(self._box_dl, self._scr_win_fm, Gtk.PositionType(1), 1, 1)
        # grid.attach_next_to(textview_console, label_help, Gtk.PositionType(3), 12, 20)
        self._grid.attach_next_to(self._scr_win_console, self._label_help, Gtk.PositionType(3), 10, 18)
        # grid.attach_next_to(box_, label_dl_dir, Gtk.PositionType(3), 1, 1)
        self.set_child(self._grid)

    def refresh_directory(self):
        print("Refreshing the downloads directory listing")
        self._dl_dir_list = os.listdir(DOWNLOAD_DIR)
        self._dl_dir_str = '\n'.join(self._dl_dir_list)
        buff = self._textview_fm.get_buffer()
        buff.set_text(f"{self._dl_dir_str}")

    def download_videos(self):
        self.refresh_directory()
        GLib.timeout_add(interval=250, function=self.update_GUI)
        buff_in = self._textview_input.get_buffer()
        text = buff_in.get_text(buff_in.get_start_iter(), buff_in.get_end_iter(), True)
        urls = text.splitlines()

        # Spawn a thread to process download so GUI doesn't freeze

        for lineno, url in enumerate(urls):
            self._dl_thread = YTDLThread(self._prog_dict, url, lineno) # The threads will share data via _prog_dict
            self._dl_thread.start()
            # GLib.idle_add(dl_thread, (url, lineno))

            GLib.timeout_add(100, self.update_GUI)

            self.refresh_directory()

            # If errcode is non-zero, there was an error downloading
            print(f"error code: {self._errcode}")
            # You cannot modify a text buffer from another thread, and must use GLib.idle_add() to do so.
            if self._errcode == 0:
                # Delete the line of the already downloaded file from the input
                GLib.idle_add(self.delete_downloaded_line, lineno)

        self._prog_dict['finished'] = True

    # Call this function periodically
    def update_GUI(self):
        self._dl_prog_bar.set_fraction(self._prog_dict['progress']/100)
        # print(f"Fraction: {self._dl_prog_bar.get_fraction()}")
        if not self._dl_thread.is_alive() and self._prog_dict['finished'] == True:
            return False # End the timeout_add() calls by returning False

        textbuff = self._textview_console.get_buffer()
        if self._prog_dict['stdout']:
            text = textbuff.get_text(textbuff.get_start_iter(), textbuff.get_end_iter(), True)
            text += self._prog_dict['stdout'] + "\n"
            self._prog_dict['stdout'] = ""
            textbuff.set_text(text)

        if self._prog_dict['stderr']:
            text = textbuff.get_text(textbuff.get_start_iter(), textbuff.get_end_iter(), True)
            text += self._prog_dict['stderr'] + "\n"
            self._prog_dict['stderr'] = ""
            textbuff.set_text(text)

        return True # Return True for periodic calls to continue

    # Removes the line of the video we just downloaded from the input text buffer.
    def delete_downloaded_line(self, lineno: int):
        buff_in = self._textview_input.get_buffer()
        text_in = buff_in.get_text(buff_in.get_start_iter(), buff_in.get_end_iter(), True)
        file_list = text_in.splitlines()
        if (lineno < len(file_list)):
            file_list.pop(lineno)
            text_in = '\n'.join(file_list)
            print(f"{lineno}\t{text_in}")
            buff_in.set_text(text_in)

    """ Clear the entire output of any TextView object """
    def clear_buffer(self, textview: Gtk.TextView):
        buff = textview.get_buffer()
        buff.set_text("")

class YTDLApp(Gtk.Application):
    def __init__(self):
        Gtk.Application.__init__(self)
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        self._win = YTDLWindow(application=app)
        self._win.present()

if __name__ == "__main__":
    if not os.path.exists(DOWNLOAD_DIR):
        os.mkdir(DOWNLOAD_DIR)

    app = YTDLApp()
    app.run()
