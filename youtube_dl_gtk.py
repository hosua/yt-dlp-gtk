import yt_dlp
import gi
import os
import sys
import json
from time import sleep

import subprocess
from threading import Thread

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GObject, GLib, Pango
SEP = os.sep
DOWNLOAD_DIR = 'downloads'

prog_dict = {'id': 0, 'progress': 0.00, 'finished': False, 'stdout_buffer': "", 'stderr_buffer': ""}

def updateGUI(textview_console : Gtk.TextView, prog_bar : Gtk.ProgressBar):
    prog_bar.set_fraction(prog_dict['progress']/100)
    print(f"Fraction: {prog_bar.get_fraction()}")
    textbuff = textview_console.get_buffer()
    if prog_dict['stdout_buffer']:
        text = textbuff.get_text(textbuff.get_start_iter(), textbuff.get_end_iter(), True)
        text += prog_dict['stdout_buffer'] + "\n"
        prog_dict['stdout_buffer'] = ""
        textbuff.set_text(text)

    if prog_dict['stderr_buffer']:
        text = textbuff.get_text(textbuff.get_start_iter(), textbuff.get_end_iter(), True)
        text += prog_dict['stderr_buffer'] + "\n"
        prog_dict['stderr_buffer'] = ""
        textbuff.set_text(text)

class YtDLogger():
    def debug(self, msg):
        if msg.startswith('[debug] '):
            print(msg)
        elif msg.startswith('[download] '):
            print(msg)
            prog_dict['stdout_buffer'] += msg + "\n"
            percent_finished = msg.split()[1].strip('%')
            try:
                percent_finished = float(percent_finished)
            except ValueError:
                percent_finished = 0.0
            prog_dict['progress'] = percent_finished
            if prog_dict['progress'] == 100:
                prog_dict['finished'] = True
        else:
            print(msg)
            prog_dict['stdout_buffer'] += msg + "\n"

    def info(self, msg):
        prog_dict['stdout_buffer'] += msg + "\n"
        print(msg)

    def warning(self, msg):
        prog_dict['stderr_buffer'] += msg + "\n"
        print(msg)

    def error(self, msg):
        prog_dict['stderr_buffer'] += msg + "\n"
        print(msg)

def prog_hook(d: dict):
    if d['finished'] == True:
        print('Download finished, now post-processing...')

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
    'logger': YtDLogger(),
    'outtmpl': DOWNLOAD_DIR + SEP + '%(title)s.%(ext)s',
    'format': select_hq,
}

ydl_audio_only = { # Extract audio from video
    'logger': YtDLogger(),
    'outtmpl': DOWNLOAD_DIR + SEP + '%(title)s.%(ext)s',
    'format': 'm4a/bestaudio/best',
    # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
    'postprocessors': [{  # Extract audio using ffmpeg
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'm4a',
    }]
}

ydl_mp4 = {
    'logger': YtDLogger(),
    'outtmpl': DOWNLOAD_DIR + SEP + '%(title)s.%(ext)s',
    'format': 'mp4/bv*+mergeall[vcodec=none]" best',
}

ydl_filter_length = {
    'logger': YtDLogger(),
    'outtmpl': DOWNLOAD_DIR + SEP + '%(title)s.%(ext)s',
    'match_filter': longer_than_interval,
}

def download_videos(textview_input: Gtk.TextView, textview_fm: Gtk.TextView, textview_console: Gtk.TextView, prog_bar: Gtk.ProgressBar):
    buff_in = textview_input.get_buffer()
    text = buff_in.get_text(buff_in.get_start_iter(), buff_in.get_end_iter(), True)
    urls = text.splitlines()

    # Removes the line of the video we just downloaded in the text buffer.
    def del_downloaded_line(lineno: int):
        # TODO: You cannot access Gtk TextBuffer from another thread!
        buff_in = textview_input.get_buffer()
        text_in = buff_in.get_text(buff_in.get_start_iter(), buff_in.get_end_iter(), True)
        file_list = text_in.splitlines()
        if (lineno < len(file_list)):
            file_list.pop(lineno)
            text_in = '\n'.join(file_list)
            print(f"{lineno}\t{text_in}")
            buff_in.set_text(text_in)


    errcode = 0
    def dl(url: str, lineno: int):
        # TODO: Implement ability to choose different ydl_opts
        # TODO: Implement a download progress bar
        with yt_dlp.YoutubeDL(ydl_mp4) as ydl:
            # ydl.download(url)
            metadata = ydl.extract_info(url)
            with open('metadata.json', 'w') as f:
                json.dump(ydl.sanitize_info(metadata), f)
            ydl.download(url)
            errcode = ydl._download_retcode
            refresh_directory(textview_fm)
            # If errcode is non-zero, there was an error downloading
            print(f"error code: {errcode}")
            # You cannot modify a text buffer from another thread, and must use GLib.idle_add() to do so.
            if (errcode == 0):
                # Delete the line of the already downloaded file from the input
                GLib.idle_add(del_downloaded_line, lineno)




    # Spawn a thread to process download so GUI doesn't freeze

    for lineno, url in enumerate(urls):
        dl_thread = Thread(target=dl, args=(url,lineno))
        dl_thread.start()
        # GLib.idle_add(dl_thread, (url, lineno))

        while dl_thread.is_alive():
            print('dl thread alive')

            # gui_thread = Thread(target=updateGUI, args=(textview_console, prog_bar))
            # gui_thread.start()
            # prog_bar.set_fraction(prog_dict['progress']/100)
            # updateGUI(textview_console, prog_bar)
            # prog_dict['id'] = GLib.timeout_add(100, updateGUI, textview_console, prog_bar)
            GLib.idle_add(updateGUI, textview_console, prog_bar)
            sleep(0.1)

