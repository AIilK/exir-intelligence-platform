from fastapi import FastAPI


app = FastAPI(
    title="Exir AI Platform",
    version="1.0"
)


@app.get("/")
def root():

    return {
        "message": "Exir AI Platform Running"
    }