# -*- coding: utf-8 -*-
"""
Player POV - FastAPI Web Server
Run with: uvicorn main:app --reload
"""

import os
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from pipeline import sync_videos, stitch_segments

app = FastAPI(title="Player POV")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

jobs: dict = {}


def run_pipeline(job_id: str, vid1: str, vid2: str, name: str):
    def progress(step, pct):
        jobs[job_id]["progress"] = pct
        jobs[job_id]["message"] = step

    jobs[job_id]["status"] = "running"
    result = sync_videos(
        video1_path=vid1,
        video2_path=vid2,
        output_dir=str(OUTPUT_DIR / job_id),
        final_name=name,
        progress_callback=progress,
    )

    if result["success"]:
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
    else:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = result.get("error", "Unknown error")


def run_stitch(job_id: str, segment_paths: list, output_path: str):
    def progress(step, pct):
        jobs[job_id]["progress"] = pct
        jobs[job_id]["message"] = step

    jobs[job_id]["status"] = "running"
    result = stitch_segments(
        segment_paths=segment_paths,
        output_path=output_path,
        progress_callback=progress,
    )

    if result["success"]:
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
    else:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = result.get("error", "Unknown error")


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/api/stitch")
async def start_stitch(
    background_tasks: BackgroundTasks,
    segments: List[UploadFile] = File(...),
    name: str = Form(default="pov_stitched"),
):
    job_id = str(uuid.uuid4())[:8]
    job_upload_dir = UPLOAD_DIR / job_id
    job_upload_dir.mkdir(parents=True)

    segment_paths = []
    for seg in segments:
        seg_path = job_upload_dir / seg.filename
        with open(seg_path, "wb") as f:
            f.write(await seg.read())
        segment_paths.append(str(seg_path))

    segment_paths.sort()

    output_path = str(OUTPUT_DIR / job_id / f"{name}_stitched.mp4")
    os.makedirs(str(OUTPUT_DIR / job_id), exist_ok=True)

    jobs[job_id] = {"status": "queued", "progress": 0, "message": "Queued"}
    background_tasks.add_task(run_stitch, job_id, segment_paths, output_path)

    return {"job_id": job_id}


@app.post("/api/sync")
async def start_sync(
    background_tasks: BackgroundTasks,
    video1: UploadFile = File(...),
    video2: UploadFile = File(...),
    name: str = Form(default="session"),
):
    job_id = str(uuid.uuid4())[:8]
    job_upload_dir = UPLOAD_DIR / job_id
    job_upload_dir.mkdir(parents=True)

    vid1_path = job_upload_dir / video1.filename
    vid2_path = job_upload_dir / video2.filename

    with open(vid1_path, "wb") as f:
        f.write(await video1.read())
    with open(vid2_path, "wb") as f:
        f.write(await video2.read())

    jobs[job_id] = {"status": "queued", "progress": 0, "message": "Queued"}
    background_tasks.add_task(
        run_pipeline, job_id, str(vid1_path), str(vid2_path), name
    )

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def job_status(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return jobs[job_id]


@app.get("/api/download/{job_id}/{filename}")
def download_file(job_id: str, filename: str):
    for f in OUTPUT_DIR.rglob(filename):
        return FileResponse(
            str(f),
            media_type="video/mp4",
            filename=filename,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    return JSONResponse({"error": "File not found"}, status_code=404)


app.mount("/static", StaticFiles(directory="static"), name="static")