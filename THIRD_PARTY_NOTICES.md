# Dependency notices

Dependencies are fetched at installation time; their licenses and notices continue to apply. This application package does not include OCR model weights. Consult each dependency's installed distribution metadata for its exact license text and transitive dependencies.

| Dependency | Primary source / notice |
| --- | --- |
| PyMuPDF / MuPDF | [PyMuPDF licensing](https://pymupdf.readthedocs.io/en/latest/about.html): AGPL/commercial dual licensing |
| pikepdf / qpdf | [pikepdf](https://github.com/pikepdf/pikepdf), [qpdf](https://github.com/qpdf/qpdf) |
| Surya (optional) | [Source and usage](https://github.com/datalab-to/surya), [code license](https://github.com/datalab-to/surya/blob/master/LICENSE), [model license](https://github.com/datalab-to/surya/blob/master/MODEL_LICENSE) |
| FastAPI / Starlette / Uvicorn | [FastAPI](https://github.com/fastapi/fastapi), [Starlette](https://github.com/Kludex/starlette), [Uvicorn](https://github.com/encode/uvicorn) |
| SQLAlchemy / psycopg | [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy), [psycopg](https://github.com/psycopg/psycopg) |
| Celery / redis-py | [Celery](https://github.com/celery/celery), [redis-py](https://github.com/redis/redis-py) |
| Image/numeric processing | [Pillow](https://github.com/python-pillow/Pillow), [NumPy](https://github.com/numpy/numpy), [SciPy](https://github.com/scipy/scipy), [OpenCV](https://github.com/opencv/opencv), [scikit-image](https://github.com/scikit-image/scikit-image) |
| Font/text/report tools | [FontTools](https://github.com/fonttools/fonttools), [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz), [ReportLab](https://www.reportlab.com/), [openpyxl](https://openpyxl.readthedocs.io/) |
| S3 client | [boto3](https://github.com/boto/boto3) |

Choose the appropriate PyMuPDF license for your distribution/deployment. Surya code and model weights have separate licensing terms; check the current model terms before commercial deployment. This notice identifies dependencies and does not grant rights to third-party components or certify legal compliance.
