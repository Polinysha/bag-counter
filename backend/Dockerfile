# Single image, used as both the "api" and "worker" services in
# docker-compose.yml (see the `command:` override there). Keeping one
# image avoids re-downloading the (fairly large) torch/mmdet stack
# twice and guarantees the API and the worker always run the exact
# same detector code/version.

FROM python:3.10-slim AS base

# --- system deps -----------------------------------------------------
# libgl1/libglib2.0-0: required by opencv for video decode/encode.
# ffmpeg: fallback muxer/codec support for less common input formats.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- core + CV python deps --------------------------------------------
# Split so the lite image (SKIP_ML_STACK=true, see below) still gets a
# fully working tracker/roi/counter/anomaly stack and MockDetector -
# only the MMDetection/torch stack is conditional.
COPY requirements/base.txt requirements/cv.txt ./requirements/
RUN pip install --no-cache-dir \
        -r requirements/base.txt \
        -r requirements/cv.txt

# --- heavy ML stack (BagDetector / MMDetection) -----------------------
# ARG SKIP_ML_STACK=true builds a "lite" image: no torch/mmcv/mmdet, no
# weight download. app/worker/pipeline/detector.py::build_detector()
# already falls back to MockDetector automatically when MMDetection
# can't be imported, so the rest of the pipeline (tracker/roi/counter/
# anomaly/video_processor - everything unit-tested in backend/tests)
# runs unchanged. Used for CI (lint/type-check/unit tests) and for
# local dev on non-CV code, where the full ML stack is unnecessary
# build weight. The production/demo image is always built with the
# default (SKIP_ML_STACK=false) so BagDetector is available.
# See requirements/ml.txt for the pinned version list this mirrors.
ARG SKIP_ML_STACK=false

# CPU-only torch by default (works everywhere, no GPU required to run
# the demo). For GPU inference, replace this with the CUDA wheel that
# matches your host driver and set BC_MMDET_DEVICE=cuda:0.
RUN if [ "$SKIP_ML_STACK" = "false" ]; then \
        pip install --no-cache-dir torch==2.1.2 torchvision==0.16.2 \
            --index-url https://download.pytorch.org/whl/cpu && \
        pip install --no-cache-dir -U openmim==0.3.9 && \
        mim install mmengine==0.10.4 && \
        mim install "mmcv==2.1.0" && \
        pip install --no-cache-dir mmdet==3.3.0 && \
        mkdir -p /opt/mmdetection/configs/rtmdet && \
        mim download mmdet \
            --config rtmdet_tiny_8xb32-300e_coco \
            --dest /opt/mmdetection/configs/rtmdet ; \
    else \
        echo "SKIP_ML_STACK=true: building a lite image, BagDetector unavailable, MockDetector will be used" ; \
    fi

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    BC_SKIP_ML_STACK=${SKIP_ML_STACK}

# Overridden per-service by docker-compose.yml `command:`
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
