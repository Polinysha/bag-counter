# Single image, used as both the "api" and "worker" services in
# docker-compose.yml (see the `command:` override there). Keeping one
# image avoids re-downloading the (fairly large) torch/mmdet stack
# twice and guarantees the API and the worker always run the exact
# same detector code/version.

FROM python:3.10-slim

# --- system deps -----------------------------------------------------
# libgl1/libglib2.0-0: required by opencv for video decode/encode.
# ffmpeg: fallback muxer/codec support for less common input formats.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- python deps -------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# CPU-only torch by default (works everywhere, no GPU required to run
# the demo). For GPU inference, replace this with the CUDA wheel that
# matches your host driver and set BC_MMDET_DEVICE=cuda:0.
RUN pip install --no-cache-dir torch==2.1.2 torchvision==0.16.2 \
        --index-url https://download.pytorch.org/whl/cpu

# mmcv ships prebuilt wheels per torch/cuda(or cpu) combination - mim
# resolves the right one automatically for the torch version above.
RUN pip install --no-cache-dir -U openmim \
    && mim install mmengine==0.10.4 \
    && mim install "mmcv==2.1.0" \
    && pip install --no-cache-dir mmdet==3.3.0

# Fetch the RTMDet-tiny COCO-pretrained config + checkpoint used as the
# default detector (see app/config.py). `mim download` pulls both the
# python config file and the .pth weights in one step, so no separate
# mmdetection source checkout is needed just to get configs/.
RUN mkdir -p /opt/mmdetection/configs/rtmdet && \
    mim download mmdet \
        --config rtmdet_tiny_8xb32-300e_coco \
        --dest /opt/mmdetection/configs/rtmdet

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Overridden per-service by docker-compose.yml `command:`
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
