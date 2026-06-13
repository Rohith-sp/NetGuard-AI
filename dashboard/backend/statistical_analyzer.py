import math
from collections import deque

class StatisticalProfiler:
    """
    Unsupervised Dynamic Statistical Profiler for NetGuard AI.
    Handles Data Poisoning (Z-Score) and Slow Rate (Long-Term Packet Tracking)
    using pure mathematics instead of string labels.
    """
    def __init__(self):
        # ── Payload Tracker (Data Poisoning) ──
        self.device_ema = {} # device -> temp_ema
        self.device_var = {} # device -> temp_var
        self.alpha = 0.2  # Smoothing factor
        
        # ── Time-Series Tracker (Slow Rate) ──
        self.device_timestamps = {} # device -> deque(maxlen=5)

    def track_payload(self, device: str, temp: float) -> bool:
        """
        Calculates the Z-Score of an incoming temperature reading against a live
        Exponential Moving Average (EMA) per device. Returns True if it's a massive outlier (Z > 3.0).
        """
        if temp is None or not device:
            return False

        if device not in self.device_ema:
            self.device_ema[device] = temp
            self.device_var[device] = 1.0
            return False

        ema = self.device_ema[device]
        var = self.device_var[device]

        # Calculate Z-Score
        std_dev = math.sqrt(var)
        if std_dev < 0.1:
            std_dev = 0.1

        z_score = abs(temp - ema) / std_dev

        # Update EMA & Variance only if NOT an outlier (prevents poisoning the baseline)
        if z_score < 3.0:
            diff = temp - ema
            self.device_ema[device] += self.alpha * diff
            self.device_var[device] = (1 - self.alpha) * (var + self.alpha * diff ** 2)

        return z_score > 3.0

    def track_packet(self, device: str, ts: float):
        """Record the arrival time of a packet for a specific device."""
        if not device:
            return
        if device not in self.device_timestamps:
            self.device_timestamps[device] = deque(maxlen=5)
        self.device_timestamps[device].append(ts)

    def detect_slow_rate(self) -> str | None:
        """
        Returns the device name if any device's median Inter-Arrival Time (IAT)
        of the last 5 packets exceeds 10,000ms (10 seconds), mathematically proving a Slow Rate attack.
        """
        for device, ts_deque in self.device_timestamps.items():
            if len(ts_deque) < 5:
                continue
            ts_list = sorted(list(ts_deque))
            iats = [(ts_list[i+1] - ts_list[i]) * 1000 for i in range(len(ts_list)-1)]
            iats.sort()
            median_iat = iats[len(iats)//2]
            if median_iat > 10000.0:
                return device
        return None
