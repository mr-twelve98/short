import yt_dlp
import os
import logging
from slugify import slugify

logger = logging.getLogger(__name__)

def download_video(url, output_dir="temp"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'video')
            video_path = ydl.prepare_filename(info)
            # Ensure the extension is correct if merged
            if not video_path.endswith('.mp4'):
                video_path = os.path.splitext(video_path)[0] + '.mp4'

            return {
                'title': video_title,
                'path': video_path,
                'id': info.get('id')
            }
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            raise e

def get_video_info(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None
