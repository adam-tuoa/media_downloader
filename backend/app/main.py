# backend/app/main.py (Part 1)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from yt_dlp import YoutubeDL
import os
import tempfile
import shutil
from typing import List, Optional

class VideoURL(BaseModel):
    url: str
    format_id: Optional[str] = None
    quality_preset: Optional[str] = None  # Add quality preset

class VideoFormat(BaseModel):
    format_id: str
    ext: str
    resolution: str
    filesize: Optional[int]
    note: str
    has_video: bool
    has_audio: bool
    quality: str = ""

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def format_filesize(size_bytes: Optional[int]) -> str:
    if not size_bytes:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} GB"

def get_video_ydl_opts(format_id=None):
    """Options for video downloads"""
    return {
        'format': format_id if format_id else 'bestvideo+bestaudio/best',
        'format_sort': ['res', 'ext:mp4:m4a', 'size', 'br'],
        'merge_output_format': 'mp4',
        'quiet': False,
        'no_warnings': False,
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
    }

def get_audio_ydl_opts():
    """Options for audio downloads"""
    return {
        'format': 'bestaudio',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'prefer_ffmpeg': True,
        'keepvideo': False,
        'extract_audio': True,
        'audio_format': 'mp3',
        'quiet': False,
        'no_warnings': False,
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
    }

def filter_formats_by_height(formats, target_height):
    """Filter formats by target height (for quality presets)"""
    if not target_height:
        return formats
    
    filtered = []
    for fmt in formats:
        height = 0
        if 'x' in fmt.resolution:
            try:
                height = int(fmt.resolution.split('x')[1])
            except (IndexError, ValueError):
                continue
                
        if height and height <= target_height:
            filtered.append(fmt)
    
    return filtered if filtered else formats  # Return all formats if no matches

@app.post("/formats")
async def get_formats(video: VideoURL):
    try:
        quality_preset = video.quality_preset or 'best'
        
        # Handle audio-only case
        if quality_preset == 'audio-only':
            return {
                "title": "Audio Download",
                "formats": [{
                    "format_id": "audio-only",
                    "ext": "mp3",
                    "resolution": "Audio Only",
                    "filesize": None,
                    "note": "MP3 Audio (192kbps)",
                    "has_video": False,
                    "has_audio": True,
                    "quality": "192kbps"
                }]
            }
        # Handle video formats
        with YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video.url, download=False)
            formats = []
            
            # Get all formats with both video and audio
            for f in info['formats']:
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    resolution = f.get('resolution', 'N/A')
                    height = f.get('height', 0)
                    width = f.get('width', 0)
                    
                    if resolution == 'N/A' and height:
                        resolution = f"{width}x{height}"
                    
                    quality_parts = []
                    if f.get('format_note'):
                        quality_parts.append(f.get('format_note'))
                    if f.get('fps'):
                        quality_parts.append(f"{f.get('fps')}fps")
                    
                    quality = " - ".join(filter(None, quality_parts))
                    
                    format_info = VideoFormat(
                        format_id=f['format_id'],
                        ext='mp4',
                        resolution=resolution,
                        filesize=f.get('filesize'),
                        note=f"{format_filesize(f.get('filesize'))} - {quality}",
                        has_video=True,
                        has_audio=True,
                        quality=quality
                    )
                    formats.append(format_info)
            
            # Sort formats by resolution and filesize
            formats.sort(
                key=lambda x: (
                    int(x.resolution.split('x')[1]) if 'x' in x.resolution and x.resolution.split('x')[1].isdigit() else 0,
                    x.filesize or 0
                ),
                reverse=True
            )
            
            # Filter formats based on quality preset
            if quality_preset == '360p':
                formats = filter_formats_by_height(formats, 360)
            elif quality_preset == '720p':
                formats = filter_formats_by_height(formats, 720)
            elif quality_preset == '1080p':
                formats = filter_formats_by_height(formats, 1080)
            
            return {
                "title": info.get('title', 'Unknown Title'),
                "duration": info.get('duration'),
                "formats": formats
            }
            
    except Exception as e:
        print(f"Error in get_formats: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/download")
async def download_content(video: VideoURL):
    temp_dir = tempfile.mkdtemp()
    try:
        format_id = video.format_id
        print(f"Requested format: {format_id}")
        
        if format_id == 'audio-only':
            print("Processing audio download...")
            ydl_opts = get_audio_ydl_opts()
            ydl_opts['outtmpl'] = os.path.join(temp_dir, '%(title)s.%(ext)s')
            ext = 'mp3'
            content_type = 'audio/mpeg'
        else:
            print("Processing video download...")
            ydl_opts = get_video_ydl_opts(format_id)
            ydl_opts['outtmpl'] = os.path.join(temp_dir, '%(title)s.%(ext)s')
            ext = 'mp4'
            content_type = 'video/mp4'
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video.url, download=True)
            title = info['title']
            
            # Find the downloaded file
            files = [f for f in os.listdir(temp_dir) if f.endswith(f'.{ext}')]
            if not files:
                raise Exception(f"Download failed: No {ext} file created")
            
            downloaded_file = os.path.join(temp_dir, files[0])
            print(f"File found: {downloaded_file}")
            
            file_size = os.path.getsize(downloaded_file)
            if file_size == 0:
                raise Exception("Downloaded file is empty")
            
            safe_title = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in title)
            safe_filename = f"{safe_title}.{ext}"
            
            def cleanup():
                try:
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                except Exception as e:
                    print(f"Cleanup error: {e}")

            def file_iterator():
                try:
                    with open(downloaded_file, 'rb') as f:
                        while chunk := f.read(8192):
                            yield chunk
                finally:
                    cleanup()

            print(f"Streaming {content_type} file: {safe_filename}")
            return StreamingResponse(
                file_iterator(),
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{safe_filename}"',
                    "Content-Length": str(file_size)
                }
            )
            
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/")
async def read_root():
    return {"message": "YouTube Downloader API is running"}