def refresh_directory(textview_fm: Gtk.TextView):
    print("Refreshing the downloads directory")
    dl_dir_list = os.listdir(DOWNLOAD_DIR)
    dl_dir_str = '\n'.join(dl_dir_list)

    buff = textview_fm.get_buffer()
    buff.set_text(f"{dl_dir_str}")

""" Clear the entire output of any TextView object """
def clear_buffer(textview: Gtk.TextView):
    buff = textview_input.get_buffer()
    buff.set_text("")

def on_activate(app):
    win = Gtk.ApplicationWindow(application=app)
    win.set_default_size(1280, 720)
    grid = Gtk.Grid(column_spacing=10, row_spacing=10)

    box_btn = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    box_dl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    box_console = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

    btn_dl = Gtk.Button(label="Download All")
    btn_exit = Gtk.Button(label="Exit")
    btn_clear = Gtk.Button(label="Clear")
    label_title = Gtk.Label()
    label_title.set_markup("<span size='20.0pt'>YoutubeDL GUI - Made By Hosua</span>")
    win.set_titlebar(label_title)
    label_links = Gtk.Label()
    label_links.set_markup("<span size='18.0pt'>Links</span>")
    label_help = Gtk.Label()
    label_help.set_wrap_mode(Pango.WrapMode.CHAR)
    label_help.set_markup("<span size='10.5pt'>Enter your video links in the links textbox on the left. If you wish to\ndownload multiple videos, separate each link on their own lines.</span>")
    label_dl = Gtk.Label()
    label_dl.set_markup("<span size='18.0pt'> Downloads Directory Listing</span>")
    label_dl_dir = Gtk.Label()
    label_dl_dir.set_markup(f"<span size='12.5pt'>Your files are being downloaded to:\n</span><span size='9.0pt'>{os.path.abspath(DOWNLOAD_DIR)}</span>")
    label_dl_prog  = Gtk.Label()
    label_dl_prog.set_markup("<span size='17.5pt'>Download Progress</span>")
    dl_prog_bar = Gtk.ProgressBar()
    dl_prog_bar.set_fraction(0);

    box_dl.append(label_dl_prog)
    box_dl.append(dl_prog_bar)

    # TODO: Allow user to change download folder location, and save this setting.
    textview_input = Gtk.TextView(editable=True) # Textbox where user enters links
    textview_fm = Gtk.TextView(editable=False, cursor_visible=False) # Shows the user the downloads folder
    textview_console = Gtk.TextView(editable=False, cursor_visible=False) # Display stdout and stderr output from yt-dlp
    ctx = textview_input.get_style_context()

    scr_win_input = Gtk.ScrolledWindow()
    scr_win_input.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
    scr_win_input.set_child(textview_input)
    scr_win_input.set_kinetic_scrolling(True)

    scr_win_fm = Gtk.ScrolledWindow()
    scr_win_fm.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
    scr_win_fm.set_child(textview_fm)
    scr_win_fm.set_kinetic_scrolling(True)

    scr_win_console = Gtk.ScrolledWindow()
    scr_win_console.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
    scr_win_console.set_child(textview_console)
    scr_win_console.set_kinetic_scrolling(True)

    refresh_directory(textview_fm)

    btn_dl.connect('clicked', lambda x : download_videos(textview_input, textview_fm, textview_console, dl_prog_bar))
    btn_exit.connect('clicked', lambda x : win.close())
    btn_clear.connect('clicked', lambda x : clear_buffer(textview_input))

    box_btn.append(btn_dl)
    box_btn.append(btn_clear)
    box_btn.append(btn_exit)

    grid.attach(label_title, 50, 0, 3, 1)
    grid.attach_next_to(label_title, scr_win_input, Gtk.PositionType(2), 1, 1)
    grid.attach(textview_input, 0, 1, 30, 20)
    grid.attach(scr_win_input, 0, 1, 50, 20)

    grid.attach(textview_fm, 0, 52, 30, 20)
    grid.attach(scr_win_fm, 0, 52, 50, 20)

    grid.attach(label_dl, 24, 51, 3, 1)
    grid.attach(label_links, 25, 0, 1, 1)
    box_dl.append(label_dl_dir)
    grid.attach_next_to(box_btn, scr_win_input, Gtk.PositionType(1), 1, 1)
    grid.attach_next_to(label_help, box_btn, Gtk.PositionType(3), 1, 1)
    grid.attach_next_to(box_dl, scr_win_fm, Gtk.PositionType(1), 1, 1)
    # grid.attach_next_to(textview_console, label_help, Gtk.PositionType(3), 12, 20)
    grid.attach_next_to(scr_win_console, label_help, Gtk.PositionType(3), 10, 18)
    # grid.attach_next_to(box_, label_dl_dir, Gtk.PositionType(3), 1, 1)

    win.set_child(grid)
    win.present()

if __name__ == "__main__":
    if not os.path.exists(DOWNLOAD_DIR):
        os.mkdir(DOWNLOAD_DIR)

    app = Gtk.Application(application_id='org.gtk.Example')
    app.connect('activate', on_activate)
    app.run(None)
