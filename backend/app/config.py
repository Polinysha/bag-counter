"""
Central configuration. All values can be overridden via environment
variables (see .env.example in the repo root / docker-compose.yml).
"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- storage -----------------------------------------------------
    data_dir: Path = Path("/data")
    uploads_subdir: str = "uploads"
    processed_subdir: str = "processed"
    db_subdir: str = "db"

    # --- queue / broker ------------------------------------------------
    redis_url: str = "redis://redis:6379/0"
    queue_name: str = "video_processing"
    job_timeout_seconds: int = 60 * 60  # 1 hour hard timeout per video

    # --- detection model ------------------------------------------------
    # Any MMDetection model zoo config/checkpoint pair works here.
    # RTMDet-tiny is small & fast enough for CPU-only demo boxes.
    # baked into the docker image at build time via `mim download`
    # (see backend/Dockerfile) - no network access needed at runtime.
    mmdet_config: str = "/opt/mmdetection/configs/rtmdet/rtmdet_tiny_8xb32-300e_coco.py"
    mmdet_checkpoint: str = (
        "/opt/mmdetection/configs/rtmdet/"
        "rtmdet_tiny_8xb32-300e_coco_20220902_112414-78e30dcc.pth"
    )
    mmdet_device: str = "cpu"  # "cuda:0" if a GPU is available
    detection_score_thr: float = 0.35
    # class-agnostic: an object is treated as a "bag candidate" if its
    # detected box center falls inside the conveyor ROI, regardless of
    # the COCO label the detector assigned it (see README for why).
    min_box_area_ratio: float = 0.002  # relative to frame area
    max_box_area_ratio: float = 0.35

    # --- ROI / counting line --------------------------------------------
    # Normalized (0..1) coordinates so the same config works for any
    # input resolution. Defaults are tuned for the supplied input.mp4
    # (belt runs diagonally from the far/top opening towards the
    # camera / bottom-left where bags drop onto the pile).
    roi_polygon: list = [
        [0.359, 0.028],
        [0.672, 0.042],
        [0.531, 0.833],
        [0.0, 1.0],
        [0.0, 0.833],
        [0.234, 0.556],
    ]
    counting_line: list = [[0.169, 0.506], [0.469, 0.356]]  # [ [x1,y1], [x2,y2] ]
    # direction, in pixels, that counts as "a bag left the belt":
    # positive = moving towards the near/bottom-left side of the line
    count_direction: str = "forward"

    # --- tracking --------------------------------------------------------
    tracker_iou_threshold: float = 0.25
    tracker_max_age: int = 15  # frames a track may go unmatched
    tracker_min_hits: int = 2  # frames before a track is confirmed

    # --- anomaly monitoring ----------------------------------------------
    anomaly_stall_seconds: float = 8.0
    anomaly_size_deviation: float = 0.6  # relative to running median
    anomaly_double_count_seconds: float = 0.6
    anomaly_low_confidence_window: int = 30
    anomaly_low_confidence_thr: float = 0.30

    # --- output video ------------------------------------------------------
    output_fourcc: str = "mp4v"
    draw_roi: bool = True
    draw_trails: bool = True

    # --- upload limits -----------------------------------------------------
    # Rejects the upload before it's fully written to disk (see
    # StorageService.save_upload) - protects against someone filling the
    # `data` volume with one huge/malicious upload. 2 GiB comfortably
    # covers a multi-minute 1080p conveyor clip; raise via BC_MAX_UPLOAD_MB
    # if your footage is longer/higher-res.
    max_upload_mb: int = 2048

    class Config:
        env_prefix = "BC_"

    @property
    def uploads_dir(self) -> Path:
        p = self.data_dir / self.uploads_subdir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def processed_dir(self) -> Path:
        p = self.data_dir / self.processed_subdir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_dir(self) -> Path:
        p = self.data_dir / self.db_subdir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.db_dir}/app.db"


settings = Settings()
