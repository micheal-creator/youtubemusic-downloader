import os
import shutil
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

class ParseRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str

def cleanup_file(path: str):
    """Deletes temporary downloaded files after sending."""
    if os.path.exists(path):
        os.remove(path)

@app.post("/api/parse")
def parse_url(req: ParseRequest):
    """Extracts playlist/video details without downloading."""
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'skip_download': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            
            tracks = []
            if 'entries' in info:  # Playlist
                for entry in info['entries']:
                    if entry:
                        tracks.append({
                            "id": entry.get("id"),
                            "title": entry.get("title", "Unknown Title"),
                            "duration": entry.get("duration", 0),
                            "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                            "thumbnail": entry.get("thumbnails", [{}])[0].get("url", "")
                        })
            else:  # Single Video
                tracks.append({
                    "id": info.get("id"),
                    "title": info.get("title", "Unknown Title"),
                    "duration": info.get("duration", 0),
                    "url": req.url,
                    "thumbnail": info.get("thumbnail", "")
                })

            return {"status": "success", "tracks": tracks}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/download")
def download_track(req: DownloadRequest, background_tasks: BackgroundTasks):
    """Downloads a YouTube audio stream and converts it to MP3."""
    out_template = os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s')
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            filename = ydl.prepare_filename(info)
            mp3_filename = os.path.splitext(filename)[0] + ".mp3"

        # Schedule file removal after download completes
        background_tasks.add_task(cleanup_file, mp3_filename)

        return FileResponse(
            path=mp3_filename,
            filename=os.path.basename(mp3_filename),
            media_type='audio/mpeg'
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    """Serves the frontend page."""
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
