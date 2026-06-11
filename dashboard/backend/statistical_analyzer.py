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
        self.temp_ema = None
        self.temp_var = 1.0
        self.alpha = 0.2  # Smoothing factor
        
        # ── Time-Series Tracker (Slow Rate) ──
        self.global_packet_timestamps = deque(maxlen=5)

    def track_payload(self, temp: float) -> bool:
        """
        Calculates the Z-Score of an incoming temperature reading against a live
        Exponential Moving Average (EMA). Returns True if it's a massive outlier (Z > 3.0).
        """
        if temp is None:
            return False

        if self.temp_ema is None:
            self.temp_ema = temp
            return False

        # Calculate Z-Score
        std_dev = math.sqrt(self.temp_var)
        if std_dev < 0.1:
            std_dev = 0.1

        z_score = abs(temp - self.temp_ema) / std_dev

        # Update EMA & Variance only if NOT an outlier (prevents poisoning the baseline)
        if z_score < 3.0:
            diff = temp - self.temp_ema
            self.temp_ema += self.alpha * diff
            self.temp_var = (1 - self.alpha) * (self.temp_var + self.alpha * diff ** 2)

        return z_score > 3.0

    def track_packet(self, ts: float):
        """Record the arrival time of any packet globally."""
        self.global_packet_timestamps.append(ts)

    def detect_slow_rate(self) -> bool:
        """
        Returns True if the median Inter-Arrival Time (IAT) of the last 5 packets
        exceeds 10,000ms (10 seconds), mathematically proving a Slow Rate attack.
        """
        if len(self.global_packet_timestamps) < 5:
            return False
            
        ts_list = sorted(list(self.global_packet_timestamps))
        iats = [(ts_list[i+1] - ts_list[i]) * 1000 for i in range(len(ts_list)-1)]
        
        iats.sort()
        median_iat = iats[len(iats)//2]
        
        return median_iat > 10000.0
