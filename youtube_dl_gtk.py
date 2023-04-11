import yt_dlp
import gi
import os
import sys

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
import glib
SEP = os.sep
DOWNLOAD_DIR = 'downloads'

def format_selector(ctx):
    """ Select the best video and the best audio that won't result in an mkv.
    NOTE: This is just an example and does not handle all cases """

    # formats are already sorted worst to best
    formats = ctx.get('formats')[::-1]

    # acodec='none' means there is no audio
    best_video = next(f for f in formats
                      if f['vcodec'] != 'none' and f['acodec'] == 'none')

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

ydl_opts = {
    'outtmpl': DOWNLOAD_DIR + SEP + '%(title)s.%(ext)s',
    'format': format_selector,
}

def download_videos(textview: Gtk.TextView):
    buff = textview.get_buffer()
    text = buff.get_text(buff.get_start_iter(), buff.get_end_iter(), True)
    urls = text.splitlines()

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(urls)

def clear_buffer(textview: Gtk.TextView):
    buff = textview.get_buffer()
    buff.set_text("")

def on_activate(app):
    win = Gtk.ApplicationWindow(application=app)
    win.set_default_size(800, 600)
    grid = Gtk.Grid(column_spacing=5, row_spacing=5)


    btn_dl = Gtk.Button(label="Download")
    btn_exit = Gtk.Button(label="Exit")
    btn_clear = Gtk.Button(label="Clear")
    label_title = Gtk.Label()
    label_title.set_markup("<big>YoutubeDL GUI</big>")
    label_author = Gtk.Label()
    label_author.set_markup("<big>Made by Hosua</big>")
    label_info = Gtk.Label(label="Enter links to videos you want to download in the text box.\nPlease only put one link per line.")
    textview = Gtk.TextView(editable=True) # Textbox where user enters links
    ctx = textview.get_style_context()

    css = 'textview {padding: 10px 20px 10px 20px;}'
    css_provider = Gtk.CssProvider()
    css_provider.load_from_data(css, -1)

    ctx.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    scrolled_win = Gtk.ScrolledWindow()
    scrolled_win.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
    scrolled_win.set_child(textview)
    scrolled_win.set_kinetic_scrolling(True)

    btn_dl.connect('clicked', lambda x : download_videos(textview))
    btn_exit.connect('clicked', lambda x : win.close())
    btn_clear.connect('clicked', lambda x : clear_buffer(textview))
    win.close()

    grid.attach(label_title, 50, 0, 1, 1)
    # grid.attach_next_to(label_title, scrolled_win, Gtk.PositionType(2), 1, 1)
    grid.attach(textview, 0, 100, 150, 50)
    grid.attach(label_author, 50, 101, 1, 1)
    grid.attach(scrolled_win, 0, 1, 100, 50)
    grid.attach_next_to(btn_dl, scrolled_win, Gtk.PositionType(1), 1, 1)
    grid.attach_next_to(btn_clear, btn_dl, Gtk.PositionType(3), 1, 1)
    # grid.attach(btn_dl, 100, 0, 1, 1)
    grid.attach_next_to(btn_exit, btn_clear, Gtk.PositionType(3), 1, 1)
    grid.attach_next_to(label_info, btn_exit, Gtk.PositionType(3), 10, 1)
    win.set_child(grid)
    win.present()

if __name__ == "__main__":
    if not os.path.exists(DOWNLOAD_DIR):
        os.mkdir(DOWNLOAD_DIR)

    app = Gtk.Application(application_id='org.gtk.Example')
    app.connect('activate', on_activate)
    app.run(None)
