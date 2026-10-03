#!/usr/bin/env python3
import subprocess
import time
import curses
import sys
import os
import shutil
import argparse
from wcwidth import wcswidth


def find_playerctl():
    onefile_dir = os.environ.get('NUITKA_ONEFILE_BINARY_DIR')
    if onefile_dir:
        local_path = os.path.join(onefile_dir, 'playerctl')
        if os.path.isfile(local_path) and os.access(local_path, os.X_OK):
            return local_path
    
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    local_path = os.path.join(base_dir, 'playerctl')
    if os.path.isfile(local_path) and os.access(local_path, os.X_OK):
        return local_path
    
    return shutil.which('playerctl')


def run_playerctl(args):
    playerctl_path = find_playerctl()
    if not playerctl_path:
        return None
    
    try:
        result = subprocess.run(
            [playerctl_path] + args,
            capture_output=True, text=True, check=True, timeout=2
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_player_info():
    metadata_raw = run_playerctl([
        'metadata', '--format', '{{ playerName }}\n{{ artist }}\n{{ title }}\n{{ mpris:length }}'
    ])
    position_raw = run_playerctl(['position'])
    
    if metadata_raw and position_raw:
        metadata = metadata_raw.split('\n')
        if len(metadata) >= 4:
            player = metadata[0] if metadata[0] else "Unknown"
            artist = metadata[1] if metadata[1] else "Unknown Artist"
            title = metadata[2] if metadata[2] else "Unknown Track"
            total_sec = int(metadata[3]) // 1000000 if metadata[3].isdigit() else 0
            current_sec = float(position_raw)
            return player, artist, title, current_sec, total_sec
    
    return None, None, None, 0, 0


def format_time(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def truncate_text(text, max_width):
    if wcswidth(text) <= max_width:
        return text
    
    result = ""
    for char in text:
        if wcswidth(result + char) > max_width - 3:
            break
        result += char
    return result + "..."


def create_progress_bar(current, total, width):
    if total == 0:
        return " " * width
    progress = current / total
    filled = int(width * progress)
    return "/" * filled + " " * (width - filled)


def pad_to_width(text, target_width):
    current_width = wcswidth(text)
    if current_width >= target_width:
        return text[:target_width]
    return text + " " * (target_width - current_width)


def center_text(text, width):
    text_width = wcswidth(text)
    left_pad = (width - text_width) // 2
    right_pad = width - text_width - left_pad
    return " " * left_pad + text + " " * right_pad


PALETTES = {
    1: {'name': 'Blue (default)', 'title': curses.COLOR_CYAN, 'track': curses.COLOR_YELLOW, 'artist': curses.COLOR_GREEN, 'progress': curses.COLOR_WHITE, 'border': curses.COLOR_BLUE},
    2: {'name': 'Green', 'title': curses.COLOR_GREEN, 'track': curses.COLOR_WHITE, 'artist': curses.COLOR_CYAN, 'progress': curses.COLOR_YELLOW, 'border': curses.COLOR_GREEN},
    3: {'name': 'Red', 'title': curses.COLOR_RED, 'track': curses.COLOR_WHITE, 'artist': curses.COLOR_YELLOW, 'progress': curses.COLOR_WHITE, 'border': curses.COLOR_RED},
    4: {'name': 'Purple', 'title': curses.COLOR_MAGENTA, 'track': curses.COLOR_WHITE, 'artist': curses.COLOR_CYAN, 'progress': curses.COLOR_WHITE, 'border': curses.COLOR_MAGENTA},
    5: {'name': 'Yellow', 'title': curses.COLOR_YELLOW, 'track': curses.COLOR_WHITE, 'artist': curses.COLOR_GREEN, 'progress': curses.COLOR_YELLOW, 'border': curses.COLOR_YELLOW},
    6: {'name': 'Monochrome', 'title': curses.COLOR_WHITE, 'track': curses.COLOR_WHITE, 'artist': curses.COLOR_WHITE, 'progress': curses.COLOR_WHITE, 'border': curses.COLOR_WHITE},
}


def parse_args():
    parser = argparse.ArgumentParser(
        prog='nowpl',
        description='A terminal "Now Playing" widget that displays the current track from any MPRIS-compatible player.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  nowpl                  Run with default settings
  nowpl -C 3             Use red color palette
  nowpl -b               Enable bold text
  nowpl -x               Disable box border
  nowpl -C 2 -b -x       Green palette, bold text, no border

color palettes:
  1  Blue (default)
  2  Green
  3  Red
  4  Purple
  5  Yellow
  6  Monochrome

controls:
  q, Escape  Exit the program
"""
    )
    
    parser.add_argument('-C', '--color', type=int, default=1, choices=range(1, 7), metavar='N', help='Color palette number (1-6, default: 1)')
    parser.add_argument('-b', '--bold', action='store_true', help='Use bold text')
    parser.add_argument('-x', '--no-box', action='store_true', help='Disable box border around the widget')
    
    return parser.parse_args()


def draw_box(stdscr, y, x, width, color):
    stdscr.addstr(y, x, "┌" + "─" * width + "┐", color)
    stdscr.addstr(y + 1, x, "│" + " " * width + "│", color)
    stdscr.addstr(y + 2, x, "├" + "─" * width + "┤", color)
    stdscr.addstr(y + 3, x, "│" + " " * width + "│", color)
    stdscr.addstr(y + 4, x, "│" + " " * width + "│", color)
    stdscr.addstr(y + 5, x, "├" + "─" * width + "┤", color)
    stdscr.addstr(y + 6, x, "│" + " " * width + "│", color)
    stdscr.addstr(y + 7, x, "└" + "─" * width + "┘", color)


def main(stdscr, args):
    palette = PALETTES.get(args.color, PALETTES[1])
    
    curses.curs_set(0)
    stdscr.timeout(500)
    
    curses.start_color()
    curses.use_default_colors()
    
    curses.init_pair(1, palette['title'], -1)
    curses.init_pair(2, palette['track'], -1)
    curses.init_pair(3, palette['artist'], -1)
    curses.init_pair(4, palette['progress'], -1)
    curses.init_pair(5, palette['border'], -1)
    
    bold_attr = curses.A_BOLD if args.bold else curses.A_NORMAL
    
    playerctl_missing = find_playerctl() is None
    
    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        
        box_width = min(width - 4, 80)
        if box_width < 40:
            box_width = width - 2
        
        start_x = max(0, (width - box_width) // 2)
        start_y = 2
        
        if playerctl_missing:
            if not args.no_box:
                draw_box(stdscr, start_y, start_x, box_width, curses.color_pair(5) | bold_attr)
                stdscr.addstr(start_y + 1, start_x, "│" + center_text("playerctl not found", box_width) + "│", curses.color_pair(1) | bold_attr)
                stdscr.addstr(start_y + 3, start_x, "│" + center_text("Please install playerctl", box_width) + "│", curses.color_pair(1) | bold_attr)
            else:
                stdscr.addstr(start_y, start_x, center_text("playerctl not found", box_width), curses.color_pair(1) | bold_attr)
                stdscr.addstr(start_y + 1, start_x, center_text("Please install playerctl", box_width), curses.color_pair(1) | bold_attr)
        else:
            player, artist, title, current, total = get_player_info()
            
            if player and title:
                if not args.no_box:
                    draw_box(stdscr, start_y, start_x, box_width, curses.color_pair(5) | bold_attr)
                
                player_text = player.upper()
                if args.no_box:
                    stdscr.addstr(start_y, start_x, center_text(player_text, box_width), curses.color_pair(1) | bold_attr)
                else:
                    stdscr.addstr(start_y + 1, start_x, "│" + center_text(player_text, box_width) + "│", curses.color_pair(1) | bold_attr)
                
                title_text = truncate_text(title, box_width - 2)
                title_padded = pad_to_width(title_text, box_width)
                if args.no_box:
                    stdscr.addstr(start_y + 3, start_x, title_padded, curses.color_pair(2) | bold_attr)
                else:
                    stdscr.addstr(start_y + 3, start_x, "│" + title_padded + "│", curses.color_pair(2) | bold_attr)
                
                artist_text = truncate_text(artist, box_width - 2)
                artist_padded = pad_to_width(artist_text, box_width)
                if args.no_box:
                    stdscr.addstr(start_y + 4, start_x, artist_padded, curses.color_pair(3) | bold_attr)
                else:
                    stdscr.addstr(start_y + 4, start_x, "│" + artist_padded + "│", curses.color_pair(3) | bold_attr)
                
                time_str = f"{format_time(current)} / {format_time(total)}"
                time_width = wcswidth(time_str)
                bar_width = max(10, box_width - time_width - 4)
                bar = create_progress_bar(current, total, bar_width)
                progress_line = pad_to_width(f"[{bar}] {time_str}", box_width)
                
                if args.no_box:
                    stdscr.addstr(start_y + 6, start_x, progress_line, curses.color_pair(4) | bold_attr)
                else:
                    stdscr.addstr(start_y + 6, start_x, "│" + progress_line + "│", curses.color_pair(4) | bold_attr)
            else:
                if not args.no_box:
                    draw_box(stdscr, start_y, start_x, box_width, curses.color_pair(5) | bold_attr)
                    stdscr.addstr(start_y + 1, start_x, "│" + center_text("Nothing is playing", box_width) + "│", curses.color_pair(1) | bold_attr)
                    stdscr.addstr(start_y + 3, start_x, "│" + center_text("Start playing music", box_width) + "│", curses.color_pair(1) | bold_attr)
                else:
                    stdscr.addstr(start_y, start_x, center_text("Nothing is playing", box_width), curses.color_pair(1) | bold_attr)
                    stdscr.addstr(start_y + 1, start_x, center_text("Start playing music", box_width), curses.color_pair(1) | bold_attr)
        
        stdscr.refresh()
        
        key = stdscr.getch()
        if key == ord('q') or key == 27:
            break


if __name__ == "__main__":
    args = parse_args()
    curses.wrapper(lambda stdscr: main(stdscr, args))
