# Units — read carefully

- `camera.csv:t_cam_s` = **seconds** (float, camera clock)
- `imu.csv:t_imu_ms` = **milliseconds** (int, IMU clock = reference)
- Camera ~30 Hz, IMU 100 Hz. Both clocks share an epoch but the camera clock has a per-segment offset and drift.
- `motion_score` (camera) and `az` (IMU) both spike on the same physical bumps → use them to estimate offset.
- Dropouts exist in both streams. A frame without a valid IMU partner must be put on HOLD (empty `imu_t_ms`).
- `shock/` = teacher shock test: camera clock resets mid-stream.
