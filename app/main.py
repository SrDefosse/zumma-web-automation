from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from uuid import UUID
from app.schemas import TaskCreate
from app.services.tasks import create_job, run_job, get_job_result, init_db

app = FastAPI(title="Web Automation API")

# sirve imagenes descargadas
app.mount("/images", StaticFiles(directory="storage/images"), name="images")

@app.on_event("startup")
async def on_startup():
    await init_db()

@app.post("/tasks", status_code=202)
async def post_tasks(payload: TaskCreate, bg: BackgroundTasks):
    job_id = await create_job(payload.task_id, payload.lookup_key)
    bg.add_task(run_job, job_id) 
    return {"job_id": str(job_id)}

@app.get("/tasks/{job_id}")
async def get_tasks(job_id: UUID):
    doc = await get_job_result(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    return doc
